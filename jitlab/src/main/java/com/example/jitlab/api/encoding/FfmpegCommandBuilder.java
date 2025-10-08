package com.example.jitlab.api.encoding;
import java.util.ArrayList;
import java.util.List;

public class FfmpegCommandBuilder {

    public static List<String> build(String input, String output, String codec, String resolution, boolean gpu) {
        List<String> cmd = new ArrayList<>();

        // Base command
        cmd.add("ffmpeg");
        cmd.add("-y"); 
        cmd.add("-hide_banner"); 

        // Input
        cmd.add("-i");
        cmd.add(input);

        // Encoder selection
        String encoder = switch (codec.toLowerCase()) {
            case "h264" -> gpu ? "h264_nvenc" : "libx264";
            case "hevc", "h265" -> gpu ? "hevc_nvenc" : "libx265";
            case "av1" -> gpu ? "av1_nvenc" : "libaom-av1";
            case "vp9" -> "libvpx-vp9";
            default -> throw new IllegalArgumentException("Unsupported codec: " + codec);
        };

        // Codec video
        cmd.add("-c:v");
        cmd.add(encoder);

        // Resolution
        cmd.add("-vf");
        cmd.add("scale=-2:" + resolution);

        // Bitrate
        cmd.add("-b:v");
        cmd.add("3M");

        // Output file
        cmd.add(output);

        return cmd;
    }
}
