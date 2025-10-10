import pynvml
import subprocess
import threading
import time
import os
import signal

# --- Configuration ---
GPU_INDEX = 0
# INPUT_FILE = "./videos/input.mp4"
INPUT_FILE = "./videos/video14minute1080p60.mp4"
OUTPUT_FILE = "./videos/output_nvenc_av1.mkv"
FFMPEG_PATH = "ffmpeg"

# Hardware-accelerated AV1 encoding command (using h264_cuvid for decoding and av1_nvenc for encoding)
# This command ensures all work is done on the GPU as much as possible.
# NOTE: The '-c:v av1_nvenc' requires an NVIDIA GPU with AV1 NVENC support.
FFMPEG_COMMAND = [
    FFMPEG_PATH,
    "-y",
    "-hwaccel", "cuda",
    "-i", INPUT_FILE,
    "-c:v", "av1_nvenc",
    # "-c:v", "h264_nvenc",
    "-preset", "p5",       # p1 (slowest/best) to p7 (fastest/worst)
    # "-preset", "p5",       # p1 (slowest/best) to p7 (fastest/worst)
    "-tune", "hq",         # high quality tuning
    "-b:v", "5M",          # Target bitrate
    "-c:a", "copy",
    OUTPUT_FILE
]

# List to store monitoring data
monitoring_data = []
stop_monitoring = threading.Event()

def monitor_gpu(gpu_index, interval_sec=1):
    """Initializes NVML and continuously queries GPU metrics."""
    print(f"Starting GPU Monitor for Device {gpu_index}...")
    
    # Initialize NVML
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
    except pynvml.NVMLError as e:
        print(f"NVML Error: {e}")
        stop_monitoring.set()
        return

    while not stop_monitoring.is_set():
        try:
            # 1. Utilization Rates (GPU and Memory)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            # 2. Power Usage (in milliwatts)
            power_mw = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
            # 3. Memory Usage
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            mem_used_mib = mem_info.used // (1024 * 1024)

            data = {
                "timestamp": time.time(),
                "gpu_util_perc": utilization.gpu,
                "mem_util_perc": utilization.memory,
                "power_watts": round(power_mw, 2),
                "mem_used_MiB": mem_used_mib,
            }
            monitoring_data.append(data)
            
            # Print real-time status
            print(f"| GPU: {data['gpu_util_perc']:3d}% | Mem: {data['mem_used_MiB']:5d} MiB | Power: {data['power_watts']:5.1f} W |")

        except pynvml.NVMLError as e:
            print(f"NVML monitoring error: {e}")
            break
        
        # Wait for the next interval or stop signal
        stop_monitoring.wait(interval_sec)

    # Cleanup NVML
    pynvml.nvmlShutdown()
    print("GPU Monitor stopped.")

def run_ffmpeg_encode(command):
    """Executes the FFmpeg encoding process."""
    print("\n" + "="*50)
    print(f"Executing FFmpeg command: {' '.join(command)}")
    print("="*50)
    
    try:
        # Start the FFmpeg process
        process = subprocess.Popen(command, 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.STDOUT,
                                   universal_newlines=True)
        
        # Stream FFmpeg output (optional, but good for real-time feedback)
        for line in iter(process.stdout.readline, ''):
            # You can process the output here to extract frame/FPS info if needed
            print(f"[FFMPEG] {line.strip()}")
            pass
            
        # Wait for the process to finish
        process.stdout.close()
        return_code = process.wait()
        
        if return_code != 0:
            print(f"\nFFmpeg process failed with return code {return_code}")
            
    except FileNotFoundError:
        print(f"\nError: FFmpeg command not found. Make sure '{FFMPEG_PATH}' is in your PATH.")
    except Exception as e:
        print(f"\nAn error occurred during FFmpeg execution: {e}")
    finally:
        print("\nFFmpeg encoding finished.")
        # Signal the monitoring thread to stop
        stop_monitoring.set()

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file '{INPUT_FILE}' not found. Please create it and run the script again.")
        return

    # Create and start the GPU monitoring thread
    monitor_thread = threading.Thread(target=monitor_gpu, args=(GPU_INDEX, 1))
    monitor_thread.start()
    
    # Run the FFmpeg process in the main thread
    run_ffmpeg_encode(FFMPEG_COMMAND)
    
    # Wait for the monitoring thread to properly shut down
    monitor_thread.join()

    # --- Print Summary ---
    print("\n" + "#"*50)
    print("GPU Monitoring Summary")
    print("#"*50)

    if not monitoring_data:
        print("No monitoring data collected.")
        return

    gpu_utils = [d['gpu_util_perc'] for d in monitoring_data]
    powers = [d['power_watts'] for d in monitoring_data]
    
    print(f"Total Monitoring Duration: {len(monitoring_data)} seconds")
    print(f"Average GPU Utilization: {sum(gpu_utils) / len(gpu_utils):.2f}%")
    print(f"Peak GPU Utilization:    {max(gpu_utils)}%")
    print("-" * 25)
    print(f"Average Power Draw:      {sum(powers) / len(powers):.2f} W")
    print(f"Peak Power Draw:         {max(powers):.2f} W")
    print("-" * 25)
    print(f"Data saved to 'monitoring_data' list for further analysis (e.g., plotting).")
    
    # You can also save the data to a CSV file here for later plotting
    # import csv
    # with open('gpu_metrics.csv', 'w', newline='') as f:
    #     writer = csv.DictWriter(f, fieldnames=monitoring_data[0].keys())
    #     writer.writeheader()
    #     writer.writerows(monitoring_data)

if __name__ == "__main__":
    main()