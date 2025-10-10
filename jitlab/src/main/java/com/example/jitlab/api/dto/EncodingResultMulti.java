package com.example.jitlab.api.dto;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class EncodingResultMulti {
    private String sourceResolution;
    private boolean gpu;
    private List<EncodingMetrics> metrics;
}
