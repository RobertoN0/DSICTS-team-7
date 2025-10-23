#!/usr/bin/env python3
import argparse, asyncio, time, json, csv
import httpx

async def worker(client, url, body, timeout, stop_evt, out_q, wid):
    print(f"[worker-{wid}] started")
    while not stop_evt.is_set():
        t0 = time.perf_counter()
        code = -1
        try:
            r = await client.post(url, json=body, timeout=timeout)
            await r.aread()  # include transfer time
            code = r.status_code
        except Exception as e:
            print(f"[worker-{wid}] exception: {type(e).__name__}")
            code = -1
        dt_ms = (time.perf_counter() - t0) * 1000.0
        await out_q.put((int(time.time()), dt_ms, code))
    print(f"[worker-{wid}] stopped")

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--body", default="{}")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--warmupSec", type=int, default=10)
    ap.add_argument("--runSec", type=int, default=120)
    ap.add_argument("--out", default="load_timeseries.csv")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--no-save", action="store_true", help="Disable CSV output (useful for warmup)")
    args = ap.parse_args()

    body = json.loads(args.body)
    out_q = asyncio.Queue()
    stop_evt = asyncio.Event()

    print(f"[main] starting httpx client → url={args.url}, runSec={args.runSec}, concurrency={args.concurrency}")
    async with httpx.AsyncClient(http2=False) as client:
        # start workers
        tasks = [
            asyncio.create_task(worker(client, args.url, body, args.timeout, stop_evt, out_q, i))
            for i in range(args.concurrency)
        ]
        print(f"[main] started {len(tasks)} workers")

        # warmup (don’t record)
        print(f"[main] sleeping {args.warmupSec}s for warmup")
        await asyncio.sleep(args.warmupSec)
        print(f"[main] warmup done, entering main loop")

        # record per-second buckets
        if not args.no_save:
            f = open(args.out, "w", newline="")
            w = csv.writer(f)
            w.writerow(["ts","rps","avg_ms","p50_ms","p95_ms","ok","err"])
            print("[main] CSV logging enabled")
        else:
            f = None
            w = None
            print("[main] no-save mode active, skipping CSV creation")

        current_sec = int(time.time())
        lats = []
        ok = err = 0
        end_time = time.time() + args.runSec
        print(f"[main] loop started → will end around {time.strftime('%H:%M:%S', time.localtime(end_time))}")

        while True:
            now = time.time()
            if now >= end_time:
                print("[main] reached end_time, breaking loop")
                break
            try:
                ts, dt_ms, code = await asyncio.wait_for(out_q.get(), timeout=1.0)
                if ts == current_sec:
                    lats.append(dt_ms)
                    if 200 <= code < 300:
                        ok += 1
                    else:
                        err += 1
                elif ts > current_sec:
                    while current_sec < ts:
                        if lats:
                            lats.sort()
                            n = len(lats)
                            p50 = lats[min(n-1, int(round(0.50*(n-1))))]
                            p95 = lats[min(n-1, int(round(0.95*(n-1))))]
                            avg = sum(lats)/n
                            if w:
                                w.writerow([current_sec, n, f"{avg:.3f}", f"{p50:.3f}", f"{p95:.3f}", ok, err])
                                f.flush()
                                print(f"[main] wrote stats for ts={current_sec} n={n}")
                        else:
                            if w:
                                w.writerow([current_sec, 0, "", "", "", 0, 0])
                                f.flush()
                        current_sec += 1
                        lats, ok, err = [], 0, 0
                    lats.append(dt_ms)
                    if 200 <= code < 300:
                        ok += 1
                    else:
                        err += 1
                out_q.task_done()
            except asyncio.TimeoutError:
                print(f"[main] queue timeout at {time.strftime('%H:%M:%S')} (waiting for data)")
                if time.time() >= end_time:
                    print("[main] time expired during timeout check → break")
                    break
                continue

        print("[main] loop finished, signalling stop_evt")
        stop_evt.set()

        print("[main] awaiting worker termination…")
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[main] workers terminated")
        remaining = out_q.qsize()
        if remaining > 0:
            print(f"[main] flushing {remaining} leftover items from queue…")
            while not out_q.empty():
                try:
                    _ = out_q.get_nowait()
                    out_q.task_done()
                except asyncio.QueueEmpty:
                    break
        print(f"[main] queue size before join: {out_q.qsize()}")
        await out_q.join()
        print("[main] queue join complete")

        if f:
            f.close()
            print("[main] file closed")

    print("[main] finished OK")

if __name__ == "__main__":
    asyncio.run(main())
