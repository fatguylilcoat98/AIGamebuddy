"""Buddy local API.

From the repository root:
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8766

The normal way to start everything is:
    python -m backend.launcher
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from . import app_state
from .buddy_api import router as buddy_router
from .buddy_api import stop
from .config_loader import load_config
from .game_capture import GameCapture
from .screen_capture import ScreenCapture

capture = ScreenCapture()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        stop()
        capture.close()


def _product() -> str:
    try:
        return str(load_config().get("product_name"))
    except Exception:
        return "Video Game Wingman — Powered by GNG AI"


app = FastAPI(title=_product(), version="0.3.0", lifespan=lifespan)
app.include_router(buddy_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": _product(), "character": "Buddy", "version": "0.3.0"}


@app.get("/monitors")
def monitors():
    try:
        return {"monitors": capture.monitors()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Monitor enumeration failed: {exc}") from exc


@app.get("/frame")
def frame(monitor: int = 1):
    """JPEG of the game window only. Never the desktop, and never drawn on the overlay."""
    del monitor
    session = app_state.SESSION
    own = set(getattr(session, "overlay_hwnds", set()) or set())
    if session is not None and not session.safety.capture_enabled:
        raise HTTPException(status_code=409, detail=f"Capture is stopped. {session.safety.reason}")
    try:
        grabbed = GameCapture(own_hwnds=own).snapshot()
    except Exception as exc:
        if session is not None:
            session.safety.note_error(str(exc))
        raise HTTPException(status_code=503, detail=f"Screen capture failed: {exc}") from exc
    if not grabbed:
        raise HTTPException(status_code=409, detail="No game window, so nothing was captured")
    _target, jpeg = grabbed
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
