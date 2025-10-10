# JitLab - Endpoints, Flags and Testing (summary)

This file documents the HTTP endpoints, dev flags, demo page and testing commands added during the recent work session (video upload + range download + demo). Use this as a quick reference for local development and testing.

## Base
- Default server base: `http://localhost:8080`
- Video upload directory (default): `videos/` (configurable via `app.video.upload-dir`)

## Endpoints

1) Upload an MP4 file
  - Method: POST
  - URL: `/videos/upload`
  - Content: multipart/form-data with field `file` (type: File)
  - Example (curl):
    ```bash
    curl -i -F "file=@/path/to/sample.mp4" http://localhost:8080/videos/upload
    ```
  - Response: JSON with fields: `id`, `originalFilename`, `storedFilename`, `sizeBytes`, `contentType`, `uploadTs`.
    - Use `storedFilename` to request the file for playback.

2) Download / stream video (with Range support)
  - Method: GET
  - URL: `/videos/{storedFilename}`
  - Headers: optional `Range: bytes=start-end`
  - Behavior:
    - No Range header -> `200 OK`, full file with `Content-Length`.
    - With Range -> `206 Partial Content`, `Content-Range: bytes start-end/total` and `Content-Length = chunk size`.
    - `Accept-Ranges: bytes` header is provided.
  - Example (curl full):
    ```bash
    curl -v http://localhost:8080/videos/video.mp4 -o downloaded.mp4
    ```
  - Example (curl partial):
    ```bash
    curl -v -H "Range: bytes=0-1023" http://localhost:8080/videos/video.mp4 -o part.bin
    ```

3) Demo page (static)
  - URL: `/play_range.html`
  - Location: `src/main/resources/static/play_range.html` (also packaged under `BOOT-INF/classes/static/` in the JAR)
  - Features:
    - Enter `storedFilename` and click Play.
    - Page probes the video (HEAD by default) then attempts MediaSource incremental fetches using Range requests (1MB chunks). If MediaSource isn't available or fetch/append fails, it falls back to a direct `<video>` tag pointing to `/videos/{storedFilename}`.

## Dev CORS config
- For local development the app includes a permissive CORS mapping for `/videos/**` (see `WebConfig`). This allows testing the demo from other origins while developing. Remove or tighten in production.


## Troubleshooting

- 404 when requesting `/play_range.html`:
  - Ensure the Spring Boot process was restarted after changes. The static file lives in `src/main/resources/static/play_range.html`; rebuild and restart the app.
  - Verify the JAR contains the file:
    ```bash
    jar tf target/jitlab-0.0.1-SNAPSHOT.jar | grep play_range.html
    ```

- `TypeError: Failed to fetch` in browser (demo probe failed):
  - Check the server is running and reachable via curl:
    ```bash
    curl -I http://localhost:8080/videos/<storedFilename>
    ```
  - Confirm you are using `http://` (not `https://`) unless you configured SSL. If the browser attempts HTTPS against the HTTP port Tomcat will log TLS handshake bytes as invalid HTTP.
  - If the browser forces HTTPS (HSTS), run the app on a different port (e.g., 8081) or enable HTTPS in Spring Boot (self-signed keystore).

- CORS blocked:
  - For local dev we added `WebConfig` to allow cross-origin GET/HEAD for `/videos/**`. If you still see CORS errors, ensure the demo page is loaded from the same origin (recommended): `http://localhost:8080/play_range.html`.

## Quick run & test sequence

1. Build and run:
   ```bash
   mvn -f jitlab/pom.xml -DskipTests package
   java -jar jitlab/target/jitlab-0.0.1-SNAPSHOT.jar
   ```

2. Upload a video and get `storedFilename` (use curl or Postman):
   ```bash
   curl -i -F "file=@/path/to/sample.mp4" http://localhost:8080/videos/upload
   ```

3. Open the demo page and play:
   - Visit `http://localhost:8080/play_range.html`, paste the `storedFilename` and click Play.

