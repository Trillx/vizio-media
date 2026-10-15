"""Profile-scoped source choices, Real-Debrid preparation, and byte-range relay.

Only server-issued choices can initiate playback. Private links stay in memory;
the player receives an authenticated same-origin stream URL. No transcoding.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from ipaddress import ip_address
import math
from pathlib import PurePosixPath
import re
import secrets
import socket
import threading
import time
from urllib.parse import quote, urljoin, urlsplit

import httpx
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from app.coco import CocoProvider
from app.integrations import ServiceError
from app.providers import DebridLibraryProvider, match_score

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mkv", ".avi", ".mov", ".ts", ".webm"}
FAILED = {"magnet_error", "error", "virus", "dead"}
ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
EPISODE_ID = re.compile(r"^(.*)-s([0-9]{1,3})-e([0-9]{1,4})$")


def format_hint(filename):
    name = filename.lower()
    quality = next((label for pattern, label in ((r"2160|4[ ._-]?k", "4K"), (r"1080", "1080p"), (r"720", "720p"))
                    if re.search(pattern, name)), "Unknown")
    warnings = []
    if re.search(r"hevc|[xh][ ._-]?265|10bit|10.bit|dolby[ ._-]?vision|hdr|\bdovi\b|\bdv\b", name):
        warnings.append("HEVC, HDR, or 10-bit video may not play on this TV")
    if re.search(r"dts|truehd|atmos", name):
        warnings.append("Audio may be unsupported")
    if PurePosixPath(name).suffix in {".mkv", ".avi", ".ts"}:
        warnings.append("Container support depends on the TV")
    preferred = bool(re.search(r"[xh][ ._-]?264|avc", name) and not warnings)
    return {"quality": quality, "warning": ". ".join(warnings), "preferred": preferred,
            "aac": bool(re.search(r"\baac\b", name))}


def source_rank(item):
    """Prefer the TV's verified formats before readiness, resolution, and size."""
    ready = item.get("provider") == "real_debrid_library" and item.get("status") in {"downloaded", "account download"}
    return (bool(item.get("warning")), not item.get("preferred", False), not item.get("aac", False), not ready,
            {"1080p":0,"720p":1,"Unknown":2,"4K":3}.get(item.get("quality"), 2),
            item.get("size") or 10**15, item.get("filename", "").casefold())


def recommended_file(files, choice):
    matching=[item for item in files[:100] if playable_file(item)
              and not re.search(r"(?:^|[/ ._-])(?:extras?|featurettes?|bonus|behind[ ._-]the[ ._-]scenes)(?:[/ ._-]|$)",
                                str(item.get("path", "")), re.I)
              and match_score(str(item.get("path", "")), choice.title, choice.season, choice.episode) >= .85]
    if not matching:
        return None
    ranked=sorted(matching,key=lambda item:source_rank({"filename":str(item.get("path","")),
        "size":-(item.get("bytes") or 0),**format_hint(str(item.get("path","")))}))
    return ranked[0]["id"]


def playable_file(item):
    name = str(item.get("path") or item.get("filename") or "")
    return (PurePosixPath(name.lower()).suffix in VIDEO_EXTENSIONS
            and not re.search(r"(?:^|[/ ._-])(?:sample|trailer)(?:[/ ._-]|$)", name, re.I))


def remote_id(value):
    if not isinstance(value, (str, int)) or not ID.fullmatch(str(value)):
        raise ServiceError("Real-Debrid returned an invalid file identifier.")
    return str(value)


def stream_url(value):
    """Only public HTTPS media endpoints obtained from Real-Debrid are usable."""
    if not isinstance(value, str) or len(value) > 8192:
        raise ServiceError("Real-Debrid returned an invalid stream address.")
    try:
        parts = urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.port not in (None, 443)):
            raise ValueError()
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError()
    except (ValueError, OSError):
        raise ServiceError("The media server address is unavailable or unsafe. Choose another source.", 502) from None
    return value


@dataclass
class Choice:
    profile: str
    owner: str
    title: dict
    season: int | None
    episode: int | None
    item: dict
    expires: float = field(default_factory=lambda: time.monotonic() + 1200)


