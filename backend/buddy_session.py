"""One Buddy session: memory, banter, voice, vision, and real commands."""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from pathlib import Path

from .actions import launch_process, search_games
from .audio_out import AudioOutput
from .banter import (
    angle_note,
    complete_slots,
    example_block,
    insults_player,
    known_slots,
    offline_variant,
    select_angle,
)
from .buddy_brain import BuddyBrain
from .commands import match_intent
from .config_loader import Config, default_data_dir
from .detection import Detector, merge_vision
from .emotions import EmotionDirector, parse_tags
from .memory_store import MemoryStore
from .novelty import NoveltyEngine, category_for, looks_like_callback
from .personality_pack import load_pack, normalize_personality
from .prompts import build_messages
from .providers import chat
from .results import ActionResult, ModelResult
from .takeover import InputSink, RetroArchCommandClient, evaluate_gate
from .capture_safety import OVERLAY_SIZE, SafetySwitch
from .window_layout import list_window_details, position_hwnd, strip_window_decorations, window_rect

log = logging.getLogger("buddy.session")

FREQUENCIES = ("off", "rare", "normal", "chatty")
FREQ_COOLDOWN = {"off": 3600, "rare": 40, "normal": 16, "chatty": 8}


class SystemClock:
    def unix(self) -> float:
        return time.time()

    def mono(self) -> float:
        return time.monotonic()


class _ConfigModel:
    def __init__(self, config: Config, transport=None):
        self.config = config
        self.transport = transport

    def complete(self, messages: list[dict]) -> ModelResult:
        return chat(self.config, messages, transport=self.transport)


