#!/usr/bin/env python3
"""one_run.py

Canonical orchestrator: start the monitor for the server PID (or cmd substring),
then run Locust headlessly with the provided locustfile. Writes monitor CSV and
Locust CSV prefix into the output directory.

Usage examples:
  # simple headless Locust run with monitor
  python3 tools/one_run.py --users 50 --spawn-rate 10 --runSec 120 --outdir runs

Notes:
  - The script expects the server process to already be running; it looks it up
    by a substring of the server commandline (default: `jitlab-0.0.1-SNAPSHOT.jar`).
"""

from datetime import datetime
import argparse
import os
import shlex
import subprocess
import sys
import time
import json


def find_pid(cmd_substr: str):
    try:
        out = subprocess.check_output(["pgrep", "-fa", cmd_substr], text=True)
        return int(out.strip().splitlines()[0].split()[0])
    except Exception:
        return None
    
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
    #ap.add_argument("--locustfile", default="tools/locustfile.py", help="Locustfile to run")
    #ap.add_argument("--users", type=int, default=50, help="Number of Locust users (virtual users)")
    #ap.add_argument("--spawn-rate", type=int, default=10, help="Locust spawn rate (users/sec)")
    ap.add_argument("--outdir", default="runs", help="Directory to write CSV outputs")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(args.outdir, exist_ok=True)

    ############################################
                ## Warmup phase ##
    ############################################
    #Add warmup with load_py 
    if args.warmupSec > 0:
        print(f"[one_run] Starting warmup phase for {args.warmupSec} seconds…")
        load_py = os.path.join(os.path.dirname(__file__), 'load_py.py')
        # The warmup body must be passed as a JSON string to the subprocess command
        warmup_body = json.dumps({"iterations": 2000, "payloadSize": 20000})
        warmup_cmd = ["python3", load_py, "--url", args.host, "--runSec", str(args.warmupSec), "--body", warmup_body]
        print("[one_run] START warmup:", " ".join(shlex.quote(x) for x in warmup_cmd))
        try:
            ret = subprocess.run(warmup_cmd).returncode
        except FileNotFoundError:
            print("[one_run] 'python3' not found.", file=sys.stderr)
            sys.exit(2)
        print(f"[one_run] Warmup exited with code {ret}")
        if ret != 0:
            print("[one_run] Warmup returned non-zero exit code.")


    ############################################
                ## Experiment Loop ##
    ############################################
    for i in range(args.numberOfRepetitions):
        #############################################
        ## Cool down after warmup and previous run ##
        #############################################
        print(f"[one_run] Starting experiment iteration {i + 1}…")
        time.sleep(args.timeout)

        ###########################################
                    ## Monitor Start ##
        ############################################
        pid = find_pid(args.server_cmd_substr)
        if not pid:
            print(f"[one_run] Could not find server PID by '{args.server_cmd_substr}'. Start the server first.", file=sys.stderr)
            sys.exit(1)
        print(f"[one_run] Using server PID: {pid}")

        mon_csv = os.path.join(args.outdir, f"monitor_{ts}.csv")

        # Monitor duration slightly longer than Locust run
        duration = args.runSec + 5
        mon_cmd = ["python3", "tools/monitor.py", "--pid", str(pid), "--interval", "1", "--duration", str(duration), "--out", mon_csv]
        # If user requested sudo for the monitor, prefix the command.
        if args.monitor_sudo:
            print("[one_run] monitor will be started with sudo (you may be prompted for your password)")
            mon_cmd = ["sudo"] + mon_cmd
        print("[one_run] START monitor:", " ".join(shlex.quote(x) for x in mon_cmd))
        mon_p = subprocess.Popen(mon_cmd, stdout=sys.stdout, stderr=sys.stderr)


        ###########################################
                    ## Locust Start ##
        ############################################
        #locust_prefix = os.path.join(args.outdir, f"locust_{ts}")
#
        #locust_cmd = ["locust", "-f", args.locustfile, "--headless",
        #              "-u", str(args.users), "-r", str(max(1, args.spawn_rate)),
        #              "-t", f"{args.runSec}s", "--host", args.host,
        #              "--csv", locust_prefix]
#
        ## Prefer the repo virtualenv locust binary when available (sudo strips PATH)
        #virenv_locust = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'virenv', 'bin', 'locust'))
        #if os.path.isfile(virenv_locust) and os.access(virenv_locust, os.X_OK):
        #    locust_cmd[0] = virenv_locust
#
        #print("[one_run] START locust:", " ".join(shlex.quote(x) for x in locust_cmd))
        #try:
        #    ret = subprocess.run(locust_cmd).returncode
        #except FileNotFoundError:
        #    print("[one_run] 'locust' not found. Try activating the virtualenv or install locust in system PATH.", file=sys.stderr)
        #    try:
        #        if mon_p.poll() is None:
        #            mon_p.terminate()
        #    except Exception:
        #        pass
        #    sys.exit(2)
        #print(f"[one_run] locust exited with code {ret}")
        #if ret != 0:
        #    print("[one_run] Locust returned non-zero exit code.")


        ###########################################
                    ## End of Runtime ##
        ###########################################

        # Wait for monitor to finish; enforce a small deadline
        print("[one_run] WAIT monitor to finish…")
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

    print("\n✅ Done.")
    #print(f"Locust CSV prefix: {locust_prefix}*")
    print(f"Monitor CSV:       {mon_csv}")


if __name__ == "__main__":
    run()