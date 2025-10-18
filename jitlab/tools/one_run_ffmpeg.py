#!/usr/bin/env python3
"""
Run FFmpeg transcoding experiments (single or adaptive) with monitoring and cleanup.
Implements the logic from Java's FfmpegCommandBuilder (buildSingle/buildAdaptive),
but deletes all output video files after each FFmpeg run.

Example:
  python3 tools/one_run_ffmpeg.py \
    --monitor-sudo \
    --mode adaptive \
    --input videos/input.mp4 \
    --codec h264 \
    --input-resolution 1080p \
    --use-gpu true \
    --warmupSec 10 \
    --numberOfRepetitions 3 \
    --timeout 30 \
    --outdir runs
"""

import argparse
import os
import shlex
import subprocess
import sys
import time
import signal
import tempfile
import shutil
from datetime import datetime
from typing import List


###########################################
# FFmpeg Command Builders (from Java logic)
###########################################
def build_single(input_path: str, output_path: str, codec: str, resolution: str, gpu: bool) -> List[str]:
    """Equivalent of Java's buildSingle()"""
    cmd = ["ffmpeg", "-y", "-hide_banner"]

    if gpu:
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]

    cmd += ["-i", input_path]

    codec_l = codec.lower()
    if codec_l == "h264":
        encoder = "h264_nvenc" if gpu else "libx264"
    elif codec_l in ("hevc", "h265"):
        encoder = "hevc_nvenc" if gpu else "libx265"
    elif codec_l == "av1":
        encoder = "av1_nvenc" if gpu else "libaom-av1"
    elif codec_l == "vp9":
        encoder = "libvpx-vp9"
    else:
        raise ValueError(f"Unsupported codec: {codec}")

    scale_filter = f"{'scale_cuda=-2:' if gpu else 'scale=-2:'}{resolution.replace('p', '')}"
    cmd += ["-vf", scale_filter]

    cmd += ["-c:v", encoder, "-preset", "p5" if gpu else "veryfast"]

    bitrate = {
        "1080": "6M",
        "720": "3M",
        "480": "2M",
        "360": "1M",
    }.get(resolution.replace("p", ""), "0.6M")

    cmd += ["-b:v", bitrate, "-c:a", "aac", "-b:a", "128k", output_path]
    return cmd


def build_adaptive(input_path: str, base_output: str, codec: str, gpu: bool, input_resolution: str) -> List[str]:
    """Equivalent of Java's buildAdaptive()"""
    cmd = ["ffmpeg", "-y", "-hide_banner"]

    if gpu:
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]

    cmd += ["-i", input_path]

    codec_l = codec.lower()
    if codec_l == "h264":
        encoder = "h264_nvenc" if gpu else "libx264"
    elif codec_l in ("hevc", "h265"):
        encoder = "hevc_nvenc" if gpu else "libx265"
    elif codec_l == "av1":
        encoder = "av1_nvenc" if gpu else "libaom-av1"
    elif codec_l == "vp9":
        encoder = "libvpx-vp9"
    else:
        raise ValueError(f"Unsupported codec: {codec}")

    available = ["1080", "720", "480", "360"]
    base_res = input_resolution.replace("p", "")
    start_idx = available.index(base_res) if base_res in available else 0
    to_generate = available[start_idx:]

    # filter_complex
    filter_complex = f"[0:v]split={len(to_generate)}" + "".join(f"[v{i+1}]" for i in range(len(to_generate))) + ";"
    for i, res in enumerate(to_generate):
        scale_expr = f"{'scale_cuda=-2:' if gpu else 'scale=-2:'}{res}"
        filter_complex += f"[v{i+1}]{scale_expr}[v{i+1}o];"

    cmd += ["-filter_complex", filter_complex]

    for i, res in enumerate(to_generate):
        out_file = os.path.join(base_output, f"output_{res}p.mp4")
        bitrate = {
            "1080": "6M",
            "720": "3M",
            "480": "2M",
            "360": "1M",
        }.get(res, "0.6M")
        cmd += [
            "-map", f"[v{i+1}o]",
            "-c:v", encoder,
            "-preset", "p5" if gpu else "veryfast",
            "-b:v", bitrate,
            "-c:a", "aac",
            "-b:a", "128k",
            out_file,
        ]

    return cmd


###########################################
# Process Helpers
###########################################
def start_ffmpeg(mode: str, input_path: str, tmp_dir: str, codec: str, gpu: bool, resolution: str) -> subprocess.Popen:
    """Start FFmpeg in single or adaptive mode using temporary output directory."""
    cmd = (
        build_adaptive(input_path, tmp_dir, codec, gpu, resolution)
        if mode == "adaptive"
        else build_single(input_path, os.path.join(tmp_dir, "output.mp4"), codec, resolution, gpu)
    )
    print("[one_run] START ffmpeg:", " ".join(cmd))
    preexec_fn = os.setsid if hasattr(os, "setsid") else None
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=preexec_fn)


def kill_process(proc: subprocess.Popen, name="process"):
    if not proc:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
        print(f"[one_run] {name} PID {proc.pid} terminated.")
    except subprocess.TimeoutExpired:
        print(f"[one_run] {name} did not exit in time — forcing kill.")
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


