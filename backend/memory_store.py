"""SQLite memory. Observed events and user-reported facts stay distinct."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso(unix: float) -> str:
    return datetime.fromtimestamp(unix, timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    game_title TEXT,
                    system_name TEXT,
                    personality TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    session_id INTEGER,
                    at TEXT NOT NULL,
                    game_title TEXT,
                    kind TEXT NOT NULL,
                    detail TEXT,
                    source TEXT NOT NULL,
                    confidence REAL
                );
                CREATE TABLE IF NOT EXISTS lines (
                    id INTEGER PRIMARY KEY,
                    at TEXT NOT NULL,
                    personality TEXT,
                    category TEXT,
                    text TEXT NOT NULL,
                    emotion TEXT,
                    game_title TEXT,
                    callback INTEGER DEFAULT 0,
                    angle TEXT,
                    session_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    at TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL
                );
                """
            )
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(lines)")}
        if "angle" not in cols:
            self._conn.execute("ALTER TABLE lines ADD COLUMN angle TEXT")
        if "session_id" not in cols:
            self._conn.execute("ALTER TABLE lines ADD COLUMN session_id INTEGER")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def start_session(self, unix: float, personality: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sessions (started_at, personality) VALUES (?, ?)",
                (_iso(unix), personality),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def end_session(self, session_id: int, unix: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (_iso(unix), session_id),
            )
            self._conn.commit()

    def set_profile(self, key: str, value: str, source: str, unix: float) -> None:
        if source not in {"observed", "user_reported", "system"}:
            raise ValueError("source must be observed, user_reported, or system")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO profile (key, value, source, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (key, value, source, _iso(unix)),
            )
            self._conn.commit()

    def get_profile(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM profile WHERE key = ?", (key,)).fetchone()
        return default if row is None else str(row["value"])

    def profile_rows(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value, source, updated_at FROM profile ORDER BY key"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_event(self, *, unix: float, session_id: int | None, game_title: str | None,
                  kind: str, detail: str, source: str, confidence: float) -> None:
        if source not in {"observed", "user_reported", "vision", "launcher", "system"}:
            raise ValueError("invalid event source")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO events (session_id, at, game_title, kind, detail, source, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, _iso(unix), game_title, kind, detail[:500], source, float(confidence)),
            )
            self._conn.commit()

    def count_events(self, kind: str, game_title: str | None = None) -> int:
        with self._lock:
            if game_title:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM events WHERE kind = ? AND game_title = ?",
                    (kind, game_title),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM events WHERE kind = ?",
                    (kind,),
                ).fetchone()
        return int(row["n"])

    def add_line(self, *, unix: float, personality: str, category: str, text: str,
                 emotion: str, game_title: str | None, callback: bool,
                 angle: str = "", session_id: int | None = None) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO lines (at, personality, category, text, emotion, game_title, callback, angle, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (_iso(unix), personality, category, text[:600], emotion, game_title,
                 1 if callback else 0, angle or "", session_id),
            )
            self._conn.commit()

    def recent_lines(self, limit: int = 400) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT at, personality, category, text, emotion, game_title, callback, angle, session_id "
                "FROM lines ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_message(self, *, unix: float, role: str, text: str, source: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (at, role, text, source) VALUES (?, ?, ?, ?)",
                (_iso(unix), role, text[:1200], source),
            )
            self._conn.commit()

    def reset_preferences(self) -> int:
        """Clear learned preferences. Joke history and sessions stay."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM profile")
            self._conn.commit()
            return int(cur.rowcount)

    def clear_all(self) -> dict[str, int]:
        counts = {}
        with self._lock:
            for table in ("profile", "sessions", "events", "lines", "messages"):
                cur = self._conn.execute(f"DELETE FROM {table}")
                counts[table] = int(cur.rowcount)
            self._conn.commit()
        return counts

    def summary(self) -> str:
        profile = self.profile_rows()
        with self._lock:
            sessions = self._conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
            events = self._conn.execute(
                "SELECT kind, game_title, detail, source, confidence, at FROM events "
                "ORDER BY id DESC LIMIT 8"
            ).fetchall()
            line_count = self._conn.execute("SELECT COUNT(*) AS n FROM lines").fetchone()["n"]
            last_game = self._conn.execute(
                "SELECT game_title, system_name FROM sessions WHERE game_title IS NOT NULL "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
        lines = ["Saved memory:"]
        if not profile:
            lines.append("- Preferences: none saved")
        for row in profile:
            lines.append(f"- {row['key']} = {row['value']} ({row['source']})")
        lines.append(f"- Sessions stored: {sessions}")
        lines.append(f"- Commentary lines stored: {line_count}")
        if last_game and last_game["game_title"]:
            lines.append(f"- Last recorded game: {last_game['game_title']}")
        if events:
            lines.append("- Recent events:")
            for event in events:
                game = event["game_title"] or "unknown game"
                lines.append(
                    f"  - {event['kind']} in {game} [{event['source']}, confidence {event['confidence']}] {event['detail'] or ''}".rstrip()
                )
        else:
            lines.append("- Recent events: none")
        return "\n".join(lines)

    def prompt_context(self) -> str:
        """Short context for the model. Does not include raw screenshots."""
        bits = []
        for row in self.profile_rows():
            bits.append(f"{row['key']}={row['value']} ({row['source']})")
        with self._lock:
            events = self._conn.execute(
                "SELECT kind, game_title, detail, source FROM events ORDER BY id DESC LIMIT 6"
            ).fetchall()
        for event in events:
            bits.append(
                f"event {event['kind']} game={event['game_title'] or '?'} source={event['source']} {event['detail'] or ''}".strip()
            )
        return "\n".join(bits)[:1500]
