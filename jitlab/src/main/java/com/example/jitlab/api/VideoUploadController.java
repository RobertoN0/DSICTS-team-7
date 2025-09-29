package com.example.jitlab.api;

import com.example.jitlab.api.storage.VideoStorageService;
import com.example.jitlab.api.storage.VideoStorageService.StoredVideo;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.Instant;
import java.util.Map;

@RestController
@RequestMapping("/videos")
public class VideoUploadController {

  private final VideoStorageService storage;

  public VideoUploadController(VideoStorageService storage) {
    this.storage = storage;
  }

  /**
   * Upload an MP4 video file.
   * curl -F "file=@sample.mp4" http://localhost:8080/videos/upload
   */
  @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<?> upload(@RequestPart("file") MultipartFile file) throws Exception {
    StoredVideo stored = storage.store(file);
    Map<String, Object> body = Map.of(
        "id", stored.id(),
        "originalFilename", stored.originalFilename(),
        "storedFilename", stored.storedFilename(),
        "sizeBytes", stored.sizeBytes(),
        "contentType", stored.contentType(),
        "uploadTs", Instant.now().toString()
    );
    return ResponseEntity.status(HttpStatus.CREATED).body(body);
  }

  @ExceptionHandler({IllegalArgumentException.class, SecurityException.class})
  public ResponseEntity<?> badRequest(Exception ex) {
    return ResponseEntity.badRequest().body(Map.of(
        "error", ex.getClass().getSimpleName(),
        "message", ex.getMessage()
    ));
  }
}
