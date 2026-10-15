"""Controlled Coco/RD/CDN fixtures shared by integration and browser checks."""

from pathlib import Path
from urllib.parse import parse_qs
import re

import httpx

from test_accounts_catalog import Cloud


class FakeCoco:
    def search(self, title, season=None, episode=None):
        marker = f"S{season:02}E{episode:02}" if episode is not None else title.get("year", "2020")
        name = title["title"].replace(" ", ".") + f".{marker}.1080p.H264.AAC.mp4"
        return {"items": [{"hash": "a" * 40, "name": name, "provider": "torrentio", "size": 1.2},
                          {"hash": "a" * 40, "name": name, "provider": "bitsearch", "size": 1.2},
                          {"hash": "b" * 40, "name": "Unrelated.2019.mp4", "provider": "bitsearch"}],
                "providers": {"torrentio": "ok", "bitsearch": "ok"}}


class PlaybackCloud(Cloud):
    def __init__(self):
        super().__init__()
        self.added = 0
        self.selected = [20]
        self.pack = False
        self.state = "waiting_files_selection"
        self.unrestricts = 0
        self.private_url = "https://media.example.com/PRIVATE-SIGNED-LINK/video.mp4"
        self.last_link = None
        self.playback_calls = []
        self.filename = "A.Test.Film.2020.1080p.H264.AAC.mp4"
        self.video_codec = "h264"
        self.audio_codec = "aac"

    def __call__(self, request):
        path = request.url.path
        if "/streaming/mediaInfos/" in path:
            return httpx.Response(200, json={"details": {"video": {"und1": {"codec": self.video_codec}},
                "audio": {"eng1": {"codec": self.audio_codec}}}, "link": "PRIVATE-ORIGINAL-LINK"})
        if "/torrents/info/" in path:
            self.playback_calls.append(request)
            files = [{"id": 10, "path": "/readme.txt", "selected": int(10 in self.selected), "bytes": 12},
                     {"id": 20, "path": "/" + self.filename, "selected": int(20 in self.selected), "bytes": 123456}]
            if self.pack:
                files.append({"id": 30, "path": "/A.Test.Film.2020.Alternate.1080p.mp4", "selected": int(30 in self.selected), "bytes": 555555})
            return httpx.Response(200, json={"id": "torrent-1", "status": self.state, "progress": 42,
                "files": files, "links": [f"https://real-debrid.com/d/FILE-{item['id']}" for item in files if item["selected"]]})
        if path.endswith("/torrents/addMagnet"):
            self.playback_calls.append(request)
            self.added += 1
            return httpx.Response(201, json={"id": "torrent-1"})
        if "/torrents/selectFiles/" in path:
            self.playback_calls.append(request)
            self.selected = [int(parse_qs(request.content.decode())["files"][0])]
            self.state = "downloaded"
            return httpx.Response(204)
        if path.endswith("/unrestrict/link"):
            self.playback_calls.append(request)
            self.unrestricts += 1
            self.last_link = parse_qs(request.content.decode())["link"][0]
            return httpx.Response(200, json={"id": "download-1", "download": self.private_url,
                "filename": self.filename, "filesize": 123456, "mimeType": "video/mp4"})
        return super().__call__(request)


def media_response(request, data):
    assert "authorization" not in request.headers
    assert "cookie" not in request.headers
    assert "referer" not in request.headers
    headers = {"content-type": "video/mp4", "accept-ranges": "bytes", "content-length": str(len(data))}
    status = 200
    if request.headers.get("range"):
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", request.headers["range"])
        start = int(match[1]) if match[1] else max(0, len(data) - int(match[2]))
        end = min(len(data) - 1, int(match[2])) if match[1] and match[2] else len(data) - 1
        if start >= len(data):
            return httpx.Response(416, headers={"content-range": f"bytes */{len(data)}"})
        headers.update({"content-range": f"bytes {start}-{end}/{len(data)}", "content-length": str(end - start + 1)})
        data = data[start:end + 1]
        status = 206
    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(b"" if request.method == "HEAD" else data))
