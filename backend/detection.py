"""Turn window and process info into a game identity with a confidence score.

Window titles are hints. They are not visual proof of what is on screen.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .game_session import EMULATORS, GameSession, current_session

GENERIC_TITLES = {
    "retroarch", "emulationstation", "emulationstation de", "snes9x", "mesen",
    "project64", "dolphin", "pcsx2", "mame", "ppsspp", "cemu", "yuzu", "ryujinx",
    "duckstation",
}

CORE_SYSTEMS = (
    ("snes9x", "snes"),
    ("bsnes", "snes"),
    ("higan", "snes"),
    ("mesen", "nes"),
    ("fceumm", "nes"),
    ("nestopia", "nes"),
    ("quicknes", "nes"),
    ("genesis plus", "genesis"),
    ("picodrive", "genesis"),
    ("blastem", "genesis"),
    ("genesis gx", "genesis"),
)

TITLE_SYSTEMS = (
    ("(snes)", "snes"),
    ("[snes]", "snes"),
    ("super famicom", "snes"),
    ("sfc", "snes"),
    ("(nes)", "nes"),
    ("[nes]", "nes"),
    ("famicom", "nes"),
    ("(genesis)", "genesis"),
    ("[genesis]", "genesis"),
    ("mega drive", "genesis"),
    ("megadrive", "genesis"),
    ("(md)", "genesis"),
)

EXE_SYSTEMS = {
    "snes9x.exe": "snes",
    "mesen.exe": "nes",
}

STRIP_SUFFIXES = (
    " - retroarch",
    " - snes9x",
    " - mesen",
    " - emulationstation",
)


@dataclass
class GameIdentity:
    title: str | None
    system: str | None
    confidence: float
    source: str
    uncertain: bool
    evidence: str
    executable: str | None = None
    window_title: str | None = None
    is_emulator: bool = False
    supported_platform: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def factual_line(self) -> str:
        if not self.supported_platform and self.source == "platform":
            return "Game window detection is only available on Windows. I do not know what is running."
        if self.is_emulator and not self.title:
            system = f" The system hint is {self.system}." if self.system else ""
            return f"An emulator is in front ({self.evidence}). I am not sure which game.{system}"
        if not self.title or self.uncertain:
            if self.title:
                return f"This might be {self.title}, but I am not certain. Source: {self.source}."
            return "I do not have a confident game identification."
        if self.source == "vision":
            return f"A vision model reports {self.title} with confidence {self.confidence:.2f}. That still needs a look at the real screen on your PC."
        if self.source == "window_title+vision":
            return f"The window title and the vision model both point to {self.title}."
        return f"The window title says {self.title}. I have not visually confirmed it."

    def overlay_theme(self) -> str | None:
        if self.system in {"nes", "snes", "genesis"} and self.confidence >= 0.45:
            return self.system
        return None


def _clean_title(title: str) -> str:
    cleaned = " ".join(title.split())
    lowered = cleaned.lower()
    for suffix in STRIP_SUFFIXES:
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            lowered = cleaned.lower()
    return cleaned.strip(" -")


def _system_from_text(text: str) -> str | None:
    lowered = text.lower()
    for needle, system in CORE_SYSTEMS:
        if needle in lowered:
            return system
    for needle, system in TITLE_SYSTEMS:
        if needle in lowered:
            return system
    return None


def parse_snapshot(session: GameSession, extra_emulators: list[dict] | None = None) -> GameIdentity:
    extras = {}
    for item in extra_emulators or []:
        exe = str(item.get("exe") or "").strip().lower()
        if exe:
            extras[exe] = str(item.get("name") or exe)
    if not session.supported_platform:
        return GameIdentity(None, None, 0.0, "platform", True,
                            "non-Windows host", supported_platform=False)
    if not session.active_window:
        return GameIdentity(None, None, 0.0, "window", True, "no foreground window",
                            supported_platform=True)
    executable = (session.executable or "").lower()
    known = executable in EMULATORS or executable in extras
    app = session.application or extras.get(executable)
    title_raw = session.title or ""
    system = EXE_SYSTEMS.get(executable) or _system_from_text(title_raw)
    cleaned = _clean_title(title_raw) if title_raw else ""
    generic = cleaned.lower() in GENERIC_TITLES or cleaned.lower() == (app or "").lower()
    game_title = None if generic or not cleaned else cleaned
    if game_title and system:
        confidence = 0.9
    elif game_title:
        confidence = 0.82
    elif system and known:
        confidence = 0.55
    elif known:
        confidence = 0.4
    else:
        confidence = 0.2
    uncertain = game_title is None or confidence < 0.8
    evidence = app or executable or "foreground window"
    return GameIdentity(
        title=game_title,
        system=system,
        confidence=confidence,
        source="window_title",
        uncertain=uncertain,
        evidence=evidence,
        executable=executable or None,
        window_title=title_raw or None,
        is_emulator=known,
        supported_platform=True,
    )


def merge_vision(identity: GameIdentity, guess: str | None, confidence: float) -> GameIdentity:
    """Combine a window identity with a vision guess. Low confidence does not upgrade facts."""
    if not guess or confidence < 0.7:
        return identity
    guess = " ".join(guess.split())[:80]
    if identity.title and identity.title.lower() == guess.lower() and confidence >= 0.7:
        return GameIdentity(
            identity.title, identity.system, min(0.95, max(identity.confidence, confidence)),
            "window_title+vision", False,
            identity.evidence + " plus vision",
            identity.executable, identity.window_title, identity.is_emulator, identity.supported_platform,
        )
    if identity.title and identity.title.lower() != guess.lower():
        # Disagree: stay uncertain and keep the window title as the stronger process fact.
        return GameIdentity(
            identity.title, identity.system, min(identity.confidence, 0.6),
            "window_title", True,
            f"window says {identity.title}; vision guessed {guess} at {confidence:.2f}",
            identity.executable, identity.window_title, identity.is_emulator, identity.supported_platform,
        )
    system = identity.system
    return GameIdentity(
        guess, system, confidence, "vision", confidence < 0.85,
        f"vision confidence {confidence:.2f}",
        identity.executable, identity.window_title, identity.is_emulator, identity.supported_platform,
    )


class Detector:
    def __init__(self, session_fn=None, extra_emulators: list[dict] | None = None):
        self.session_fn = session_fn or current_session
        self.extra_emulators = extra_emulators or []

    def detect(self) -> GameIdentity:
        return parse_snapshot(self.session_fn(), self.extra_emulators)
