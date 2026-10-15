"""Search, selection, RD preparation, range seeking, and profile isolation."""

import json
from concurrent.futures import ThreadPoolExecutor
import socket
import time

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.playback import stream_url
from app.integrations import ServiceError
from playback_fixtures import FakeCoco, PlaybackCloud, media_response
from test_accounts_catalog import owner, configure, select, WRITE


@pytest.fixture
def playback_env(tmp_path, monkeypatch):
    cloud = PlaybackCloud()
    media = bytes(range(256)) * 4
    app = create_app(Settings(bind_ip="127.0.0.1", data_dir=tmp_path / "data", media_dir=tmp_path),
        test_client=True, coco=FakeCoco(), transport=httpx.MockTransport(cloud),
        media_transport=httpx.MockTransport(lambda request: media_response(request, media)))
    # Deterministic public CDN DNS; dedicated URL tests cover local-address rejection.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    with TestClient(app) as client:
        owner(client)
        configure(client, "tmdb")
        select(client)
        assert client.post("/api/admin/profiles/household/real_debrid/token", json={"token": "PRIVATE-RD-API-TOKEN"}, headers=WRITE).status_code == 200
        yield client, cloud, app, media


def sources(client, title="tmdb-movie-101", suffix=""):
    response = client.get(f"/api/catalog/{title}/sources?discover=true" + suffix)
    assert response.status_code == 200, response.text
    return response.json()


def start_coco(client, title="tmdb-movie-101", suffix=""):
    result = sources(client, title, suffix)
    item = next(item for item in result["items"] if item["provider"] == "cocoscrapers")
    response = client.post("/api/playback", json={"selection_id": item["selection_id"]}, headers=WRITE)
    assert response.status_code == 200, response.text
    return response.json(), item


def ready(client, app, preparation):
    app.state.playback.viewings[preparation["id"]].next_poll = 0
    response = client.get("/api/playback/" + preparation["id"])
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "ready", response.text
    return response.json()


def test_source_search_deduplicates_and_never_submits_or_exposes_private_links(playback_env):
    client, cloud, app, _ = playback_env
    result = sources(client)
    assert len(result["items"]) == 2
    assert result["items"][0]["provider"] == "real_debrid_library"
    assert result["items"][1]["preferred"]
    assert cloud.added == 0 and cloud.unrestricts == 0
    assert "magnet:" not in json.dumps(result)
    assert "private-download" not in json.dumps(result)
    assert "PRIVATE-RD-API-TOKEN" not in json.dumps(result)


def test_movie_selection_prepares_once_streams_ranges_and_saves_resume(playback_env):
    client, cloud, app, media = playback_env
    preparing, item = start_coco(client)
    assert preparing["state"] == "preparing"
    playing = ready(client, app, preparing)
    assert "PRIVATE-SIGNED-LINK" not in json.dumps(playing)
    assert cloud.last_link.endswith("FILE-20")
    duplicate = client.post("/api/playback", json={"selection_id": item["selection_id"]}, headers=WRITE)
    assert duplicate.json()["id"] == playing["id"] and cloud.added == 1
    url = playing["stream"]
    whole = client.get(url)
    assert whole.status_code == 200 and whole.content == media
    part = client.get(url, headers={"Range": "bytes=100-199"})
    assert part.status_code == 206 and part.content == media[100:200]
    assert part.headers["content-range"] == "bytes 100-199/1024"
    assert part.headers["cache-control"] == "no-store"
    assert client.head(url).content == b""
    assert client.get(url, headers={"Range": "bytes=-10"}).content == media[-10:]
    assert client.get(url, headers={"Range": "bytes=2000-"}).status_code == 416
    assert client.get(url, headers={"Range": "bytes=0-2,5-8"}).status_code == 416
    body = {"position": 123, "duration": 5400}
    assert client.put("/api/playback/" + playing["id"] + "/progress", json=body, headers=WRITE).status_code == 200
    assert client.get("/api/watching/tmdb-movie-101").json()["position"] == 123
    assert client.get("/api/playback/" + playing["id"]).json()["progress"]["position"] == 123
    continuing = client.get("/api/home/personal").json()["continue_watching"]
    assert continuing[0]["id"] == "tmdb-movie-101" and continuing[0]["progress"]["position"] == 123


def test_pack_requires_file_selection_and_maps_links_in_selected_file_order(playback_env):
    client, cloud, app, _ = playback_env
    cloud.pack = True
    preparation, _ = start_coco(client)
    assert preparation["state"] == "files"
    assert [item["id"] for item in preparation["files"]] == [20, 30]
    url = "/api/playback/" + preparation["id"] + "/files"
    assert client.post(url, json={"file_id": 10}, headers=WRITE).status_code == 400
    selected = client.post(url, json={"file_id": 30}, headers=WRITE)
    assert selected.status_code == 200, selected.text
    ready(client, app, preparation)
    assert cloud.last_link.endswith("FILE-30")


