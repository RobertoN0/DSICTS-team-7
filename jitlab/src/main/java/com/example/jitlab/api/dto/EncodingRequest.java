package com.example.jitlab.api.dto;
import lombok.Data;

@Data
public class EncodingRequest {
    private String codec;           // Video codec (e.g., "h264", "hevc")
    private String resolution;      // Video resolution (e.g., "1080p", "720p")
    private boolean useGpu;         // Use GPU acceleration
}
