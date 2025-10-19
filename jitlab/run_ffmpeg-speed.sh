#!/usr/bin/env bash
set -euo pipefail
trap 'kill $(jobs -p) 2>/dev/null || true' EXIT

# ============================================================
# 🔧 CONFIGURATION (edit these variables before running)
# ============================================================
INPUT_VIDEO="videos/Timer.mp4"   # Input video path
CODEC="h264"                     # Codec: h264 | hevc | av1
PRESET="hq"                      # Preset: p5 | hq | slow | fast
MODE="ladder"                    # Encoding mode: single | ladder
N_JOBS=10                         # Number of FFmpeg processes in parallel
POWER_SAMPLE_INTERVAL=0.5        # GPU power sampling interval (in seconds)
# ============================================================

# Create temporary directories for logs and outputs
LOG_DIR=$(mktemp -d logs_XXXXXX)
OUT_DIR=$(mktemp -d outputs_XXXXXX)
POWER_LOG="$LOG_DIR/gpu_power.log"

echo "==============================================="
echo "🎬  Starting FFmpeg batch experiment"
echo "-----------------------------------------------"
echo "Input:     $INPUT_VIDEO"
echo "Codec:     $CODEC"
echo "Preset:    $PRESET"
echo "Mode:      $MODE"
echo "Jobs:      $N_JOBS"
echo "Logs:      $LOG_DIR"
echo "Outputs:   $OUT_DIR"
echo "==============================================="

# ============================================================
# ⚡ Start GPU power monitor in background
# ============================================================
# Continuously sample GPU power draw (in watts) using nvidia-smi
# Writes timestamp,power to a CSV file until the process is killed.
echo "timestamp,power" > "$POWER_LOG"
(
  while true; do
    nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits \
    | awk '{print strftime("%s"), ",", $1}' >> "$POWER_LOG"
    sleep "$POWER_SAMPLE_INTERVAL"
  done
) &
GPU_MON_PID=$!

# ============================================================
# 🎥 Function that builds the FFmpeg command for each job
# ============================================================
function ffmpeg_cmd() {
  local input="$1"
  local outdir="$2"

  if [[ "$MODE" == "ladder" ]]; then
    # Multi-output ladder mode: produces 1080p, 720p, 480p, 360p renditions
    cat <<EOF
ffmpeg -y -hide_banner -hwaccel cuda -hwaccel_output_format cuda -i "$input" \
-filter_complex "[0:v]split=4[v1][v2][v3][v4];
[v1]scale_cuda=-2:1080[v1o];
[v2]scale_cuda=-2:720[v2o];
[v3]scale_cuda=-2:480[v3o];
[v4]scale_cuda=-2:360[v4o]" \
-map "[v1o]" -c:v ${CODEC}_nvenc -preset ${PRESET} -b:v 6M -c:a aac -b:a 128k "$outdir/1080p.mp4" \
-map "[v2o]" -c:v ${CODEC}_nvenc -preset ${PRESET} -b:v 3M -c:a aac -b:a 128k "$outdir/720p.mp4" \
-map "[v3o]" -c:v ${CODEC}_nvenc -preset ${PRESET} -b:v 2M -c:a aac -b:a 128k "$outdir/480p.mp4" \
-map "[v4o]" -c:v ${CODEC}_nvenc -preset ${PRESET} -b:v 1M -c:a aac -b:a 96k "$outdir/360p.mp4"
EOF
  else
    # Single-output mode: one 1080p encoding
    cat <<EOF
ffmpeg -y -hide_banner -hwaccel cuda -hwaccel_output_format cuda -i "$input" \
-vf scale_cuda=-2:1080 \
-c:v ${CODEC}_nvenc -preset ${PRESET} -b:v 6M \
-c:a aac -b:a 128k "$outdir/output.mp4"
EOF
  fi
}

# ============================================================
# 🚀 Launch N FFmpeg jobs in parallel
# ============================================================
for i in $(seq 1 $N_JOBS); do
  (
    mkdir -p "$OUT_DIR/job_$i"
    CMD=$(ffmpeg_cmd "$INPUT_VIDEO" "$OUT_DIR/job_$i")
    echo "[Job $i] $CMD" > "$LOG_DIR/job_${i}.cmd"
    eval "$CMD" 2> "$LOG_DIR/ffmpeg_${i}.log"
  ) &
done

# Wait for all parallel FFmpeg jobs to finish
wait || true
kill "$GPU_MON_PID" || true

echo "✅ All FFmpeg processes completed."

# ============================================================
# 📊 Compute mean FFmpeg speed across all jobs
# ============================================================
# Extracts all “speed=...” occurrences from logs and averages them
SPEEDS=$(grep -ho "speed=[0-9.]\+x" "$LOG_DIR"/ffmpeg_*.log | sed 's/speed=\([0-9.]\+\)x/\1/')
MEAN_SPEED=$(echo "$SPEEDS" | awk '{sum+=$1; count++} END {if(count>0) print sum/count; else print "N/A"}')

# ============================================================
# ⚡ Compute mean GPU power
# ============================================================
# Averages all sampled power values from the GPU power log
MEAN_POWER=$(awk -F, '{sum+=$2; count++} END {if(count>0) print sum/count; else print "N/A"}' "$POWER_LOG")

# ============================================================
# 🧹 Cleanup temporary data (logs and outputs)
# ============================================================
echo "🧹 Cleaning up temporary files..."
rm -rf "$OUT_DIR" "$LOG_DIR"

# ============================================================
# 📈 Final results
# ============================================================
echo "----------------------------------"
echo "Mean FFmpeg Speed : ${MEAN_SPEED}x"
echo "Mean GPU Power    : ${MEAN_POWER} W"
echo "----------------------------------"