@dataclass
class Viewing:
    choice: Choice
    id: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    torrent: str = ""
    file_id: int | None = None
    link: str = ""
    url: str = ""
    filename: str = ""
    expires: float = field(default_factory=lambda: time.monotonic() + 8 * 3600)
    resolved: float = 0
    next_poll: float = 0
    result: dict = field(default_factory=dict)
    media: dict = field(default_factory=dict)
    lock: object = field(default_factory=threading.RLock)

    @property
    def media_id(self):
        suffix = f"-s{self.choice.season}-e{self.choice.episode}" if self.choice.episode is not None else ""
        return self.choice.title["id"] + suffix


class Playback:
    def __init__(self, services, store, *, coco=None, transport=None):
        self.services, self.store = services, store
        self.coco = coco or CocoProvider(lambda: self.services.config("cocoscrapers"))
        self.choices, self.viewings = {}, {}
        self.lock = threading.RLock()
        self.searching = set()
        self.http = httpx.Client(transport=transport, trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(30, connect=8), limits=httpx.Limits(max_connections=6, max_keepalive_connections=2))
        self.streams = threading.BoundedSemaphore(4)

    def close(self):
        self.http.close()

    def invalidate(self, profile):
        with self.lock:
            self.choices = {key: value for key, value in self.choices.items() if value.profile != profile}
            self.viewings = {key: value for key, value in self.viewings.items() if value.choice.profile != profile}

    def prune(self):
        now = time.monotonic()
        self.choices = {key: value for key, value in self.choices.items() if value.expires > now}
        self.viewings = {key: value for key, value in self.viewings.items() if value.expires > now}

    def rd(self, profile, method, path, **kwargs):
        return self.services.authorized(profile, "real_debrid", method, path, **kwargs)

    def search(self, profile, owner, title, season=None, episode=None, discover=False):
        self.services.access(profile, "real_debrid")
        if title["kind"] == "tv" and episode is None and discover:
            raise ServiceError("Choose a season and episode before searching for sources.", 400)
        with self.lock:
            if profile in self.searching:
                raise ServiceError("A source search is already running for this profile.", 429, 5)
            self.searching.add(profile)
        notices, providers = [], {}
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                library = pool.submit(DebridLibraryProvider(self.services).search, profile, title, season, episode)
                public = pool.submit(self.coco.search, title, season, episode) if discover else None
                try:
                    items = library.result()
                except ServiceError as error:
                    items = []
                    notices.append("Account files: " + error.message)
                if public:
                    try:
                        scraped = public.result()
                        providers = scraped.get("providers", {})
                        hashes = set()
                        for raw in scraped.get("items", [])[:500]:
                            digest = str(raw.get("hash") or "").lower()
                            name = str(raw.get("name") or "")[:500]
                            if not re.fullmatch(r"[0-9a-f]{40}", digest) or digest in hashes or match_score(name, title, season, episode) < .7:
                                continue
                            hashes.add(digest)
                            size = float(raw.get("size") or 0)
                            items.append({"id": "coco-" + digest, "hash": digest, "kind": "magnet",
                                "provider": "cocoscrapers", "scraper": str(raw.get("provider", ""))[:40],
                                "filename": name, "size": int(size * 1024**3) if math.isfinite(size) and size > 0 else 0,
                                "status": "Availability checked when selected", "match_score": 1})
                        unavailable = [key for key, value in providers.items() if value in {"timeout", "unavailable"}]
                        if unavailable:
                            notices.append("Some providers could not be reached: " + ", ".join(unavailable) + ".")
                    except (ServiceError, ValueError, TypeError) as error:
                        notices.append(error.message if isinstance(error, ServiceError) else "Some source results could not be read.")
            items = [{**item, **format_hint(item["filename"])} for item in items]
            items.sort(key=source_rank)
            with self.lock:
                self.prune()
                if len(self.choices) > 1000:
                    self.choices.clear()
                for item in items[:100]:
                    token = secrets.token_urlsafe(24)
                    self.choices[token] = Choice(profile, owner, title, season, episode, dict(item))
                    item["selection_id"] = token
                    item.pop("hash", None)
                if items:
                    items[0]["recommended"] = True
            return {"items": items[:100], "provider": "cocoscrapers" if discover else "real_debrid_library",
                "providers": providers, "notice": " ".join(notices) or
                ("Choose a source to prepare it in Real-Debrid. H.264 with AAC is the safest starting point for this TV." if discover
                 else "Files from the first 100 downloads and 100 torrents in your Real-Debrid account.")}
        finally:
            with self.lock:
                self.searching.discard(profile)

    def start(self, profile, owner, selection_id):
        existing = None
        with self.lock:
            self.prune()
            choice = self.choices.get(selection_id)
            if not choice or choice.profile != profile or choice.owner != owner:
                raise ServiceError("This source choice expired. Search for sources again.", 404)
            # Repeated button presses reuse the same preparation and do not add duplicates.
            for viewing in self.viewings.values():
                if viewing.choice is choice:
                    existing = viewing
                    break
            if existing is None:
                if len(self.viewings) >= 100:
                    raise ServiceError("Too many playback sessions. Try again later.", 429)
                viewing = Viewing(choice)
                viewing.filename = choice.item["filename"]
                # Initialize before a second request can inspect this session.
                viewing.lock.acquire()
                self.viewings[viewing.id] = viewing
        if existing is not None:
            return self.status(profile, owner, existing.id)
        try:
            try:
                item = choice.item
                if item["kind"] == "magnet":
                    data = self.rd(profile, "POST", "/torrents/addMagnet", data={"magnet": "magnet:?xt=urn:btih:" + item["hash"]})
                    viewing.torrent = remote_id(data.get("id"))
                elif item["kind"] == "torrent":
                    viewing.torrent = remote_id(item["id"].removeprefix("rd-torrent-"))
                else:
                    identifier = item["id"].removeprefix("rd-download-")
                    entries = self.rd(profile, "GET", "/downloads", params={"page": 1, "limit": 100})
                    current = next((entry for entry in entries if str(entry.get("id")) == identifier), None)
                    if not current:
                        raise ServiceError("This account file is no longer available. Search again.", 404)
                    viewing.link = current.get("link") or current.get("download") or ""
                return self.status(profile, owner, viewing.id)
            finally:
                viewing.lock.release()
        except Exception:
            with self.lock:
                self.viewings.pop(viewing.id, None)
            raise

    def get(self, profile, owner, session):
        with self.lock:
            viewing = self.viewings.get(session)
            if not viewing or viewing.choice.profile != profile or viewing.choice.owner != owner or viewing.expires < time.monotonic():
                raise ServiceError("Playback session expired. Choose the source again.", 404)
        self.services.access(profile, "real_debrid")
        return viewing

    def status(self, profile, owner, session, file_id=None):
        viewing = self.get(profile, owner, session)
        with viewing.lock:
            if viewing.result.get("state") == "ready" and file_id is None:
                viewing.result["progress"] = self.store.playback(profile, viewing.media_id)
                return viewing.result
            if viewing.next_poll > time.monotonic() and file_id is None and viewing.result:
                return viewing.result
            files = []
            if viewing.torrent:
                info = self.rd(profile, "GET", "/torrents/info/" + viewing.torrent)
                state = info.get("status", "queued")
                if state in FAILED:
                    raise ServiceError("Real-Debrid could not prepare this source. Choose another source.", 409)
                files = [item for item in info.get("files", [])[:5000] if playable_file(item)]
                if viewing.choice.episode is not None:
                    files = [item for item in files if match_score(str(item.get("path", "")), viewing.choice.title,
                        viewing.choice.season, viewing.choice.episode) >= .7]
                if not files and state in {"downloaded", "waiting_files_selection"}:
                    raise ServiceError("No matching video file was found in this source. Choose another source.", 409)
                if file_id is not None:
                    selected = next((item for item in files if item.get("id") == file_id), None)
                    if not selected:
                        raise ServiceError("Choose a video file listed for this source.", 400)
                    if state == "waiting_files_selection":
                        self.rd(profile, "POST", "/torrents/selectFiles/" + viewing.torrent, data={"files": str(file_id)})
                    elif not selected.get("selected"):
                        raise ServiceError("This video is not selected in your existing torrent. Choose a selected file or another source.", 409)
                    viewing.file_id = file_id
                    viewing.filename = str(selected.get("path", "")).rsplit("/", 1)[-1][:500]
                if viewing.file_id is None and files and state in {"downloaded", "waiting_files_selection"}:
                    available = [item for item in files if state == "waiting_files_selection" or item.get("selected")]
                    # Never silently pick a different movie or episode from a pack.
                    if len(available) == 1:
                        selected = available[0]
                        return self.status(profile, owner, session, int(selected["id"]))
                    viewing.result = {"id": session, "state": "files", "files": [
                        {"id": int(item["id"]), "filename": str(item.get("path", ""))[:500],
                         "size": item.get("bytes", 0), **format_hint(str(item.get("path", "")))} for item in available[:100]],
                        "recommended_file_id": recommended_file(available, viewing.choice),
                        "message": "Choose the video file to watch."}
                    return viewing.result
                if state != "downloaded":
                    percent = info.get("progress", 0)
                    percent = max(0, min(100, float(percent))) if isinstance(percent, (int, float)) and math.isfinite(percent) else 0
                    viewing.result = {"id": session, "state": "preparing", "progress": percent, "retry_after": 3,
                        "message": "Real-Debrid is preparing this source. You can wait or go back and choose another."}
                    viewing.next_poll = time.monotonic() + 3
                    return viewing.result
                selected_files = [item for item in info.get("files", []) if item.get("selected")]
                index = next((index for index, item in enumerate(selected_files) if item.get("id") == viewing.file_id), -1)
                links = info.get("links", [])
                if index < 0 or len(selected_files) != len(links):
                    raise ServiceError("This torrent uses split links that cannot be played directly. Choose another source.", 409)
                viewing.link = links[index]
            self.resolve(viewing)
            return viewing.result

    def resolve(self, viewing):
        if not isinstance(viewing.link, str) or not viewing.link.startswith("https://") or len(viewing.link) > 8192:
            raise ServiceError("This source does not have a usable Real-Debrid link.", 409)
        data = self.rd(viewing.choice.profile, "POST", "/unrestrict/link", data={"link": viewing.link})
        if not isinstance(data, dict):
            raise ServiceError("This source contains several downloads. Choose another source.", 409)
        viewing.url = stream_url(data.get("download"))
        viewing.filename = str(data.get("filename") or viewing.filename)[:500]
        viewing.resolved = time.monotonic()
        if not viewing.media:
            viewing.media = {"checked": False, "video": [], "audio": []}
            identifier = data.get("id")
            if isinstance(identifier, str) and ID.fullmatch(identifier):
                try:
                    info = self.rd(viewing.choice.profile, "GET", "/streaming/mediaInfos/" + identifier)
                    details = info.get("details") or {}
                    for kind in ("video", "audio"):
                        streams = details.get(kind) or {}
                        if isinstance(streams, dict):
                            viewing.media[kind] = list(dict.fromkeys(str(item.get("codec", ""))[:40].lower()
                                for item in list(streams.values())[:20] if isinstance(item, dict) and item.get("codec")))
                    viewing.media["checked"] = bool(viewing.media["video"])
                except (ServiceError, AttributeError, TypeError):
                    pass  # RD may not have indexed media information for this file.
        hints = format_hint(viewing.filename)
        codec_warnings = []
        if any(codec not in {"h264", "avc", "avc1"} for codec in viewing.media["video"]):
            codec_warnings.append("Video codec has not been verified on this TV")
        if any(codec not in {"aac", "mp3"} for codec in viewing.media["audio"]):
            codec_warnings.append("Audio codec may not play on this TV")
        hints["warning"] = ". ".join(filter(None, [hints["warning"], *codec_warnings]))
        viewing.result = {"id": viewing.id, "state": "ready", "title_id": viewing.media_id,
            "title": viewing.choice.title["title"] + (f" / S{viewing.choice.season:02} E{viewing.choice.episode:02}" if viewing.choice.episode is not None else ""),
            "filename": viewing.filename, "stream": "/api/playback/" + viewing.id + "/stream",
            "progress": self.store.playback(viewing.choice.profile, viewing.media_id),
            "media": viewing.media, **hints}

    def stop(self, profile, owner, session):
        self.get(profile, owner, session)
        with self.lock:
            self.viewings.pop(session, None)
        # Remote files belong to the account. Stopping playback never deletes them.
        return {"stopped": True}

    def relay(self, profile, owner, session, method="GET", range_header=None):
        viewing = self.get(profile, owner, session)
        if not self.streams.acquire(blocking=False):
            raise ServiceError("Too many active video connections. Try again shortly.", 429, 3)
        response = None
        try:
            with viewing.lock:
                if not viewing.url:
                    raise ServiceError("This video is not ready yet.", 409)
                if time.monotonic() - viewing.resolved > 3 * 3600:
                    self.resolve(viewing)
                url = viewing.url
            headers = {"Accept-Encoding": "identity"}
            if range_header:
                if not re.fullmatch(r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)", range_header) or len(range_header) > 100:
                    return Response(status_code=416, headers={"Accept-Ranges": "bytes"})
                headers["Range"] = range_header
            for attempt in range(2):
                for redirect in range(4):
                    stream_url(url)
                    request = self.http.build_request(method, url, headers=headers)
                    response = self.http.send(request, stream=True)
                    if not response.is_redirect:
                        break
                    url = urljoin(url, response.headers.get("location", ""))
                    response.close()
                else:
                    raise ServiceError("The media server redirected too many times.")
                if response.status_code not in {401, 403, 404, 410} or attempt:
                    break
                response.close()
                with viewing.lock:
                    self.resolve(viewing)
                    url = viewing.url
            if response.status_code == 416:
                result = Response(status_code=416, headers={"Content-Range": response.headers.get("content-range", "bytes */*")})
                response.close()
                return result
            if response.status_code not in {200, 206}:
                raise ServiceError("The media server could not send this video. Go back and choose another source.", 502)
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"video/mp4", "video/x-matroska", "video/webm", "video/mp2t", "video/quicktime", "video/x-msvideo", "application/octet-stream", "binary/octet-stream", "application/force-download", "application/x-force-download", "application/download", ""}:
                raise ServiceError("The media server returned a page instead of video. Choose another source.", 502)
            outgoing = {key: response.headers[key] for key in ("content-length", "content-range", "accept-ranges") if key in response.headers}
            outgoing["Cache-Control"] = "no-store"
            mime = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mkv": "video/x-matroska", ".webm": "video/webm", ".ts": "video/mp2t", ".mov": "video/quicktime", ".avi": "video/x-msvideo"}.get(PurePosixPath(viewing.filename.lower()).suffix, content_type or "application/octet-stream")
            if method == "HEAD":
                result = Response(status_code=response.status_code, headers=outgoing, media_type=mime)
                response.close()
                return result
            upstream = response
            released = False
            release_lock = threading.Lock()

            def finish():
                nonlocal released
                with release_lock:
                    if not released:
                        released = True
                        upstream.close()
                        self.streams.release()

            def chunks():
                try:
                    yield from upstream.iter_raw(256 * 1024)
                finally:
                    finish()

            result = StreamingResponse(chunks(), status_code=upstream.status_code, headers=outgoing,
                media_type=mime, background=BackgroundTask(finish))
            response = None
            return result
        except httpx.HTTPError:
            raise ServiceError("The video connection failed. Choose the source again to retry.", 503) from None
        finally:
            if response is not None:
                response.close()
            # Streaming responses own the semaphore until their background cleanup.
            if response is not None or 'result' not in locals() or not isinstance(result, StreamingResponse):
                self.streams.release()
