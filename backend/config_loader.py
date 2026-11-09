"""Load Buddy configuration. Secrets stay in the environment, not in git."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = ROOT / "config" / "buddy.config.sample.json"
LOCAL_PATH = ROOT / "config" / "buddy.config.json"

DEFAULTS: dict[str, Any] = {
    "product_name": "Video Game Wingman — Powered by GNG AI",
    "banner_title": "GAME WINGMAN",
    "character_name": "Buddy",
    "personality": "sassy",
    "provider": "offline",
    "port": 8766,
    "ollama": {"base_url": "http://127.0.0.1:11434", "model": "llama3.2"},
    "meta": {
        "base_url": "https://api.meta.ai/v1",
        "model": "",
        "api_key_env": "BUDDY_META_API_KEY",
    },
    "openai_compatible": {
        "base_url": "",
        "model": "",
        "api_key_env": "BUDDY_CHAT_API_KEY",
    },
    "vision": {
        "provider": "none",
        "model": "",
        "base_url": "",
        "api_key_env": "BUDDY_VISION_API_KEY",
        "interval_seconds": 8,
        "enabled": False,
    },
    "voice": {"enabled": True, "volume": 80, "rate": 0, "output_device": "", "mute": False},
    "commentary": {"frequency": "normal", "cooldown_seconds": 18},
    "overlay": {
        "theme": "auto",
        "layout": "full",
        "corner": "bottom-right",
        "monitor": 1,
        "manage_emulator_window": True,
    },
    "retroarch": {
        "path": "",
        "command_host": "127.0.0.1",
        "command_port": 55355,
        "command_enabled": False,
    },
    "emulationstation": {"path": ""},
    "libraries": [],
    "extra_emulators": [],
    "takeover": {"enabled": False},
    "wake_word": False,
    "data_dir": "",
}


def strip_json_comments(text: str) -> str:
    """Remove // comments that are not inside strings."""
    out = []
    i = 0
    in_string = False
    escape = False
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Config:
    def __init__(self, data: dict[str, Any], path: Path | None, warnings: list[str]):
        self.data = data
        self.path = path
        self.warnings = list(warnings)

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


def default_data_dir(config: Config) -> Path:
    custom = str(config.get("data_dir") or "").strip()
    if custom:
        return Path(custom).expanduser()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "VideoGameWingman"
    return ROOT / "runtime"


def load_config(path: Path | None = None) -> Config:
    warnings: list[str] = []
    chosen = path
    raw: dict[str, Any] = {}
    if chosen is None:
        chosen = LOCAL_PATH if LOCAL_PATH.exists() else SAMPLE_PATH
    if chosen and Path(chosen).exists():
        text = Path(chosen).read_text(encoding="utf-8")
        raw = json.loads(strip_json_comments(text) or "{}")
        if not isinstance(raw, dict):
            raise ValueError(f"Config must be a JSON object: {chosen}")
    data = _deep_merge(DEFAULTS, raw)
    character = str(data.get("character_name") or "Buddy").strip() or "Buddy"
    if character.lower() == "zion":
        warnings.append("character_name Zion is not allowed. Using Buddy.")
        character = "Buddy"
    data["character_name"] = character
    product = str(data.get("product_name") or DEFAULTS["product_name"]).strip()
    data["product_name"] = product or DEFAULTS["product_name"]
    banner = str(data.get("banner_title") or "GAME WINGMAN").strip() or "GAME WINGMAN"
    data["banner_title"] = banner[:22]
    personality = str(data.get("personality") or "sassy").strip().lower()
    if personality == "regular":
        personality = "casual"
    data["personality"] = personality
    return Config(data, Path(chosen) if chosen else None, warnings)


def env_secret(name: str) -> str:
    if not name:
        return ""
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
        return ""
    return os.environ.get(name, "").strip()
