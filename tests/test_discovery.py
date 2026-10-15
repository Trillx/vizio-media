"""Exercise home discovery through the same authenticated HTTP routes as the TV."""

import httpx

from test_accounts_catalog import environment, owner, configure, select, connect, WRITE


def test_live_home_genres_recommendations_and_public_cache(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,"tmdb")
    response=client.get("/api/home")
    assert response.status_code==200
    result=response.json()
    assert [row["id"] for row in result["shelves"]]==["all","comedy","horror"]
    assert result["hero"]["id"]=="tmdb-movie-101"
    assert result["hero"]["backdrop"]=="/api/artwork/w780/wide.jpg"
    assert [item["id"] for item in result["shelves"][0]["items"]]==["tmdb-movie-101","tmdb-tv-202"]
    discovers=[r for r in cloud.calls if r.url.path=="/3/discover/movie"]
    assert {r.url.params["with_genres"] for r in discovers}=={"35","27"}
    assert all(r.url.params["include_adult"]=="false" for r in discovers)
    calls=len(cloud.calls)
    assert client.get("/api/home").json()==result
    assert len(cloud.calls)==calls
    animation=client.get("/api/home?genre=animation").json()
    assert [row["id"] for row in animation["shelves"]]==["animation"]
    assert animation["hero"]["id"]=="tmdb-movie-16"
    for seed,expected in [("tmdb-movie-101","tmdb-movie-505"),("tmdb-tv-202","tmdb-tv-505")]:
        assert client.get("/api/home/related/"+seed).json()["items"][0]["id"]==expected
    assert client.get("/api/home/shelf?genre=comedy&page=2").json()["page"]==2
    for suffix in ["?genre=unknown","/shelf?page=0","/shelf?page=501"]:
        assert client.get("/api/home"+suffix).status_code==422
    assert "SECRET" not in response.text


def test_one_failed_collection_does_not_hide_other_shelves(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,"tmdb")
    original=app.state.services.http._transport

    def selective(request):
        if request.url.params.get("with_genres")=="27":
            return httpx.Response(503,json={})
        return cloud(request)

    app.state.services.http._transport=httpx.MockTransport(selective)
    try:
        result=client.get("/api/home").json()
        assert result["shelves"][0]["items"]
        assert result["shelves"][1]["items"]
        assert result["shelves"][2]["error"]
        assert result["shelves"][2]["items"]==[]
    finally:
        app.state.services.http._transport=original


def test_expired_home_cache_remains_available_during_outage(environment):
    client,cloud,app=environment
    owner(client)
    configure(client,"tmdb")
    first=client.get("/api/home").json()
    with app.state.store.connection() as connection:
        connection.execute("UPDATE catalog_cache SET expires_at=0")
    cloud.unavailable=True
    result=client.get("/api/home").json()
    assert result["hero"]==first["hero"]
    assert all(row["stale"] for row in result["shelves"])
    assert "saved" in result["notice"]


def test_samples_are_honest_before_catalog_setup(environment):
    client,cloud,app=environment
    result=client.get("/api/home").json()
    assert result["hero"]["sample"]
    assert result["hero"]["playable"]
    assert result["notice"]
    assert client.get("/api/home?genre=horror").json()["shelves"][0]["items"]==[]
    assert client.get("/api/home/related/sample-bunny").json()["items"]==[]


def test_personal_home_is_authenticated_uncached_and_profile_scoped(environment):
    client,cloud,app=environment
    assert client.get("/api/home/personal").status_code==401
    owner(client)
    configure(client,"tmdb")
    connect(client,cloud,app,"trakt")
    client.put("/api/progress/big-buck-bunny",json={"position":12,"duration":33},headers=WRITE)
    response=client.get("/api/home/personal")
    result=response.json()
    assert response.headers["Cache-Control"]=="no-store"
    assert result["continue_watching"][0]["progress"]["position"]==12
    assert result["watchlist"]["state"]=="connected"
    assert result["watchlist"]["items"][0]["id"]=="tmdb-movie-101"
    assert "SECRET" not in response.text
    alice=client.post("/api/admin/profiles",json={"name":"Alice","pin":"1234"},headers=WRITE).json()["id"]
    select(client,alice,"1234")
    other=client.get("/api/home/personal").json()
    assert other["profile"]["id"]==alice
    assert other["continue_watching"]==[]
    assert other["watchlist"]["state"]=="disconnected"
    assert other["watchlist"]["items"]==[]
    select(client)
    client.delete("/api/accounts/trakt",headers=WRITE)
    assert client.get("/api/home/personal").json()["watchlist"]["items"]==[]
    client.put("/api/progress/big-buck-bunny",json={"position":33,"duration":33},headers=WRITE)
    assert client.get("/api/home/personal").json()["continue_watching"]==[]
    with app.state.store.connection() as connection:
        keys=[row[0] for row in connection.execute("SELECT key FROM catalog_cache")]
    assert all("personal" not in key and "watchlist" not in key for key in keys)
    client.post("/api/profiles/lock",json={},headers=WRITE)
    assert client.get("/api/home/personal").status_code==401
