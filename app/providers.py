"""Small provider boundary inspired by aggregator concepts, independently written."""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Protocol

from app.integrations import Services


class SourceProvider(Protocol):
    def search(self, profile_id: str, title: dict, season: int | None = None, episode: int | None = None) -> list[dict]: ...


def words(value: str) -> str:
    value=unicodedata.normalize("NFKD",value).casefold()
    return " ".join(re.findall(r"[^\W_]+",value,flags=re.UNICODE))


def match_score(filename: str, title: dict, season: int | None = None, episode: int | None = None) -> float:
    name=words(filename)
    target=words(title["title"])
    if not target:
        return 0
    overlap=len(set(target.split()) & set(name.split()))/max(1,len(set(target.split())))
    score=0.85*overlap+0.15*SequenceMatcher(None,target,name).ratio()
    years=re.findall(r"\b(?:19|20)\d{2}\b",name)
    if title.get("year") and years and str(title["year"]) not in years:
        score*=0.5
    if season is not None:
        marker=rf"(?:s0*{season}e0*{episode}\b|\b0*{season}x0*{episode}\b)" if episode is not None else rf"(?:s0*{season}(?:e|\b)|season[ ._-]*0*{season}\b)"
        if not re.search(marker,filename,re.IGNORECASE):
            return 0
    return score


class DebridLibraryProvider:
    def __init__(self, services: Services):
        self.services=services

    def search(self, profile_id: str, title: dict, season: int | None = None, episode: int | None = None) -> list[dict]:
        downloads=self.services.authorized(profile_id,"real_debrid","GET","/downloads",params={"page":1,"limit":100})
        torrents=self.services.authorized(profile_id,"real_debrid","GET","/torrents",params={"page":1,"limit":100})
        results=[]
        for kind,entries in (("download",downloads),("torrent",torrents)):
            for entry in entries if isinstance(entries,list) else []:
                filename=str(entry.get("filename") or "")[:500]
                score=match_score(filename,title,season,episode)
                if score < 0.7:
                    continue
                results.append({"id":f"rd-{kind}-{entry.get('id','')}","provider":"real_debrid_library","filename":filename,
                    "size":max(0,int(entry.get("filesize") or entry.get("bytes") or 0)),
                    "status":str(entry.get("status") or "account download"),"match_score":round(score,3),"kind":kind})
        # No stream URL, private token, magnet, or torrent is returned or automatically added.
        return sorted({r["id"]:r for r in results}.values(),key=lambda r:r["match_score"],reverse=True)[:40]