###########################################
# Main Runner
###########################################
def run():
    ap = argparse.ArgumentParser(description="Run FFmpeg transcoding experiments (single/adaptive) with auto-cleanup")
    ap.add_argument("--mode", choices=["single", "adaptive"], default="adaptive", help="Transcoding mode")
    ap.add_argument("--input", required=True, help="Input video file")
    ap.add_argument("--codec", default="h264", help="Codec (h264, hevc, av1, vp9)")
    ap.add_argument("--input-resolution", default="1080p", help="Input resolution (e.g. 1080p)")
    ap.add_argument("--use-gpu", default="false", help="Use GPU acceleration (true/false)")
    ap.add_argument("--outdir", default="runs", help="Output directory for metrics")
    ap.add_argument("--monitor-sudo", action="store_true", help="Run monitor under sudo")

    ap.add_argument("--timeout", type=int, default=60, help="Seconds to wait between runs (default: 60)")
    ap.add_argument("--warmupSec", type=int, default=0, help="Warmup duration in seconds (default: 0)")
    ap.add_argument("--numberOfRepetitions", type=int, default=30, help="Number of repetitions (default: 30)")
    args = ap.parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        print(f"[one_run] ❌ Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    gpu = str(args.use_gpu).lower() == "true"
    os.makedirs(args.outdir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    codec = args.codec
    hardware = "gpu" if gpu else "cpu"
    root_dir = os.path.join(args.outdir, f"{codec}-{hardware}")
    os.makedirs(root_dir, exist_ok=True)
    profile_dir = os.path.join(root_dir, f"{args.mode}_{ts}")
    os.makedirs(profile_dir, exist_ok=True)

    python_bin = sys.executable or "python3"

    ############################################
    # Warmup
    ############################################
    if args.warmupSec > 0:
        print(f"[one_run] Starting warmup for {args.warmupSec}s…")
        tmp_dir = tempfile.mkdtemp(prefix="ffmpeg_warmup_")
        ffmpeg_proc = start_ffmpeg(args.mode, input_path, tmp_dir, codec, gpu, args.input_resolution)
        time.sleep(args.warmupSec)
        kill_process(ffmpeg_proc, "ffmpeg (warmup)")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("[one_run] Warmup complete.\n")

    ############################################
    # Experiment Loop
    ############################################
    for i in range(args.numberOfRepetitions):
        iter_dir = os.path.join(profile_dir, f"iter_{i+1}")
        os.makedirs(iter_dir, exist_ok=True)

        print(f"[one_run] Starting iteration {i+1}/{args.numberOfRepetitions}…")
        if i > 0 and args.timeout > 0:
            print(f"[one_run] Cooling down for {args.timeout}s before next run…")
            time.sleep(args.timeout)

        ffmpeg_proc = None
        mon_proc = None
        tmp_dir = tempfile.mkdtemp(prefix="ffmpeg_iter_")

        try:
            ffmpeg_proc = start_ffmpeg(args.mode, input_path, tmp_dir, codec, gpu, args.input_resolution)
            pid = ffmpeg_proc.pid
            print(f"[one_run] Using FFmpeg PID: {pid}")

            # Start monitor
            mon_csv = os.path.join(iter_dir, "monitor_iter.csv")
            mon_cmd = [
                python_bin,
                "tools/monitor.py",
                "--pid", str(pid),
                "--interval", "1",
                "--duration", "99999",
                "--out", mon_csv,
            ]
            if args.monitor_sudo:
                mon_cmd = ["sudo"] + mon_cmd
            print("[one_run] START monitor:", " ".join(mon_cmd))
            mon_proc = subprocess.Popen(mon_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            gpu_p = None
            gpu_csv = None
            if args.use_gpu == "true":
                gpu_csv = os.path.join(iter_dir, "gpu_monitor_iter.csv")
                gpu_cmd = [
                    "python3", "tools/gpu_monitor.py",                
                    "--duration", str(99999),        
                    "--out", gpu_csv
                ]
                print("[one_run] START gpu_monitor:", " ".join(shlex.quote(x) for x in gpu_cmd))
                gpu_p = subprocess.Popen(gpu_cmd, stdout=sys.stdout, stderr=sys.stderr)

            # Wait for FFmpeg to finish
            ffmpeg_proc.wait()
            print("[one_run] FFmpeg finished.")

            # Stop monitor
            while ffmpeg_proc.poll() is None:
                time.sleep(0.2)
            if ffmpeg_proc.poll() is None:
                mon_proc.terminate()
                try:
                    mon_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    mon_proc.kill()
            if gpu_p:
                while ffmpeg_proc.poll() is None:
                    time.sleep(0.2)
                if ffmpeg_proc.poll() is None:
                    gpu_p.terminate()
                    try:
                        gpu_p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        gpu_p.kill()

        finally:
            kill_process(ffmpeg_proc, "ffmpeg")
            kill_process(mon_proc, "monitor")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            print(f"[one_run] Cleaned up temporary files: {tmp_dir}")

    print("\n✅ Done.")
    print(f"Metrics saved under: {profile_dir}")


if __name__ == "__main__":
    run()
