"""Household profiles, owner-only setup, catalog, and scoped service accounts."""

import secrets
import sqlite3
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Path as PathParameter, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.catalog import Catalog
from app.discovery import Discovery
from app.config import ROOT
from app.integrations import SERVICES, ServiceError, Services
from app.providers import DebridLibraryProvider
from app.security import LoginLimiter, check_password, password_hash, token_hash
from app.store import Store


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Body):
    password: str = Field(min_length=1,max_length=128)


class ProfileSelection(Body):
    id: str = Field(min_length=1,max_length=64,pattern=r"^[a-zA-Z0-9_-]+$")
    pin: str = Field(default="",max_length=8)


class ProfileChange(Body):
    name: str = Field(min_length=1,max_length=32)
    pin: str | None = Field(default=None,max_length=8)
    clear_pin: bool = False

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip() or not value.isprintable():
            raise ValueError("Enter a readable profile name.")
        return value.strip()

    @field_validator("pin")
    @classmethod
    def valid_pin(cls, value):
        if value and (not value.isascii() or not value.isdigit() or len(value)<4):
            raise ValueError("Use four to eight digits for the profile PIN.")
        return value


class Credentials(Body):
    read_token: str | None = Field(default=None,max_length=2048)
    client_id: str | None = Field(default=None,max_length=256)
    client_secret: str | None = Field(default=None,max_length=2048)
    redirect_uri: str | None = Field(default=None,max_length=500)

    @field_validator("read_token","client_id","client_secret","redirect_uri")
    @classmethod
    def safe_value(cls, value):
        if value and (not value.isprintable() or any(c.isspace() for c in value.strip())):
            raise ValueError("This field must not contain spaces or control characters.")
        return value.strip() if value else value


class PersonalToken(Body):
    token: str = Field(min_length=5,max_length=2048,pattern=r"^[A-Za-z0-9._~-]+$")


class Linking:
    def __init__(self, store: Store, services: Services, *, test_client: bool = False):
        self.store,self.services=store,services
        self.limiter=LoginLimiter()
        self.test_client=test_client

    def local(self, request: Request):
        peers={"127.0.0.1","::1"}
        hosts={"127.0.0.1","localhost","::1"}
        if self.test_client:
            peers.add("testclient")
            hosts.add("testserver")
        if not request.client or request.client.host not in peers or request.url.hostname not in hosts:
            raise HTTPException(403,"Account manager is available only on this PC at http://127.0.0.1:8765/manage.")

    def session(self, request: Request, kind: str) -> dict | None:
        cookie=request.cookies.get("vizio_"+kind,"")
        if not cookie or len(cookie)>256:
            return None
        return self.store.session(token_hash(cookie),kind)

    def admin(self, request: Request):
        self.local(request)
        if not self.session(request,"admin"):
            raise HTTPException(401,"Sign in to Account manager first.")

    def profile(self, request: Request, *, required: bool = True) -> str:
        session=self.session(request,"profile")
        if session and self.store.profile(session["profile_id"]):
            return session["profile_id"]
        if required:
            raise HTTPException(401,"Choose and unlock a profile first.")
        profiles=self.store.profiles()
        if len(profiles)!=1 or profiles[0]["requires_pin"]:
            raise HTTPException(401,"Choose and unlock a profile first.")
        return "household"

    def issue(self, response: Response, kind: str, profile_id: str | None = None):
        token=secrets.token_urlsafe(32)
        self.store.add_session(token_hash(token),kind,profile_id,time.time()+8*3600)
        response.set_cookie("vizio_"+kind,token,httponly=True,samesite="strict",max_age=8*3600,path="/")

    def throttle(self, request: Request, target: str):
        if not self.limiter.allow(request.client.host+":"+target):
            raise HTTPException(429,"Too many attempts. Wait one minute before trying again.",headers={"Retry-After":"60"})


