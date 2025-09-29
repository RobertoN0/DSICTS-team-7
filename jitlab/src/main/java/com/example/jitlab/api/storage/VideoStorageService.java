package com.example.jitlab.api.storage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.*;
import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

@Service
public class VideoStorageService {

  private final Path rootDir;
  private final long maxSizeBytes;

  public VideoStorageService(
      @Value("${app.video.upload-dir:videos}") String uploadDir,
      @Value("${app.video.max-size-bytes:524288000}") long maxSizeBytes // 500MB default
  ) throws IOException {
    this.rootDir = Paths.get(uploadDir).toAbsolutePath().normalize();
    this.maxSizeBytes = maxSizeBytes;
    Files.createDirectories(this.rootDir);
  }

  public StoredVideo store(MultipartFile file) throws IOException {
    if (file.isEmpty()) {
      throw new IllegalArgumentException("Empty file");
    }
    if (file.getSize() > maxSizeBytes) {
      throw new IllegalArgumentException("File too large: " + file.getSize());
    }
    validateContentType(file);

    String originalName = sanitize(file.getOriginalFilename());
    if (originalName.isBlank()) originalName = "video.mp4";

    String ext = originalName.contains(".") ? originalName.substring(originalName.lastIndexOf('.')) : ".mp4";
    String id = Instant.now().toEpochMilli() + "-" + UUID.randomUUID();
    String storedName = id + ext;
    Path target = rootDir.resolve(storedName).normalize();
    if (!target.startsWith(rootDir)) {
      throw new SecurityException("Invalid path");
    }
    Files.copy(file.getInputStream(), target, StandardCopyOption.REPLACE_EXISTING);

    return new StoredVideo(id, originalName, storedName, target, file.getSize(), file.getContentType());
  }

  private void validateContentType(MultipartFile file) {
    String ct = file.getContentType();
    if (ct == null) {
      throw new IllegalArgumentException("Missing content type");
    }
    // Accept typical mp4 variants
    if (!MediaType.valueOf(ct).isCompatibleWith(MediaType.valueOf("video/mp4"))) {
      // Some browsers may send application/octet-stream; allow only if extension .mp4
      String name = file.getOriginalFilename();
      if (name == null || !name.toLowerCase(Locale.ROOT).endsWith(".mp4")) {
        throw new IllegalArgumentException("Unsupported content type: " + ct);
      }
    }
  }

  private String sanitize(String in) {
    if (in == null) return "";
    String cleaned = in.replace('\\', '/');
    cleaned = Paths.get(cleaned).getFileName().toString(); // strip path components
    cleaned = cleaned.replaceAll("[^A-Za-z0-9._-]", "_");
    // collapse multiple underscores
    cleaned = cleaned.replaceAll("_+", "_");
    return cleaned.trim();
  }

  /**
   * Resolve a stored filename to an absolute, validated path inside the upload directory.
   * Throws NoSuchFileException if not found, SecurityException if path is outside root.
   */
  public Path loadAsPath(String storedFilename) throws IOException {
    if (storedFilename == null || storedFilename.isBlank()) {
      throw new IllegalArgumentException("Missing filename");
    }
    Path target = rootDir.resolve(storedFilename).normalize();
    if (!target.startsWith(rootDir)) {
      throw new SecurityException("Invalid path");
    }
    if (!Files.exists(target)) {
      throw new NoSuchFileException(target.toString());
    }
    return target;
  }

  public record StoredVideo(
      String id,
      String originalFilename,
      String storedFilename,
      Path path,
      long sizeBytes,
      String contentType
  ) {}
}
