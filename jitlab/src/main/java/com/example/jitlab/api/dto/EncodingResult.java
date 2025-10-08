package com.example.jitlab.api.dto;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class EncodingResult {
    private String codec;
    private String resolution;
    private boolean gpu;
    private long elapsedMs;
    private long outputSizeBytes;
    private String outputPath;
}
