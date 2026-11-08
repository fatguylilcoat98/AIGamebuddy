"""AIGamebuddy local HTTP controller routes.

Include in the existing FastAPI server in main.py:
    from buddy_api import router
    app.include_router(router)

All endpoints are local-only when the server is bound to 127.0.0.1.
No microphone or screen capture begins until explicitly requested.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from buddy_controller import BuddyController

router = APIRouter(prefix="/buddy", tags=["Buddy"])
_controller: BuddyController | None = None
_state_lock = Lock()
_busy = Lock()


class Settings(BaseModel):
    personality: str = "sassy"
    vision_enabled: bool = False
    speech_enabled: bool = True
    cooldown_seconds: float = Field(default=25.0, ge=0, le=600)


class TextInput(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


class ObserveInput(BaseModel):
    priority: int = Field(default=1, ge=0, le=3)
    question: str = Field(default="What is happening in this game?", min_length=1, max_length=500)


def _get_controller() -> BuddyController:
    with _state_lock:
        if _controller is None:
            raise HTTPException(status_code=409, detail="Start a Buddy session first")
        return _controller


def _exclusive(action):
    if not _busy.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Buddy is busy; retry shortly")
    try:
        return action()
    finally:
        _busy.release()


@router.get("/status")
def status():
    with _state_lock:
        controller = _controller
        if controller is None:
            return {"running": False}
        return {
            "running": True,
            "personality": controller.dialogue.personality,
            "vision_enabled": controller.vision_enabled,
            "speech_enabled": controller.speech_enabled,
            "recording": bool(controller._ears and controller._ears.recording),
        }


@router.post("/start")
def start(settings: Settings):
    global _controller
    def action():
        global _controller
        with _state_lock:
            if _controller is not None:
                raise HTTPException(status_code=409, detail="Session already running; stop it first")
            try:
                _controller = BuddyController(**settings.model_dump())
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"running": True}
    return _exclusive(action)


@router.post("/stop")
def stop():
    global _controller
    def action():
        global _controller
        with _state_lock:
            controller = _controller
            _controller = None
        if controller is not None:
            controller.close()
        return {"running": False}
    return _exclusive(action)


@router.post("/talk/start")
def talk_start():
    def action():
        try:
            _get_controller().start_talking()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"recording": True}
    return _exclusive(action)


@router.post("/talk/finish")
async def talk_finish():
    return await run_in_threadpool(lambda: _exclusive(lambda: _get_controller().finish_talking().to_dict()))


@router.post("/say")
async def say(body: TextInput):
    return await run_in_threadpool(lambda: _exclusive(lambda: _get_controller().say_to_buddy(body.text).to_dict()))


@router.post("/observe")
async def observe(body: ObserveInput):
    return await run_in_threadpool(lambda: _exclusive(lambda: _get_controller().observe(priority=body.priority, question=body.question).to_dict()))


@router.post("/settings")
def update_settings(settings: Settings):
    """Update the live session after any in-flight operation finishes."""
    def action():
        controller = _get_controller()
        if settings.personality not in ("casual", "sassy", "extreme"):
            raise HTTPException(status_code=422, detail="Invalid personality")
        with controller._lock:
            controller.dialogue.personality = settings.personality
            controller.vision_enabled = settings.vision_enabled
            controller.speech_enabled = settings.speech_enabled
            controller.brain.cooldown_seconds = settings.cooldown_seconds
        return {"running": True, "personality": settings.personality,
                "vision_enabled": settings.vision_enabled,
                "speech_enabled": settings.speech_enabled}
    return _exclusive(action)
