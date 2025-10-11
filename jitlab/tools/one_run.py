#!/usr/bin/env python3
"""one_run.py

Canonical orchestrator: start the monitor for the server PID (or cmd substring),
then run Locust headlessly with the provided locustfile. Writes monitor CSV and
Locust CSV prefix into the output directory.

Usage examples:
  # simple headless Locust run with monitor
  python3 tools/one_run.py --profile baseline --users 50 --spawn-rate 10 --runSec 120 --outdir runs --codec h264 --resolution 480 --use-gpu false

Notes:
  - The script shells out to `build_and_cleanup.py` (configurable via --build-script)
    to start the server for each iteration and to perform post-run cleanup.
"""

from datetime import datetime
import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
import json

from typing import List

    
PROFILE_FLAGS = {
    "baseline": [],
    "interpret": ["-Xint"],
    "c2-only": ["-XX:-TieredCompilation"],
    "c1-only": ["-XX:+TieredCompilation", "-XX:TieredStopAtLevel=1"],
    "low-threshold": ["-XX:CompileThreshold=1000"],
    "single-compiler": ["-XX:CICompilerCount=1"],
    "heap": ["-Xms1g", "-Xmx1g"],
}

def _profile_flags(profile: str) -> List[str]:
    try:
        return PROFILE_FLAGS[profile]
    except KeyError as exc:
        raise ValueError(f"Unknown profile '{profile}'. Known: {', '.join(PROFILE_FLAGS)}") from exc

    
# Example usage command:
# python3 tools/one_run.py --monitor-sudo  --runSec 300 --numberOfRepetitions 30 --timeout 60 --warmupSec 60 --users 1000 --spawn-rate 20