def feature_routes(store: Store, services: Services, catalog: Catalog, linking: Linking) -> APIRouter:
    router=APIRouter()
    discovery=Discovery(store,services,catalog)

    def known_profile(profile_id: str):
        if not store.profile(profile_id):
            raise HTTPException(404,"Profile not found.")

    @router.get("/manage")
    def manager(request: Request):
        linking.local(request)
        return FileResponse(ROOT/"web"/"manage.html",media_type="text/html",headers={"Cache-Control":"no-store"})

    @router.get("/api/admin/status")
    def admin_status(request: Request):
        linking.local(request)
        return {"setup_required":not bool(store.owner_hash()),"signed_in":bool(linking.session(request,"admin"))}

    @router.post("/api/admin/setup")
    def setup(body: Login, request: Request, response: Response):
        linking.local(request)
        linking.throttle(request,"owner")
        if len(body.password)<12 or not body.password.strip():
            raise HTTPException(400,"Use an account-manager password of at least twelve characters.")
        try:
            store.setup_owner(password_hash(body.password))
        except sqlite3.IntegrityError:
            raise HTTPException(409,"Account manager is already set up. Sign in instead.") from None
        linking.issue(response,"admin")
        return {"signed_in":True}

    @router.post("/api/admin/login")
    def login(body: Login, request: Request, response: Response):
        linking.local(request)
        linking.throttle(request,"owner")
        if not check_password(body.password,store.owner_hash()):
            raise HTTPException(401,"The account-manager password was not accepted.")
        linking.limiter.clear(request.client.host+":owner")
        linking.issue(response,"admin")
        return {"signed_in":True}

    @router.post("/api/admin/logout")
    def logout(request: Request, response: Response):
        linking.local(request)
        store.drop_session(token_hash(request.cookies.get("vizio_admin","")))
        response.delete_cookie("vizio_admin",path="/")
        return {"signed_in":False}

    @router.get("/api/admin/config")
    def config(request: Request):
        linking.admin(request)
        return services.configuration_status()

    @router.put("/api/admin/config/{service}")
    def configure(service: str, body: Credentials, request: Request):
        linking.admin(request)
        allowed={"tmdb":{"read_token"},"trakt":{"client_id","client_secret","redirect_uri"},"real_debrid":{"client_id"}}
        if service not in allowed:
            raise HTTPException(404,"Unknown service.")
        values=body.model_dump(exclude_none=True)
        if set(values)-allowed[service]:
            raise HTTPException(400,"Unexpected credential fields for this service.")
        services.configure(service,values)
        return services.configuration_status()[service]

    @router.delete("/api/admin/config/{service}")
    def remove_config(service: str, request: Request):
        linking.admin(request)
        if service not in SERVICES|{"tmdb"}:
            raise HTTPException(404,"Unknown service.")
        services.remove_configuration(service)
        return {"configured":False}

    @router.get("/api/admin/profiles")
    def admin_profiles(request: Request):
        linking.admin(request)
        return {"profiles":[{**p,"accounts":services.status(p["id"])} for p in store.profiles()]}

    @router.post("/api/admin/profiles",status_code=201)
    def create_profile(body: ProfileChange, request: Request):
        linking.admin(request)
        try:
            identifier=store.create_profile(body.name,password_hash(body.pin) if body.pin else None)
        except ValueError as error:
            raise HTTPException(409,str(error)) from None
        return {"id":identifier,"name":body.name,"requires_pin":bool(body.pin)}

    @router.put("/api/admin/profiles/{profile_id}")
    def change_profile(profile_id: str, body: ProfileChange, request: Request):
        linking.admin(request)
        known_profile(profile_id)
        pin_hash=store.profile(profile_id)["pin_hash"]
        if body.pin:
            pin_hash=password_hash(body.pin)
        elif body.clear_pin:
            pin_hash=None
        store.update_profile(profile_id,body.name,pin_hash)
        return {"id":profile_id,"name":body.name,"requires_pin":bool(pin_hash)}

    @router.delete("/api/admin/profiles/{profile_id}")
    def delete_profile(profile_id: str, request: Request):
        linking.admin(request)
        known_profile(profile_id)
        if any(store.account(profile_id,s) for s in SERVICES):
            raise HTTPException(409,"Disconnect this profile's service accounts before deleting it.")
        try:
            store.delete_profile(profile_id)
        except ValueError as error:
            raise HTTPException(409,str(error)) from None
        return {"deleted":True}

    @router.post("/api/admin/profiles/{profile_id}/real_debrid/token")
    def personal_token(profile_id: str, body: PersonalToken, request: Request):
        linking.admin(request)
        known_profile(profile_id)
        services.personal_token(profile_id,body.token)
        return services.status(profile_id)["real_debrid"]

    @router.post("/api/admin/profiles/{profile_id}/{service}/start")
    def admin_start(profile_id: str, service: str, request: Request):
        linking.admin(request)
        known_profile(profile_id)
        return services.start(profile_id,service)

    @router.post("/api/admin/profiles/{profile_id}/flows/{flow_id}/poll")
    def admin_poll(profile_id: str, flow_id: str, request: Request):
        linking.admin(request)
        known_profile(profile_id)
        return services.poll(profile_id,flow_id)

    @router.delete("/api/admin/profiles/{profile_id}/flows/{flow_id}")
    def admin_cancel(profile_id: str, flow_id: str, request: Request):
        linking.admin(request)
        known_profile(profile_id)
        return services.cancel(profile_id,flow_id)

    @router.delete("/api/admin/profiles/{profile_id}/accounts/{service}")
    def admin_disconnect(profile_id: str, service: str, request: Request):
        linking.admin(request)
        known_profile(profile_id)
        return services.disconnect(profile_id,service)

    @router.post("/api/admin/profiles/{profile_id}/accounts/{service}/refresh")
    def refresh_status(profile_id: str, service: str, request: Request):
        linking.admin(request)
        known_profile(profile_id)
        if service not in SERVICES: raise HTTPException(404,"Unknown service.")
        services.identify(profile_id,service,required=True)
        return services.status(profile_id)[service]

    @router.get("/api/profiles")
    def profiles():
        return {"profiles":store.profiles()}

    @router.post("/api/profiles/select")
    def select_profile(body: ProfileSelection, request: Request, response: Response):
        profile=store.profile(body.id)
        if not profile:
            raise HTTPException(404,"Profile not found.")
        if profile["pin_hash"]:
            linking.throttle(request,"profile:"+body.id)
            if not check_password(body.pin,profile["pin_hash"]):
                raise HTTPException(401,"That profile PIN was not accepted.")
            linking.limiter.clear(request.client.host+":profile:"+body.id)
        previous=linking.session(request,"profile")
        if previous:
            store.drop_session(previous["token_hash"])
        linking.issue(response,"profile",body.id)
        return {"id":profile["id"],"name":profile["name"],"requires_pin":bool(profile["pin_hash"])}

    @router.post("/api/profiles/lock")
    def lock_profile(request: Request, response: Response):
        store.drop_session(token_hash(request.cookies.get("vizio_profile","")))
        response.delete_cookie("vizio_profile",path="/")
        return {"profile":None}

    @router.get("/api/me")
    def me(request: Request):
        session=linking.session(request,"profile")
        profile=store.profile(session["profile_id"]) if session else None
        public={"id":profile["id"],"name":profile["name"],"requires_pin":bool(profile["pin_hash"])} if profile else None
        return {"profile":public,"accounts":services.status(profile["id"]) if profile else None,
            "catalog":services.configuration_status()}

    @router.get("/api/accounts")
    def accounts(request: Request):
        return services.status(linking.profile(request))

    @router.post("/api/accounts/{service}/start")
    def start(service: str, request: Request):
        return services.start(linking.profile(request),service)

    @router.post("/api/flows/{flow_id}/poll")
    def poll(flow_id: str, request: Request):
        return services.poll(linking.profile(request),flow_id)

    @router.delete("/api/flows/{flow_id}")
    def cancel(flow_id: str, request: Request):
        return services.cancel(linking.profile(request),flow_id)

    @router.delete("/api/accounts/{service}")
    def disconnect(service: str, request: Request):
        return services.disconnect(linking.profile(request),service)

    @router.get("/api/catalog/search")
    def search(q: str = Query(default="",max_length=120), kind: Literal["all","movie","tv"] = "all", page: int = Query(default=1,ge=1,le=500)):
        return catalog.search(q.strip(),kind,page)

    @router.get("/api/home")
    def home(genre: Literal["all","comedy","horror","science-fiction","animation"] = "all"):
        return discovery.home(genre)

    @router.get("/api/home/shelf")
    def home_shelf(genre: Literal["all","comedy","horror","science-fiction","animation"] = "all", page: int = Query(default=1,ge=1,le=500)):
        return discovery.collection(genre,page)

    @router.get("/api/home/related/{media_id}")
    def related(media_id: str):
        return discovery.recommendations(media_id)

    @router.get("/api/home/personal")
    def home_personal(request: Request):
        return discovery.personal(linking.profile(request))

    @router.get("/api/catalog/watchlist")
    def watchlist(request: Request):
        return catalog.watchlist(linking.profile(request))

    @router.get("/api/catalog/{media_id}")
    def details(media_id: str):
        return catalog.details(media_id)

    @router.get("/api/catalog/{media_id}/seasons/{number}")
    def season(media_id: str, number: int = PathParameter(ge=0,le=200)):
        return catalog.season(media_id,number)

    @router.get("/api/catalog/{media_id}/sources")
    def sources(media_id: str, request: Request, season: int | None = Query(default=None,ge=0,le=200), episode: int | None = Query(default=None,ge=1,le=1000)):
        profile_id=linking.profile(request)
        if episode is not None and season is None:
            raise HTTPException(400,"Choose a season before an episode.")
        title=catalog.details(media_id)
        items=DebridLibraryProvider(services).search(profile_id,title,season,episode)
        return {"items":items,"provider":"real_debrid_library","notice":"Filename matches from up to 100 downloads and 100 torrents in your linked account. Review each match. This does not search public providers or resolve playback."}

    @router.get("/api/artwork/{size}/{name}")
    def artwork(size: str,name: str):
        return FileResponse(catalog.artwork(size,name),headers={"Cache-Control":"private, max-age=86400"})

    return router
