import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

WRITE = {"X-Vizio-Media": "1"}


@pytest.fixture
def settings(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "sample.mp4").write_bytes(bytes(range(256)) * 4)
    return Settings(bind_ip="127.0.0.1", data_dir=tmp_path / "data", media_dir=media)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, test_client=True)) as connection:
        yield connection


def test_ui_health_and_static_files(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Big Buck" in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").json()["media_ready"] is True


def test_progress_survives_another_app_instance(client, settings):
    body = {"position": 12.5, "duration": 33.023333}
    assert client.put("/api/progress/big-buck-bunny", json=body, headers=WRITE).status_code == 200
    with TestClient(create_app(settings, test_client=True)) as reopened:
        result = reopened.get("/api/progress/big-buck-bunny").json()
    assert result["position"] == 12.5
    assert result["duration"] == 33.023333


@pytest.mark.parametrize("body", [
    {"position": -1, "duration": 33}, {"position": 40, "duration": 33},
    {"position": 0, "duration": 0}, {"position": 0, "duration": 999999},
])
def test_invalid_progress_is_rejected(client, body):
    assert client.put("/api/progress/big-buck-bunny", json=body, headers=WRITE).status_code == 422


def test_unknown_title_and_missing_media(client, settings):
    assert client.get("/api/progress/unknown").status_code == 404
    assert client.put("/api/progress/unknown", json={"position": 1, "duration": 33}, headers=WRITE).status_code == 404
    (settings.media_dir / "sample.mp4").unlink()
    assert client.get("/media/sample.mp4").status_code == 404
    assert client.get("/api/health").json()["media_ready"] is False


def test_video_ranges_and_head_for_tv_seeking(client):
    response = client.get("/media/sample.mp4", headers={"Range": "bytes=100-199"})
    assert response.status_code == 206
    assert response.content == bytes(range(100, 200))
    assert response.headers["content-range"] == "bytes 100-199/1024"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert client.get("/media/sample.mp4", headers={"Range": "bytes=-10"}).content == bytes(range(246, 256))
    assert client.get("/media/sample.mp4", headers={"Range": "bytes=2000-"}).status_code == 416
    assert client.head("/media/sample.mp4").content == b""


def test_client_ip_cannot_be_spoofed(settings):
    with TestClient(create_app(settings), client=("203.0.113.1", 50000)) as outside:
        assert outside.get("/", headers={"X-Forwarded-For": "192.0.2.20"}).status_code == 403
    with TestClient(create_app(settings), client=("192.0.2.20", 50000), base_url="http://127.0.0.1") as television:
        assert television.get("/").status_code == 200


def test_browser_write_and_host_guards(client):
    payload = {"position": 1, "duration": 33}
    assert client.put("/api/progress/big-buck-bunny", json=payload).status_code == 403
    assert client.put("/api/progress/big-buck-bunny", json=payload, headers=dict(WRITE, Origin="https://evil.example")).status_code == 403
    assert client.put("/api/progress/big-buck-bunny", json=payload, headers=dict(WRITE, Origin="http://testserver")).status_code == 200
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/diagnostics", content="x" * 9000, headers=WRITE).status_code == 413
    assert client.get("/static/../data/vizio-media.sqlite3").status_code == 404


def test_diagnostics_are_bounded_and_queryable(client):
    event = {"session_id": "tv-123", "kind": "key", "payload": {"key": "ArrowRight", "code": 39}}
    assert client.post("/api/diagnostics", json=event, headers=WRITE).status_code == 201
    result = client.get("/api/diagnostics").json()["events"][0]
    assert result["payload"]["code"] == 39
    assert result["session_id"] == "tv-123"
    event["payload"] = {"too_long": "x" * 513}
    assert client.post("/api/diagnostics", json=event, headers=WRITE).status_code == 422
    store = client.app.state.store
    for index in range(505):
        store.log("tv-123", "key", {"code": index})
    assert len(store.diagnostics()) == 100
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0] == 500
