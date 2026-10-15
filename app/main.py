"""Serve the TV UI, one local test video, and bounded diagnostic/progress APIs."""

import math
import posixpath
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import ROOT, Settings
from app.store import Store
from app.security import Vault
from app.integrations import Services, ServiceError
from app.catalog import Catalog
from app.routes import Linking, feature_routes
from app.playback import Playback
from app.playback_routes import playback_routes

TITLE_ID = "big-buck-bunny"


class Progress(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    position: float = Field(ge=0, le=86400)
    duration: float = Field(gt=0, le=86400)

    @model_validator(mode="after")
    def within_duration(self):
        if self.position > self.duration:
            raise ValueError("position must not exceed duration")
        return self


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(pattern=r"^[a-zA-Z0-9-]{1,64}$")
    kind: str = Field(pattern=r"^(capabilities|key|video|check|error)$")
    payload: dict[str, str | int | float | bool | None]

    @model_validator(mode="after")
    def bounded_payload(self):
        if len(self.payload) > 16:
            raise ValueError("too many diagnostic fields")
        for key, value in self.payload.items():
            if len(key) > 64 or (isinstance(value, str) and len(value) > 512):
                raise ValueError("diagnostic field too long")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("diagnostic values must be finite")
        return self


def create_app(settings: Settings | None = None, *, test_client: bool = False, transport=None, coco=None, media_transport=None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.data_dir)
    sealed=store.sealed_values()
    vault=Vault(settings.data_dir,require_existing=bool(sealed))
    for value in sealed:
        vault.open(value)  # Refuse a mismatched key before accepting any requests.
    services=Services(store,vault,transport)
    catalog=Catalog(store,services,settings.data_dir)
    linking=Linking(store,services,test_client=test_client)
    playback=Playback(services,store,coco=coco,transport=media_transport)

    @asynccontextmanager
    async def lifespan(app):
        yield
        playback.close()
        services.close()

    app = FastAPI(title="Vizio Media", docs_url=None, redoc_url=None, openapi_url=None,lifespan=lifespan)
    app.state.store = store
    app.state.settings = settings
    app.state.services=services
    app.state.catalog=catalog
    app.state.linking=linking
    app.state.playback=playback
    allowed_clients = {settings.bind_ip, settings.tv_ip, "127.0.0.1", "::1"}
    allowed_hosts = [settings.bind_ip, "localhost", "127.0.0.1", "[::1]"]
    if test_client:
        allowed_clients.add("testclient")
        allowed_hosts.append("testserver")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        headers={"Retry-After":str(error.retry_after)} if error.retry_after else None
        return JSONResponse({"detail":error.message,"retry_after":error.retry_after},status_code=error.status,headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # FastAPI's default includes submitted values, which could contain credentials.
        return JSONResponse({"detail":"Check the submitted fields.","fields":[".".join(str(p) for p in e["loc"]) for e in error.errors()]},status_code=422)

    @app.middleware("http")
    async def local_guard(request: Request, call_next):
        # Never trust X-Forwarded-For. Uvicorn is also run with proxy headers disabled.
        if not request.client or request.client.host not in allowed_clients:
            return JSONResponse({"detail": "Only the TV and this computer may access this test."}, status_code=403)
        guard_path=posixpath.normpath(request.url.path.replace("\\","/")).casefold()
        if guard_path.startswith("/api/admin/") or guard_path in {"/manage","/static/manage.html"}:
            try:
                linking.local(request)
            except HTTPException as error:
                return JSONResponse({"detail":error.detail},status_code=error.status_code)
        if request.method not in {"GET", "HEAD"}:
            if request.headers.get("x-vizio-media") != "1":
                return JSONResponse({"detail": "Missing application request header."}, status_code=403)
            origin = request.headers.get("origin")
            if origin:
                expected = urlsplit(str(request.url))
                actual = urlsplit(origin)
                if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
                    return JSONResponse({"detail": "Cross-origin writes are disabled."}, status_code=403)
            # Bound the body before FastAPI parses JSON, including chunked requests.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 8192:
                    return JSONResponse({"detail": "Request too large."}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; media-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if request.url.path in {"/","/manage","/static/manage.html"} or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def home():
        return FileResponse(ROOT / "web" / "index.html", media_type="text/html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.4.1", "media_ready": (settings.media_dir / "sample.mp4").is_file()}

    @app.get("/api/progress/{title_id}")
    def get_progress(title_id: str, request: Request):
        if title_id != TITLE_ID:
            raise HTTPException(404, "Unknown test title")
        return store.playback(linking.profile(request,required=False),title_id)

    @app.put("/api/progress/{title_id}")
    def save_progress(title_id: str, progress: Progress, request: Request):
        if title_id != TITLE_ID:
            raise HTTPException(404, "Unknown test title")
        return store.save_playback(linking.profile(request,required=False),title_id,progress.position,progress.duration)

    @app.post("/api/diagnostics", status_code=201)
    def log_diagnostic(event: Diagnostic):
        store.log(event.session_id, event.kind, event.payload)
        return {"saved": True}

    @app.get("/api/diagnostics")
    def diagnostics():
        return {"events": store.diagnostics()}

    @app.api_route("/media/sample.mp4", methods=["GET", "HEAD"])
    def sample():
        path = settings.media_dir / "sample.mp4"
        if not path.is_file():
            raise HTTPException(404, "Run scripts/download_sample.py to fetch the licensed test clip.")
        # Starlette FileResponse supports byte ranges without loading the film into memory.
        return FileResponse(path, media_type="video/mp4")

    app.include_router(feature_routes(store,services,catalog,linking,playback))
    app.include_router(playback_routes(playback,linking,catalog,store))
    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    return app
