#!/usr/bin/env bash
set -euo pipefail

# run_profiles.sh
# Iterate JVM profiles and run the existing run.sh for each profile,
# saving outputs into per-profile subfolders under runs/.
# Usage: ./run_profiles.sh [--] [one_run.py args]
# Example:
#   ./run_profiles.sh -- --monitor-sudo --runSec 30 --timeout 5 --numberOfRepetitions 1 --warmupSec 0 --codec h264 --resolution 480 --use-gpu false

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_SCRIPT="$ROOT_DIR/run.sh"

if [ ! -x "$RUN_SCRIPT" ]; then
  echo "Existing run script not found or not executable: $RUN_SCRIPT" >&2
  exit 1
fi

# Profiles to run (in order)
PROFILES=(baseline interpret c2-only c1-only low-threshold single-compiler heap)

# Collect remaining args (forwarded to one_run)
if [ "${1-}" = "--" ]; then
  shift
fi
FORWARD_ARGS=("$@")

TS="$(date +%Y%m%d_%H%M%S)"

echo "[run_profiles] Starting experiment batch: $TS"

for p in "${PROFILES[@]}"; do
  outdir="runs/${p}_${TS}"
  mkdir -p "$outdir"

  echo "\n[run_profiles] Running profile: $p -> outdir=$outdir"

  # Ensure we forward an explicit --outdir per-profile so one_run writes there
  args=("${FORWARD_ARGS[@]}")
  # Remove any existing --outdir occurrences from args
  newargs=()
  skip_next=0
  for a in "${args[@]}"; do
    if [ "$skip_next" -eq 1 ]; then
      skip_next=0
      continue
    fi
    if [ "$a" = "--outdir" ]; then
      skip_next=1
      continue
    fi
    # also strip occurrences like --outdir=VALUE
    case "$a" in
      --outdir=*) continue ;;
    esac
    newargs+=("$a")
  done

  # Append our per-profile outdir
  newargs+=("--outdir" "$outdir")

  # Run the existing run.sh which will build/start the server and call one_run.py
  echo "[run_profiles] Command: $RUN_SCRIPT $p -- ${newargs[*]}"
  "$RUN_SCRIPT" "$p" -- "${newargs[@]}"

  echo "[run_profiles] Completed profile: $p"
done

echo "[run_profiles] All profiles completed. Outputs under: runs/"
