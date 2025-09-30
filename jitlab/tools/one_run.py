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


def find_pid(cmd_substr: str):
    try:
        out = subprocess.check_output(["pgrep", "-fa", cmd_substr], text=True)
        return int(out.strip().splitlines()[0].split()[0])
    except Exception:
        return None


def run():
    ap = argparse.ArgumentParser(description="Run monitor + headless Locust experiment")
    ap.add_argument("--users", type=int, default=50, help="Number of Locust users (virtual users)")
    ap.add_argument("--spawn-rate", type=int, default=10, help="Locust spawn rate (users/sec)")
    ap.add_argument("--runSec", type=int, default=120, help="Duration of the locust run in seconds")
    ap.add_argument("--locustfile", default="tools/locustfile.py", help="Locustfile to run")
    ap.add_argument("--host", default="http://localhost:8080", help="Target host for Locust")
    ap.add_argument("--server-cmd-substr", default="jitlab-0.0.1-SNAPSHOT.jar", help="Substring to find server PID")
    ap.add_argument("--outdir", default="runs", help="Directory to write CSV outputs")
    ap.add_argument("--monitor-sudo", action="store_true", help="Run the monitor under sudo (useful if energy_uj is not readable)")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(args.outdir, exist_ok=True)

    pid = find_pid(args.server_cmd_substr)
    if not pid:
        print(f"[one_run] Could not find server PID by '{args.server_cmd_substr}'. Start the server first.", file=sys.stderr)
        sys.exit(1)
    print(f"[one_run] Using server PID: {pid}")

    mon_csv = os.path.join(args.outdir, f"monitor_{ts}.csv")
    locust_prefix = os.path.join(args.outdir, f"locust_{ts}")

    # Monitor duration slightly longer than Locust run
    duration = args.runSec + 5
    mon_cmd = ["python3", "tools/monitor.py", "--pid", str(pid), "--interval", "1", "--duration", str(duration), "--out", mon_csv]
    # If user requested sudo for the monitor, prefix the command.
    if args.monitor_sudo:
        print("[one_run] monitor will be started with sudo (you may be prompted for your password)")
        mon_cmd = ["sudo"] + mon_cmd
    print("[one_run] START monitor:", " ".join(shlex.quote(x) for x in mon_cmd))
    mon_p = subprocess.Popen(mon_cmd, stdout=sys.stdout, stderr=sys.stderr)

    locust_cmd = ["locust", "-f", args.locustfile, "--headless",
                  "-u", str(args.users), "-r", str(max(1, args.spawn_rate)),
                  "-t", f"{args.runSec}s", "--host", args.host,
                  "--csv", locust_prefix]

    # Prefer the repo virtualenv locust binary when available (sudo strips PATH)
    virenv_locust = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'virenv', 'bin', 'locust'))
    if os.path.isfile(virenv_locust) and os.access(virenv_locust, os.X_OK):
        locust_cmd[0] = virenv_locust

    print("[one_run] START locust:", " ".join(shlex.quote(x) for x in locust_cmd))
    try:
        ret = subprocess.run(locust_cmd).returncode
    except FileNotFoundError:
        print("[one_run] 'locust' not found. Try activating the virtualenv or install locust in system PATH.", file=sys.stderr)
        try:
            if mon_p.poll() is None:
                mon_p.terminate()
        except Exception:
            pass
        sys.exit(2)
    print(f"[one_run] locust exited with code {ret}")
    if ret != 0:
        print("[one_run] Locust returned non-zero exit code.")

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
    print(f"Locust CSV prefix: {locust_prefix}*")
    print(f"Monitor CSV:       {mon_csv}")

    # Attempt to generate plots where possible.
    # If Locust created a stats CSV, convert a single summary row into a minimal load CSV
    # compatible with tools/plot.py and then call plot.py.
    stats_csv = locust_prefix + "_stats.csv"
    if os.path.isfile(stats_csv) and os.path.isfile(mon_csv):
        try:
            # read locust stats and produce a small 'load' CSV with expected header
            import csv as _csv
            load_conv = os.path.join(args.outdir, f"load_from_locust_{ts}.csv")
            with open(stats_csv, 'r', newline='') as s, open(load_conv, 'w', newline='') as o:
                reader = _csv.reader(s)
                writer = _csv.writer(o)
                writer.writerow(["ts","rps","avg_ms","p50_ms","p95_ms","ok","err"])
                header = next(reader, None)
                cols = {c: i for i, c in enumerate(header)} if header else {}

                # Heuristics for column names in Locust stats csv
                def idx(*names):
                    for n in names:
                        if n in cols:
                            return cols[n]
                    return None

                idx_rps = idx('Total RPS', 'Total rps', 'total_rps', 'TotalRPS')
                idx_avg = idx('Average', 'avg_response_time')
                idx_p50 = idx('Median', 'median_response_time')
                idx_p95 = idx('95%', '95%') or idx('p95', 'p95_ms')
                idx_ok = idx('Request Count', 'request_count', 'Total Requests')
                idx_fail = idx('Failure Count', 'failure_count', 'Total Failures')

                ts0 = int(time.time())
                wrote = False
                for row in reader:
                    if not any(row):
                        continue
                    def safe(i, cast=float, default=0):
                        try:
                            return cast(row[i]) if i is not None and i < len(row) else default
                        except Exception:
                            return default

                    rps = safe(idx_rps, float, 0.0)
                    avg_ms = safe(idx_avg, float, 0.0)
                    p50 = safe(idx_p50, float, 0.0)
                    p95 = safe(idx_p95, float, 0.0)
                    ok = int(safe(idx_ok, float, 0))
                    err = int(safe(idx_fail, float, 0))
                    writer.writerow([ts0, f"{rps:.3f}", f"{avg_ms:.3f}", f"{p50:.3f}", f"{p95:.3f}", ok, err])
                    wrote = True
                    break

            if not wrote:
                print("[one_run] Could not extract values from locust stats for plotting; skipping.")
            else:
                print(f"[one_run] Generated load CSV from locust stats: {load_conv}")
                env = os.environ.copy()
                env["MPLBACKEND"] = "Agg"
                plot_cmd = ["python3", "tools/plot.py", "--load", load_conv, "--monitor", mon_csv, "--title", f"Locust run {ts}"]
                try:
                    print("[one_run] START plot:", " ".join(shlex.quote(x) for x in plot_cmd))
                    subprocess.check_call(plot_cmd, env=env)
                except subprocess.CalledProcessError as e:
                    print(f"[one_run] plotting failed (exit {e.returncode}).", file=sys.stderr)
        except Exception as e:
            print(f"[one_run] Failed to prepare plot data: {e}", file=sys.stderr)


if __name__ == "__main__":
    run()