class BuddySession:
    def __init__(self, config: Config, *, memory: MemoryStore | None = None, clock=None,
                 model=None, audio=None, detector=None, vision=None, rng=None,
                 process_runner=None, command_client=None):
        self.config = config
        self.clock = clock or SystemClock()
        self.character = str(config.get("character_name") or "Buddy")
        self.buddy_character = str(config.get("buddy_character") or "male")
        if self.buddy_character not in {"male", "female"}:
            self.buddy_character = "male"
        self.buddy_hidden = False
        self._ra_menu_open = False
        self.resting_direction = str(config.get("resting_direction") or "left")
        if self.resting_direction not in {"left", "right", "center"}:
            self.resting_direction = "left"
        self.product = str(config.get("product_name"))
        self.banner = str(config.get("banner_title") or "GAME WINGMAN")
        data_dir = default_data_dir(config)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = data_dir
        self.memory = memory or MemoryStore(data_dir / "buddy.sqlite3")
        self.model = model if model is not None else _ConfigModel(config)
        self.audio = audio if audio is not None else AudioOutput()
        self.detector = detector if detector is not None else Detector(
            extra_emulators=list(config.get("extra_emulators") or [])
        )
        self.vision = vision
        self.rng = rng or random.Random()
        self.process_runner = process_runner
        self.commands = command_client if command_client is not None else RetroArchCommandClient(
            str(config.get("retroarch", "command_host") or "127.0.0.1"),
            int(config.get("retroarch", "command_port") or 0),
            bool(config.get("retroarch", "command_enabled")),
        )
        self.input_sink = InputSink()
        self.novelty = NoveltyEngine(self.memory)
        self.emotion = EmotionDirector()
        self.brain = BuddyBrain(cooldown_seconds=float(config.get("commentary", "cooldown_seconds") or 16))
        self.personality = self._initial_personality()
        self.pack = load_pack(self.personality)
        self.frequency = str(config.get("commentary", "frequency") or "normal")
        if self.frequency not in FREQUENCIES:
            self.frequency = "normal"
        self.brain.cooldown_seconds = FREQ_COOLDOWN[self.frequency]
        self.volume = int(config.get("voice", "volume") or 80)
        self.muted = bool(config.get("voice", "mute"))
        self.speech_enabled = bool(config.get("voice", "enabled", default=True))
        self.output_device = str(config.get("voice", "output_device") or "")
        self.vision_enabled = bool(config.get("vision", "enabled"))
        self.theme_mode = str(config.get("overlay", "theme") or "snes")
        self.theme = self.theme_mode if self.theme_mode in {"nes", "snes", "genesis"} else "snes"
        self.layout = str(config.get("overlay", "layout") or "full")
        self.corner = str(config.get("overlay", "corner") or "bottom-right")
        self.manage_window = bool(config.get("overlay", "manage_emulator_window", default=True))
        self.offline_confirmed = False
        self.mode = "spectator"
        self.gate_open = False
        self.running = False
        self.closed = False
        self.session_id: int | None = None
        self.identity = self.detector.detect()
        self.last_text = ""
        self.last_reason = ""
        self.mouth = 0.0
        self._callbacks = 0
        self._vision_guess = None
        self._vision_confidence = 0.0
        self._lock = threading.Lock()
        self._ears = None
        self._layout_note = ""
        self.overlay_hwnds: set[int] = set()
        self.safety = SafetySwitch()
        self._last_capture = 0.0
        self._placed: tuple | None = None
        self.retroarch_notice = ""
        self.retroarch_pid: int | None = None
        self.retroarch_started_by_buddy = False
        self._retro_launch_started = False
        self.game_hole: tuple[int, int, int, int] | None = None
        self.retroarch_finder = None
        self.window_source = None
        self.rect_source = None
        self.window_positioner = None
        self.process_stopper = None
        self._borderless: set[int] = set()
        self._status_game = ""
        self._paused_since = None
        self._stuck_spoken = False
        self.status_query = None
        self.talk_mode = "hold"
        self.quiet_until_called = False
        self.anim_yaw = -0.92
        self._yaw_hold: tuple[float, float] | None = None
        self._next_glance = 0.0
        self._glance_until = 0.0
        self.current_rom = ""
        self.continue_on_launch = False
        self.toast = ""
        from .look_schedule import normalize_look_interval
        self.look_interval = normalize_look_interval(config.get("commentary", "look_interval_seconds"))
        self._last_look = 0.0
        self._look_busy = False
        self._look_started = 0.0
        self._last_said = 0.0
        from .frame_comment import FrameCommentator
        from .game_watch import GameWatch
        self._commentator = FrameCommentator()
        self._watch = GameWatch()
        self._script_lines: list[str] | None = None
        self._script_index = 0
        self.announcer = False
        self._booth_turn = "male"
        self._speaking_as = self.buddy_character
        self._load_ui()
        if os.environ.get("BUDDY_LOOK_SECONDS"):
            from .look_schedule import normalize_look_interval
            self.look_interval = normalize_look_interval(os.environ.get("BUDDY_LOOK_SECONDS"))

    def _initial_personality(self) -> str:
        saved = self.memory.get_profile("personality")
        raw = saved or str(self.config.get("personality") or "sassy")
        try:
            return normalize_personality(raw)
        except ValueError:
            return "sassy"

    def _ui_path(self) -> Path:
        return self.data_dir / "ui-state.json"

    def _load_ui(self) -> None:
        from .frame_migration import migrate_saved_theme, migrate_setup_state
        path = self._ui_path()
        data: dict = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}
        data = migrate_saved_theme(data, self.data_dir / "frame-revision.txt")
        try:
            from .setup_flow import state_path
            migrate_setup_state(state_path())
        except Exception:
            log.info("Setup state was left as it is.")
        if not data:
            self.theme = "snes"
            self.theme_mode = "snes"
            return
        self.volume = int(data.get("volume", self.volume))
        self.muted = bool(data.get("muted", self.muted))
        self.layout = data.get("layout", self.layout)
        self.corner = data.get("corner", self.corner)
        self.output_device = str(data.get("output_device", self.output_device))
        self.frequency = data.get("frequency", self.frequency)
        if self.frequency in FREQ_COOLDOWN:
            self.brain.cooldown_seconds = FREQ_COOLDOWN[self.frequency]
        self.vision_enabled = bool(data.get("vision_enabled", self.vision_enabled))
        self.offline_confirmed = bool(data.get("offline_confirmed", False))
        if data.get("theme_mode"):
            self.theme_mode = data["theme_mode"]
        if data.get("theme") in {"nes", "snes", "genesis"}:
            self.theme = data["theme"]
        if data.get("buddy_character") in {"male", "female"}:
            self.buddy_character = data["buddy_character"]
        if data.get("resting_direction") in {"left", "right", "center"}:
            self.resting_direction = data["resting_direction"]
        if data.get("personality"):
            try:
                self.personality = normalize_personality(str(data["personality"]))
                self.pack = load_pack(self.personality)
            except ValueError:
                pass
        self.buddy_hidden = bool(data.get("buddy_hidden", False))
        if data.get("talk_mode") in {"hold", "wake"}:
            self.talk_mode = data["talk_mode"]
        self.quiet_until_called = bool(data.get("quiet_until_called", False))
        if "look_interval" in data:
            from .look_schedule import normalize_look_interval
            self.look_interval = normalize_look_interval(data.get("look_interval"))
        self.announcer = bool(data.get("announcer", False))

    def _save_ui(self) -> None:
        payload = {
            "volume": self.volume, "muted": self.muted, "layout": self.layout,
            "corner": self.corner, "output_device": self.output_device,
            "frequency": self.frequency, "vision_enabled": self.vision_enabled,
            "offline_confirmed": self.offline_confirmed, "theme_mode": self.theme_mode,
            "theme": self.theme, "personality": self.personality,
            "buddy_character": self.buddy_character,
            "resting_direction": self.resting_direction,
            "buddy_hidden": self.buddy_hidden,
            "talk_mode": self.talk_mode,
            "quiet_until_called": self.quiet_until_called,
            "look_interval": self.look_interval,
            "announcer": self.announcer,
        }
        try:
            self._ui_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not save UI state: %s", exc)

    def start(self) -> ActionResult:
        with self._lock:
            if self.closed:
                return ActionResult(False, "Buddy is closed.", reason="closed")
            if self.running:
                return ActionResult(True, f"{self.character} is already running.", reason="already_running")
            now = self.clock.unix()
            self.session_id = self.memory.start_session(now, self.personality)
            self.running = True
            from .talk_input import start_wake_listener
            heard = start_wake_listener(self, lambda: self.closed)
            if heard != "listening":
                log.info("Mic helper is not installed, so Buddy cannot hear the room yet. Talking out loud still works once it is.")
            self.memory.set_profile("personality", self.personality, "system", now)
        greeting = self._maybe_greet()
        message = f"{self.character} is running."
        return ActionResult(True, message, text=greeting.text, spoken=greeting.spoken,
                            emotion=greeting.emotion, reason="started")

    def close(self) -> None:
        with self._lock:
            if self.closed:
                return
            self.closed = True
            self.running = False
            self.safety.disable("session closed", quiet=True)
            session_id = self.session_id
        if session_id is not None:
            self.memory.end_session(session_id, self.clock.unix())
        if self._ears is not None:
            self._ears.cancel()
        self.audio.stop()
        self._release_retroarch()
        self._save_ui()

    def hud(self) -> dict:
        with self._lock:
            emotion = self.emotion.snapshot(self.clock.mono())
            return {
                "running": self.running,
                "character": self.character,
                "buddy_character": self.buddy_character,
                "buddy_hidden": self.buddy_hidden,
                "resting_direction": self.resting_direction,
                "product": self.product,
                "banner": self.banner,
                "personality": self.personality,
                "theme": self.theme,
                "theme_mode": self.theme_mode,
                "layout": self.layout,
                "corner": self.corner,
                "volume": self.volume,
                "muted": self.muted,
                "frequency": self.frequency,
                "vision_enabled": self.vision_enabled,
                "expression": emotion["expression"],
                "from_expression": emotion["from_expression"],
                "expression_blend": emotion["expression_blend"],
                "gaze": emotion["gaze"],
                "mouth": self.mouth,
                "yaw": self.anim_yaw,
                "announcer": self.announcer,
                "speaking_as": getattr(self, "_speaking_as", self.buddy_character),
                "talk_mode": self.talk_mode,
                "quiet_until_called": self.quiet_until_called,
                "toast": self.toast,
                "last_text": self.last_text,
                "last_reason": self.last_reason,
                "game": self.identity.factual_line(),
                "mode": self.mode,
                "gate_open": self.gate_open,
                "offline_confirmed": self.offline_confirmed,
                "layout_note": self._layout_note,
                "recording": bool(self._ears and self._ears.recording),
            }

    def hold_pose(self, yaw: float, expression: str, mouth: float = 0.0, seconds: float = 6) -> None:
        """Hold a head angle long enough for a screenshot. Speech still wins after it."""
        moment = self.clock.mono()
        self._yaw_hold = (float(yaw), moment + seconds)
        self.anim_yaw = float(yaw)
        self.mouth = mouth
        self.emotion.set_expression(expression, moment, seconds)

    def tick_animation(self, now: float | None = None) -> None:
        moment = self.clock.mono() if now is None else now
        speaking = bool(getattr(self.audio, "speaking", False))
        self.emotion.tick(moment, speaking=speaking, mouth=self.mouth)
        if speaking:
            self.emotion.set_expression("talk", moment, 0.5)
            self.mouth = self.mouth if self.mouth > 0 else 0.35
        held = self._yaw_hold
        if held and moment < held[1] and not speaking:
            target = held[0]
        elif speaking:
            target = 0.0
        elif moment < self._glance_until:
            target = -0.2
        else:
            target = -0.92 if self.resting_direction != "right" else 0.9
            if self._next_glance <= 0:
                self._next_glance = moment + 8.0
            if moment >= self._next_glance:
                self._glance_until = moment + 0.85
                self._next_glance = moment + 8.0 + self.rng.random() * 7.0
                target = -0.2
        from .hologram import step_yaw
        self.anim_yaw = step_yaw(self.anim_yaw, target, 0.14)

    def refresh_identity(self):
        found = self.detector.detect()
        if self._vision_guess:
            found = merge_vision(found, self._vision_guess, self._vision_confidence)
        self.identity = found
        if self.theme_mode == "auto":
            theme = found.overlay_theme()
            if theme:
                self.theme = theme
        return found

    def handle_text(self, text: str) -> ActionResult:
        if self.closed:
            return ActionResult(False, "Buddy is closed.", reason="closed")
        cleaned = (text or "").strip()
        if not cleaned:
            return ActionResult(False, "I did not hear anything.", reason="empty")
        self.memory.add_message(unix=self.clock.unix(), role="player", text=cleaned, source="user_reported")
        helped = self._offer_help(cleaned)
        if helped is not None:
            return helped
        intent = match_intent(cleaned)
        if intent:
            result = self._dispatch(intent)
            if result.message and not result.text and result.reason != "memory":
                spoken = self._play(result.message)
                return ActionResult(result.ok, result.message, text=result.message, spoken=spoken,
                                    reason=result.reason, data=result.data, emotion=result.emotion)
            return result
        note = ""
        if self._helper_ready():
            note = self._screen_note()
        heard = self._reply_from_watch(cleaned)
        if heard is not None:
            return heard
        memory = self._watch.context()
        if memory:
            note = f"{note}\n{memory}".strip() if note else memory
        return self._banter(
            player_text=cleaned, spontaneous=False, event="", priority=2, direct=True, observation=note,
        )

    def _dispatch(self, intent) -> ActionResult:
        name = intent.name
        if name == "stop_insults":
            self.memory.set_profile("insults_allowed", "false", "user_reported", self.clock.unix())
            self.emotion.set_expression("idle", self.clock.mono(), 2)
            return self._show("I will stop insulting you. I can still help.", emotion="idle", category="status")
        if name == "allow_insults":
            self.memory.set_profile("insults_allowed", "true", "user_reported", self.clock.unix())
            return self._show("Insults are allowed again. I will still skip a joke that I have already used.",
                              category="status", emotion="smug")
        if name == "mute":
            return self.set_mute(True)
        if name == "unmute":
            return self.set_mute(False)
        if name == "volume_set":
            return self.set_volume(int(intent.args["level"]))
        if name == "volume_step":
            delta = 10 if intent.args["direction"] == "up" else -10
            return self.set_volume(self.volume + delta)
        if name == "silence":
            self.brain.mark_spoken("player asked for quiet", now=self.clock.mono())
            self.brain.cooldown_seconds = max(self.brain.cooldown_seconds, 60)
            return self._show("I'll stay quiet for a bit.", category="status", emotion="idle")
        if name == "quiet_until_called":
            return self.be_quiet_until_called()
        if name == "talk_less":
            return self.talk_less()
        if name == "talk_more":
            return self.talk_more()
        if name == "frequency":
            return self.set_frequency(intent.args["level"])
        if name == "layout_compact":
            return self.set_layout("compact")
        if name == "layout_full":
            return self.set_layout("full")
        if name == "theme_nes":
            return self.set_theme("nes")
        if name == "theme_snes":
            return self.set_theme("snes")
        if name == "theme_genesis":
            return self.set_theme("genesis")
        if name == "personality":
            return self.set_personality(intent.args["name"])
        if name == "character_male":
            return self.set_buddy_character("male")
        if name == "character_female":
            return self.set_buddy_character("female")
        if name == "rest_left":
            return self.set_resting_direction("left")
        if name == "rest_right":
            return self.set_resting_direction("right")
        if name == "rest_center":
            return self.set_resting_direction("center")
        if name == "memory_view":
            return ActionResult(True, self.memory.summary(), reason="memory")
        if name == "memory_reset":
            return self.reset_memory()
        if name == "memory_clear":
            return self.clear_memory()
        if name == "observe":
            if "playing" in intent.name:
                pass
            return self.observe_once() if name == "observe" else self._identify()
        if name == "open_retroarch":
            return self._launch_retroarch([])
        if name == "open_es":
            return launch_process(str(self.config.get("emulationstation", "path") or ""), runner=self.process_runner)
        if name == "emulator_menu":
            return self.commands.send("MENU_TOGGLE", requires_control=False, gate_open=False)
        if name == "find_game":
            return search_games(list(self.config.get("libraries") or []), intent.args["query"])
        if name == "load_game":
            return self.load_game(intent.args["query"])
        if name == "takeover":
            return self.request_takeover()
        if name == "coop":
            return self.request_coop()
        if name == "release":
            return self.release_control()
        return ActionResult(False, "I recognized a command but I do not have an action for it.", reason="unhandled")

    def _identify(self) -> ActionResult:
        self.refresh_identity()
        return ActionResult(True, self.identity.factual_line(), reason="identity")

    def set_buddy_character(self, value: str) -> ActionResult:
        from .hologram import normalize_character
        chosen = normalize_character(value)
        if chosen is None:
            return ActionResult(False, "I did not change the character. Choose male or female.",
                                reason="bad_character")
        self.buddy_character = chosen
        self._save_ui()
        label = "Male" if chosen == "male" else "Female"
        return self._show(f"Buddy character is {label}. The name is still {self.character}.",
                          category="status", emotion="smile")

    def set_resting_direction(self, value: str) -> ActionResult:
        from .hologram import normalize_resting
        chosen = normalize_resting(value)
        if chosen is None:
            return ActionResult(False, "I did not change the resting direction. Choose left, right, or center.",
                                reason="bad_rest")
        self.resting_direction = chosen
        self._save_ui()
        return self._show(f"Resting direction is {chosen}.", category="status", emotion="smile")

    def set_personality(self, name: str) -> ActionResult:
        try:
            chosen = normalize_personality(name)
        except ValueError as exc:
            return ActionResult(False, str(exc), reason="bad_personality")
        self.personality = chosen
        self.pack = load_pack(chosen)
        self.memory.set_profile("personality", chosen, "user_reported", self.clock.unix())
        self._save_ui()
        return self._show(f"Personality is now {self.pack.display_name}. I will help the same either way.",
                          category="status", emotion="smile")

    def set_volume(self, level: int) -> ActionResult:
        self.volume = max(0, min(100, int(level)))
        self._save_ui()
        if self.volume == 0:
            return self._show("Volume is 0, so I will not play audio.", category="status")
        return self._show(f"Volume is {self.volume}.", category="status")

    def stop_buddy(self) -> ActionResult:
        """Hide the hologram and stop the voice. The game keeps running."""
        self.buddy_hidden = True
        self.muted = True
        self.audio.stop()
        self._save_ui()
        return ActionResult(True, "Buddy is quiet and hidden. The game is still running.",
                            reason="buddy_stopped")

    def start_buddy(self) -> ActionResult:
        """Bring the hologram and the voice back."""
        self.buddy_hidden = False
        self.muted = False
        self.running = True
        self._save_ui()
        return self._show("I'm here.", category="status", emotion="smile")

    def set_look_interval(self, seconds: int) -> ActionResult:
        from .look_schedule import LOOK_INTERVALS, normalize_look_interval
        chosen = normalize_look_interval(seconds)
        if int(seconds) not in LOOK_INTERVALS:
            return ActionResult(False, "I did not change how often I look.", reason="bad_look_interval")
        self.look_interval = chosen
        self._save_ui()
        label = "1 minute" if chosen == 60 else f"{chosen} seconds"
        return self._show(f"I'll look at the game every {label}.", category="status", emotion="talk")

    def maybe_look_at_game(self, now: float | None = None) -> None:
        """Capture the game window on the timer. Skip when a look is still running."""
        import threading
        from .look_schedule import look_due
        moment = self.clock.mono() if now is None else now
        decision = look_due(
            last=self._last_look, now=moment, interval=self.look_interval, busy=self._look_busy,
        )
        if decision == "wait":
            return
        if decision == "skip":
            if moment - self._look_started > 12:
                log.warning("Watchdog restarted a stuck look")
                self._look_busy = False
            else:
                log.info("Skipped a look; the previous one is still running")
                return
        log.info("Look tick interval=%ss", self.look_interval)
        self._last_look = moment
        self._look_started = moment
        self._look_busy = True
        threading.Thread(target=self._look_worker, name="buddy-look", daemon=True).start()

    def _next_scripted_frame(self) -> str:
        """A CI match script, one frame per look, so the log can show a comeback."""
        path = os.environ.get("BUDDY_FRAME_SCRIPT") or ""
        if not path:
            return ""
        if self._script_lines is None:
            try:
                self._script_lines = [
                    line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()
                ]
            except OSError:
                self._script_lines = []
        if self._script_index >= len(self._script_lines or []):
            return ""
        line = self._script_lines[self._script_index]
        self._script_index += 1
        return line

    def _model_is_live(self) -> bool:
        provider = str(self.config.get("provider") or "offline").strip().lower()
        return provider not in {"", "offline", "none", "off"}

    def _ask_follow(self, prompt: str) -> str:
        """One short reply from the configured chat model. Offline stays empty."""
        if not self._model_is_live():
            return ""
        try:
            from .emotions import parse_tags
            from .personas import persona_prompt
            result = self.model.complete([
                {"role": "system", "content": persona_prompt(self.personality)},
                {"role": "user", "content": prompt},
            ])
            text = (getattr(result, "text", "") or "").strip()
            if not text:
                return ""
            parsed = parse_tags(text)
            text = (parsed.text or "").strip() or text
        except Exception:
            log.info("Follow model did not answer")
            return ""
        return text[:220]

    def comment_on_frame(self, observation: str) -> str:
        """Remember the frame, compare it with the last one, and say what changed."""
        change = self._watch.update(observation)
        log.info("Game memory %s", self._watch.context())
        log.info("Frame change: %s", change or "none")
        if not (observation or "").strip():
            line, made = self._commentator.line("", self.personality, have_frame=False)
            self._say_line(line, made)
            return line
        line, made = self._watch.comment(
            self.personality, ask=self._ask_follow, history=self._watch.said,
        )
        self._say_line(line, made)
        return line

    def _reply_from_watch(self, text: str):
        """Answer Chris from the match memory, using the model when it is on."""
        if self._model_is_live():
            spoken = self._ask_follow(self._watch.player_prompt(text, self.personality))
            if spoken:
                log.info("Spoke source=llm voice=%s: %s", self.buddy_character, spoken)
                return self._show(spoken, category="chat", emotion="talk")
        local = self._watch.answer(text, self.personality)
        if not local:
            return None
        return self._show(local, category="chat", emotion="talk")

    def _look_worker(self) -> None:
        try:
            from .frame_comment import describe_frame
            scripted = self._next_scripted_frame()
            captured = None if scripted else self._capture_game_window()
            observation = scripted
            source = "follow" if scripted else "frame"
            if scripted:
                log.info("Look tick scripted frame: %s", scripted)
            elif captured is None:
                log.info("Looked at the game. interval=%ss captured=no", self.look_interval)
            else:
                _width, _height, jpeg = captured
                log.info(
                    "Looked at the game. interval=%ss captured=%sx%s bytes=%s",
                    self.look_interval, _width, _height, len(jpeg),
                )
                try:
                    observation = describe_frame(jpeg)
                except Exception:
                    observation = ""
                if self._helper_ready():
                    note = self._screen_note()
                    if note:
                        observation = note
                        source = "vision"
            if observation:
                self.comment_on_frame(observation)
            else:
                line, made = self._commentator.line("", self.personality, have_frame=False)
                if source == "vision":
                    made = "vision"
                self._say_line(line, made)
        except Exception:
            log.exception("Look at the game failed")
        finally:
            self._look_busy = False

    def _say_line(self, text: str, source: str) -> None:
        if self.frequency == "off" or self.quiet_until_called:
            log.info("Look tick held. frequency=%s quiet=%s", self.frequency, self.quiet_until_called)
            return
        gap = 5 if os.environ.get("BUDDY_SMOKE_CHATTY") == "1" else {"chatty": 6, "normal": 12, "rare": 25}.get(self.frequency, 12)
        now = self.clock.mono()
        if getattr(self.audio, "speaking", False):
            log.info("Look tick held. someone is still talking")
            return
        scripted = source == "follow" and bool(os.environ.get("BUDDY_FRAME_SCRIPT"))
        if not scripted and now - self._last_said < gap:
            log.info("Look tick held. next line in %.0fs", gap - (now - self._last_said))
            return
        self._last_said = now
        if self.announcer:
            self._booth_turn = "female" if self._booth_turn == "male" else "male"
            self._speaking_as = self._booth_turn
            role = "play-by-play" if self._booth_turn == "male" else "color"
            text = f"{role}: {text}"
        else:
            self._speaking_as = self.buddy_character
        log.info("Spoke source=%s voice=%s: %s", source, self._speaking_as, text)
        self._append_spoken(text, source)
        import threading
        worker = threading.Thread(target=self._play, args=(text,), name="buddy-say", daemon=True)
        worker.start()
        worker.join(8)
        if worker.is_alive():
            log.warning("Speech timed out. Buddy will keep talking.")
            try:
                self.audio.stop()
            except Exception:
                pass

    def _append_spoken(self, text: str, source: str) -> None:
        path = self.data_dir / "spoken.log"
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{stamp}\tsource={source}\tvoice={getattr(self, '_speaking_as', '')}\t{text}\n")
        except OSError:
            log.warning("Could not write spoken.log")

    def set_announcer(self, enabled: bool) -> ActionResult:
        self.announcer = bool(enabled)
        self._save_ui()
        line = "We're on the call together." if self.announcer else "Just me again."
        return self._show(line, category="status", emotion="talk")

    def _offer_help(self, text: str) -> ActionResult | None:
        lower = text.lower()
        if not any(word in lower for word in (
            "stuck", "where do i", "where should", "cheat", "code", "konami", "look it up", "how do i", "i'm lost", "im lost",
        )):
            return None
        from .game_help import lookup_help
        game = self._status_game or getattr(self.identity, "title", "") or ""
        line, source = lookup_help(game, text)
        log.info("Help source=%s game=%s", source, game)
        self._speaking_as = self.buddy_character
        self._append_spoken(line, "help")
        log.info("Spoke source=help: %s", line)
        return self._show(line, category="help", emotion="talk")

    def _capture_game_window(self):
        """JPEG of the emulator window only. The frame around it is not included."""
        try:
            from .game_capture import GameCapture
            shot = GameCapture(own_hwnds=set(self.overlay_hwnds)).snapshot()
        except Exception:
            return None
        if not shot:
            return None
        target, jpeg = shot
        rect = target.window_rect or (0, 0, 0, 0)
        width = max(0, int(rect[2]) - int(rect[0])) if len(rect) == 4 else 0
        height = max(0, int(rect[3]) - int(rect[1])) if len(rect) == 4 else 0
        if width < 1 or height < 1:
            width = len(jpeg)
            height = 1
        return width, height, jpeg

    def set_talk_mode(self, mode: str) -> ActionResult:
        if mode not in {"hold", "wake"}:
            return ActionResult(False, "I did not change how you talk to me.", reason="bad_talk_mode")
        self.talk_mode = mode
        self._save_ui()
        if mode == "hold":
            text = "Hold the two shoulder buttons, or hold F9, when you want to talk."
        else:
            text = "Say Hey Buddy when you want me. F9 still works."
        return self._show(text, category="status", emotion="talk")

    def set_talk_amount(self, level: str) -> ActionResult:
        mapped = {"ask": "off", "sometimes": "normal", "a lot": "chatty"}.get(level, level)
        if mapped not in {"off", "normal", "chatty", "rare"}:
            return ActionResult(False, "I did not change how much I talk.", reason="bad_talk_amount")
        self.quiet_until_called = False
        self.frequency = mapped
        self.brain.cooldown_seconds = FREQ_COOLDOWN.get(mapped, 16)
        self._save_ui()
        labels = {"off": "only when you ask", "rare": "sometimes", "normal": "sometimes", "chatty": "a lot"}
        return self._show(f"I'll talk {labels.get(mapped, mapped)}.", category="status", emotion="talk")

    def talk_less(self) -> ActionResult:
        order = ["chatty", "normal", "off"]
        if self.frequency not in order:
            self.frequency = "normal"
        index = min(len(order) - 1, order.index(self.frequency) + 1)
        self.frequency = order[index]
        if self.frequency == "off":
            self.quiet_until_called = True
        self._save_ui()
        self.brain.cooldown_seconds = FREQ_COOLDOWN.get(self.frequency, 18)
        return self._show("I'll talk less.", category="status", emotion="idle")

    def talk_more(self) -> ActionResult:
        self.quiet_until_called = False
        order = ["off", "normal", "chatty"]
        current = self.frequency if self.frequency in order else "normal"
        self.frequency = order[min(len(order) - 1, order.index(current) + 1)]
        self._save_ui()
        self.brain.cooldown_seconds = FREQ_COOLDOWN.get(self.frequency, 12)
        return self._show("I can talk more.", category="status", emotion="smile")

    def be_quiet_until_called(self) -> ActionResult:
        self.quiet_until_called = True
        self._save_ui()
        return self._show("I'll be quiet until you call me.", category="status", emotion="idle")

    def has_continue(self, rom: str) -> bool:
        from .save_slots import has_continue, state_directory
        return has_continue(state_directory(self.data_dir), rom)

    def save_spot(self, slot: int) -> ActionResult:
        from .retroarch_menu import send_commands
        from .save_slots import remember_save, save_commands, save_line, state_directory
        if not self.commands.enabled:
            self.commands.enabled = True
        error = send_commands(self.commands, save_commands(slot), pause=0.02, sleep=lambda _s: None)
        if error:
            self.toast = "I could not save your spot."
            return ActionResult(False, self.toast, reason="save_failed")
        folder = state_directory(self.data_dir)
        remember_save(folder, self.current_rom or self._status_game or "game", slot)
        self.toast = f"Saved your spot in slot {slot}."
        line = save_line(self.personality, slot)
        return self._show(line, category="status", emotion="smile")

    def load_spot(self, slot: int) -> ActionResult:
        from .retroarch_menu import send_commands
        from .save_slots import has_slot, load_commands, load_line, state_directory
        rom = self.current_rom or self._status_game or "game"
        if not has_slot(state_directory(self.data_dir), rom, slot) and slot != 0:
            self.toast = f"Slot {slot} is empty."
            return ActionResult(False, self.toast, reason="empty_slot")
        if not self.commands.enabled:
            self.commands.enabled = True
        error = send_commands(self.commands, load_commands(slot), pause=0.02, sleep=lambda _s: None)
        if error:
            self.toast = "I could not load that spot."
            return ActionResult(False, self.toast, reason="load_failed")
        self.toast = f"Loaded slot {slot}."
        return self._show(load_line(slot), category="status", emotion="talk")

    def _autosave_continue(self) -> None:
        rom = self.current_rom or self._status_game
        if not rom or not self.commands.enabled:
            return
        from .retroarch_menu import send_commands
        from .save_slots import remember_save, save_commands, state_directory
        error = send_commands(self.commands, save_commands(0), pause=0.01, sleep=lambda _s: None)
        if error:
            return
        remember_save(state_directory(self.data_dir), rom, 0)
        if os.name == "nt":
            import time
            time.sleep(0.35)

    def _helper_ready(self) -> bool:
        if os.environ.get("BUDDY_CHAT_API_KEY") or os.environ.get("BUDDY_META_API_KEY"):
            return True
        try:
            from .setup_flow import SECRET_NAME, WindowsVault
            return bool(WindowsVault().get(SECRET_NAME))
        except Exception:
            return False

    def _screen_note(self) -> str:
        """One look at the game when an online helper key is stored."""
        was = self.vision_enabled
        self.vision_enabled = True
        try:
            seen = self.observe_once(speak=False)
        finally:
            self.vision_enabled = was
        if not seen.ok:
            return ""
        return str((seen.data or {}).get("summary") or seen.message or "")

    def close_game(self) -> ActionResult:
        """Close RetroArch. The overlay stays. The continue spot is saved first."""
        self._autosave_continue()
        self._force_close_retroarch()
        return ActionResult(True, "The game is closed. Buddy is still here.", reason="game_closed")

    def exit_to_desktop(self, list_pids=None, killer=None, stop_self=None) -> ActionResult:
        """Close RetroArch and every Buddy process."""
        from .process_exit import kill_pids, list_buddy_pids
        self._autosave_continue()
        self._force_close_retroarch()
        pids = list_buddy_pids() if list_pids is None else list(list_pids())
        mine = os.getpid()
        others = [int(pid) for pid in pids if int(pid) and int(pid) != mine]
        (kill_pids if killer is None else killer)(others)
        try:
            self.close()
        except Exception:
            log.exception("Close during exit failed")
        if stop_self is None:
            os._exit(0)
        stop_self()
        return ActionResult(True, "Buddy has left the desktop.", reason="exited")

    def open_retroarch_menu(self) -> ActionResult:
        from .retroarch_menu import retroarch_settings_commands, send_commands
        if not self.commands.enabled:
            self.commands.enabled = True
        error = send_commands(self.commands, retroarch_settings_commands(), pause=0.05)
        if error:
            return ActionResult(False, error, reason="menu_failed")
        self._ra_menu_open = not self._ra_menu_open
        return ActionResult(True, "RetroArch's menu is open." if self._ra_menu_open else "RetroArch's menu is closed.",
                            reason="retroarch_menu")

    def open_controller_setup(self) -> ActionResult:
        from .retroarch_menu import controller_setup_commands, send_commands
        if not self.commands.enabled:
            self.commands.enabled = True
        commands = controller_setup_commands(menu_already_open=self._ra_menu_open)
        error = send_commands(self.commands, commands, pause=0.06)
        if error:
            return ActionResult(False, error, reason="controller_failed")
        self._ra_menu_open = True
        return ActionResult(True, "The controller page is open.", reason="controller_setup")

    def _force_close_retroarch(self) -> None:
        """End the RetroArch Buddy started, even when close-on-quit is off."""
        pid = self.retroarch_pid
        self._retro_launch_started = False
        self.retroarch_started_by_buddy = False
        self._ra_menu_open = False
        if not pid:
            return
        if os.name != "nt":
            return
        try:
            import subprocess
            subprocess.Popen(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            logging.getLogger("buddy.retroarch").info("Could not close RetroArch: %s", exc)

    def set_mute(self, muted: bool) -> ActionResult:
        self.muted = bool(muted)
        if self.muted:
            self.audio.stop()
        self._save_ui()
        text = "Muted. I will still show lines, but I will not play them." if self.muted else "Unmuted."
        return self._show(text, category="status", speak=not self.muted)

    def set_frequency(self, level: str) -> ActionResult:
        if level not in FREQUENCIES:
            return ActionResult(False, f"I did not change commentary. '{level}' is not a frequency I know.",
                                reason="bad_frequency")
        self.frequency = level
        self.brain.cooldown_seconds = FREQ_COOLDOWN[level]
        self._save_ui()
        return self._show(f"Commentary frequency is {level}.", category="status")

    def set_theme_auto(self) -> ActionResult:
        self.theme_mode = "auto"
        self.refresh_identity()
        self._save_ui()
        return self._show(
            f"Overlay theme is automatic. Right now the frame is {self.theme}. I did not launch a game.",
            category="status",
        )

    def set_theme(self, theme: str) -> ActionResult:
        if theme not in {"nes", "snes", "genesis"}:
            return ActionResult(False, "I did not change the overlay. The theme must be nes, snes, or genesis.",
                                reason="bad_theme")
        self.theme = theme
        self.theme_mode = theme
        self._save_ui()
        return self._show(f"Overlay frame is now {theme}. I did not launch a game.", category="status")

    def set_layout(self, layout: str) -> ActionResult:
        if layout not in {"full", "compact"}:
            return ActionResult(False, "I did not change the layout.", reason="bad_layout")
        self.layout = layout
        self._save_ui()
        label = "compact streaming card" if layout == "compact" else "full retro frame"
        return self._show(f"Layout is now the {label}.", category="status")

    def set_output_device(self, name: str) -> ActionResult:
        devices = self.audio.devices()
        from .audio_out import AudioDevice, resolve_device
        found = resolve_device(name, [AudioDevice(item.get("index"), item["name"]) for item in devices])
        if name.strip() and found is None:
            shown = ", ".join(item["name"] for item in devices) or "(none found)"
            return ActionResult(False, f"I did not change the audio device. '{name}' was not found. Devices: {shown}",
                                reason="device_missing")
        self.output_device = "" if found is None or found.name == "default" else found.name
        self._save_ui()
        return self._show(f"Audio output is {self.output_device or 'the default device'}.", category="status")

    def set_vision(self, enabled: bool) -> ActionResult:
        self.vision_enabled = bool(enabled)
        self._save_ui()
        if self.vision_enabled:
            return self._show("Screen observation is on. I will only comment when something registers.", category="status")
        return self._show("Screen observation is off. I did not capture the screen.", category="status")

    def set_offline_confirmed(self, confirmed: bool) -> ActionResult:
        self.offline_confirmed = bool(confirmed)
        self._save_ui()
        if self.offline_confirmed:
            return ActionResult(True, "You confirmed offline single-player. I still will not automate an online game.",
                                reason="offline_flag")
        self.gate_open = False
        self.mode = "spectator"
        return ActionResult(True, "Offline confirmation is cleared. Takeover stays off.", reason="offline_flag")

    def reset_memory(self) -> ActionResult:
        count = self.memory.reset_preferences()
        self.memory.set_profile("personality", self.personality, "user_reported", self.clock.unix())
        return ActionResult(True, f"Cleared {count} saved preferences. Joke history and sessions are still there, so I will not repeat old lines.",
                            reason="memory_reset")

    def clear_memory(self) -> ActionResult:
        counts = self.memory.clear_all()
        self._callbacks = 0
        self.memory.set_profile("personality", self.personality, "user_reported", self.clock.unix())
        removed = sum(counts.values())
        return ActionResult(True, f"Cleared saved memory ({removed} rows), including joke history.",
                            reason="memory_clear", data=counts)

    def _launch_retroarch(self, extra: list[str], system: str = "", exe: str = "") -> ActionResult:
        from .frame_library import frame_for_system
        from .retroarch_finder import split_launch_extra
        rom, core = split_launch_extra(extra)
        if exe:
            retro = self.config.data.setdefault("retroarch", {})
            if isinstance(retro, dict):
                retro["path"] = exe
        frame = frame_for_system(system) or frame_for_system(self.theme) or "genesis"
        if frame_for_system(system):
            self.theme = frame
            self.theme_mode = frame
        hole = self.game_hole or self._fallback_hole(frame)
        return self.launch_into_hole(hole, force=True, rom=rom, core=core, adopt=not bool(rom))

    def _fallback_hole(self, frame: str) -> tuple[int, int, int, int]:
        from .display_info import hole_screen_rect
        from .frame_library import detect_display_size, frame_record
        size = detect_display_size()
        if size is None:
            mode = str(self.config.get("display", "mode") or "720p")
            size = (1920, 1080) if mode == "1080p" else (1280, 720)
        return hole_screen_rect(frame_record(frame)["screen"], (0, 0, size[0], size[1]))

    def _emulator_hwnd(self) -> int | None:
        from .retroarch_finder import select_game_hwnd
        from .window_layout import visible_hwnd_for_pid
        windows = self.window_source() if self.window_source else list_window_details()
        found = select_game_hwnd(windows, self.overlay_hwnds)
        if found:
            return found
        if self.retroarch_pid:
            return visible_hwnd_for_pid(self.retroarch_pid)
        return None

    def _window_rect(self, hwnd: int):
        if self.rect_source:
            return self.rect_source(hwnd)
        return window_rect(hwnd)

    def _find_retroarch_path(self) -> str:
        if self.retroarch_finder is not None:
            return str(self.retroarch_finder() or "")
        from .retroarch_finder import locate_and_remember
        return locate_and_remember(self.config)

    def launch_into_hole(self, hole: tuple[int, int, int, int], *, force: bool = False,
                         rom: str = "", core: str = "", adopt: bool = True) -> ActionResult:
        """Find RetroArch, start it in the hole, or adopt the window that is already open."""
        from .retroarch_finder import (
            NOTICE_FAILED,
            NOTICE_MISSING,
            append_arguments,
            content_args,
            wait_for_hwnd,
            write_hole_config,
        )
        retro_log = logging.getLogger("buddy.retroarch")
        rect = tuple(int(v) for v in hole)
        self.game_hole = rect
        retro_log.info("Screen hole rect: x=%s y=%s w=%s h=%s", *rect)
        if adopt and not rom:
            existing = self._emulator_hwnd()
            if existing:
                self._retro_launch_started = True
                self.retroarch_started_by_buddy = False
                self.retroarch_notice = ""
                retro_log.info("RetroArch is already open. Adopting hwnd=%s.", existing)
                return self._place_hole(existing, rect)
        path = self._find_retroarch_path()
        if not path:
            self.retroarch_notice = NOTICE_MISSING
            return ActionResult(
                False,
                "I did not launch RetroArch. It was not found. Use Find RetroArch in Buddy's box.",
                reason="retroarch_missing",
            )
        self.retroarch_notice = ""
        from .display_info import mark_exe_dpi_aware
        mark_exe_dpi_aware(path)
        if self._retro_launch_started and not force:
            existing = self._emulator_hwnd()
            if existing:
                return self._place_hole(existing, rect)
            return ActionResult(True, "RetroArch launch already started.", reason="already_started")
        rom, core = content_args(
            rom or str(self.config.get("retroarch", "rom") or ""),
            core or str(self.config.get("retroarch", "core") or ""),
            os.path.isfile,
        )
        from .game_status import runtime_cfg_lines
        from .save_slots import config_lines, state_directory
        extras = list(runtime_cfg_lines(path))
        extras.extend(config_lines(state_directory(self.data_dir), auto_load=self.continue_on_launch))
        self.continue_on_launch = False
        cfg = write_hole_config(self.data_dir / "retroarch", rect, extras)
        self.commands.enabled = True
        self.commands.host = "127.0.0.1"
        self.commands.port = 55355
        args = append_arguments(cfg, rom, core)
        retro_log.info("Launching RetroArch: %s %s", path, args)
        self._retro_launch_started = True
        launched = launch_process(path, args, runner=self.process_runner)
        if not launched.ok:
            self._retro_launch_started = False
            self.retroarch_notice = NOTICE_FAILED
            retro_log.info("RetroArch launch failed: %s", launched.message)
            return launched
        self.retroarch_pid = int(launched.data.get("pid") or 0) or None
        self.retroarch_started_by_buddy = True
        retro_log.info("RetroArch pid=%s", self.retroarch_pid)
        hwnd = wait_for_hwnd(self._emulator_hwnd, timeout=15)
        if not hwnd:
            retro_log.info("RetroArch hwnd was not found within 15s. Placement will keep checking.")
            return ActionResult(
                False,
                "RetroArch started, but its window did not appear yet.",
                reason="hwnd_timeout",
                data=launched.data,
            )
        retro_log.info("RetroArch hwnd=%s", hwnd)
        placed = self._place_hole(hwnd, rect)
        if placed.ok:
            placed.message = f"Started RetroArch in the screen hole. {placed.message}"
            placed.data = {**(placed.data or {}), **(launched.data or {})}
        return placed

    def _place_hole(self, hwnd: int, rect: tuple[int, int, int, int]) -> ActionResult:
        from .retroarch_finder import needs_replace
        from .window_layout import client_screen_rect
        retro_log = logging.getLogger("buddy.retroarch")
        # The window is the opening. A window shifted above the hole leaves the
        # transparent opening looking at empty client area.
        window = rect
        # Every pass. RetroArch's GDI driver puts the File menu back after the first snap.
        retro_log.info("Removing window decorations hwnd=%s result=%s", hwnd, strip_window_decorations(hwnd))
        current = client_screen_rect(hwnd) or self._window_rect(hwnd)
        retro_log.info("RetroArch hwnd=%s client=%s target=%s", hwnd, current, window)
        if not needs_replace(current, window):
            self._placed = (hwnd, window)
            return ActionResult(True, "RetroArch is already under the frame.", reason="stable",
                                data={"hwnd": hwnd, "rect": list(window)})
        mover = self.window_positioner or position_hwnd
        result = mover(hwnd, window, self.overlay_hwnds)
        strip_window_decorations(hwnd)
        retro_log.info("SetWindowPos hwnd=%s rect=%s ok=%s reason=%s", hwnd, window, result.ok, result.reason)
        if result.ok:
            self._placed = (hwnd, window)
        self._layout_note = result.message
        return result

    def _release_retroarch(self) -> None:
        from .retroarch_finder import should_close_on_quit
        retro_log = logging.getLogger("buddy.retroarch")
        close_it = should_close_on_quit(
            launched_by_buddy=self.retroarch_started_by_buddy,
            close_on_quit=bool(self.config.get("retroarch", "close_on_quit")),
        )
        if not close_it:
            retro_log.info("Leaving RetroArch alone (pid=%s).", self.retroarch_pid or "none")
            return
        retro_log.info("Closing RetroArch pid=%s because close_on_quit is on.", self.retroarch_pid)
        if self.process_stopper is not None:
            self.process_stopper(self.retroarch_pid)
            return
        if not self.retroarch_pid:
            return
        if os.name != "nt":
            return
        try:
            import subprocess
            subprocess.Popen(
                ["taskkill", "/PID", str(self.retroarch_pid), "/T"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            retro_log.info("Could not close RetroArch: %s", exc)

    def list_buddy_games(self) -> dict[str, list[str]]:
        from .setup_flow import scan_games
        folder = str(self.config.get("games_dir") or "")
        if not folder:
            return {"nes": [], "snes": [], "genesis": []}
        return scan_games(Path(folder))

    def play_listed_game(self, rom: str, system: str) -> ActionResult:
        """Launch one ROM the user already has. The list lives in Buddy's box."""
        from .frame_library import frame_for_system
        from .setup_catalog import default_core_filename
        exe = self._find_retroarch_path()
        core = ""
        if exe:
            candidate = Path(exe).resolve().parent / "cores" / default_core_filename(system)
            if candidate.is_file():
                core = str(candidate)
        frame = frame_for_system(system) or "genesis"
        if self.theme_mode == "auto":
            self.theme = frame
        hole = self.game_hole or self._fallback_hole(frame)
        logging.getLogger("buddy.retroarch").info("Game list picked %s (%s)", rom, system)
        self.current_rom = rom
        return self.launch_into_hole(hole, force=True, rom=rom, core=core, adopt=False)

    def poll_game_status(self, now: float | None = None) -> None:
        """Ask RetroArch what is running. Speech only. Nothing is drawn on the game."""
        if not self.commands.enabled or not self.commands.port:
            return
        from .game_status import announce_line, parse_get_status, query_status, stuck_line
        from .setup_flow import frame_for_assignment
        try:
            reply = self.status_query() if self.status_query else query_status(self.commands.host, self.commands.port)
        except Exception:
            logging.getLogger("buddy.retroarch").exception("GET_STATUS failed")
            return
        if not reply:
            return
        status = parse_get_status(reply)
        moment = self.clock.mono() if now is None else now
        if status.game and status.game != self._status_game:
            self._status_game = status.game
            self._paused_since = moment if status.state == "PAUSED" else None
            self._stuck_spoken = False
            frame = frame_for_assignment(self.config, status.system)
            if self.theme_mode == "auto" and frame:
                self.theme = frame
            log.info("Game on screen: %s %s", status.game, status.system)
            return
        if not status.game:
            self._status_game = ""
            self._paused_since = None
            self._stuck_spoken = False
            return
        if status.state != "PAUSED":
            self._paused_since = None
            self._stuck_spoken = False
            return
        if self._paused_since is None:
            self._paused_since = moment
            return
        if (not self._stuck_spoken and moment - self._paused_since >= 40):
            self._stuck_spoken = True
            if self._helper_ready():
                note = self._screen_note()
                self._banter(
                    player_text="", spontaneous=True, event="stuck", priority=2, direct=False,
                    observation=note or f"The game is paused on {status.game}.",
                )
            elif self.personality == "extreme":
                self._show(stuck_line("extreme", status.game), category="stuck", emotion="smug")

    def load_game(self, query: str) -> ActionResult:
        found = search_games(list(self.config.get("libraries") or []), query)
        if not found.ok:
            return found
        rom = found.data["matches"][0]
        core = ""
        for entry in self.config.get("libraries") or []:
            folder = str(entry.get("path") or "")
            if folder and rom.startswith(str(Path(folder))):
                core = str(entry.get("core") or "")
                break
        exe = str(self.config.get("retroarch", "path") or "")
        extra = ["-L", core, rom] if core else [rom]
        system = ""
        for entry in self.config.get("libraries") or []:
            folder = str(entry.get("path") or "")
            if folder and rom.startswith(str(Path(folder))):
                system = str(entry.get("system") or "")
                break
        launched = self._launch_retroarch(extra, system=system, exe=exe)
        if not launched.ok:
            return ActionResult(False, f"I found {rom} but did not launch it. {launched.message}", reason=launched.reason)
        return ActionResult(
            True,
            f"I found {rom} and started RetroArch (process {launched.data.get('pid')}). {launched.message}",
            reason="launched",
            data=launched.data,
        )

    def request_takeover(self) -> ActionResult:
        return self._request_mode("takeover")

    def request_coop(self) -> ActionResult:
        return self._request_mode("coop")

    def _request_mode(self, mode: str) -> ActionResult:
        self.refresh_identity()
        title = self.identity.title or ""
        decision = evaluate_gate(
            mode=mode,
            game_title=title,
            window_title=self.identity.window_title or "",
            user_confirmed_offline=self.offline_confirmed,
            enabled=bool(self.config.get("takeover", "enabled")),
        )
        if not decision.allowed:
            self.gate_open = False
            self.mode = "spectator"
            return ActionResult(False, decision.message, reason="takeover_denied",
                                data={"mode": mode, "allowed": False})
        self.mode = mode
        self.gate_open = True
        sink = self.input_sink.press(2 if mode == "coop" else 1, "start", gate_open=True)
        return ActionResult(False, decision.message + " " + sink.message, reason="takeover_not_playing",
                            emotion="smug", data={"allowed": True, "mode": mode, "game_id": decision.game_id})

    def release_control(self) -> ActionResult:
        was_open = self.gate_open or self.mode != "spectator"
        self.gate_open = False
        self.mode = "spectator"
        if was_open:
            return self._show("Takeover is off. I was not sending inputs, and I am not sending them now.",
                              category="status", emotion="smile")
        return ActionResult(True, "I was not controlling the game. You already have the controls.", reason="release")

    def note_overlay_hwnd(self, hwnd: int) -> None:
        if hwnd:
            self.overlay_hwnds.add(int(hwnd))

    def maintain_layout(self, overlay_origin: tuple[int, int], overlay_size: tuple[int, int],
                        now: float | None = None, monitor: tuple[int, int] | None = None,
                        hole: tuple[int, int, int, int] | None = None) -> ActionResult:
        if self.closed or not self.safety.move_enabled:
            reason = self.safety.reason or "closed"
            return ActionResult(False, f"I am not moving windows. {reason}", reason="safety_stop")
        moment = time.monotonic() if now is None else now
        target = tuple(monitor) if monitor else OVERLAY_SIZE
        size = (int(overlay_size[0]), int(overlay_size[1]))
        if size[0] < target[0] - 24 or size[1] < target[1] - 24:
            self.safety.note_geometry(size, moment, design=target)
            return ActionResult(
                False,
                "The overlay shrank below the monitor, so I did not move any window.",
                reason="geometry_clamped",
            )
        if self.layout != "full" or not self.manage_window:
            return ActionResult(False, "I am not managing the emulator window in this layout.", reason="layout_idle")
        if hole is not None:
            rect = tuple(int(v) for v in hole)
        else:
            from .frame_library import scaled_screen
            frame = self.theme if self.theme in {"nes", "snes", "genesis"} else "genesis"
            local = scaled_screen(frame, size)
            if local is None:
                return ActionResult(False, "This frame has no screen rectangle, so I did not move the game.",
                                    reason="no_screen")
            rect = (overlay_origin[0] + local[0], overlay_origin[1] + local[1], local[2], local[3])
        self.game_hole = rect
        hwnd = self._emulator_hwnd()
        if hwnd is None:
            self._placed = None
            return ActionResult(
                False,
                "No RetroArch or EmulationStation window, so I did not move anything.",
                reason="no_game",
            )
        return self._place_hole(hwnd, rect)

    def observe_once(self, *, speak: bool = True) -> ActionResult:
        if self.closed or not self.safety.capture_enabled:
            return ActionResult(False, f"Capture is stopped. {self.safety.reason}".strip(), reason="capture_disabled")
        if not self.vision_enabled:
            return ActionResult(False, "Vision is off, so I did not capture the screen.", reason="vision_disabled")
        now = time.monotonic()
        if not self.safety.allow_capture(now, self._last_capture):
            return ActionResult(False, "Capture is throttled to about one frame a second.", reason="capture_throttled")
        self._last_capture = now
        try:
            if self.vision is None:
                from .game_capture import GameCapture
                from .vision_frames import VisionFrames
                from .vision_service import VisionService
                service = VisionService(VisionFrames(GameCapture(own_hwnds=set(self.overlay_hwnds))))
                result = service.analyze("What is happening in this game? Reply as JSON.")
            else:
                result = self.vision.analyze("What is happening in this game?")
        except Exception as exc:
            self.safety.note_error(str(exc), now)
            return ActionResult(False, f"I could not look at the screen. {exc}", reason="vision_error")
        summary = getattr(result, "description", "") or ""
        uncertain = bool(getattr(result, "uncertain", True))
        event = getattr(result, "event", "none") or "none"
        event_confidence = float(getattr(result, "event_confidence", 0) or 0)
        guess = getattr(result, "game_guess", None)
        guess_confidence = float(getattr(result, "game_confidence", 0) or 0)
        if uncertain or event_confidence < 0.55:
            event = "none"
        if guess and guess_confidence >= 0.7:
            self._vision_guess = guess
            self._vision_confidence = guess_confidence
        else:
            self._vision_guess = None
            self._vision_confidence = 0
        self.refresh_identity()
        if event != "none":
            self.memory.add_event(
                unix=self.clock.unix(), session_id=self.session_id,
                game_title=self.identity.title, kind=event, detail=summary[:240],
                source="vision", confidence=event_confidence,
            )
            self.emotion.on_event(event, self.clock.mono())
        if uncertain:
            fact = f"I looked. I am not confident what is happening. Impression: {summary}" if summary else "I looked, and I am not confident what is happening."
        else:
            fact = f"I looked. {summary}" if summary else "I looked, and the vision model returned nothing I can use."
        shown = ""
        spoken = (False, "")
        if speak:
            comment = self._banter(player_text="", spontaneous=True, event=event if event != "none" else "idle",
                                   priority=3 if event in {"death", "win", "lose_round"} else 1, direct=False,
                                   observation=summary if not uncertain else "")
            shown = comment.text or ""
            spoken = comment.spoken
        return ActionResult(True, fact, text=shown, spoken=spoken, emotion=self.emotion.expression,
                            reason="observed" if shown else "observed_quiet",
                            data={"event": event, "uncertain": uncertain, "summary": summary})

    def start_talking(self) -> ActionResult:
        if self.closed:
            return ActionResult(False, "Buddy is closed.", reason="closed")
        self.audio.stop()
        try:
            if self._ears is None:
                from .buddy_ears import BuddyEars
                self._ears = BuddyEars()
            self._ears.start()
        except Exception as exc:
            return ActionResult(False, f"I did not start the microphone. {exc}", reason="mic_failed")
        return ActionResult(True, "Listening.", reason="listening")

    def finish_talking(self) -> ActionResult:
        if self._ears is None or not self._ears.recording:
            return ActionResult(False, "I was not recording, so there is nothing to transcribe.", reason="not_recording")
        heard = self._ears.stop_and_transcribe()
        if heard.error:
            return ActionResult(False, heard.error, reason="transcription_error")
        if not heard.text:
            return ActionResult(False, "I did not catch any words.", reason="empty_speech")
        return self.handle_text(heard.text)

    def _maybe_greet(self) -> ActionResult:
        # A greeting only when a previous session exists and a fresh line is available.
        with self.memory._lock:
            count = self.memory._conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        if count < 2:
            return ActionResult(True, "", reason="no_greeting")
        return self._banter(player_text="", spontaneous=True, event="greeting_return", priority=2, direct=False)

    def _slots(self, category: str) -> dict[str, str]:
        game = None if self.identity.uncertain else self.identity.title
        kind = category if category not in {"greeting_return", "callback_to_past_session"} else "death"
        count = self.memory.count_events(kind, game) if game else self.memory.count_events(kind)
        last = ""
        with self.memory._lock:
            row = self.memory._conn.execute(
                "SELECT kind, detail FROM events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row and row["detail"]:
            last = f"{row['kind']}: {row['detail']}"
        return known_slots(count=count, game=game, last_session_event=last or None)

    def _banter(self, *, player_text: str, spontaneous: bool, event: str, priority: int,
                direct: bool, observation: str = "") -> ActionResult:
        if not self.running and spontaneous:
            return ActionResult(True, "", reason="not_running")
        category = category_for(player_text, event, spontaneous)
        allow_callback = False
        if spontaneous and category in {"death", "lose_round", "boss_fight", "near_miss"}:
            total = self.memory.count_events(category, self.identity.title)
            if total >= 3 and total % 4 == 0 and self._callbacks < 1:
                allow_callback = True
        if spontaneous and (self.frequency == "off" or self.quiet_until_called):
            return ActionResult(True, "", reason="frequency_off")
        if spontaneous and category == "idle" and self.rng.random() < 0.75:
            return ActionResult(True, "", reason="idle_skipped")
        if spontaneous:
            brain = self.brain.decide(event or category, priority, now=self.clock.mono(),
                                     buddy_speaking=bool(getattr(self.audio, "speaking", False)),
                                     direct_request=False)
            if not brain.should_speak:
                return ActionResult(True, "", reason=brain.reason)
        use_category = "callback_to_past_session" if allow_callback else category
        angle = select_angle(self.pack, self.memory, use_category, self.clock.unix(), self.novelty,
                             personality=self.personality, priority=priority, frequency=self.frequency)
        if angle is None and use_category != "chat":
            if allow_callback:
                use_category = category
                allow_callback = False
                angle = select_angle(self.pack, self.memory, use_category, self.clock.unix(), self.novelty,
                                     personality=self.personality, priority=priority, frequency=self.frequency)
            if angle is None and use_category not in {"chat", "player_asks_help", "stuck_where_to_go"}:
                return ActionResult(True, "", reason="no_fresh_angle")
        insults_allowed = (self.memory.get_profile("insults_allowed", "true") or "true").lower() != "false"
        slots = self._slots(use_category)
        line, emotion, used_angle, callback = self._draft_line(
            player_text=player_text, spontaneous=spontaneous, category=use_category, angle=angle or "",
            insults_allowed=insults_allowed, slots=slots, observation=observation,
            allow_callback=allow_callback, priority=priority, direct=direct,
        )
        if not line:
            if direct:
                return self._show(
                    "I don't have a fresh line that sticks to the facts, so I won't invent one.",
                    category="status", emotion="idle",
                )
            return ActionResult(True, "", reason="silence")
        if not insults_allowed and insults_player(line):
            line = "I'm not going to insult you. Tell me what you want help with."
            emotion = "idle"
            used_angle = ""
            callback = False
            use_category = "status"
        return self._show(line, category=use_category, emotion=emotion, angle=used_angle,
                          callback=callback, speak=True)

    def _draft_line(self, *, player_text, spontaneous, category, angle, insults_allowed, slots,
                    observation, allow_callback, priority, direct):
        facts = "\n".join(f"{key}={value}" for key, value in slots.items()) or "(none)"
        messages = build_messages(
            character=self.character, product=self.product, pack=self.pack,
            memory_text=self.memory.prompt_context(), identity_text=self.identity.factual_line(),
            observation=observation, player_text=player_text, spontaneous=spontaneous,
            insults_allowed=insults_allowed, category=category, angle=angle or "none",
            angle_note=angle_note(self.pack, category, angle) if angle else "",
            examples=example_block(self.pack, category) if category in self.pack.seeds else "",
            known_facts=facts,
        )
        drafted = self.model.complete(messages)
        if drafted.text:
            parsed = parse_tags(drafted.text)
            if parsed.silence:
                return "", "idle", "", False
            if parsed.text:
                chosen = parsed.angle or angle
                decision = self.novelty.screen(
                    parsed.text, category=category, angle=chosen or "", personality=self.personality,
                    now=self.clock.unix(), direct=direct, allow_callback=allow_callback,
                    priority=priority, callbacks_this_session=self._callbacks, frequency=self.frequency,
                )
                if decision.allow:
                    return parsed.text, parsed.emotion, chosen or "", decision.callback
                if not direct:
                    return "", "idle", "", False
                if direct:
                    messages = build_messages(
                        character=self.character, product=self.product, pack=self.pack,
                        memory_text=self.memory.prompt_context(), identity_text=self.identity.factual_line(),
                        observation=observation, player_text=player_text, spontaneous=False,
                        insults_allowed=insults_allowed, category=category, angle=angle or "none",
                        angle_note=angle_note(self.pack, category, angle) if angle else "",
                        examples=example_block(self.pack, category) if category in self.pack.seeds else "",
                        known_facts=facts, rejected_line=parsed.text,
                    )
                    retry = self.model.complete(messages)
                    if retry.text:
                        again = parse_tags(retry.text)
                        if again.text and not again.silence:
                            second = self.novelty.screen(
                                again.text, category=category, angle=again.angle or angle or "",
                                personality=self.personality, now=self.clock.unix(), direct=True,
                                allow_callback=allow_callback, priority=priority,
                                callbacks_this_session=self._callbacks, frequency=self.frequency,
                            )
                            if second.allow:
                                return again.text, again.emotion, again.angle or angle or "", second.callback
                    if category in {"player_asks_help", "stuck_where_to_go", "chat"}:
                        return ("I don't have a fresh way to joke about that, and I won't invent the answer.",
                                "idle", "", False)
        if drafted.error and drafted.error != "offline" and not drafted.text and direct:
            return (f"The model did not answer ({drafted.error}). I won't invent a reply.", "idle", "", False)
        if not angle:
            return "", "idle", "", False
        filled_slots, real_keys = complete_slots(slots, self.pack)
        filled = offline_variant(
            self.pack, category, filled_slots, self.novelty, personality=self.personality, angle=angle,
            now=self.clock.unix(), priority=priority, frequency=self.frequency, direct=direct,
            allow_callback=allow_callback, callbacks_this_session=self._callbacks, real=real_keys,
        )
        if filled:
            return filled, "talk", angle, allow_callback and category == "callback_to_past_session" and looks_like_callback(filled)
        return "", "idle", "", False

    def _show(self, text: str, *, category: str, emotion: str = "talk", angle: str = "",
              callback: bool = False, speak: bool = True) -> ActionResult:
        self.last_text = text
        self.last_reason = category
        shown = emotion if emotion in {
            "idle", "blink", "talk", "smile", "wink", "laugh", "smug", "shocked", "celebrate", "sad"
        } else "talk"
        self.emotion.set_expression(shown, self.clock.mono(), 2.6)
        self.memory.add_line(
            unix=self.clock.unix(), personality=self.personality, category=category, text=text,
            emotion=emotion, game_title=self.identity.title, callback=callback, angle=angle,
            session_id=self.session_id,
        )
        if callback:
            self._callbacks += 1
        self.brain.mark_spoken(text, now=self.clock.mono())
        self.memory.add_message(unix=self.clock.unix(), role="buddy", text=text, source="system")
        spoken, audio_message = self._play(text) if speak else (False, "")
        message = text if not audio_message else f"{text} ({audio_message})"
        return ActionResult(True, message, text=text, spoken=spoken, emotion=shown, reason=category,
                            data={"angle": angle, "callback": callback})

    def _play(self, text: str) -> tuple[bool, str]:
        if not self.speech_enabled:
            return False, "Speech is disabled, so I did not play audio."
        def on_level(level: float) -> None:
            self.mouth = level
        heard = self.audio.speak(
            text, volume=self.volume, rate=int(self.config.get("voice", "rate") or 0),
            device_name=self.output_device, mute=self.muted, on_level=on_level,
            character=getattr(self, "_speaking_as", None) or self.buddy_character,
        )
        if not heard.ok:
            self.mouth = 0.0
            return False, heard.message
        return True, ""

    def demo_expression(self, name: str) -> ActionResult:
        from .hologram import EXPRESSIONS
        if name not in EXPRESSIONS:
            return ActionResult(False, f"I don't have an expression named {name}.", reason="bad_expression")
        self.emotion.set_expression(name, self.clock.mono(), 3)
        return ActionResult(True, f"Showing {name}.", emotion=name, reason="expression")
