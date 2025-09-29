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
