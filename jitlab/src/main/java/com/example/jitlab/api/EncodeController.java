package com.example.jitlab.api;

import com.example.jitlab.api.dto.*;
import com.example.jitlab.api.encoding.EncodingService;

import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequiredArgsConstructor
@RequestMapping("/encode")
public class EncodeController {

    private final EncodingService encodingService;

    /* Single-resolution encoding */
    @PostMapping(consumes = "multipart/form-data", produces = "application/json")
    public ResponseEntity<?> encodeVideo(
            @RequestPart("file") MultipartFile file,
            @ModelAttribute EncodingRequest request) {
        try {
            // Process single-resolution encoding
            EncodingResult result = encodingService.encode(file, request);
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            e.printStackTrace();
            return ResponseEntity.internalServerError().body(e.getMessage());
        }
    }

    /* Multi-resolution encoding */
    @PostMapping(value = "/multi", consumes = "multipart/form-data", produces = "application/json")
    public ResponseEntity<?> encodeVideoMulti(
            @RequestPart("file") MultipartFile file,
            @ModelAttribute EncodingRequest request) {
        try {
            // Process multi-resolution encoding
            var results = encodingService.encodeMulti(file, request);
            return ResponseEntity.ok(results);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(e.getMessage());
        }
    }
}