def run():
    ap = argparse.ArgumentParser(description="Run monitor + headless Locust experiment")
    ap.add_argument("--host", default="http://localhost:8080", help="Target host for Locust")
    ap.add_argument("--monitor-sudo", action="store_true", help="Run the monitor under sudo (useful if energy_uj is not readable)")
    ap.add_argument("--server-cmd-substr", default="jitlab-0.0.1-SNAPSHOT.jar", help="Substring to find server PID")
    ap.add_argument("--runSec", type=int, default=120, help="Duration of the locust run in seconds")
    ap.add_argument("--timeout", type=int, default=60, help="Seconds to wait between runs (default: 60)")
    ap.add_argument("--warmupSec", type=int, default=0, help="Duration of the warmup phase in seconds (default: 0, no warmup)")
    ap.add_argument("--numberOfRepetitions", type=int, default=30, help="Number of times to repeat the test (default: 30)")
    ap.add_argument("--locustfile", default="tools/locustfile_encode.py", help="Locustfile to run")
    ap.add_argument("--users", type=int, default=5, help="Number of Locust users (virtual users)")
    ap.add_argument("--spawn-rate", type=int, default=1, help="Locust spawn rate (users/sec)")
    ap.add_argument("--profile", default=None, help="Profile name used by build/cleanup helper")
    ap.add_argument("--codec", default=None, help="Codec to pass to locustfile (e.g. h264)")
    ap.add_argument("--resolution", default=None, help="Resolution to pass to locustfile (e.g. 480)")
    ap.add_argument("--use-gpu", default="false", help="use-gpu flag to pass to locustfile (true/false)")
    ap.add_argument("--outdir", default="runs", help="Directory to write CSV outputs")
    args = ap.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    jar_path = os.path.join(repo_root, "target", "jitlab-0.0.1-SNAPSHOT.jar")
    videos_tmp = os.path.join(repo_root, "videos", "tmp")
    python_bin = sys.executable or "python3"
    profile = args.profile or "baseline"

    if not os.path.isfile(jar_path):
        print(f"[one_run] JAR not found at {jar_path}. Run mvn package first.", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(args.outdir, exist_ok=True)


    ###########################################
                ## Helper Functions ##
    ############################################
    def start_server() -> int:
        """Start the server process for the provided profile and wait until ready."""
        flags = _profile_flags(profile)
        cmd: List[str] = ["java"] + flags + ["-jar", str(jar_path)]

        cwd = repo_root or jar_path.parent
        print(f"Starting server cmd: {' '.join(cmd)} (cwd={cwd})")
        preexec_fn = os.setsid if hasattr(os, "setsid") else None
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(cwd), preexec_fn=preexec_fn, )

        if not wait_for_server():
            print("Server did not become ready in time; terminating.")
            raise RuntimeError("Server failed readiness check.")

        print(f"Server ready (pid={proc.pid}).")
        return proc.pid

    def wait_for_server() -> bool:
        import urllib.request
        import urllib.error

        url = args.host.rstrip("/") + "/ping"
        print(f"Waiting for server readiness at {url} (timeout={60}s)")

        deadline = time.time() + max(1, 60)
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if 200 <= getattr(resp, "status", getattr(resp, "code", 200)) < 500:
                        return True
            except urllib.error.URLError:
                pass
            except Exception as exc:  # noqa: BLE001
                print(f"Readiness probe error: {exc}")
            time.sleep(1.0)
        return False

    def helper_cleanup(server_pid, monitor_pid) -> None:
        try:
            # Kill any ffmpeg process still running
            print("[one_run] Killing any ffmpeg processes...")
            subprocess.run(["pkill", "-9", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            subprocess.run(["pkill", f"server_pid={server_pid}"])
            subprocess.run(["pkill", f"monitor_pid={monitor_pid}"])
            
            # Delete and recreate videos/tmp directory
            print(f"[one_run] Cleaning directory: {videos_tmp}")
            shutil.rmtree(videos_tmp, ignore_errors=True)
        except Exception as e:
            print(f"[one_run] Cleanup failed: {e}", file=sys.stderr)


    ############################################
                ## Experiment Loop ##
    ############################################
    load_py = os.path.join(os.path.dirname(__file__), "load_py.py")

    for i in range(args.numberOfRepetitions):
        #############################################
        ## Cool down after warmup and previous run ##
        #############################################
        print(f"[one_run] Starting experiment iteration {i + 1}…")
        if args.timeout > 0:
            time.sleep(args.timeout)

        server_pid = None
        mon_p = None
        try:
            ###########################################
                        ## Server setup ##
            ###########################################
            server_pid = start_server()
            print(f"[one_run] Using server PID: {server_pid}")

            ############################################
                        ## Warmup phase ##
            ############################################
            if args.warmupSec > 0:
                print(f"[one_run] Starting warmup phase for {args.warmupSec} seconds…")
                warmup_body = json.dumps({"iterations": 2000, "payloadSize": 20000})
                warmup_cmd = [python_bin, load_py,
                    "--url", args.host,
                    "--runSec", str(args.warmupSec),
                    "--body", warmup_body,
                ]
                print("[one_run] START warmup:", " ".join(shlex.quote(x) for x in warmup_cmd))
                try:
                    ret = subprocess.run(warmup_cmd).returncode
                except FileNotFoundError:
                    print("[one_run] Python interpreter not found for warmup.", file=sys.stderr)
                    sys.exit(2)
                print(f"[one_run] Warmup exited with code {ret}")
                if ret != 0:
                    print("[one_run] Warmup returned non-zero exit code.")

            ###########################################
                        ## Monitor Start ##
            ###########################################
            mon_csv = os.path.join(args.outdir, f"monitor_{ts}.csv")
            duration = args.runSec + 5
            mon_cmd = [python_bin, "tools/monitor.py",
                "--pid", str(server_pid),
                "--interval", "1",
                "--duration", str(duration),
                "--out", mon_csv,
            ]
            if args.monitor_sudo:
                mon_cmd = ["sudo"] + mon_cmd
            print("[one_run] START monitor:", " ".join(shlex.quote(x) for x in mon_cmd))
            mon_p = subprocess.Popen(mon_cmd, stdout=sys.stdout, stderr=sys.stderr)

            ###########################################
                ## Locust encode stress test  ##
            ###########################################
            locust_prefix = os.path.join(args.outdir, f"locust_{ts}")
            locust_cmd = ["locust", "-f", args.locustfile, "--headless",
                "-u", str(args.users),
                "-r", str(max(1, args.spawn_rate)),
                "-t", f"{args.runSec}s",
                "--host", args.host,
                "--csv", locust_prefix,
            ]

            virenv_locust = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "virenv", "bin", "locust"))
            if os.path.isfile(virenv_locust) and os.access(virenv_locust, os.X_OK):
                locust_cmd[0] = virenv_locust

            print("[one_run] START locust:", " ".join(shlex.quote(x) for x in locust_cmd))
            env = os.environ.copy()
            if args.codec:
                env["LOCUST_CODEC"] = args.codec
            if args.resolution:
                env["LOCUST_RESOLUTION"] = args.resolution
            if args.use_gpu:
                env["LOCUST_USE_GPU"] = str(args.use_gpu)

            try:
                ret = subprocess.run(locust_cmd, env=env).returncode
            except FileNotFoundError:
                print("[one_run] 'locust' not found. Try activating the virtualenv or install locust in system PATH.", file=sys.stderr)
                sys.exit(2)
            print(f"[one_run] locust exited with code {ret}")
            if ret != 0:
                print("[one_run] Locust returned non-zero exit code.")

            ###########################################
                        ## End of Runtime ##
            ###########################################
            print("[one_run] WAIT monitor to finish…")
            deadline = time.time() + duration + 15
            while mon_p.poll() is None and time.time() < deadline:
                time.sleep(0.2)
            deadline = time.time() + duration + 15
            while mon_p.poll() is None and time.time() < deadline:
                time.sleep(0.2)
            if mon_p.poll() is None:
                print("[one_run] monitor did not exit in time; terminating…", file=sys.stderr)
                mon_p.terminate()
                try:
                    mon_p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    mon_p.kill()
        finally:
            helper_cleanup(server_pid, mon_p.pid if mon_p else None)

    print("\n✅ Done.")
    print(f"Locust CSV prefix: {locust_prefix}*")
    print(f"Monitor CSV:       {mon_csv}")


if __name__ == "__main__":
    run()
