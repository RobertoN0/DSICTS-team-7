#!/usr/bin/env python3
"""Async range-based loader for video-like GET (Range requests).

This tool simulates many "player" clients that request byte ranges from a
single video URL. It writes a per-second CSV compatible with `plot.py`.

Usage example:
  python3 tools/range_loader.py --url http://localhost:8080/videos/video.mp4 \
      --concurrency 32 --chunkSize 1048576 --seekProb 0.05 --runSec 60
"""
import argparse
import asyncio
import csv
import random
import time
from urllib.parse import urljoin

import httpx


async def worker(client: httpx.AsyncClient, url: str, chunk_size: int, seek_prob: float, timeout: float, stop_evt: asyncio.Event, out_q: asyncio.Queue):
    # Discover file size via HEAD (fallback to GET 0-0)
    total = None
    try:
        r = await client.head(url, timeout=timeout)
        if r.status_code == 200:
            total = int(r.headers.get('Content-Length') or 0)
    except Exception:
        total = None

    if not total:
        try:
            r = await client.get(url, headers={'Range': 'bytes=0-0'}, timeout=timeout)
            # Content-Range: bytes start-end/total
            cr = r.headers.get('Content-Range') or ''
            if '/' in cr:
                total = int(cr.split('/')[-1])
        except Exception:
            total = None

    if not total or total <= 0:
        # give up; workers will attempt simple GETs without ranges
        # fallback: do repeated full GETs (low realism but still load)
        while not stop_evt.is_set():
            t0 = time.perf_counter()
            code = -1
            try:
                r = await client.get(url, timeout=timeout)
                await r.aread()
                code = r.status_code
            except Exception:
                code = -1
            dt_ms = (time.perf_counter() - t0) * 1000.0
            await out_q.put((int(time.time()), dt_ms, code))
        return

    # Start streaming simulation
    max_offset = total - 1
    # choose a random starting offset per worker
    offset = random.randrange(0, max(1, total - 1))

    while not stop_evt.is_set():
        # decide whether to seek
        if random.random() < seek_prob:
            # jump to random aligned offset
            offset = random.randrange(0, max(1, total - 1))

        start = offset
        end = min(offset + chunk_size - 1, max_offset)

        hdrs = {'Range': f'bytes={start}-{end}'}
        t0 = time.perf_counter()
        code = -1
        try:
            r = await client.get(url, headers=hdrs, timeout=timeout)
            await r.aread()
            code = r.status_code
        except Exception:
            code = -1
        dt_ms = (time.perf_counter() - t0) * 1000.0
        await out_q.put((int(time.time()), dt_ms, code))

        # advance offset if the chunk was sequential
        if end < max_offset and random.random() >= seek_prob:
            offset = end + 1
        else:
            # otherwise pick a new offset next loop
            offset = random.randrange(0, max(1, total - 1))


async def main():
    ap = argparse.ArgumentParser(description='Range-based loader')
    ap.add_argument('--url', required=True, help='Full URL to the video (e.g. http://host:8080/videos/foo.mp4)')
    ap.add_argument('--concurrency', type=int, default=8)
    ap.add_argument('--chunkSize', type=int, default=1024*1024, help='Chunk size in bytes')
    ap.add_argument('--seekProb', type=float, default=0.01, help='Probability per chunk to seek to a random offset')
    ap.add_argument('--warmupSec', type=int, default=5)
    ap.add_argument('--runSec', type=int, default=60)
    ap.add_argument('--out', default='load_timeseries.csv')
    ap.add_argument('--timeout', type=float, default=30.0)
    args = ap.parse_args()

    out_q = asyncio.Queue()
    stop_evt = asyncio.Event()

    async with httpx.AsyncClient(http2=False) as client:
        tasks = [asyncio.create_task(worker(client, args.url, args.chunkSize, args.seekProb, args.timeout, stop_evt, out_q))
                 for _ in range(args.concurrency)]

        # warmup
        await asyncio.sleep(args.warmupSec)

        with open(args.out, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["ts","rps","avg_ms","p50_ms","p95_ms","ok","err"])

            current_sec = int(time.time())
            lats = []
            ok = err = 0

            t_end = time.time() + args.runSec
            while time.time() < t_end:
                try:
                    ts, dt_ms, code = await asyncio.wait_for(out_q.get(), timeout=0.2)
                    if ts == current_sec:
                        lats.append(dt_ms)
                        if 200 <= code < 300: ok += 1
                        else: err += 1
                    elif ts > current_sec:
                        while current_sec < ts:
                            if lats:
                                lats.sort()
                                n = len(lats)
                                p50 = lats[min(n-1, int(round(0.50*(n-1))))]
                                p95 = lats[min(n-1, int(round(0.95*(n-1))))]
                                avg = sum(lats)/n
                                w.writerow([current_sec, n, f"{avg:.3f}", f"{p50:.3f}", f"{p95:.3f}", ok, err])
                            else:
                                w.writerow([current_sec, 0, "", "", "", 0, 0])
                            f.flush()
                            current_sec += 1
                            lats, ok, err = [], 0, 0
                        lats.append(dt_ms)
                        if 200 <= code < 300: ok += 1
                        else: err += 1
                    out_q.task_done()
                except asyncio.TimeoutError:
                    now_sec = int(time.time())
                    if now_sec > current_sec:
                        w.writerow([current_sec, 0, "", "", "", 0, 0])
                        f.flush()
                        current_sec = now_sec

        stop_evt.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await out_q.join()


if __name__ == '__main__':
    asyncio.run(main())
