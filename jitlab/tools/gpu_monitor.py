import argparse, csv, os, sys, time, signal

GPU_INDEX = 0          
INTERVAL_S = 1.0        

import pynvml

RUNNING = True
def _stop(*_):
    global RUNNING
    RUNNING = False

def main():
    ap = argparse.ArgumentParser(description="NVML GPU monitor (1 Hz) → CSV")
    ap.add_argument("--duration", type=float, default=0.0, help="Seconds to run (0 = until interrupted)")
    ap.add_argument("--out", default="gpu_monitor.csv", help="Output CSV path")
    args = ap.parse_args()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _stop)

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    try:
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(GPU_INDEX)
    except pynvml.NVMLError as e:
        print(f"[gpu_monitor] NVML init failed: {e}", file=sys.stderr)
        sys.exit(2)

    # Energy counter availability (mJ since boot/rail init)
    has_counter = True
    try:
        _ = pynvml.nvmlDeviceGetTotalEnergyConsumption(h)
    except Exception:
        has_counter = False

    header = ["ts","t_rel_s","power_w","energy_j_this_sec","energy_j_total",
              "gpu_util_percent","mem_util_percent","mem_used_MiB","temp_c"]

    t0 = time.time()
    last_ts = t0
    next_tick = t0 + INTERVAL_S
    rel = 0
    last_counter_j = None
    e_total = 0.0

    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header); f.flush()

        while RUNNING:
            now = time.time()
            if args.duration and (now - t0) >= args.duration:
                break

            sleep_s = max(0.0, next_tick - now)
            if sleep_s > 0: time.sleep(sleep_s)
            ts = time.time()
            dt = max(1e-6, ts - last_ts)

            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                power_w = pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                temp_c = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)

                if has_counter:
                    try:
                        ctr_j = pynvml.nvmlDeviceGetTotalEnergyConsumption(h) / 1000.0
                        e_this = 0.0 if last_counter_j is None else max(0.0, ctr_j - last_counter_j)
                        last_counter_j = ctr_j
                    except Exception:
                        has_counter = False
                        e_this = power_w * dt
                else:
                    e_this = power_w * dt

                e_total += e_this
                w.writerow([f"{ts:.6f}", rel, f"{power_w:.3f}", f"{e_this:.6f}", f"{e_total:.6f}",
                            util.gpu, util.memory, mem.used // (1024*1024), temp_c])
                f.flush()
            except pynvml.NVMLError as e:
                print(f"[gpu_monitor] NVML error: {e}", file=sys.stderr)
                break

            last_ts = ts
            rel += 1
            next_tick += INTERVAL_S

    try:
        pynvml.nvmlShutdown()
    except Exception:
        pass
    print(f"[gpu_monitor] CSV written: {out_path}", file=sys.stderr)

if __name__ == "__main__":
    main()
