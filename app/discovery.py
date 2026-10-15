"""Public home collections and uncached, profile-scoped viewing information."""

from concurrent.futures import ThreadPoolExecutor

from app.catalog import Catalog, SAMPLES
from app.integrations import ServiceError

GENRES={"all":"For you","comedy":"Comedy","horror":"Horror","science-fiction":"Sci-fi","animation":"Animation"}
GENRE_NAMES={"comedy":"comedy","horror":"horror","science-fiction":"science fiction","animation":"animation"}


class Discovery:
    def __init__(self, store, services, catalog):
        self.store,self.services,self.catalog=store,services,catalog

    def collection(self, genre: str, page: int = 1) -> dict:
        if genre not in GENRES:
            raise ServiceError("Unknown genre.",404)
        source="tmdb" if self.services.config("tmdb").get("read_token") else "fallback"
        key=f"home:v1:{source}:{genre}:{page}"
        cached=self.store.cached(key)
        if cached:
            return cached
        try:
            if source=="fallback":
                result=self.catalog.search("",page=page)
                if genre!="all":
                    result={**result,"items":[item for item in result["items"] if GENRE_NAMES[genre] in [g.casefold().replace("-"," ") for g in item.get("genres",[])]],
                        "notice":"Set up TMDB in Account manager for full genre collections."}
            else:
                if genre=="all":
                    raw=self.services.tmdb("/trending/all/week",{"page":page,"language":"en-US"})
                else:
                    definitions=self.store.cached("home:genres")
                    if definitions is None:
                        definitions={g["name"].casefold():g["id"] for g in self.services.tmdb("/genre/movie/list").get("genres",[])}
                        self.store.cache("home:genres",definitions)
                    identifier=definitions.get(GENRE_NAMES[genre])
                    if identifier is None:
                        raise ServiceError("This genre is temporarily unavailable.",503)
                    raw=self.services.tmdb("/discover/movie",{"with_genres":identifier,"page":page,"language":"en-US",
                        "sort_by":"popularity.desc","include_adult":"false","include_video":"false"})
                items=[]
                for item in raw.get("results",[])[:20]:
                    kind=item.get("media_type","movie")
                    if kind not in {"movie","tv"} or item.get("adult") or not isinstance(item.get("id"),int):
                        continue
                    items.append(Catalog.tmdb_item(item,kind))
                unique={}
                for item in items:
                    unique.setdefault(item["id"],item)
                result={"source":"tmdb","items":list(unique.values()),"page":page,
                    "total_pages":min(500,max(1,int(raw.get("total_pages",1)))),"stale":False,"notice":None}
            result={**result,"id":genre,"title":"Popular this week" if genre=="all" else GENRES[genre]+" movies"}
            self.store.cache(key,result)
            return result
        except ServiceError:
            stale=self.store.cached(key,stale=True)
            if stale:
                return {**stale,"stale":True,"notice":"Showing saved titles while the catalog service is unavailable."}
            raise

    def recommendations(self, media_id: str) -> dict:
        self.catalog.validate_id(media_id)
        if not media_id.startswith("tmdb-") or not self.services.config("tmdb").get("read_token"):
            return {"id":"related","title":"","items":[]}
        key="home:related:"+media_id
        cached=self.store.cached(key)
        if cached:
            return cached
        _,kind,identifier=media_id.split("-")
        data=self.services.tmdb(f"/{kind}/{identifier}/recommendations",{"language":"en-US","page":1})
        items=[Catalog.tmdb_item(raw,kind) for raw in data.get("results",[])[:20]
            if isinstance(raw.get("id"),int) and not raw.get("adult") and str(raw["id"])!=identifier]
        result={"id":"related","items":items,"source":"tmdb","notice":"Related titles from the catalog"}
        self.store.cache(key,result)
        return result

    def home(self, genre: str) -> dict:
        requested=["all","comedy","horror"] if genre=="all" else [genre]
        def safe_collection(key):
            try:
                return self.collection(key)
            except ServiceError as error:
                return {"id":key,"title":"Popular this week" if key=="all" else GENRES[key]+" movies","items":[],"error":error.message}
        with ThreadPoolExecutor(max_workers=3) as executor:
            rows=list(executor.map(safe_collection,requested))
        hero=next((row["items"][0] for row in rows if row["items"]),dict(SAMPLES[0]))
        return {"genre":genre,"genres":[{"id":key,"name":name} for key,name in GENRES.items()],"hero":hero,"shelves":rows,
            "notice":next((row.get("notice") for row in rows if row.get("notice")),None)}

    def personal(self, profile_id: str) -> dict:
        profile=self.store.profile(profile_id)
        progress=self.store.playback(profile_id,"big-buck-bunny")
        continuing=[]
        if 1<progress["position"]<progress["duration"]-2:
            continuing=[{**SAMPLES[0],"progress":{"position":progress["position"],"duration":progress["duration"]}}]
        account=self.store.account(profile_id,"trakt")
        watchlist={"state":"disconnected","items":[],"notice":"Connect Trakt in Accounts to see your watchlist."}
        if account:
            if account["status"]!="connected":
                watchlist.update(state="reconnect_required",notice="Reconnect Trakt in Accounts to load your watchlist.")
            else:
                try:
                    listing=self.catalog.watchlist(profile_id)
                    entries=listing["items"]
                    def artwork(item):
                        if item["id"].startswith("tmdb-"):
                            try:
                                return self.catalog.details(item["id"])
                            except ServiceError:
                                pass
                        return item
                    # Enrich only the first visible titles; all tokens remain server-side.
                    with ThreadPoolExecutor(max_workers=3) as executor:
                        visible=list(executor.map(artwork,entries[:6]))
                    watchlist={"state":"connected","items":visible+entries[6:],"notice":listing.get("notice")}
                except ServiceError as error:
                    watchlist.update(state="unavailable",notice=error.message)
        # This response must never enter the public metadata cache.
        return {"profile":{"id":profile_id,"name":profile["name"]},"continue_watching":continuing,"watchlist":watchlist}
