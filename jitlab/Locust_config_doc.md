How the new Locust works (summary + tweakable knobs)
- Behavior per virtual user:
  - on_start: pick a file from `videos/` (or you can set `STORED_FILE` env var).
  - playback_session (weight 5):
    - HEAD the video.
    - Determine Content-Length, then perform a randomized number of Range GETs (3–20), chunk size chosen from [256k, 512k, 1M].
    - Occasionally (5% chance) seeks to a random offset between chunks.
  - upload_task (weight 1):
    - Pick a random file from `videos/` and POST it to `/videos/upload` as multipart/form-data (field name `file`).
- Tuning points you can change in locustfile.py:
  - Weights: change the `@task(5)` and `@task(1)` decorators to adjust the mix (e.g., `@task(10)` for reads and `@task(2)` for uploads).
  - Wait times: modify `wait_time = between(0.5, 1.5)` to a larger window to simulate less aggressive users.
  - Chunk sizes and distributions: edit the `chunk_size = random.choice([256*1024, 512*1024, 1024*1024])` list or add probabilities to favor certain sizes.
  - Seek probability: change the `if random.random() < 0.05:` to increase/decrease seeking frequency.
  - Session length: change `chunks_to_fetch = random.randint(3, 20)` to shift session durations.
  - Target files: set `STORED_FILE` env var to force all users to stream the same file, or populate `videos/` with representative sizes and formats.
  - Uploads: control upload file set by populating `videos/` with the files you want to use as upload payloads (synthetic or downloaded samples).

How to run an experiment (example)
1) Start your Spring Boot server as you usually do.
2) Run one_run.py:
   ```bash
   python3 tools/one_run.py --users 200 --spawn-rate 20 --runSec 180 --outdir runs
   ```
   - This will: find the server PID, start monitor.py, run Locust headless (200 users, spawn 20/s, 3 minutes), then wait for monitor to finish.
3) Results:
   - Locust CSV files: `runs/locust_<timestamp>_stats.csv`, etc.
   - Monitor CSV: `runs/monitor_<timestamp>.csv`
