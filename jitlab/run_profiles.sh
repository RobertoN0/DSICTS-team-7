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
JAR_FILE="$ROOT_DIR/target/jitlab-0.0.1-SNAPSHOT.jar"

if [ ! -x "$RUN_SCRIPT" ]; then
  echo "Existing run script not found or not executable: $RUN_SCRIPT" >&2
  exit 1
fi

# Profiles to run (in order)
PROFILES=(baseline c2-only c1-only) # interpret low-threshold single-compiler heap

# Build once up-front (fail fast if build fails)
echo "[run_profiles] Building project once via Maven..."
(cd "$ROOT_DIR" && mvn clean package -DskipTests)

if [ ! -f "$JAR_FILE" ]; then
  echo "[run_profiles] ERROR: Built JAR not found at $JAR_FILE" >&2
  exit 2
fi

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
  # We set SKIP_BUILD=1 so run.sh will not invoke Maven again.
  echo "[run_profiles] Command: SKIP_BUILD=1 $RUN_SCRIPT $p -- ${newargs[*]}"
  SKIP_BUILD=1 "$RUN_SCRIPT" "$p" -- "${newargs[@]}"

  echo "[run_profiles] Completed profile: $p"
done

echo "[run_profiles] All profiles completed. Outputs under: runs/"