def test_episode_source_uses_exact_episode_and_separate_progress(playback_env):
    client, cloud, app, _ = playback_env
    assert client.get("/api/catalog/tmdb-tv-202/sources?discover=true").status_code == 400
    cloud.filename = "A.Test.Show.S01E02.1080p.H264.AAC.mp4"
    preparation, _ = start_coco(client, "tmdb-tv-202", "&season=1&episode=2")
    playing = ready(client, app, preparation)
    assert playing["title_id"] == "tmdb-tv-202-s1-e2"
    assert client.put("/api/playback/" + playing["id"] + "/progress", json={"position": 20, "duration": 1200}, headers=WRITE).status_code == 200
    assert client.get("/api/watching/tmdb-tv-202-s1-e1").json()["position"] == 0
    assert client.get("/api/home/personal").json()["continue_watching"][0]["watching_id"] == "tmdb-tv-202-s1-e2"


def test_profile_sessions_cannot_reuse_sources_streams_or_progress(playback_env):
    client, cloud, app, _ = playback_env
    preparation, item = start_coco(client)
    playing = ready(client, app, preparation)
    assert client.post("/api/admin/profiles", json={"name": "Other"}, headers=WRITE).status_code == 201
    other = next(profile for profile in app.state.store.profiles() if profile["id"] != "household")
    select(client, other["id"])
    assert client.post("/api/playback", json={"selection_id": item["selection_id"]}, headers=WRITE).status_code == 404
    assert client.get(playing["stream"]).status_code == 404
    assert client.put("/api/playback/" + playing["id"] + "/progress", json={"position": 10, "duration": 100}, headers=WRITE).status_code == 404
    select(client)
    assert client.get(playing["stream"]).status_code == 404  # A new login cannot reuse the previous session's stream.


def test_expired_choice_disconnect_and_failed_torrent_have_actionable_errors(playback_env):
    client, cloud, app, _ = playback_env
    result = sources(client)
    choice = result["items"][0]["selection_id"]
    app.state.playback.choices[choice].expires = 0
    assert client.post("/api/playback", json={"selection_id": choice}, headers=WRITE).status_code == 404
    cloud.state = "dead"
    result = sources(client)
    item = next(item for item in result["items"] if item["provider"] == "cocoscrapers")
    response = client.post("/api/playback", json={"selection_id": item["selection_id"]}, headers=WRITE)
    assert response.status_code == 409 and "another source" in response.text
    cloud.state = "downloaded"
    preparation, _ = start_coco(client)
    assert client.delete("/api/accounts/real_debrid", headers=WRITE).status_code == 200
    assert client.get(preparation["stream"]).status_code == 404


def test_download_link_is_refreshed_after_cdn_expiry(playback_env):
    client, cloud, app, media = playback_env
    result = sources(client)
    item = result["items"][0]
    response = client.post("/api/playback", json={"selection_id": item["selection_id"]}, headers=WRITE)
    assert response.status_code == 200, response.text
    playing = response.json()
    calls = []
    def cdn(request):
        calls.append(request)
        return httpx.Response(403) if len(calls) == 1 else media_response(request, media)
    app.state.playback.http.close()
    app.state.playback.http = httpx.Client(transport=httpx.MockTransport(cdn))
    assert client.get(playing["stream"]).content == media
    assert cloud.unrestricts == 2


def test_concurrent_clicks_add_one_torrent_without_deadlocking(playback_env):
    client, cloud, app, _ = playback_env
    item = next(item for item in sources(client)["items"] if item["provider"] == "cocoscrapers")
    choice = app.state.playback.choices[item["selection_id"]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(app.state.playback.start, "household", choice.owner, item["selection_id"]) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert results[0]["id"] == results[1]["id"] and cloud.added == 1


def test_actual_codec_metadata_warns_about_unsupported_audio(playback_env):
    client, cloud, app, _ = playback_env
    cloud.audio_codec = "dts"
    preparation, _ = start_coco(client)
    playing = ready(client, app, preparation)
    assert playing["media"] == {"checked": True, "video": ["h264"], "audio": ["dts"]}
    assert "Audio codec" in playing["warning"]
    assert "PRIVATE-ORIGINAL-LINK" not in json.dumps(playing)


def test_selected_nonvideo_files_do_not_shift_the_chosen_video_link(playback_env):
    client, cloud, app, _ = playback_env
    cloud.pack = True
    cloud.state = "downloaded"
    cloud.selected = [10, 20, 30]
    preparation, _ = start_coco(client)
    assert preparation["state"] == "files"
    response = client.post("/api/playback/" + preparation["id"] + "/files", json={"file_id": 30}, headers=WRITE)
    assert response.json()["state"] == "ready", response.text
    assert cloud.last_link.endswith("FILE-30")


def test_real_debrid_force_download_header_is_served_as_video(playback_env):
    client, cloud, app, media = playback_env
    preparation, _ = start_coco(client)
    playing = ready(client, app, preparation)
    def cdn(request):
        response = media_response(request, media)
        response.headers["content-type"] = "application/force-download"
        return response
    app.state.playback.http.close()
    app.state.playback.http = httpx.Client(transport=httpx.MockTransport(cdn))
    response = client.get(playing["stream"], headers={"Range":"bytes=100-199"})
    assert response.status_code == 206 and response.content == media[100:200]
    assert response.headers["content-type"] == "video/mp4"


@pytest.mark.parametrize("url", ["http://example.com/video", "https://user:pass@example.com/video", "https://example.com:8765/video", "file:///etc/passwd"])
def test_unsafe_stream_schemes_ports_and_credentials_are_rejected(url):
    with pytest.raises(ServiceError):
        stream_url(url)


def test_private_stream_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ServiceError):
        stream_url("https://media.example.com/video")
