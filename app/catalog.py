"""Normalized metadata, bounded caches, and licensed local sample discovery."""

import hashlib
import re
import tempfile
from pathlib import Path

from app.integrations import ServiceError, Services
from app.store import Store

MEDIA_ID = re.compile(r"^(?:sample-(?:bunny|sintel|dream)|(?:tmdb|trakt)-(?:movie|tv)-[1-9][0-9]{0,9})$")
IMAGE_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,150}\.(?:jpg|png|webp)$")
SAMPLES = [
    {"id":"sample-bunny","title":"Big Buck Bunny","year":"2008","kind":"movie","overview":"A large rabbit takes on three troublesome woodland neighbors. A licensed 33-second trailer is included.","poster":"/static/art/hero.jpg","source":"samples","playable":True,"sample":True,"runtime":1,"genres":["Animation"],"ids":{}},
    {"id":"sample-sintel","title":"Sintel","year":"2010","kind":"movie","overview":"A young traveler searches for a dragon. This sample title has no playable video.","poster":"/static/art/sintel.svg","source":"samples","playable":False,"sample":True,"runtime":15,"genres":["Fantasy"],"ids":{}},
    {"id":"sample-dream","title":"Elephants Dream","year":"2006","kind":"movie","overview":"Two characters explore a mechanical world. This sample title has no playable video.","poster":"/static/art/dream.svg","source":"samples","playable":False,"sample":True,"runtime":11,"genres":["Animation"],"ids":{}},
]


