package com.example.jitlab.api.dto;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class EncodingMetrics {
    private String resolution;
    private long elapsedMs;
    private long outputSizeBytes;
}

