package com.example.jitlab.api.dto;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class EncodingResult {
    private long elapsedMs;
    private long outputSizeBytes;
}
