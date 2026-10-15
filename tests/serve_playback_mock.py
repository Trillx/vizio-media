"""Isolated full playback browser fixture. No household credentials or data."""

from pathlib import Path
import sys
import tempfile

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.main import create_app
import app.playback as playback_module
from playback_fixtures import FakeCoco, PlaybackCloud, media_response


class BrowserPlaybackCloud(PlaybackCloud):
    def __call__(self, request):
        if request.url.path in {"/t/p/w342/art.jpg", "/t/p/w780/wide.jpg"}:
            return httpx.Response(200, content=(ROOT / "web/art/hero.jpg").read_bytes(), headers={"Content-Type": "image/jpeg"})
        return super().__call__(request)


if __name__ == "__main__":
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="browser-playback-", dir=ROOT / ".tmp") as directory:
        cloud = BrowserPlaybackCloud()
        data = (ROOT / "media/sample.mp4").read_bytes()
        # Only the fixture's one artificial CDN is permitted in this test process.
        def fixture_url(value):
            if value != cloud.private_url:
                raise ValueError("Unknown fixture URL")
            return value
        playback_module.stream_url = fixture_url
        app = create_app(Settings(bind_ip="127.0.0.1", port=8768, data_dir=Path(directory), media_dir=ROOT / "media"),
            transport=httpx.MockTransport(cloud), coco=FakeCoco(),
            media_transport=httpx.MockTransport(lambda request: media_response(request, data)))
        app.state.services.configure("tmdb", {"read_token": "TMDB-READ-SECRET"})
        app.state.services.personal_token("household", "PRIVATE-RD-API-TOKEN")
        uvicorn.run(app, host="127.0.0.1", port=8768, proxy_headers=False, access_log=False)
