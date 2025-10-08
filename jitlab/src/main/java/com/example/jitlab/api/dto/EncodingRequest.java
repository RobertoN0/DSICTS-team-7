package com.example.jitlab.api.dto;
import lombok.Data;

@Data
public class EncodingRequest {
    private String codec;
    private String resolution;
    private boolean useGpu;
}
