"""Shared result objects. ok is True only when the action really happened."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ActionResult:
    ok: bool
    message: str
    text: str = ""
    spoken: bool = False
    emotion: str = "idle"
    reason: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelResult:
    text: str
    provider: str
    error: str = ""
    model: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text) and not self.error
