package com.example.jitlab.api;

import org.springframework.core.io.InputStreamResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRange;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import com.example.jitlab.api.storage.GridFsVideoService;
import org.springframework.data.mongodb.gridfs.GridFsResource;
import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/videos")
public class VideoController {

  private final GridFsVideoService storage;

  public VideoController(GridFsVideoService storage) {
    this.storage = storage;
  }
  /**
   * Stream a video file with support for single HTTP Range header. Example:
   * curl -H "Range: bytes=0-1023" http://localhost:8080/videos/{storedFilename}
   */
@GetMapping("/{id}")
public ResponseEntity<?> getVideo(
    @PathVariable String id,
    @RequestHeader(value = "Range", required = false) String rangeHeader
) throws IOException {
  GridFsResource resource = storage.load(id);
  if (resource == null) {
    return ResponseEntity.notFound().build();
  }

  long fileLength = resource.contentLength();
  String contentType = resource.getContentType() != null ? resource.getContentType() : "video/mp4";

  // Nessun Range → file intero
  if (rangeHeader == null || rangeHeader.isBlank()) {
    return ResponseEntity.ok()
        .header(HttpHeaders.ACCEPT_RANGES, "bytes")
        .contentLength(fileLength)
        .contentType(MediaType.parseMediaType(contentType))
        .body(new InputStreamResource(resource.getInputStream()));
  }

  // Range singolo
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
  InputStream is = resource.getInputStream();
  try {
    is.skip(start);
  } catch (IOException e) {
    is.close();
    throw e;
  }
  InputStreamResource body = new InputStreamResource(new LimitedInputStream(is, chunkLength));

  String contentRange = String.format("bytes %d-%d/%d", start, end, fileLength);
  return ResponseEntity.status(HttpStatus.PARTIAL_CONTENT)
      .header(HttpHeaders.ACCEPT_RANGES, "bytes")
      .header(HttpHeaders.CONTENT_RANGE, contentRange)
      .contentLength(chunkLength)
      .contentType(MediaType.parseMediaType(contentType))
      .body(body);
}


  /**
   * Upload an MP4 video file.
   * curl -F "file=@sample.mp4" http://localhost:8080/videos/upload
   */
  @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<?> upload(@RequestPart("file") MultipartFile file) throws Exception {
    String id = storage.save(file);
    Map<String, Object> body = Map.of(
        "id", id,
        "originalFilename", file.getOriginalFilename(),
        "sizeBytes", file.getSize(),
        "contentType", file.getContentType(),
        "uploadTs", Instant.now().toString()
    );
    return ResponseEntity.status(HttpStatus.CREATED).body(body);
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