class Catalog:
    def __init__(self, store: Store, services: Services, directory: Path):
        self.store, self.services = store, services
        self.art = directory / "artwork"
        self.art.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_id(media_id: str):
        if not MEDIA_ID.fullmatch(media_id):
            raise ServiceError("Unknown catalog title.",404)

    @staticmethod
    def tmdb_item(data: dict, kind: str | None = None) -> dict:
        kind=kind or ("tv" if data.get("media_type")=="tv" else "movie")
        image=str(data.get("poster_path") or "").lstrip("/")
        poster="/api/artwork/w342/"+image if IMAGE_NAME.fullmatch(image) else None
        backdrop=str(data.get("backdrop_path") or "").lstrip("/")
        return {"id":f"tmdb-{kind}-{int(data['id'])}","title":str(data.get("title") or data.get("name") or "Untitled")[:300],
            "year":str(data.get("release_date") or data.get("first_air_date") or "")[:4],"kind":kind,
            "overview":str(data.get("overview") or "No description available.")[:8000],"poster":poster,
            "backdrop":"/api/artwork/w780/"+backdrop if IMAGE_NAME.fullmatch(backdrop) else poster,
            "source":"tmdb","playable":False,"sample":False,"runtime":data.get("runtime") or None,
            "genres":[str(g.get("name","")) for g in data.get("genres",[]) if isinstance(g,dict)],
            "seasons":[{"number":s["season_number"],"name":s.get("name","Season"),"episode_count":s.get("episode_count",0)} for s in data.get("seasons",[]) if isinstance(s,dict) and isinstance(s.get("season_number"),int)],
            "ids":{"tmdb":data["id"],**{k:v for k,v in (data.get("external_ids") or {}).items() if k in {"imdb_id","tvdb_id"}}}}

    @staticmethod
    def trakt_item(data: dict, kind: str) -> dict:
        ids=data.get("ids") or {}
        return {"id":f"trakt-{kind}-{int(ids['trakt'])}","title":str(data.get("title") or "Untitled")[:300],
            "year":str(data.get("year") or ""),"kind":kind,"overview":str(data.get("overview") or "No description available.")[:8000],
            "poster":None,"source":"trakt","playable":False,"sample":False,"runtime":data.get("runtime"),
            "genres":data.get("genres") or [],"ids":ids,"seasons":[]}

    def search(self, query: str, kind: str = "all", page: int = 1) -> dict:
        source="tmdb" if self.services.config("tmdb").get("read_token") else ("trakt" if self.services.config("trakt").get("client_id") else "samples")
        if source=="samples":
            terms=query.casefold().split()
            items=[dict(s) for s in SAMPLES if kind in {"all",s["kind"]} and all(t in (s["title"]+" "+s["year"]).casefold() for t in terms)]
            return {"source":"samples","items":items if page==1 else [],"page":page,"total_pages":1,"stale":False,
                    "notice":"Searching the three local sample titles. Set up TMDB or a Trakt application in Account manager for the full catalog."}
        key="search:"+hashlib.sha256(f"{source}:{kind}:{page}:{query.casefold()}".encode()).hexdigest()
        cached=self.store.cached(key)
        if cached:
            return cached
        try:
            if source=="tmdb":
                params={"query":query,"page":page,"include_adult":"false","language":"en-US"}
                path=("/search/multi" if kind=="all" else "/search/"+kind) if query else f"/trending/{kind if kind!='all' else 'all'}/week"
                data=self.services.tmdb(path,params)
                items=[]
                for item in data.get("results",[]):
                    media_type=item.get("media_type",kind)
                    if item.get("adult") or media_type not in {"movie","tv"} or not isinstance(item.get("id"),int):
                        continue
                    items.append(self.tmdb_item(item,media_type))
                total_pages=min(500,max(1,int(data.get("total_pages",1))))
            else:
                types={"all":"movie,show","movie":"movie","tv":"show"}[kind]
                path="/search/"+types if query else ("/shows/trending" if kind=="tv" else "/movies/trending")
                response=self.services.raw("GET","https://api.trakt.tv"+path,headers=self.services.trakt_headers(),params={"query":query,"page":page,"limit":20,"extended":"full"})
                data=self.services.checked(response)
                items=[]
                for item in data:
                    media_type=item.get("type") or ("show" if "show" in item else "movie")
                    content=item.get(media_type,{})
                    if media_type in {"movie","show"} and content.get("ids",{}).get("trakt"):
                        items.append(self.trakt_item(content,"tv" if media_type=="show" else "movie"))
                total_pages=min(500,max(1,int(response.headers.get("X-Pagination-Page-Count",page+(len(items)==20)))))
            # Deduplicate by provider/media ID, as a source aggregator would.
            items=list({item["id"]:item for item in items}.values())
            result={"source":source,"items":items,"page":page,"total_pages":total_pages,"stale":False,"notice":None}
            self.store.cache(key,result)
            return result
        except ServiceError:
            stale=self.store.cached(key,stale=True)
            if stale:
                return {**stale,"stale":True,"notice":"The metadata service is unavailable. Showing cached results."}
            raise

    def details(self, media_id: str) -> dict:
        self.validate_id(media_id)
        if media_id.startswith("sample-"):
            return next(dict(s) for s in SAMPLES if s["id"]==media_id)
        key="detail:"+media_id
        cached=self.store.cached(key)
        if cached:
            return cached
        provider,kind,identifier=media_id.split("-")
        if provider=="tmdb":
            data=self.services.tmdb(f"/{kind}/{identifier}",{"append_to_response":"external_ids","language":"en-US"})
            result=self.tmdb_item(data,kind)
        else:
            data=self.services.trakt(f"/{'shows' if kind=='tv' else 'movies'}/{identifier}",{"extended":"full"})
            result=self.trakt_item(data,kind)
        self.store.cache(key,result)
        return result

    def season(self, media_id: str, number: int) -> dict:
        self.validate_id(media_id)
        if not media_id.startswith("tmdb-tv-"):
            raise ServiceError("Season browsing needs TMDB metadata. Set up TMDB in Account manager.",409)
        key=f"season:{media_id}:{number}"
        cached=self.store.cached(key)
        if cached:
            return cached
        data=self.services.tmdb(f"/tv/{media_id.split('-')[-1]}/season/{number}",{"language":"en-US"})
        episodes=[{"id":f"{media_id}-s{number}-e{e['episode_number']}","number":e["episode_number"],"name":str(e.get("name") or "Episode"),
            "overview":str(e.get("overview") or "No description available.")[:8000],"runtime":e.get("runtime"),"air_date":e.get("air_date")} for e in data.get("episodes",[]) if isinstance(e.get("episode_number"),int)]
        result={"title_id":media_id,"number":number,"name":data.get("name","Season"),"episodes":episodes}
        self.store.cache(key,result)
        return result

    def watchlist(self, profile_id: str) -> dict:
        data=self.services.trakt("/sync/watchlist",{"page":1,"limit":100,"extended":"full"},profile_id)
        items=[]
        for entry in data if isinstance(data,list) else []:
            kind=entry.get("type")
            media=entry.get(kind,{})
            if kind in {"movie","show"} and media.get("ids",{}).get("trakt"):
                item=self.trakt_item(media,"tv" if kind=="show" else "movie")
                if media.get("ids",{}).get("tmdb") and self.services.config("tmdb").get("read_token"):
                    item["id"]=f"tmdb-{item['kind']}-{int(media['ids']['tmdb'])}"
                items.append(item)
        return {"source":"trakt","items":items,"page":1,"total_pages":1,"stale":False,
            "notice":"Showing up to 100 watchlist entries. Additional pages are available on Trakt." if len(data)==100 else None}

    def artwork(self, size: str, name: str) -> Path:
        if size not in {"w342","w780"} or not IMAGE_NAME.fullmatch(name):
            raise ServiceError("Unknown artwork.",404)
        path=self.art/(size+"-"+name)
        if path.is_file():
            return path
        try:
            with self.services.http.stream("GET",f"https://image.tmdb.org/t/p/{size}/{name}") as response:
                if response.status_code!=200 or not response.headers.get("Content-Type","").startswith("image/"):
                    raise ServiceError("Artwork is unavailable.",404)
                content=bytearray()
                for chunk in response.iter_bytes(65536):
                    content.extend(chunk)
                    if len(content)>3*1024*1024:
                        raise ServiceError("Artwork was too large.",404)
        except Exception as error:
            if isinstance(error,ServiceError): raise
            raise ServiceError("Artwork could not be loaded.",404) from None
        with tempfile.NamedTemporaryFile(dir=self.art,suffix=".part",delete=False) as temporary:
            temporary.write(content)
            temporary_path=Path(temporary.name)
        temporary_path.replace(path)
        entries=sorted([p for p in self.art.iterdir() if p.suffix in {".jpg",".png",".webp"}],key=lambda p:p.stat().st_mtime)
        for obsolete in entries[:-200]:
            if obsolete!=path:
                obsolete.unlink(missing_ok=True)
        return path
