<h1 align="center">Video Transcoding Sustainability Study</h1>

<p align="center">
  <strong>What does a JVM warm-up setting cost, in watts, at the scale of a video platform?</strong>
</p>

<p align="center">
  An energy and carbon study of GPU video transcoding across JVM JIT compilation profiles, measured
  under sustained load against a Spring Boot transcoding server and extrapolated to the daily
  footprint of a commercial video service. Group 7, Designing Sustainable ICT Systems, TU Delft.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Field-green%20software-1F5673?style=flat-square" alt="Green software">
  <img src="https://img.shields.io/badge/Method-controlled%20energy%20measurement-1F5673?style=flat-square" alt="Controlled energy measurement">
  <img src="https://img.shields.io/badge/License-MIT-2C6248?style=flat-square" alt="MIT License">
</p>

<p align="center">
  <a href="final_report/"><strong>Final report</strong></a> ·
  <a href="plots/">Plots</a> ·
  <a href="jitlab/">Experiment harness</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Java-3D4453?style=flat-square&logo=openjdk&logoColor=white" alt="Java">
  <img src="https://img.shields.io/badge/Spring%20Boot-3D4453?style=flat-square&logo=springboot&logoColor=white" alt="Spring Boot">
  <img src="https://img.shields.io/badge/FFmpeg-3D4453?style=flat-square&logo=ffmpeg&logoColor=white" alt="FFmpeg">
  <img src="https://img.shields.io/badge/NVENC-3D4453?style=flat-square&logo=nvidia&logoColor=white" alt="NVENC">
  <img src="https://img.shields.io/badge/Locust-3D4453?style=flat-square" alt="Locust">
  <img src="https://img.shields.io/badge/Python-3D4453?style=flat-square&logo=python&logoColor=white" alt="Python">
</p>

---

## Experiment Files
We here document our repository structure and main files used for the experiment.

The following diagram is a summary of the experiment workflow and used scripts, together with their role in the run.
![Experiment Workflow](resources/experiment_flow_diagram.png)

As other important code files we consider:

- Server Side:
    - [`EncodeController.java`](jitlab/src/main/java/com/example/jitlab/api/EncodeController.java): server's controller that exposes the endpoint for a video transcoding request.
    - [`FfmpegCommandBuilder`](jitlab/src/main/java/com/example/jitlab/api/encoding/FfmpegCommandBuilder.java): responsible for contructing the appropriate ffmpeg command based on input parameters
    - [`EncodingService.java`](jitlab/src/main/java/com/example/jitlab/api/encoding/EncodingService.java): resposible for execution of ffmpeg commands

- Tools and scripts:
    - [`one_run_ffmpeg.py`](jitlab/tools/one_run_ffmpeg.py): script used to monitor a single ffmpeg run
    - [`run_ffmpeg_speed.sh`](jitlab/run_ffmpeg_speed.sh): script used to obtain average transcoding speed and power with GPU
    - [`plots_scripts`](jitlab/tools/plots_scripts/main.py): python module used to create comparison diagrams available in [/plots](plots/h264_GPU)

- Results:
    - Main experimental results are stored in [`/results`](jitlab/results/), which contains:
        - `h264-gpu/` → 7 JIT compiler profiles (baseline, c1-only, c2-only, interpret, heap, low-threshold, double-thread);
        - `hevc-gpu/` → baseline profile;
        - `av1-gpu/` → baseline profile.
    - Retrieved Carbon Intensity Factors can be found in [/emission-data](jitlab/emission-data)

---

## How to run

Before running, make sure to have executed a `sudo` command in the launching terminal to insert the password, beacause it is then used authomatically by the monitoring scripts. 

To recreate the experiment, you have to run the [`run_profile.sh`](jitlab/run_profiles.sh) script specifying the necessary parameters. To run what we did use the following command:

```bash
./run_profiles.sh -- --monitor-sudo --runSec 180 --timeout 90 --numberOfRepetitions 30 --warmupSec 90  --codec h264 --resolution 1080 --use-gpu true
```

Make sure to have the python dependencies installed on your local machine or on a virtual enviroment with:
```bash
pip install requirements.txt
```

FFmpeg must be installed and accessible from the command line.
```bash
ffmpeg --version
```
In order to reproduce our experiment the video we used can be found at: https://www.youtube.com/watch?v=iHdviZkM7S4

GPU-accelerated transcoding (--use-gpu true) is only supported on NVIDIA GPUs with NVENC hardware encoder support.
