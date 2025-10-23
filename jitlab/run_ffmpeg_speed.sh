#!/usr/bin/env bash
set -euo pipefail
trap 'kill $(jobs -p) 2>/dev/null || true' EXIT

# ============================================================
# CONFIGURATION
# ============================================================
INPUT_VIDEO="videos/Timer.mp4"   # Input video path
CODEC="h264"                     # Codec: h264 | hevc | av1
PRESET_GPU="hq"                  # Preset for GPU encoders
PRESET_CPU="veryfast"            # Preset for CPU encoders
MODE="ladder"                    # Encoding mode: single | ladder
USE_GPU=false                     # true = use NVENC | false = use CPU
N_JOBS=11                        # Number of FFmpeg parallel jobs
POWER_SAMPLE_INTERVAL=0.5        # GPU power sampling interval (seconds)
# ============================================================

LOG_DIR=$(mktemp -d logs_XXXXXX)
OUT_DIR=$(mktemp -d outputs_XXXXXX)
POWER_LOG="$LOG_DIR/gpu_power.log"

echo "==============================================="
echo "Starting FFmpeg batch experiment"
echo "-----------------------------------------------"
echo "Input:     $INPUT_VIDEO"
echo "Codec:     $CODEC"
echo "Preset:    $([ "$USE_GPU" = true ] && echo $PRESET_GPU || echo $PRESET_CPU)"
echo "Mode:      $MODE"
echo "Jobs:      $N_JOBS"
echo "Logs:      $LOG_DIR"
echo "Outputs:   $OUT_DIR"
echo "==============================================="

# ============================================================
# GPU Power Logger (only if GPU mode)
# ============================================================
if [ "$USE_GPU" = true ]; then
  echo "timestamp,power" > "$POWER_LOG"
  (
    while :; do
      nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits \
      | awk '{print strftime("%s"), ",", $1}' >> "$POWER_LOG"
      sleep "$POWER_SAMPLE_INTERVAL"
    done
  ) &
  GPU_MON_PID=$!
fi

# ============================================================
# FFmpeg Command 
# ============================================================
function ffmpeg_cmd() {
  local input="$1"
  local outdir="$2"

  local preset
  local encoder
  local scale

  if [ "$USE_GPU" = true ]; then
    case "$CODEC" in
      h264) encoder="h264_nvenc" ;;
      hevc|h265) encoder="hevc_nvenc" ;;
      av1) encoder="av1_nvenc" ;;
      *) echo "Unsupported codec: $CODEC" >&2; exit 1 ;;
    esac
    preset="$PRESET_GPU"
    scale="scale_cuda=-2:"
  else
    case "$CODEC" in
      h264) encoder="libx264" ;;
      hevc|h265) encoder="libx265" ;;
      av1) encoder="libaom-av1" ;;
      vp9) encoder="libvpx-vp9" ;;
      *) echo "Unsupported codec: $CODEC" >&2; exit 1 ;;
    esac
    preset="$PRESET_CPU"
    scale="scale=-2:"
  fi

  if [[ "$MODE" == "ladder" ]]; then
    if [ "$USE_GPU" = true ]; then
      hwflags="-hwaccel cuda -hwaccel_output_format cuda"
    else
      hwflags=""
    fi

    echo "ffmpeg -hide_banner -y $hwflags -i \"$input\" \
-filter_complex \"[0:v]split=4[v1][v2][v3][v4];
[v1]${scale}1080[v1o];
[v2]${scale}720[v2o];
[v3]${scale}480[v3o];
[v4]${scale}360[v4o]\" \
-map \"[v1o]\" -c:v $encoder -preset $preset -b:v 6M -c:a aac -b:a 128k \"$outdir/1080p.mp4\" \
-map \"[v2o]\" -c:v $encoder -preset $preset -b:v 3M -c:a aac -b:a 128k \"$outdir/720p.mp4\" \
-map \"[v3o]\" -c:v $encoder -preset $preset -b:v 2M -c:a aac -b:a 128k \"$outdir/480p.mp4\" \
-map \"[v4o]\" -c:v $encoder -preset $preset -b:v 1M -c:a aac -b:a 96k \"$outdir/360p.mp4\""
  else
    if [ "$USE_GPU" = true ]; then
      hwflags="-hwaccel cuda -hwaccel_output_format cuda"
    else
      hwflags=""
    fi

    echo "ffmpeg -hide_banner -y $hwflags -i \"$input\" \
-vf ${scale}1080 -c:v $encoder -preset $preset -b:v 6M \
-c:a aac -b:a 128k \"$outdir/output.mp4\""
  fi
}

# ============================================================
# Run FFmpeg jobs in parallel
# ============================================================
PIDS=()
for i in $(seq 1 $N_JOBS); do
  mkdir -p "$OUT_DIR/job_$i"
  CMD=$(ffmpeg_cmd "$INPUT_VIDEO" "$OUT_DIR/job_$i")
  eval "$CMD" 2> "$LOG_DIR/ffmpeg_${i}.log" &
  PIDS+=($!)
done

for pid in "${PIDS[@]}"; do
  wait "$pid" || true
done

# Stop GPU monitor if running
if [ "$USE_GPU" = true ]; then
  kill "$GPU_MON_PID" 2>/dev/null || true
  wait "$GPU_MON_PID" 2>/dev/null || true
fi

echo "All FFmpeg jobs finished."

# ============================================================
# Compute Mean FFmpeg Speed
# ============================================================
SPEEDS=$(grep -ho "speed=[0-9.]\+x" "$LOG_DIR"/ffmpeg_*.log | sed 's/speed=\([0-9.]\+\)x/\1/')
MEAN_SPEED=$(echo "$SPEEDS" | awk '{sum+=$1; count++} END {if(count>0) print sum/count; else print "N/A"}')

# ============================================================
# Compute Mean GPU Power (only for GPU mode)
# ============================================================
if [ "$USE_GPU" = true ]; then
  MEAN_POWER=$(awk -F, '{sum+=$2; count++} END {if(count>0) print sum/count; else print "N/A"}' "$POWER_LOG")
else
  MEAN_POWER="N/A (CPU mode)"
fi

# ============================================================
# Cleanup temporary data
# ============================================================
echo "Cleaning up temporary files..."
rm -rf "$OUT_DIR" "$LOG_DIR"

# ============================================================
# Final Results
# ============================================================
echo "----------------------------------"
echo "Mean FFmpeg Speed : ${MEAN_SPEED}x"
echo "Mean Power         : ${MEAN_POWER} W"
echo "----------------------------------"
