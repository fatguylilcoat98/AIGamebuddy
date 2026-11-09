"""Local HTTP routes. They call the same Buddy session as the overlay."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import app_state
from .buddy_session import BuddySession
from .config_loader import load_config

router = APIRouter(prefix="/buddy", tags=["Buddy"])


class Settings(BaseModel):
    personality: str = "sassy"
    vision_enabled: bool = False
    speech_enabled: bool = True
    cooldown_seconds: float = Field(default=18.0, ge=0, le=600)


class TextInput(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


class ObserveInput(BaseModel):
    priority: int = Field(default=1, ge=0, le=10)
    question: str = Field(default="What is happening in this game?", min_length=1, max_length=500)


def _session() -> BuddySession:
    session = app_state.SESSION
    if session is None or not session.running:
        raise HTTPException(status_code=409, detail="Start a Buddy session first")
    return session


@router.get("/status")
def status():
    session = app_state.SESSION
    if session is None:
        return {"running": False}
    return session.hud()


@router.post("/start")
def start(settings: Settings):
    if app_state.SESSION is None:
        app_state.SESSION = BuddySession(load_config())
    session = app_state.SESSION
    if not session.running:
        session.start()
    result = session.set_personality(settings.personality)
    session.set_vision(settings.vision_enabled)
    session.speech_enabled = settings.speech_enabled
    session.brain.cooldown_seconds = settings.cooldown_seconds
    return {"running": True, "personality": session.personality, "detail": result.message}


@router.post("/stop")
def stop():
    session = app_state.SESSION
    if session is not None:
        session.close()
        app_state.SESSION = None
    return {"running": False}


@router.post("/say")
def say(body: TextInput):
    return _session().handle_text(body.text).to_dict()


@router.post("/observe")
def observe(body: ObserveInput):
    del body
    return _session().observe_once().to_dict()


@router.post("/settings")
def apply_settings(settings: Settings):
    session = _session()
    result = session.set_personality(settings.personality)
    session.set_vision(settings.vision_enabled)
    session.speech_enabled = settings.speech_enabled
    return {"ok": result.ok, "message": result.message, "hud": session.hud()}


@router.get("/memory")
def memory():
    return {"text": _session().memory.summary()}


@router.post("/memory/reset")
def memory_reset():
    return _session().reset_memory().to_dict()


@router.post("/memory/clear")
def memory_clear():
    return _session().clear_memory().to_dict()


@router.get("/audio/devices")
def audio_devices():
    return {"devices": _session().audio.devices()}
