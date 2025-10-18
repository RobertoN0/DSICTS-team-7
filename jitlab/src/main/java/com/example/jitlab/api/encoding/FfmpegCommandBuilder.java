package com.example.jitlab.api.encoding;

import java.util.ArrayList;
import java.util.List;

public class FfmpegCommandBuilder {

    public static List<String> buildSingle(String input, String output, String codec, String resolution, boolean gpu) {
        List<String> cmd = new ArrayList<>();

        cmd.add("ffmpeg");
        cmd.add("-y");
        cmd.add("-hide_banner");

        if (gpu) {
            cmd.add("-hwaccel");
            cmd.add("cuda");
            cmd.add("-hwaccel_output_format");
            cmd.add("cuda");
        }

        cmd.add("-i");
        cmd.add(input);

        String encoder = switch (codec.toLowerCase()) {
            case "h264" -> gpu ? "h264_nvenc" : "libx264";
            case "hevc", "h265" -> gpu ? "hevc_nvenc" : "libx265";
            case "av1" -> gpu ? "av1_nvenc" : "libaom-av1";
            case "vp9" -> "libvpx-vp9";
            default -> throw new IllegalArgumentException("Unsupported codec: " + codec);
        };

        // Scale filter based on GPU or CPU
        String scaleFilter = (gpu ? "scale_cuda=-2:" : "scale=-2:") + resolution.replace("p", "");
        cmd.add("-vf");
        cmd.add(scaleFilter);

        cmd.add("-c:v");
        cmd.add(encoder);
        cmd.add("-preset");
        cmd.add(gpu ? "p5" : "veryfast");

        // Rough bitrate per target resolution
        String res = resolution.replace("p", "");   
        String bitrate = switch (res) {
            case "1080" -> "6M";
            case "720" -> "3M";
            case "480" -> "2M";
            case "360" -> "1M";
            default -> "0.6M";
        };
        cmd.add("-b:v");
        cmd.add(bitrate);

        cmd.add("-c:a");
        cmd.add("aac");
        cmd.add("-b:a");
        cmd.add("128k");

        cmd.add(output);

        return cmd;
    }

    public static List<String> buildAdaptive(String input, String baseOutput, String codec, boolean gpu, String inputResolution) {
        List<String> cmd = new ArrayList<>();

        cmd.add("ffmpeg");
        cmd.add("-y");
        cmd.add("-hide_banner");

        if (gpu) {
            cmd.add("-hwaccel");
            cmd.add("cuda");
            cmd.add("-hwaccel_output_format");
            cmd.add("cuda");
        }

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

        // ---------- Decide which resolutions to generate ----------
        List<String> available = List.of("1080", "720", "480", "360");
        int startIdx = available.indexOf(inputResolution.replace("p", ""));
        if (startIdx == -1) startIdx = 0; // default to 1080 if not found
        List<String> toGenerate = available.subList(startIdx, available.size());

        // ---------- Build filter_complex ----------
        StringBuilder filter = new StringBuilder("[0:v]split=" + toGenerate.size());
        for (int i = 0; i < toGenerate.size(); i++) {
            filter.append("[v").append(i + 1).append("]");
        }
        filter.append(";");

        for (int i = 0; i < toGenerate.size(); i++) {
            String scaleCmd = gpu ? "scale_cuda=-2:" : "scale=-2:";
            filter.append("[v").append(i + 1).append("]")
                    .append(scaleCmd).append(toGenerate.get(i))
                    .append("[v").append(i + 1).append("o];");
        }

        cmd.add("-filter_complex");
        cmd.add(filter.toString());

        // ---------- Build output mappings ----------
        for (int i = 0; i < toGenerate.size(); i++) {
            String res = toGenerate.get(i);
            String outFile = baseOutput.replace(".mp4", "_" + res + "p.mp4");

            cmd.add("-map");
            cmd.add("[v" + (i + 1) + "o]");
            cmd.add("-c:v");
            cmd.add(encoder);
            if (gpu) {
                cmd.add("-preset");
                cmd.add("hq");
            } else {
                cmd.add("-preset");
                cmd.add("veryfast");
            }

            // Bitrate mapping
            String bitrate = switch (res) {
                case "1080" -> "6M";
                case "720" -> "3M";
                case "480" -> "2M";
                case "360" -> "1M";
                default -> "0.6M";
            };
            cmd.add("-b:v");
            cmd.add(bitrate);

            // Audio
            cmd.add("-c:a");
            cmd.add("aac");
            cmd.add("-b:a");
            cmd.add("128k");

            cmd.add(outFile);
        }

        return cmd;
    }
}
