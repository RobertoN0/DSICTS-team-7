#!/usr/bin/env bash
set -euo pipefail

# build-profiles available: baseline | interpret | c2-only | c1-only | low-threshold | single-compiler | heap

# Usage: ./run.sh [--no-build] [profile] -- [one_run.py args]
# Notes:
#   - Use --no-build (or env SKIP_BUILD=1) to skip Maven build. Useful when invoked by run_profiles.sh.
# Example: ./run.sh baseline -- --monitor-sudo --runSec 5 --timeout 2 --numberOfRepetitions 1 --warmupSec 0 --codec h264 --resolution 480 --use-gpu false --outdir runs/test_profile

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
JAR_FILE="$ROOT_DIR/target/jitlab-0.0.1-SNAPSHOT.jar"

usage() {
  cat <<EOF
Usage: $0 [--no-build] [profile] -- [one_run.py args]

Profiles (kept simple to match README):
  baseline        : default java -jar
  interpret       : java -Xint (interpret-only)
  c2-only         : java -XX:-TieredCompilation (C2 only)
  c1-only         : java -XX:+TieredCompilation -XX:TieredStopAtLevel=1 (C1-only)
  low-threshold   : java -XX:CompileThreshold=1000
  single-compiler : java -XX:CICompilerCount=1
  heap            : java -Xms1g -Xmx1g

Example:
  $0 baseline -- --runSec 120
   SKIP_BUILD=1 $0 c2-only -- --runSec 120
   $0 --no-build interpret -- --runSec 120
EOF
}

if [ "${1-}" = "-h" ] || [ "${1-}" = "--help" ]; then
  usage
  exit 0
fi

PROFILE_DEFAULT="baseline"

# Parse optional --no-build flag before profile
NO_BUILD_FLAG=0
while [ "${1-}" = "--no-build" ]; do
  NO_BUILD_FLAG=1
  shift || true
done

PROFILE="${1-}"

if [ -z "$PROFILE" ] || [[ "$PROFILE" == --* ]]; then
  # no profile provided, use default and keep all args
  PROFILE="$PROFILE_DEFAULT"
  ARGS=("$@")
else
  # consume first arg as profile, remaining args after '--' forwarded to one_run
  shift || true
  # if next token is '--', consume it
  if [ "${1-}" = "--" ]; then
    shift || true
  fi
  ARGS=("$@")
fi

case "$PROFILE" in
  baseline)
    JAVA_FLAGS=()
    ;;
  interpret)
    JAVA_FLAGS=("-Xint")
    ;;
  c2-only)
    JAVA_FLAGS=("-XX:-TieredCompilation")
    ;;
  c1-only)
    JAVA_FLAGS=("-XX:+TieredCompilation" "-XX:TieredStopAtLevel=1")
    ;;
  low-threshold)
    JAVA_FLAGS=("-XX:CompileThreshold=1000")
    ;;
  single-compiler)
    JAVA_FLAGS=("-XX:CICompilerCount=1")
    ;;
  heap)
    JAVA_FLAGS=("-Xms1g" "-Xmx1g")
    ;;
  *)
    echo "Unknown profile: $PROFILE" >&2
    usage
    exit 2
    ;;
esac

echo "[run.sh] Using profile: $PROFILE"
if [ ${#JAVA_FLAGS[@]} -gt 0 ]; then
  echo "[run.sh] JVM flags: ${JAVA_FLAGS[*]}"
fi

###########################################
          ## Build MVN project ##
###########################################
if [ "${SKIP_BUILD-0}" = "1" ] || [ "$NO_BUILD_FLAG" = "1" ]; then
  echo "[run.sh] Skipping Maven build (SKIP_BUILD=${SKIP_BUILD-0}, --no-build flag=$NO_BUILD_FLAG)"
else
  echo "[run.sh] Building project (maven)..."
  (cd "$ROOT_DIR" && mvn clean package -DskipTests)
fi

if [ ! -f "$JAR_FILE" ]; then
  echo "JAR not found at $JAR_FILE" >&2
  exit 1
fi

SERVER_PID=0

start_server() {
  echo "[run.sh] Starting server..."
  # build java command
  CMD=("java")
  CMD+=("${JAVA_FLAGS[@]}")
  CMD+=("-jar" "$JAR_FILE")

  # start in background, redirect stdout/stderr
  echo "[run.sh] Command: ${CMD[*]}"
  nohup "${CMD[@]}" > /dev/null 2>&1 &
  SERVER_PID=$!
  echo "[run.sh] Server PID: $SERVER_PID"
}

# at top of script (before defining stop_server):
CLEANUP_DONE=0

cleanup() {
  if [ "${CLEANUP_DONE:-0}" -ne 0 ]; then
    return
  fi
  CLEANUP_DONE=1
  echo "[run.sh] Cleaning up (cleanup() called)"
  stop_server || true
}

# trap that preserves original exit code and calls cleanup exactly once
trap 'rc=$?; echo "[run.sh] Trapped exit - cleaning up (rc=$rc)"; cleanup; exit $rc' EXIT INT TERM

stop_server() {
  if [ "$SERVER_PID" -ne 0 ] 2>/dev/null; then
    echo "[run.sh] Stopping server PID $SERVER_PID"
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}

###########################################
  ## Start Server with correct profile ##
###########################################
start_server

# Wait for server to be ready by polling /ping
echo "[run.sh] Waiting for server to be ready (http://localhost:8080/ping)..."
READY=0
for i in {1..60}; do
  if curl -sS --max-time 1 http://localhost:8080/ping >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo "[run.sh] Server did not become ready in time." >&2
  exit 3
fi
echo "[run.sh] Server is ready."

# Check for python3 installation
PY="$(command -v python3 || true)"

if [ -z "$PY" ]; then
  echo "python3 not found. Please install Python 3." >&2
  exit 4
fi

###########################################
  ## Start one_run.py for experiment ##
###########################################
ONE_RUN="$ROOT_DIR/tools/one_run.py"
if [ ! -f "$ONE_RUN" ]; then
  echo "one_run.py not found at $ONE_RUN" >&2
  exit 1
fi

echo "[run.sh] Running orchestrator: $PY $ONE_RUN ${ARGS[*]}"
"$PY" "$ONE_RUN" "${ARGS[@]}"

echo "[run.sh] Orchestrator finished. Cleaning up..."
stop_server
CLEANUP_DONE=1

echo "[run.sh] Done."
