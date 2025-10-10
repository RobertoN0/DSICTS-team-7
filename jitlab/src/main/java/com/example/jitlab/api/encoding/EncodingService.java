package com.example.jitlab.api.encoding;

import com.example.jitlab.api.dto.EncodingMetrics;
import com.example.jitlab.api.dto.EncodingRequest;
import com.example.jitlab.api.dto.EncodingResult;
import com.example.jitlab.api.dto.EncodingResultMulti;

import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.*;
import java.util.ArrayList;
import java.util.List;

@Service
public class EncodingService {

    /**
     * Base method: encodes a file received as MultipartFile
     */
    public EncodingResult encode(MultipartFile file, EncodingRequest request) throws Exception {

        Path projectRoot = Paths.get(System.getProperty("user.dir"));
        Path tmpDir = projectRoot.resolve("videos/tmp");
        Files.createDirectories(tmpDir);

        // Copy the uploaded file into a safe directory (outside Tomcat)
        Path inputFile = tmpDir.resolve("input_" + System.currentTimeMillis() + ".mp4");
        file.transferTo(inputFile.toFile());

        // Execute encoding starting from this file
        EncodingResult result = encodeFromPath(inputFile, request);

        // Remove the temporary source file
        try {
            Files.deleteIfExists(inputFile);
        } catch (IOException ignored) {}

        return result;
    }

    /**
     * Method for multi-encoding into multiple resolutions
     */
    public EncodingResultMulti encodeMulti(MultipartFile file, EncodingRequest request) throws Exception {

        List<String> resolutions = List.of("1080p", "720p", "480p", "360p");

        String inputRes = request.getResolution();
        int startIndex = resolutions.indexOf(inputRes);
        if (startIndex == -1) {
            throw new IllegalArgumentException("Unsupported input resolution: " + inputRes);
        }

        // Copy the file only once locally (outside Tomcat)
        Path projectRoot = Paths.get(System.getProperty("user.dir"));
        Path tmpDir = projectRoot.resolve("videos/tmp");
        Files.createDirectories(tmpDir);

        Path originalInput = tmpDir.resolve("multi_input_" + System.currentTimeMillis() + ".mp4");
        file.transferTo(originalInput.toFile());

        List<String> toEncode = resolutions.subList(startIndex, resolutions.size());
        List<EncodingMetrics> results = new ArrayList<>();

        // Each iteration now works on a stable local file
        for (String res : toEncode) {
            EncodingRequest subReq = new EncodingRequest();
            subReq.setCodec(request.getCodec());
            subReq.setResolution(res);
            subReq.setUseGpu(request.isUseGpu());

            EncodingResult result = encodeFromPath(originalInput, subReq);

            results.add(
                    EncodingMetrics.builder()
                            .resolution(res)
                            .elapsedMs(result.getElapsedMs())
                            .outputSizeBytes(result.getOutputSizeBytes())
                            .build()
            );
        }

        // (Optional) delete the source file after completion
        try {
            Files.deleteIfExists(originalInput);
        } catch (IOException ignored) {}

        return EncodingResultMulti.builder()
                .sourceResolution(inputRes)
                .gpu(request.isUseGpu())
                .metrics(results)
                .build();
    }

    /**
     * Internal method: performs encoding starting from an existing file on disk
     */
    public EncodingResult encodeFromPath(Path inputFile, EncodingRequest request) throws Exception {

        Path tmpDir = inputFile.getParent();

        // Define output file
        Path outputFile = tmpDir.resolve(
                "encoded_%s_%s_%d.mp4".formatted(
                        request.getCodec(),
                        request.getResolution(),
                        System.currentTimeMillis()
                )
        );

        // Build the ffmpeg command
        List<String> command = FfmpegCommandBuilder.build(
                inputFile.toString(),
                outputFile.toString(),
                request.getCodec(),
                request.getResolution(),
                request.isUseGpu()
        );

        // Execute ffmpeg
        long start = System.nanoTime();
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);
        Process proc = pb.start();
        int exitCode = proc.waitFor();
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        if (exitCode != 0) {
            throw new RuntimeException("FFmpeg failed with exit code: " + exitCode);
        }

        long outputSize = Files.size(outputFile);

        return EncodingResult.builder()
                .codec(request.getCodec())
                .resolution(request.getResolution())
                .gpu(request.isUseGpu())
                .elapsedMs(elapsedMs)
                .outputSizeBytes(outputSize)
                .outputPath(outputFile.toAbsolutePath().toString())
                .build();
    }
}
