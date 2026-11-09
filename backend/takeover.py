"""Hard permission gate for offline single-player control.

Opening the gate does not move a character. Input is a separate step and
reports failure until a real gamepad output is configured. Online and
competitive play is refused even if the player confirms offline.
"""
from __future__ import annotations

from dataclasses import dataclass

from .results import ActionResult

APPROVED_TAKEOVER = (
    {"id": "sf2", "names": ("street fighter ii", "street fighter 2", "sf2"),
     "note": "offline versus the computer"},
    {"id": "bass", "names": ("bassmasters", "bassmaster", "bass masters", "bass master"),
     "note": "offline fishing"},
)

APPROVED_COOP = (
    {"id": "double-dragon", "names": ("double dragon",)},
    {"id": "contra", "names": ("contra",)},
    {"id": "tmnt", "names": ("teenage mutant ninja turtles", "tmnt")},
)

ONLINE_MARKERS = (
    "netplay", "fightcade", "ranked", "online", "lobby", "matchmaking",
    "versus online", "wifi", "disconnected",
)


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    message: str
    game_id: str = ""
    mode: str = "spectator"

    def to_result(self) -> ActionResult:
        return ActionResult(self.allowed, self.message, reason="takeover_gate",
                            data={"game_id": self.game_id, "mode": self.mode})


def _hit(title: str, names: tuple[str, ...]) -> bool:
    lowered = title.lower()
    return any(name in lowered for name in names)


def _online(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in ONLINE_MARKERS)


def evaluate_gate(*, mode: str, game_title: str, window_title: str,
                  user_confirmed_offline: bool, enabled: bool) -> GateDecision:
    mode = mode if mode in {"takeover", "coop"} else "takeover"
    blob = f"{game_title} {window_title}".strip()
    if not enabled:
        return GateDecision(False, "I did not take control. Takeover is disabled in config.", mode=mode)
    if _online(blob):
        return GateDecision(
            False,
            "I did not take control. The title looks like online or netplay, and I will not automate that.",
            mode=mode,
        )
    if not user_confirmed_offline:
        return GateDecision(
            False,
            "I did not take control. Confirm this is an offline single-player game in the menu first.",
            mode=mode,
        )
    catalog = APPROVED_COOP if mode == "coop" else APPROVED_TAKEOVER
    match = next((item for item in catalog if _hit(blob, item["names"])), None)
    if match is None:
        shown = game_title or window_title or "this game"
        return GateDecision(
            False,
            f"I did not take control. {shown} is not on the approved offline {mode} list.",
            mode=mode,
        )
    if mode == "coop":
        message = (
            f"Permission granted for offline co-op in {match['id']} on RetroArch port 2. "
            "No input was sent. Gamepad output is not configured."
        )
    else:
        message = (
            f"Permission granted for {match['note']} ({match['id']}). "
            "No input was sent. Gameplay control is not implemented yet."
        )
    return GateDecision(True, message, game_id=match["id"], mode=mode)


class InputSink:
    """Placeholder output. It never claims a button was pressed."""

    def press(self, port: int, button: str, *, gate_open: bool) -> ActionResult:
        if not gate_open:
            return ActionResult(False, "The permission gate is closed, so I did not send input.",
                                reason="input_blocked")
        return ActionResult(
            False,
            f"No gamepad output is configured, so I did not press {button} on port {port}.",
            reason="input_unconfigured",
        )


class RetroArchCommandClient:
    """Optional UDP command sender. Disabled unless config turns it on."""

    def __init__(self, host: str, port: int, enabled: bool, send_fn=None):
        self.host = host or "127.0.0.1"
        self.port = int(port or 0)
        self.enabled = bool(enabled)
        self._send_fn = send_fn

    def send(self, command: str, *, requires_control: bool, gate_open: bool) -> ActionResult:
        if requires_control and not gate_open:
            return ActionResult(False, "The permission gate is closed, so I did not send that command.",
                                reason="command_blocked")
        if not self.enabled or not self.port:
            return ActionResult(
                False,
                "RetroArch network commands are disabled in config, so I did not send anything.",
                reason="command_disabled",
            )
        payload = command.strip()
        if not payload or any(ch in payload for ch in "\r\n"):
            return ActionResult(False, "I did not send a command. The command text was empty or invalid.",
                                reason="command_invalid")
        try:
            if self._send_fn is None:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sock.sendto(payload.encode("utf-8"), (self.host, self.port))
                finally:
                    sock.close()
            else:
                self._send_fn(self.host, self.port, payload.encode("utf-8"))
        except OSError as exc:
            return ActionResult(False, f"Could not reach RetroArch at {self.host}:{self.port}. Nothing was sent. {exc}",
                                reason="command_failed")
        return ActionResult(True, f"Sent {payload} to RetroArch at {self.host}:{self.port}.",
                            reason="command_sent", data={"command": payload})
