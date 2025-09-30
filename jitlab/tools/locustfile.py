"""Locust test scenario that models video playback sessions and uploads.

Usage:
  pip install locust
  locust -f tools/locustfile.py --host=http://localhost:8080

Open http://localhost:8089 to configure virtual users and start the test.
"""
from locust import HttpUser, task, between
import random
import os
import glob

# Config via environment variables (optional)
STORED_ENV = os.getenv('STORED_FILE')
VIDEOS_DIR = os.getenv('VIDEOS_DIR', os.path.join(os.path.dirname(__file__), '..', 'videos'))


class VideoUser(HttpUser):
    # shorter wait_time so users perform actions frequently; tune as needed
    wait_time = between(0.5, 1.5)

    def on_start(self):
        # pick a storedFilename to play; prefer env var, otherwise random from videos/
        if STORED_ENV:
            self.stored = STORED_ENV
            return

        try:
            pattern = os.path.join(VIDEOS_DIR, '*')
            files = [os.path.basename(p) for p in glob.glob(pattern) if os.path.isfile(p)]
            if files:
                self.stored = random.choice(files)
            else:
                self.stored = 'video.mp4'
        except Exception:
            self.stored = 'video.mp4'

    @task(5)
    def playback_session(self):
        """Weighted playback task: HEAD + several range GETs."""
        try:
            self.client.head(f"/videos/{self.stored}")
        except Exception:
            pass

        chunk_size = random.choice([256*1024, 512*1024, 1024*1024])
        chunks_to_fetch = random.randint(3, 20)

        total = 0
        try:
            r = self.client.head(f"/videos/{self.stored}")
            total = int(r.headers.get('Content-Length') or 0)
        except Exception:
            total = 0

        if total <= 0:
            try:
                self.client.get(f"/videos/{self.stored}")
            except Exception:
                pass
            return

        start = random.randint(0, max(0, total - 1))
        for i in range(chunks_to_fetch):
            if start >= total:
                break
            end = min(start + chunk_size - 1, total - 1)
            headers = {"Range": f"bytes={start}-{end}"}
            try:
                self.client.get(f"/videos/{self.stored}", headers=headers)
            except Exception:
                pass

            if random.random() < 0.05:
                start = random.randint(0, max(0, total - 1))
            else:
                start = end + 1

    @task(1)
    def upload_task(self):
        """Weighted upload task: posts a random file from videos/ to /videos/upload."""
        try:
            pattern = os.path.join(VIDEOS_DIR, '*')
            files = [p for p in glob.glob(pattern) if os.path.isfile(p)]
            if not files:
                return
            path = random.choice(files)
            fname = os.path.basename(path)
            with open(path, 'rb') as fh:
                files_payload = {'file': (fname, fh, 'video/mp4')}
                try:
                    self.client.post('/videos/upload', files=files_payload, timeout=120)
                except Exception:
                    pass
        except Exception:
            pass
