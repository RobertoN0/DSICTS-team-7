#!/usr/bin/env bash
set -euo pipefail

# run_experiment.sh
# This script performs a full experiment sequence:
# 1️⃣ Runs one_run_ffmpeg.py with Timer.mp4
# 2️⃣ Waits 5 minutes for cooldown
# 3️⃣ Runs run_profiles.sh for H.264 CPU

VIDEO_INPUT="videos/Timer.mp4"
OUTDIR="runs-final"
COOLDOWN_MINUTES=2

#python3 tools/one_run_ffmpeg.py \
#    --monitor-sudo \
#    --mode adaptive \
#    --input "$VIDEO_INPUT" \
#    --codec h264 \
#    --input-resolution 1080p \
#    --use-gpu true \
#    --warmupSec 90 \
#    --numberOfRepetitions 2 \
#    --timeout 90 \
#    --outdir "$OUTDIR"
#
#echo "============================================================"
#echo "🕒 Cooldown for ${COOLDOWN_MINUTES} minutes..."
#echo "============================================================"
#sleep $((COOLDOWN_MINUTES * 60))
#
#python3 tools/one_run_ffmpeg.py \
#    --monitor-sudo \
#    --mode adaptive \
#    --input "$VIDEO_INPUT" \
#    --codec h264 \
#    --input-resolution 1080p \
#    --use-gpu true \
#    --warmupSec 90 \
#    --numberOfRepetitions 2 \
#    --timeout 90 \ 
#    --outdir "$OUTDIR"
#
#echo "============================================================"
#echo "▶️ Starting H.264 CPU experiment using run_profiles.sh"
#echo "============================================================"
#
COMMON_ARGS="--monitor-sudo --runSec 180 --timeout 90 --numberOfRepetitions 30 --warmupSec 90"

./run_profiles.sh -- $COMMON_ARGS --codec h264 --resolution 1080 --use-gpu true
RUN_PROFILES_FILTER=baseline ./run_profiles.sh -- $COMMON_ARGS --codec hevc --resolution 1080 --use-gpu true
RUN_PROFILES_FILTER=baseline ./run_profiles.sh -- $COMMON_ARGS --codec av1  --resolution 1080 --use-gpu true

echo "============================================================"
echo "✅ All experiments completed successfully!"
echo "============================================================"
