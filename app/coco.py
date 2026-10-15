"""Run the separately licensed CocoScrapers adapter using bounded JSON IPC."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from app.integrations import ServiceError

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA256 = "f33b11e3fcc8967aeca65548398212ba7c806298845eac2e57ba38cd35a6436e"


class CocoProvider:
    def __init__(self):
        self.slots = threading.BoundedSemaphore(2)

    def search(self, title, season=None, episode=None):
        archive = ROOT / "vendor" / "cocoscrapers-1.0.32.zip"
        if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
            raise ServiceError("CocoScrapers is missing or damaged. Reinstall the application.", 503)
        if not self.slots.acquire(blocking=False):
            raise ServiceError("Source search is busy. Try again in a moment.", 429, 5)
        try:
            # Pass metadata only. The worker does not inherit service tokens or app settings.
            environment = {key: value for key, value in os.environ.items()
                           if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "LANG", "SSL_CERT_FILE"}}
            result = subprocess.run([sys.executable, "-I", str(ROOT / "coco_worker" / "worker.py")],
                input=json.dumps({"title": title, "season": season, "episode": episode}),
                text=True, capture_output=True, timeout=23, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
                raise ValueError("Invalid worker response")
            data = json.loads(result.stdout)
            if data.get("error"):
                raise ValueError("Worker did not start")
            return data
        except (subprocess.TimeoutExpired, OSError, ValueError):
            raise ServiceError("CocoScrapers could not finish. Try again or choose a file from your account.", 503) from None
        finally:
            self.slots.release()
