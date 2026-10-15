"""Exercise OAuth state, isolation, encryption, and search through real HTTP routes."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.integrations import RD_GRANT, ServiceError
from app.main import create_app

WRITE={"X-Vizio-Media":"1"}
OWNER_PASSWORD="a-local-test-owner-password"


class Cloud:
    def __init__(self):
        self.approved={"trakt":False,"real_debrid":False}
        self.calls=[]
        self.refreshes=0
        self.refresh_error=False
        self.rate_limit=False
        self.invalid_url=False
        self.search_calls=0
        self.token_status=None
        self.unavailable=False

    def __call__(self,request):
        self.calls.append(request)
        if self.unavailable:
            raise httpx.ConnectError('Service unavailable in test',request=request)
        path=request.url.path
        host=request.url.host
        if path.endswith("/device/code"):
            return httpx.Response(200,json={"device_code":"PRIVATE-DEVICE-CODE","user_code":"ABCD-1234","interval":1,"expires_in":600,
                "verification_url":"https://evil.example/approve" if self.invalid_url else ("https://trakt.tv/activate" if host=="auth.trakt.tv" else "https://real-debrid.com/device")})
        if path=="/oauth/device/token":
            if self.token_status:
                return httpx.Response(self.token_status,json={})
            if self.rate_limit:
                return httpx.Response(429,json={},headers={"Retry-After":"12"})
            if not self.approved["trakt"]:
                return httpx.Response(400,json={"error":"authorization_pending"})
            return httpx.Response(200,json={"access_token":"TRAKT-ACCESS-SECRET","refresh_token":"TRAKT-REFRESH-SECRET","expires_in":3600})
        if path=="/oauth/token":
            self.refreshes+=1
            body=json.loads(request.content)
            assert body["redirect_uri"]=="urn:ietf:wg:oauth:2.0:oob"
            assert body["refresh_token"]=="TRAKT-REFRESH-SECRET"
            if self.refresh_error:
                return httpx.Response(400,json={"error":"invalid_grant"})
            return httpx.Response(200,json={"access_token":"ROTATED-ACCESS-SECRET","refresh_token":"ROTATED-REFRESH-SECRET","expires_in":3600})
        if path.endswith("/device/credentials"):
            if not self.approved["real_debrid"]:
                return httpx.Response(403,json={"error":"authorization_pending"})
            return httpx.Response(200,json={"client_id":"USER-BOUND-ID","client_secret":"USER-BOUND-SECRET"})
        if path=="/oauth/v2/token":
            body=parse_qs(request.content.decode())
            assert body["client_id"]==["USER-BOUND-ID"]
            assert body["client_secret"]==["USER-BOUND-SECRET"]
            assert body["grant_type"]==[RD_GRANT]
            if body["code"]==["RD-REFRESH-SECRET"]:
                self.refreshes+=1
            else:
                assert body["code"]==["PRIVATE-DEVICE-CODE"]
            return httpx.Response(200,json={"access_token":"RD-ACCESS-SECRET","refresh_token":"RD-REFRESH-SECRET","expires_in":3600})
        if path=="/oauth/revoke" or path.endswith("/disable_access_token"):
            return httpx.Response(204)
        if path=="/users/settings":
            assert request.headers.get("Authorization","").startswith("Bearer ")
            return httpx.Response(200,json={"user":{"username":"Linked Trakt user"}})
        if path.endswith("/user"):
            return httpx.Response(200,json={"username":"Linked RD user"})
        if path=="/3/configuration":
            return httpx.Response(200,json={"images":{"secure_base_url":"https://image.tmdb.org/t/p/"}})
        if path=="/3/genre/movie/list":
            return httpx.Response(200,json={"genres":[{"id":35,"name":"Comedy"},{"id":27,"name":"Horror"},{"id":878,"name":"Science Fiction"},{"id":16,"name":"Animation"}]})
        if path in {"/3/trending/all/week","/3/discover/movie"}:
            number=int(request.url.params.get("with_genres",101))
            return httpx.Response(200,json={"total_pages":2,"results":[
                {"id":number,"media_type":"movie","title":"A Test Film" if number==101 else "Genre Film "+str(number),"release_date":"2020-02-01","poster_path":"/art.jpg","backdrop_path":"/wide.jpg","overview":"A catalog story for movie night."},
                {"id":202,"media_type":"tv","name":"A Test Show","first_air_date":"2021-01-01"},
                {"id":number,"media_type":"movie","title":"A Test Film" if number==101 else "Genre Film "+str(number)},
                {"id":303,"media_type":"person","name":"A Person"},
                {"id":404,"media_type":"movie","title":"Adult title","adult":True},
            ]})
        if path in {"/3/movie/101/recommendations","/3/tv/202/recommendations"}:
            return httpx.Response(200,json={"results":[{"id":505,"title":"Another Test Film","name":"Another Test Show","poster_path":"/art.jpg"}]})
        if path=="/movies/trending":
            return httpx.Response(200,json=[])
        if path in {"/3/search/multi","/3/search/movie","/3/search/tv"}:
            self.search_calls+=1
            return httpx.Response(200,json={"total_pages":2,"results":[
                {"id":101,"media_type":"movie","title":"A Test Film","release_date":"2020-02-01","overview":"Metadata from the test service.","poster_path":"/art.jpg"},
                {"id":202,"media_type":"tv","name":"A Test Show","first_air_date":"2021-01-01"},
                {"id":303,"media_type":"person","name":"A Person"},
            ]})
        if path=="/3/tv/202":
            return httpx.Response(200,json={"id":202,"name":"A Test Show","first_air_date":"2021-01-01","seasons":[{"season_number":1,"name":"Season 1","episode_count":2}]})
        if path=="/3/tv/202/season/1":
            return httpx.Response(200,json={"name":"Season 1","episodes":[{"episode_number":1,"name":"First episode"},{"episode_number":2,"name":"Second episode"}]})
        if path=="/3/movie/101":
            return httpx.Response(200,json={"id":101,"title":"A Test Film","release_date":"2020-02-01"})
        if path.endswith("/downloads"):
            return httpx.Response(200,json=[{"id":"own-file","filename":"A.Test.Film.2020.1080p.mp4","filesize":123456,"download":"https://private-download.example/SECRET"},
                {"id":"different-file","filename":"Unrelated.Film.2019.mp4"}])
        if path.endswith("/torrents"):
            return httpx.Response(200,json=[])
        if path=="/sync/watchlist":
            return httpx.Response(200,json=[{"type":"movie","movie":{"title":"A Test Film","year":2020,"ids":{"trakt":123,"tmdb":101}}}])
        if path=="/t/p/w342/art.jpg":
            return httpx.Response(200,content=b"image fixture",headers={"Content-Type":"image/jpeg"})
        raise AssertionError("Unexpected service endpoint: "+host+path)


@pytest.fixture
def environment(tmp_path):
    media=tmp_path/"media"
    media.mkdir()
    (media/"sample.mp4").write_bytes(b"sample")
    cloud=Cloud()
    app=create_app(Settings(bind_ip="127.0.0.1",data_dir=tmp_path/"data",media_dir=media),test_client=True,transport=httpx.MockTransport(cloud))
    with TestClient(app) as client:
        yield client,cloud,app


def owner(client):
    response=client.post("/api/admin/setup",json={"password":OWNER_PASSWORD},headers=WRITE)
    assert response.status_code==200,response.text


def configure(client,service):
    fields={"tmdb":{"read_token":"TMDB-READ-SECRET"},"trakt":{"client_id":"TRAKT-CLIENT-SECRET"},"real_debrid":{"client_id":"REGISTERED-RD-APP"}}[service]
    response=client.put("/api/admin/config/"+service,json=fields,headers=WRITE)
    assert response.status_code==200,response.text


def select(client,profile="household",pin=""):
    response=client.post("/api/profiles/select",json={"id":profile,"pin":pin},headers=WRITE)
    assert response.status_code==200,response.text


def elapsed(app,flow):
    with app.state.store.connection() as connection:
        connection.execute("UPDATE oauth_flows SET next_poll=0 WHERE id=?",(flow,))


def connect(client,cloud,app,service):
    configure(client,service)
    select(client)
    start=client.post(f"/api/accounts/{service}/start",json={},headers=WRITE)
    assert start.status_code==200,start.text
    flow=start.json()["id"]
    cloud.approved[service]=True
    elapsed(app,flow)
    result=client.post(f"/api/flows/{flow}/poll",json={},headers=WRITE)
    assert result.status_code==200,result.text
    assert result.json()["state"]=="connected"
    return flow


def test_owner_setup_login_validation_and_secret_redaction(environment):
    client,cloud,app=environment
    assert client.get("/api/admin/config").status_code==401
    owner(client)
    assert client.cookies.get("vizio_admin")
    assert client.get("/api/admin/status").json()["signed_in"]
    assert client.post("/api/admin/setup",json={"password":OWNER_PASSWORD},headers=WRITE).status_code==409
    secret="PRIVATE-INPUT-THAT-MUST-NOT-ECHO"
    response=client.put("/api/admin/config/tmdb",json={"unexpected":secret},headers=WRITE)
    assert response.status_code==422 and secret not in response.text
    client.post("/api/admin/logout",json={},headers=WRITE)
    assert client.get("/api/admin/config").status_code==401
    assert client.post("/api/admin/login",json={"password":"wrong"},headers=WRITE).status_code==401
    assert client.post("/api/admin/login",json={"password":OWNER_PASSWORD},headers=WRITE).status_code==200
    assert app.state.store.owner_hash()!=OWNER_PASSWORD


def test_manager_and_setup_are_loopback_only(environment):
    client,cloud,app=environment
    with TestClient(app,client=("192.0.2.20",5000),base_url="http://127.0.0.1") as tv:
        for path in ("/manage","/static/manage.html","/static//manage.html","/static/MANAGE.HTML","/api/admin/status","/api/admin/config"):
            assert tv.get(path,headers={"X-Forwarded-For":"127.0.0.1"}).status_code==403
        assert tv.get("/api/profiles").status_code==200


def test_profile_pins_sessions_and_progress_are_isolated(environment):
    client,cloud,app=environment
    owner(client)
    alice=client.post("/api/admin/profiles",json={"name":"Alice","pin":"1234"},headers=WRITE).json()["id"]
    bob=client.post("/api/admin/profiles",json={"name":"Bob","pin":"5678"},headers=WRITE).json()["id"]
    assert client.post("/api/profiles/select",json={"id":alice,"pin":"9999"},headers=WRITE).status_code==401
    select(client,alice,"1234")
    client.put("/api/progress/big-buck-bunny",json={"position":12,"duration":33},headers=WRITE)
    select(client,bob,"5678")
    assert client.get("/api/progress/big-buck-bunny").json()["position"]==0
    select(client,alice,"1234")
    assert client.get("/api/progress/big-buck-bunny").json()["position"]==12
    assert "pin_hash" not in client.get("/api/profiles").text
    assert app.state.store.profile(alice)["pin_hash"]!="1234"
    client.post("/api/profiles/lock",json={},headers=WRITE)
    assert client.get("/api/accounts").status_code==401


def test_pin_attempts_are_rate_limited(environment):
    client,cloud,app=environment
    owner(client)
    identifier=client.post("/api/admin/profiles",json={"name":"PIN","pin":"1234"},headers=WRITE).json()["id"]
    for _ in range(5):
        assert client.post("/api/profiles/select",json={"id":identifier,"pin":"0000"},headers=WRITE).status_code==401
    response=client.post("/api/profiles/select",json={"id":identifier,"pin":"1234"},headers=WRITE)
    assert response.status_code==429 and response.headers["retry-after"]=="60"


def test_locked_profile_progress_cannot_fall_back_to_household(environment):
    client,cloud,app=environment
    owner(client)
    client.put('/api/admin/profiles/household',json={'name':'Household','pin':'1234'},headers=WRITE)
    assert client.get('/api/progress/big-buck-bunny').status_code==401
    select(client,pin='1234')
    assert client.get('/api/progress/big-buck-bunny').status_code==200
    client.put('/api/admin/profiles/household',json={'name':'Household'},headers=WRITE)
    assert client.get('/api/accounts').status_code==401


def test_application_settings_cannot_change_during_device_signin(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,'trakt')
    select(client)
    flow=client.post('/api/accounts/trakt/start',json={},headers=WRITE).json()['id']
    assert client.delete('/api/admin/config/trakt',headers=WRITE).status_code==409
    assert client.put('/api/admin/config/trakt',json={'client_id':'A-DIFFERENT-ID'},headers=WRITE).status_code==409
    client.delete('/api/flows/'+flow,headers=WRITE)
    assert client.delete('/api/admin/config/trakt',headers=WRITE).status_code==200


def test_missing_or_mismatched_vault_key_refuses_startup(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,'tmdb')
    settings=app.state.settings
    key=settings.data_dir/'vault.key'
    original=key.read_bytes()
    key.unlink()
    with pytest.raises(RuntimeError,match='key is missing'):
        create_app(settings)
    assert not key.exists()
    from cryptography.fernet import Fernet
    key.write_bytes(Fernet.generate_key())
    with pytest.raises(RuntimeError,match='cannot be decrypted'):
        create_app(settings)
    key.write_bytes(original)


@pytest.mark.parametrize('code,state',[(404,'invalid'),(409,'used'),(410,'expired'),(418,'denied')])
def test_trakt_terminal_device_states_clear_secrets(environment,code,state):
    client,cloud,app=environment
    owner(client)
    configure(client,'trakt')
    select(client)
    flow=client.post('/api/accounts/trakt/start',json={},headers=WRITE).json()['id']
    elapsed(app,flow)
    cloud.token_status=code
    assert client.post('/api/flows/'+flow+'/poll',json={},headers=WRITE).json()['state']==state
    assert app.state.store.flow(flow)['sealed']==''
    assert app.state.store.account('household','trakt') is None


def test_trakt_flow_interval_completion_and_encrypted_storage(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,"trakt")
    select(client)
    response=client.post("/api/accounts/trakt/start",json={},headers=WRITE)
    assert response.status_code==200,response.text
    assert "PRIVATE-DEVICE-CODE" not in response.text
    flow=response.json()["id"]
    calls=len(cloud.calls)
    assert client.post(f"/api/flows/{flow}/poll",json={},headers=WRITE).json()["state"]=="pending"
    assert len(cloud.calls)==calls
    elapsed(app,flow)
    assert client.post(f"/api/flows/{flow}/poll",json={},headers=WRITE).json()["state"]=="pending"
    cloud.approved["trakt"]=True
    elapsed(app,flow)
    response=client.post(f"/api/flows/{flow}/poll",json={},headers=WRITE)
    assert response.json()["state"]=="connected"
    assert app.state.store.flow(flow)["sealed"]==""
    status=client.get("/api/accounts").text
    assert "Linked Trakt user" in status and "ACCESS-SECRET" not in status
    with app.state.store.connection() as connection:
        account=connection.execute("SELECT sealed FROM accounts").fetchone()[0]
        config=connection.execute("SELECT sealed FROM service_config").fetchone()[0]
    assert "TRAKT-ACCESS-SECRET" not in account and "TRAKT-CLIENT-SECRET" not in config
    bob=client.post("/api/admin/profiles",json={"name":"Bob"},headers=WRITE).json()["id"]
    select(client,bob)
    assert client.post(f"/api/flows/{flow}/poll",json={},headers=WRITE).status_code==404
    assert client.get("/api/accounts").json()["trakt"]["state"]=="disconnected"


def test_trakt_rotates_refresh_pair_once_under_concurrent_requests(environment):
    client,cloud,app=environment
    owner(client)
    connect(client,cloud,app,"trakt")
    account=app.state.store.account("household","trakt")
    app.state.store.save_account("household","trakt",account["sealed"],account["display_name"],time.time()-1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _: app.state.services.access("household","trakt"),range(2)))
    assert results==["ROTATED-ACCESS-SECRET"]*2
    assert cloud.refreshes==1
    data=app.state.services.vault.open(app.state.store.account("household","trakt")["sealed"])
    assert data["refresh_token"]=="ROTATED-REFRESH-SECRET"


def test_bad_refresh_requires_reconnect_without_repeated_retries(environment):
    client,cloud,app=environment
    owner(client)
    connect(client,cloud,app,"trakt")
    account=app.state.store.account("household","trakt")
    app.state.store.save_account("household","trakt",account["sealed"],account["display_name"],time.time()-1)
    cloud.refresh_error=True
    for _ in range(2):
        with pytest.raises(ServiceError): app.state.services.access("household","trakt")
    assert cloud.refreshes==1
    assert app.state.store.account("household","trakt")["status"]=="reconnect_required"


def test_rd_device_credentials_and_nonstandard_refresh_grant(environment):
    client,cloud,app=environment
    owner(client)
    flow=connect(client,cloud,app,"real_debrid")
    account=app.state.store.account("household","real_debrid")
    data=app.state.services.vault.open(account["sealed"])
    assert data["client_id"]=="USER-BOUND-ID"
    assert data["client_secret"]=="USER-BOUND-SECRET"
    app.state.store.save_account("household","real_debrid",account["sealed"],account["display_name"],time.time()-1)
    assert app.state.services.access("household","real_debrid")=="RD-ACCESS-SECRET"
    assert cloud.refreshes==1


def test_personal_token_is_owner_only_and_can_disconnect(environment):
    client,cloud,app=environment
    assert client.post("/api/admin/profiles/household/real_debrid/token",json={"token":"PRIVATE-RD-API-TOKEN"},headers=WRITE).status_code==401
    owner(client)
    result=client.post("/api/admin/profiles/household/real_debrid/token",json={"token":"PRIVATE-RD-API-TOKEN"},headers=WRITE)
    assert result.status_code==200 and "PRIVATE-RD-API-TOKEN" not in result.text
    select(client)
    result=client.delete("/api/accounts/real_debrid",headers=WRITE)
    assert result.status_code==200 and result.json()["remote_token_disabled"]
    assert app.state.store.account("household","real_debrid") is None


def test_connection_check_reports_an_unreachable_service(environment):
    client,cloud,app=environment
    owner(client)
    connect(client,cloud,app,'trakt')
    cloud.unavailable=True
    result=client.post('/api/admin/profiles/household/accounts/trakt/refresh',json={},headers=WRITE)
    assert result.status_code==503
    assert app.state.store.account('household','trakt')['status']=='connected'


def test_expiry_cancel_and_rate_limit_preserve_safe_state(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,"trakt")
    select(client)
    flow=client.post("/api/accounts/trakt/start",json={},headers=WRITE).json()["id"]
    elapsed(app,flow)
    cloud.rate_limit=True
    result=client.post(f"/api/flows/{flow}/poll",json={},headers=WRITE).json()
    assert result["state"]=="pending" and result["retry_after"]>=10
    assert client.delete(f"/api/flows/{flow}",headers=WRITE).json()["state"]=="cancelled"
    assert app.state.store.flow(flow)["sealed"]==""
    flow=client.post("/api/accounts/trakt/start",json={},headers=WRITE).json()["id"]
    with app.state.store.connection() as connection:
        connection.execute("UPDATE oauth_flows SET expires_at=0 WHERE id=?",(flow,))
    assert client.post(f"/api/flows/{flow}/poll",json={},headers=WRITE).json()["state"]=="expired"


def test_unexpected_device_signin_host_is_rejected(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,"trakt")
    select(client)
    cloud.invalid_url=True
    assert client.post("/api/accounts/trakt/start",json={},headers=WRITE).status_code==502


def test_catalog_samples_live_search_cache_and_seasons(environment):
    client,cloud,app=environment
    initial=client.get("/api/catalog/search",params={"q":"bunny"}).json()
    assert initial["source"]=="samples" and initial["items"][0]["id"]=="sample-bunny"
    assert not client.get("/api/catalog/search",params={"q":"missing"}).json()["items"]
    assert client.get("/api/catalog/search",params={"kind":"invalid"}).status_code==422
    owner(client)
    configure(client,"tmdb")
    for _ in range(2):
        result=client.get("/api/catalog/search",params={"q":"Test"}).json()
        assert [item["kind"] for item in result["items"]]==["movie","tv"]
        assert "TMDB-READ-SECRET" not in json.dumps(result)
        assert result["items"][0]["poster"]=="/api/artwork/w342/art.jpg"
    assert cloud.search_calls==1
    detail=client.get("/api/catalog/tmdb-tv-202").json()
    assert detail["seasons"][0]["number"]==1
    episodes=client.get("/api/catalog/tmdb-tv-202/seasons/1").json()["episodes"]
    assert len(episodes)==2 and episodes[0]["id"]=="tmdb-tv-202-s1-e1"
    assert client.get("/api/catalog/tmdb-tv-202/seasons/-1").status_code==422
    assert client.get("/api/artwork/w342/art.jpg").status_code==200
    assert client.get("/api/artwork/original/art.jpg").status_code==404


def test_authorized_account_file_search_and_watchlist_are_scoped(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,"tmdb")
    assert client.get("/api/catalog/tmdb-movie-101/sources").status_code==401
    select(client)
    client.post("/api/admin/profiles/household/real_debrid/token",json={"token":"PRIVATE-RD-API-TOKEN"},headers=WRITE)
    response=client.get("/api/catalog/tmdb-movie-101/sources")
    assert response.status_code==200,response.text
    assert response.json()["items"][0]["filename"]=="A.Test.Film.2020.1080p.mp4"
    assert "private-download" not in response.text and "PRIVATE-RD-API-TOKEN" not in response.text
    connect(client,cloud,app,"trakt")
    assert client.get("/api/catalog/watchlist").json()["items"][0]["id"]=="tmdb-movie-101"
