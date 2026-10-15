"""HTTP contract for preparing sources and resuming catalog titles."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.integrations import ServiceError
from app.playback import EPISODE_ID


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection_id: str = Field(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class FileSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: int = Field(ge=0, le=1000000)


class WatchingProgress(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    position: float = Field(ge=0, le=86400)
    duration: float = Field(gt=0, le=86400)

    @model_validator(mode="after")
    def within_duration(self):
        if self.position > self.duration:
            raise ValueError("Position exceeds duration")
        return self


def playback_routes(playback, linking, catalog, store):
    router = APIRouter()

    def identity(request):
        profile = linking.profile(request)
        return profile, linking.session(request, "profile")["token_hash"]

    def validate_title(media_id):
        episode = EPISODE_ID.fullmatch(media_id)
        catalog.validate_id(episode[1] if episode else media_id)
        if episode and (int(episode[2]) > 200 or not 1 <= int(episode[3]) <= 1000):
            raise ServiceError("Unknown episode.", 404)

    @router.post("/api/playback")
    def start(body: Selection, request: Request):
        return playback.start(*identity(request), body.selection_id)

    @router.get("/api/playback/{session}")
    def status(session: str, request: Request):
        return playback.status(*identity(request), session)

    @router.post("/api/playback/{session}/files")
    def choose_file(session: str, body: FileSelection, request: Request):
        return playback.status(*identity(request), session, body.file_id)

    @router.delete("/api/playback/{session}")
    def stop(session: str, request: Request):
        return playback.stop(*identity(request), session)

    @router.put("/api/playback/{session}/progress")
    def session_progress(session: str, body: WatchingProgress, request: Request):
        profile, owner = identity(request)
        viewing = playback.get(profile, owner, session)
        store.remember_watching(profile, viewing.media_id, viewing.choice.title)
        return store.save_playback(profile, viewing.media_id, body.position, body.duration)

    @router.api_route("/api/playback/{session}/stream", methods=["GET", "HEAD"])
    def stream(session: str, request: Request):
        return playback.relay(*identity(request), session, request.method, request.headers.get("range"))

    @router.get("/api/watching/{media_id}")
    def progress(media_id: str, request: Request):
        validate_title(media_id)
        return store.playback(linking.profile(request), media_id)

    @router.put("/api/watching/{media_id}")
    def save_progress(media_id: str, body: WatchingProgress, request: Request):
        validate_title(media_id)
        profile = linking.profile(request)
        title_id = EPISODE_ID.fullmatch(media_id)
        title = catalog.details(title_id[1] if title_id else media_id)
        store.remember_watching(profile, media_id, title)
        return store.save_playback(profile, media_id, body.position, body.duration)

    return router
