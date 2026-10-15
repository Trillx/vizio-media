# SPDX-License-Identifier: GPL-3.0-only
"""JSON stdin/stdout adapter for an unmodified, pinned CocoScrapers archive.

This process receives title metadata only. It never receives account credentials.
Kodi UI/settings/storage helpers are replaced with local compatibility modules.
"""

import importlib
import json
import os
from pathlib import Path
import queue
import socket
import sys
import threading
import time
import types
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit

import httpx

ARCHIVE = Path(__file__).resolve().parents[1] / "vendor" / "cocoscrapers-1.0.32.zip"
PROVIDERS = ("torrentio", "bitsearch", "eztv")
_local = threading.local()


class Window:
    def __init__(self):
        self.values = {}

    def getProperty(self, key):
        return self.values.get(key, "")

    def setProperty(self, key, value):
        self.values[key] = value

    def clearProperty(self, key):
        self.values.pop(key, None)


def install_helpers():
    control = types.ModuleType("cocoscrapers.modules.control")
    defaults = {"filter.undesirables": "false", "filter.foreign.single.audio": "false",
                "torrentio.bypass_filter": "false"}
    control.setting = lambda key, fallback=None: defaults.get(key, fallback or "false")
    control.setSetting = lambda *args: None
    control.homeWindow = Window()
    control.sleep = lambda milliseconds: time.sleep(min(2, milliseconds / 1000))
    # The two SQLite-dependent Kodi modules are never loaded by this worker.
    cache = types.ModuleType("cocoscrapers.modules.cache")
    cache.get = lambda function, hours, *args, **kwargs: function(*args, **kwargs)
    cache.remove = lambda *args: None
    undesirables = types.ModuleType("cocoscrapers.modules.undesirables")
    undesirables.Undesirables = type("Undesirables", (), {"get_enabled": lambda self: []})
    logs = types.ModuleType("cocoscrapers.modules.log_utils")

    def log(message="", *args, **kwargs):
        if "Exception:" in str(message):
            _local.failed = True

    logs.log = log
    logs.error = lambda *args, **kwargs: setattr(_local, "failed", True)
    for name in ("LOGDEBUG", "LOGINFO", "LOGWARNING", "LOGERROR", "LOGNOTICE"):
        setattr(logs, name, 0)
    for module in (control, cache, undesirables, logs):
        sys.modules[module.__name__] = module
    sys.path.insert(0, str(ARCHIVE) + "/script.module.cocoscrapers/lib")
    # Upstream package initializers enumerate a real Kodi directory. Provider
    # modules themselves can be imported unchanged directly from the ZIP.
    for suffix in ("sources_cocoscrapers", "sources_cocoscrapers.torrents"):
        package = types.ModuleType("cocoscrapers." + suffix)
        package.__path__ = [str(ARCHIVE) + "/script.module.cocoscrapers/lib/cocoscrapers/" + suffix.replace(".", "/")]
        sys.modules[package.__name__] = package


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("Provider returned an unsafe URL")
    addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Provider returned a local address")


def network_request(url, output="", timeout=8, post=None, headers=None, **kwargs):
    """Bounded HTTPS transport. Never solves access challenges or disables TLS."""
    try:
        with httpx.Client(timeout=min(10, float(timeout)), trust_env=False, follow_redirects=False) as http:
            for _ in range(4):
                public_url(url)
                with http.stream("POST" if post else "GET", url, data=post,
                                 headers={"User-Agent": "Mozilla/5.0", **(headers or {})}) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes(65536):
                        body.extend(chunk)
                        if len(body) > 5 * 1024 * 1024:
                            raise ValueError("Provider response too large")
                    text = body.decode(response.encoding or "utf-8", errors="replace")
                    if output == "extended":
                        return text, str(response.status_code), dict(response.headers), dict(response.headers), ""
                    return bytes(body) if kwargs.get("as_bytes") else text
            raise ValueError("Too many provider redirects")
    except Exception:
        _local.failed = True
        return None


def run_search(payload, request=None):
    install_helpers()
    client = importlib.import_module("cocoscrapers.modules.client")
    client.request = request or network_request
    title = payload["title"]
    ids = title.get("ids") or {}
    data = {"title": title["title"], "year": str(title.get("year") or "0"),
            "imdb": ids.get("imdb_id") or ids.get("imdb") or "", "aliases": []}
    episodic = payload.get("episode") is not None
    if episodic:
        data.update(tvshowtitle=title["title"], season=str(payload["season"]), episode=str(payload["episode"]))
    requested = [name for name in payload.get("providers", PROVIDERS) if name in PROVIDERS]
    results = queue.Queue()

    def scrape(name):
        _local.failed = False
        try:
            provider = importlib.import_module("cocoscrapers.sources_cocoscrapers.torrents." + name).source()
            if not episodic and not provider.hasMovies:
                results.put((name, [], "skipped"))
                return
            if name == "torrentio" and not data["imdb"]:
                results.put((name, [], "missing_imdb"))
                return
            items = provider.sources(dict(data), {}) or []
            results.put((name, items[:250], "unavailable" if _local.failed else "ok"))
        except Exception:
            results.put((name, [], "unavailable"))

    for name in requested:
        threading.Thread(target=scrape, args=(name,), daemon=True).start()
    deadline = time.monotonic() + 18
    found, statuses = [], {}
    while len(statuses) < len(requested) and time.monotonic() < deadline:
        try:
            name, items, status = results.get(timeout=max(.01, deadline - time.monotonic()))
            statuses[name] = status
            found.extend(items)
        except queue.Empty:
            break
    for name in requested:
        statuses.setdefault(name, "timeout")
    normalized = [{"name": str(item.get("name", ""))[:500], "hash": str(item.get("hash", ""))[:80],
                   "provider": str(item.get("provider", ""))[:40], "quality": str(item.get("quality", ""))[:20],
                   "size": item.get("size", 0)} for item in found[:500] if isinstance(item, dict)]
    return {"items": normalized, "providers": statuses}


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.buffer.read(32769))
        result = run_search(payload)
    except Exception:
        result = {"items": [], "providers": {}, "error": "CocoScrapers worker could not start."}
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
    sys.stdout.flush()
    # Third-party provider threads are bounded by the worker's lifetime.
    os._exit(0)