4. Or use curl to stream / range:
   ```bash
   curl -v -H "Range: bytes=0-1023" http://localhost:8080/videos/<storedFilename> -o part.bin
   ```

  ## Notes about the current codebase (2025-09-30)

  - Headless Locust: we run Locust in headless mode for automated, scriptable experiments. "Headless" means Locust runs without its web UI and instead executes the defined user behaviour from the `tools/locustfile.py` directly from the command line. Use `locust --headless -f tools/locustfile.py -u <users> -r <spawn_rate> -t <duration> --csv=<out_prefix>` to run a timed experiment; `one_run.py` wraps this to start the monitor and save CSVs.

  - Merged controller: the upload and download endpoints are now in a single `VideoController.java` under `src/main/java/com/example/jitlab/api/`. It exposes:
    - GET `/videos/{storedFilename}` — full file or single-range partial content support (206) with `Accept-Ranges: bytes`.
    - POST `/videos/upload` — multipart `file` upload (returns JSON with metadata and `storedFilename`).
    The merged controller delegates storage to `VideoStorageService`.

  ## Current status / recommended next steps

  - Current: `tools/locustfile.py` is the primary experiment definition. `tools/range_loader.py` remains available for single-mode range-only experiments. `tools/upload_loader.py` was removed in favour of centralized upload task inside Locust.
  - To reproduce multipart parsing issues or to validate uploads:
    1. Ensure there is a small test file in `jitlab/videos/` (or point the Locust env `VIDEOS_DIR` to a folder with test files).
    2. Start the app (`mvn spring-boot:run` or `java -jar target/...jar`) and tail logs.
    3. Run a short headless Locust run that will exercise uploads (e.g., `locust -f tools/locustfile.py --headless -u 20 -r 5 -t 1m --csv=runs/locust_smoke`) or use `one_run.py`.

  ---
  Revision: synchronized with codebase state and recent changes (2025-09-30).

  ## Suggestions for tomorrow (prioritized)

  1) Reproduce and capture the multipart parsing stacktrace
    - Goal: reliably reproduce the server-side `MultipartException` seen earlier and capture the full `Caused by:` stack frames.
    - Steps:
      - Ensure a small sample file exists at `jitlab/videos/test_small.mp4` (use `dd` or `ffmpeg` if needed).
      - Start the server and tail logs: `mvn spring-boot:run` or `java -jar target/jitlab-0.0.1-SNAPSHOT.jar` then `tail -F server.log`.
      - Run a short headless Locust smoke run that will exercise uploads: `python3 tools/one_run.py --users 10 --spawn-rate 3 --runSec 60 --outdir runs --monitor-sudo` (use `--monitor-sudo` if you need energy readings).
      - If a multipart error appears, copy the log lines that include the topmost application frames before the Tomcat trace — those are the true root cause.

  2) Run reproducible smoke experiments and collect baseline
    - Goal: collect baseline resource and request metrics for small, medium, and larger workloads.
    - Example runs:
      - Small: 10 users, 1m
      - Medium: 50 users, 5m
      - Large: 200 users, 10m (if hardware permits)
    - Use `python3 tools/one_run.py --users <n> --spawn-rate <r> --runSec <s> --outdir runs`.
    - Keep all produced CSVs and a short notes file describing machine status (idle CPU, other processes) for each run.

  3) Improve plotting and data wrangling
    - Goal: unify CSV formats so `tools/plot.py` can plot outputs from range loaders, upload loaders and Locust without fragile heuristics.
    - Plan:
      - Add a small converter script `tools/locust_to_load.py` that reliably maps Locust stats rows to the `load` CSV format we use for plotting.
      - Or modify `tools/plot.py` to understand both `range_loader` output and `locust _stats.csv` formats.

  4) Housekeeping & automation
    - Keep a canonical `one_run.py` (done) and remove old/duplicate code blocks. Add `--locust-bin` option if users prefer specifying a binary explicitly.
    - Add a short `RUNBOOK.md` with commands for: starting server, reproducing multipart error, running smoke runs, and where to find CSVs/logs.

  5) If multipart parsing errors only occur under load
    - Investigate upstream/proxy and Tomcat connector settings:
      - Check `maxPostSize` on the connector (Tomcat config) and any reverse proxy buffering/truncation.
      - Enable structured request logging or increase Spring's multipart debug level temporarily.

  Who should do what (quick delegation)
    - Reproducer: create `videos/test_small.mp4`, run smoke upload experiment and capture logs (someone with terminal access and sudo rights).
    - Data wrangler: add `tools/locust_to_load.py` or make `plot.py` accept Locust formats.
    - Ops / config: if multipart errors persist under load, check any reverse proxy/nginx configuration or Tomcat connector tuning.

  Quick checklist for tomorrow's first 30 minutes
    - Create small test file (5–10 MB) in `jitlab/videos/`.
    - Start server and confirm `http://localhost:8080/play_range.html` loads.
    - Run `python3 tools/one_run.py --users 10 --spawn-rate 3 --runSec 60 --outdir runs --monitor-sudo` and watch logs for multipart errors.
    - Save the run CSVs to `runs/` and attach them to the issue describing the repro.

## Encoding endpoints

- POST `/encode`
  - Content: multipart/form-data with fields:
    - `file` (video file)
    - `codec` (e.g., `h264`, `hevc`, `av1`, `vp9`)
    - `resolution` (vertical height, e.g., `1080`)
    - `useGpu` (`true`/`false`) to pick GPU encoder when available
  - Response: JSON `EncodingResult` for a single output file at the requested resolution.
  - Example:
    ```bash
    curl -F "file=@/path/to/in.mp4" -F codec=h264 -F resolution=720 -F useGpu=false \
      http://localhost:8080/encode
    ```

- POST `/encode/multi`
  - Content: same fields as above.
  - Behavior: encodes the uploaded video to the given resolution and all lower rungs down to 360p. For example:
    - `resolution=1080` -> outputs 1080, 720, 480, 360
    - `resolution=720` -> outputs 720, 480, 360
    - `resolution=480` -> outputs 480, 360
  - Response: JSON array of objects with only per-resolution metrics (no filenames):
    `[{"resolution":"1080","elapsedMs":12345,"outputSizeBytes":10485760}, ...]`
  - Example:
    ```bash
    curl -F "file=@/path/to/in.mp4" -F codec=h264 -F resolution=1080 -F useGpu=true \
      http://localhost:8080/encode/multi
    ```
