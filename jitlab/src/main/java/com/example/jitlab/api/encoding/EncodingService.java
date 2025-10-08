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

    public EncodingResult encode(MultipartFile file, EncodingRequest request) throws Exception {

        // Create temporary folder for encoded files if it doesn't exist
        Path projectRoot = Paths.get(System.getProperty("user.dir"));
        Path tmpDir = projectRoot.resolve("videos/tmp");
        Files.createDirectories(tmpDir);

        // Save the uploaded file temporarily in the tmp directory
        Path inputFile = tmpDir.resolve("input_" + System.currentTimeMillis() + ".mp4");
        file.transferTo(inputFile.toFile());

        // Define the name and path for the encoded output video
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

        // Execute ffmpeg as an external process
        long start = System.nanoTime();
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);
        Process proc = pb.start();

        // Wait for the encoding process to finish and measure duration
        int exitCode = proc.waitFor();
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        if (exitCode != 0) {
            throw new RuntimeException("FFmpeg failed with exit code: " + exitCode);
        }

        // Calculate output file size
        long outputSize = Files.size(outputFile);

        // Delete the temporary input file
        try {
            Files.deleteIfExists(inputFile);
        } catch (IOException ignored) {}

        // Build and return the result object for the controller
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
