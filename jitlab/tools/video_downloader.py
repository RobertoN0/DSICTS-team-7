#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Downloads a YouTube video at the specified resolution in MP4 format **with audio**.
Strategy:
  1) Prefers MP4 "adaptive" (video-only) streams at the requested resolution(s)
     + best audio (m4a), then merges with ffmpeg into a single .mp4.
  2) If no adaptive MP4 is found, uses MP4 "progressive" (audio+video together) at the
     best available resolution ≤ requested.
  3) Avoids returning WebM as final file (keeps MP4).
Requirements: ffmpeg in PATH, pytubefix installed.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from pytubefix import YouTube


# ----------------------------- Utils ---------------------------------

def sanitize_filename(name: str) -> str:
    # Rimuove caratteri non validi per filesystem
    name = re.sub(r'[\\/*?:"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def res_to_int(res: Optional[str]) -> int:
    # "1080p" -> 1080, "0p"/None -> 0
    if not res or not res.endswith("p"):
        return 0
    try:
        return int(res[:-1])
    except ValueError:
        return 0


def ffmpeg_path() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise EnvironmentError("ffmpeg not found in PATH")
    return ff


# --------------------------- Listing (debug) ---------------------------

def list_streams(yt: YouTube) -> None:
    print(f"\nAvailable streams for: {yt.title}\n")
    for s in yt.streams.order_by('resolution').desc():
        info = {
            'itag': getattr(s, 'itag', None),
            'type': getattr(s, 'type', None),
            'mime_type': getattr(s, 'mime_type', None),
            'resolution': getattr(s, 'resolution', None),
            'fps': getattr(s, 'fps', None),
            'abr': getattr(s, 'abr', None),
            'is_progressive': getattr(s, 'is_progressive', False),
            'filesize_approx': getattr(s, 'filesize_approx', None)
        }
        print(info)
    print()


# ------------------------ Selection of streams ----------------------

def find_best_adaptive_mp4_video(yt: YouTube, desired_resolutions: List[str]):
    """
    Gives the best MP4 adaptive stream (video-only) at the first
    available resolution in the desired list (in order of preference).
    If none match, returns the best MP4 adaptive <= max requested.
    """
    video_mp4 = [
        s for s in yt.streams.filter(adaptive=True, file_extension='mp4')
        if getattr(s, 'resolution', None)
    ]
    if not video_mp4:
        return None

    # Sort all adaptive mp4 by ascending resolution
    video_mp4_sorted = sorted(video_mp4, key=lambda s: res_to_int(s.resolution))

    # 1) exact match in order of preference (first item in list has max priority)
    desired_order = [r if r.endswith("p") else f"{r}p" for r in desired_resolutions]
    for r in desired_order:
        for s in video_mp4_sorted:
            if s.resolution == r:
                return s

    # 2) fallback: best <= max desired
    max_target = max((res_to_int(r) for r in desired_order), default=0)
    candidates = [s for s in video_mp4_sorted if res_to_int(s.resolution) <= max_target]
    return candidates[-1] if candidates else None


def find_best_progressive_mp4(yt: YouTube, desired_resolutions: List[str]):
    """
    Progressive MP4 (audio+video together). Uses *only* as fallback
    if no adaptive mp4 exists: takes the best ≤ requested resolution.
    """
    progs = [
        s for s in yt.streams.filter(progressive=True, file_extension='mp4')
        if getattr(s, 'resolution', None)
    ]
    if not progs:
        return None

    progs_sorted = sorted(progs, key=lambda s: res_to_int(s.resolution))
    desired_order = [r if r.endswith("p") else f"{r}p" for r in desired_resolutions]

    # exact match
    for r in desired_order:
        for s in progs_sorted:
            if s.resolution == r:
                return s

    # best ≤ max target
    max_target = max((res_to_int(r) for r in desired_order), default=0)
    candidates = [s for s in progs_sorted if res_to_int(s.resolution) <= max_target]
    return candidates[-1] if candidates else progs_sorted[-1]


def find_best_audio_m4a(yt: YouTube):
    """Prefers audio-only in mp4/m4a (AAC) container."""
    audios = [s for s in yt.streams.filter(only_audio=True)]
    if not audios:
        return None
    # prefer audio/mp4 (m4a)
    m4a = [s for s in audios if 'audio/mp4' in (getattr(s, 'mime_type', '') or '').lower()]
    pool = m4a if m4a else audios
    # highest bitrate
    def abr_kbps(s):
        abr = getattr(s, 'abr', '') or ''
        m = re.search(r'(\d+)\s*kbps', abr)
        return int(m.group(1)) if m else 0
    return sorted(pool, key=abr_kbps)[-1]


# ------------------------------ Merge ---------------------------------

def merge_with_ffmpeg(video_path: Path, audio_path: Path, out_path: Path) -> None:
    """
    Merges video (mp4 video-only) + audio (m4a) into a single MP4.
    -c:v copy keeps the video intact; audio is re-encoded to AAC for compatibility.
    """
    ff = ffmpeg_path()
    cmd = [
        ff, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


# ------------------------------ Download ------------------------------

def download(url: str, output_dir: str = "./videos",
             desired_resolutions: Optional[List[str]] = None) -> str:
    """
    Downloads MP4 with audio at the best available resolution among the desired ones.
    Returns the path of the final MP4 file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    desired_resolutions = desired_resolutions or ["1080p", "720p", "480p", "360p"]

    yt = YouTube(url)
    title = sanitize_filename(yt.title)
    print(f"Title: {title}")

    # 1) Prefers ADAPTIVE MP4 (video-only) + audio → merge in MP4
    v = find_best_adaptive_mp4_video(yt, desired_resolutions)
    if v:
        print(f"Downloading adaptive MP4 video-only: itag={v.itag} res={v.resolution}")
        v_file = Path(v.download(output_path=output_dir))

        a = find_best_audio_m4a(yt)
        if not a:
            raise RuntimeError("No audio-only found (m4a/AAC) for merging.")
        print(f"Downloading audio-only: itag={a.itag} abr={a.abr}")
        a_file = Path(a.download(output_path=output_dir))

        merged = Path(output_dir) / f"{title}_{v.resolution}_merged.mp4"
        try:
            merge_with_ffmpeg(v_file, a_file, merged)
            print(f"Merged to {merged}")
            return str(merged)
        finally:
            # optional: keep sources or clean up
            pass

    # 2) Fallback: MP4 (audio+video together)
    print("No suitable adaptive MP4 found: trying progressive MP4…")
    prog = find_best_progressive_mp4(yt, desired_resolutions)
    if prog:
        print(f"Downloading progressive MP4: itag={prog.itag} res={prog.resolution}")
        out_file = Path(prog.download(output_path=output_dir))
        print(f"Downloaded to {out_file}")
        return str(out_file)

    # 3) No MP4 available
    raise RuntimeError("No suitable MP4 stream found (neither adaptive nor progressive).")


# -------------------------------- CLI ---------------------------------

def build_desired_list(res_arg: str) -> List[str]:
    if res_arg.lower() == "highest":
        return ["2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]
    parts = [p.strip() for p in res_arg.split(",") if p.strip()]
    out = []
    for p in parts:
        out.append(p if p.endswith("p") else f"{p}p")
    # ensure order from most desired to least desired
    return out


def main():
    ap = argparse.ArgumentParser(description="Download YouTube video in MP4 with audio.")
    ap.add_argument("url", help="YouTube URL")
    ap.add_argument("--out", "-o", default="./videos", help="Output directory (default: ./videos)")
    ap.add_argument("--res", "--resolution", dest="resolution", default="1080p",
                    help="Desired resolution (e.g. 1080p) or comma-separated list (e.g. '1080p,720p') "
                         "or 'highest' for maximum available.")
    ap.add_argument("--list", action="store_true", help="Show available streams and exit (debug).")
    args = ap.parse_args()

    yt = YouTube(args.url)

    if args.list:
        list_streams(yt)
        return

    desired = build_desired_list(args.resolution)
    try:
        final_file = download(args.url, output_dir=args.out, desired_resolutions=desired)
        print("Result file:", final_file)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
