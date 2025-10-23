# tools/locustfile.py
from locust import HttpUser, task, between, events
import os
import random
from pathlib import Path

# Adjust path relative to this locustfile; this expects repository layout:
# repo/jitlab/tools/locustfile.py  -> videos folder at repo/jitlab/videos
VIDEO_DIR = Path(__file__).resolve().parents[1] / "videos"

# Defaults if CLI flags not provided
DEFAULT_CODECS = ["h264", "hevc", "av1"]
DEFAULT_RESOLUTIONS = ["360", "480", "720", "1080"]
DEFAULT_USE_GPU = ["false", "true"]

# Global config populated from CLI options via events.init
CONFIG = {
    "codec": None,
    "resolution": None,
    "use_gpu": None,
}


@events.init.add_listener
def _(environment, **kwargs):
    """Parse additional CLI args passed to locust.

    Usage example:
      locust -f tools/locustfile_encode.py --headless -u 3 -r 1 -t 3m --host http://localhost:8080 --codec h264 --resolution 1080 --use-gpu false
    """
    # locust exposes environment.parsed_options where custom args are available
    parsed = getattr(environment, "parsed_options", None)
    if parsed is None:
        return

    # These attributes will exist if passed as --codec/--resolution/--use-gpu
    # locust passes unknown args into parsed_options as attributes
    codec = getattr(parsed, "codec", None)
    resolution = getattr(parsed, "resolution", None)
    use_gpu = getattr(parsed, "use_gpu", None) or getattr(parsed, "use-gpu", None)

    CONFIG["codec"] = codec
    CONFIG["resolution"] = resolution
    CONFIG["use_gpu"] = use_gpu

    # If locust was launched without CLI flags but one_run passed env vars,
    # read them from environment here as fallback.
    if CONFIG["codec"] is None:
        CONFIG["codec"] = os.environ.get("LOCUST_CODEC")
    if CONFIG["resolution"] is None:
        CONFIG["resolution"] = os.environ.get("LOCUST_RESOLUTION")
    if CONFIG["use_gpu"] is None:
        CONFIG["use_gpu"] = os.environ.get("LOCUST_USE_GPU")


class EncodeUser(HttpUser):
    # wait time between tasks
    wait_time = between(0.5, 2)

    def on_start(self):
        # Build a list of videos once at start
        if not VIDEO_DIR.exists() or not VIDEO_DIR.is_dir():
            raise RuntimeError(f"Video directory not found: {VIDEO_DIR}")

        exts = {".mp4"}
        self.videos = [p for p in VIDEO_DIR.iterdir() if p.suffix.lower() in exts and p.is_file()]

        if not self.videos:
            raise RuntimeError(f"No videos found in {VIDEO_DIR}; add test videos before running Locust")

    @task
    def encode_video(self):
        # pick file
        video_path = random.choice(self.videos)

        # determine codec/resolution/use_gpu from CONFIG or fallback to random/defaults
        codec = CONFIG.get("codec") or random.choice(DEFAULT_CODECS)
        resolution = CONFIG.get("resolution") or random.choice(DEFAULT_RESOLUTIONS)
        use_gpu = CONFIG.get("use_gpu") or random.choice(DEFAULT_USE_GPU)

        data = {
            "codec": codec,
            "resolution": resolution,
            "useGpu": use_gpu
        }

        # Open file per request to avoid keeping big files in memory between tasks
        with open(video_path, "rb") as fh:
            files = {"file": (video_path.name, fh, "video/mp4")}
            with self.client.post("/encode/multi", files=files, data=data, catch_response=True, timeout=600) as resp:
                if resp.status_code != 200:
                    resp.failure(f"Unexpected status {resp.status_code}: {resp.text[:200]}")
                else:
                    try:
                        j = resp.json()
                        if not isinstance(j, dict):
                            resp.failure(f"Unexpected JSON response: {j}")
                    except Exception:
                        # if not JSON, skip the JSON check
                        pass