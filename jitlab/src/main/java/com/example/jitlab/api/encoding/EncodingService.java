package com.example.jitlab.api.encoding;

import com.example.jitlab.api.dto.EncodingRequest;
import com.example.jitlab.api.dto.EncodingResult;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.*;
import java.util.List;

@Service
public class EncodingService {

    // Single-resolution encode, returns elapsed time and output size only
    public EncodingResult encode(MultipartFile file, EncodingRequest request) throws Exception {
        Path projectRoot = Paths.get(System.getProperty("user.dir"));
        Path tmpDir = projectRoot.resolve("videos/tmp");
        Files.createDirectories(tmpDir);

        //Path inputFile = tmpDir.resolve("input_" + System.currentTimeMillis() + ".mp4");
        String timestamp = String.valueOf(System.currentTimeMillis());
        Path inputFile = Files.createTempFile("input_" + timestamp + "_", ".mp4");
        file.transferTo(inputFile.toFile());

        Path outputFile = tmpDir.resolve(
                "encoded_%s_%s_%d.mp4".formatted(
                        request.getCodec(),
                        request.getResolution(),
                        System.currentTimeMillis()
                )
        );

        List<String> command = FfmpegCommandBuilder.buildSingle(
                inputFile.toString(),
                outputFile.toString(),
                request.getCodec(),
                request.getResolution(),
                request.isUseGpu()
        );

        long start = System.nanoTime();
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);
        Process proc = pb.start();
        int exitCode = proc.waitFor();
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        if (exitCode != 0) {
            throw new RuntimeException("FFmpeg single encode failed with exit code: " + exitCode);
        }

        long outputSize = Files.size(outputFile);

        try { Files.deleteIfExists(inputFile); } catch (IOException ignored) {}

        return EncodingResult.builder()
                .elapsedMs(elapsedMs)
                .outputSizeBytes(outputSize)
                .build();
    }

    // Adaptive multi-resolution encode; returns elapsed time and the sum of all output sizes
    public EncodingResult encodeMulti(MultipartFile file, EncodingRequest request) throws Exception {
        Path projectRoot = Paths.get(System.getProperty("user.dir"));
        Path tmpDir = projectRoot.resolve("videos/tmp");
        Files.createDirectories(tmpDir);

        //Path inputFile = tmpDir.resolve("multi_input_" + System.currentTimeMillis() + ".mp4");
        String timestamp = String.valueOf(System.currentTimeMillis());
        Path inputFile = Files.createTempFile("multi_input_" + timestamp + "_", ".mp4");
        file.transferTo(inputFile.toFile());

        String baseOutput = tmpDir.resolve("encoded_multi_" + System.currentTimeMillis() + ".mp4").toString();

        List<String> command = FfmpegCommandBuilder.buildAdaptive(
                inputFile.toString(),
                baseOutput,
                request.getCodec(),
                request.isUseGpu(),
                request.getResolution()
        );

        long start = System.nanoTime();
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);
        Process proc = pb.start();
            
        //StringBuilder ffmpegOutput = new StringBuilder();
        //try (var reader = new java.io.BufferedReader(new java.io.InputStreamReader(proc.getInputStream()))) {
        //    String line;
        //    while ((line = reader.readLine()) != null) {
        //        ffmpegOutput.append(line).append("\n");
        //    }
        //}

        int exitCode = proc.waitFor();
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        if (exitCode != 0) {
            //System.err.println("==== FFmpeg command failed ====");
            //System.err.println(String.join(" ", command));
            //System.err.println("---- FFmpeg output ----");
            //System.err.println(ffmpegOutput);
            //System.err.println("------------------------");
            throw new RuntimeException("FFmpeg failed with exit code: " + exitCode);
        }


        // Sum sizes of all generated outputs (best-effort over common ladder)
        long totalBytes = 0L;
        for (String res : List.of("1080", "720", "480", "360", "240")) {
            Path outFile = Paths.get(baseOutput.replace(".mp4", "_" + res + "p.mp4"));
            if (Files.exists(outFile)) {
                totalBytes += Files.size(outFile);
            }
        }

        try { Files.deleteIfExists(inputFile); } catch (IOException ignored) {}

        return EncodingResult.builder()
                .elapsedMs(elapsedMs)
                .outputSizeBytes(totalBytes)
                .build();
    }
}
