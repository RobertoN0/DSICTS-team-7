package com.example.jitlab.api;

import com.example.jitlab.api.storage.VideoStorageService;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRange;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.MimeTypeUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

@RestController
@RequestMapping("/videos")
public class VideoDownloadController {

  private final VideoStorageService storage;

  public VideoDownloadController(VideoStorageService storage) {
    this.storage = storage;
  }

  /**
   * Stream a video file with support for single HTTP Range header. Example:
   * curl -H "Range: bytes=0-1023" http://localhost:8080/videos/{storedFilename}
   */
  @GetMapping(value = "/{storedFilename}")
  public ResponseEntity<?> getVideo(
      @PathVariable String storedFilename,
      @RequestHeader(value = "Range", required = false) String rangeHeader
  ) throws IOException {
    Path path = storage.loadAsPath(storedFilename);
    long fileLength = Files.size(path);
    String contentType = Files.probeContentType(path);
    if (contentType == null) contentType = MimeTypeUtils.APPLICATION_OCTET_STREAM_VALUE;

    // No Range header -> return full file with 200
    if (rangeHeader == null || rangeHeader.isBlank()) {
      InputStreamResource resource = new InputStreamResource(Files.newInputStream(path));
      return ResponseEntity.ok()
          .header(HttpHeaders.ACCEPT_RANGES, "bytes")
          .contentLength(fileLength)
          .contentType(MediaType.parseMediaType(contentType))
          .body(resource);
    }

    // Parse single range
    List<HttpRange> ranges = HttpRange.parseRanges(rangeHeader);
    if (ranges.isEmpty()) {
      return ResponseEntity.status(HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
          .header(HttpHeaders.CONTENT_RANGE, "bytes */" + fileLength)
          .build();
    }

    HttpRange r = ranges.get(0);
    long start = r.getRangeStart(fileLength);
    long end = r.getRangeEnd(fileLength);
    if (start >= fileLength) {
      return ResponseEntity.status(HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
          .header(HttpHeaders.CONTENT_RANGE, "bytes */" + fileLength)
          .build();
    }

    long chunkLength = end - start + 1;
    InputStream is = Files.newInputStream(path);
    try {
      is.skip(start);
    } catch (IOException e) {
      is.close();
      throw e;
    }
    InputStreamResource resource = new InputStreamResource(new LimitedInputStream(is, chunkLength));

    String contentRange = String.format("bytes %d-%d/%d", start, end, fileLength);
    return ResponseEntity.status(HttpStatus.PARTIAL_CONTENT)
        .header(HttpHeaders.ACCEPT_RANGES, "bytes")
        .header(HttpHeaders.CONTENT_RANGE, contentRange)
        .contentLength(chunkLength)
        .contentType(MediaType.parseMediaType(contentType))
        .body(resource);
  }

}

/**
 * Simple InputStream wrapper that limits the number of readable bytes.
 */
class LimitedInputStream extends InputStream {
  private final InputStream in;
  private long remaining;

  LimitedInputStream(InputStream in, long limit) {
    this.in = in;
    this.remaining = limit;
  }

  @Override
  public int read() throws IOException {
    if (remaining <= 0) return -1;
    int v = in.read();
    if (v != -1) remaining--;
    if (v == -1) in.close();
    return v;
  }

  @Override
  public int read(byte[] b, int off, int len) throws IOException {
    if (remaining <= 0) return -1;
    int toRead = (int) Math.min(len, remaining);
    int r = in.read(b, off, toRead);
    if (r > 0) remaining -= r;
    if (remaining <= 0) in.close();
    return r;
  }

  @Override
  public void close() throws IOException {
    in.close();
  }
}
