"""Short help for a game the player already has running.

Famous codes are remembered here. Anything else is a quick lookup, and Buddy
says so when the answer is thin.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

# Direction pads for games people still own. Not a dump of a whole guide.
KNOWN_CODES = (
    ("contra", "Up, up, down, down, left, right, left, right, B, A. That's the Konami code. It gives you extra lives in Contra."),
    ("super mario bros", "The warp is the pipes in world 1-2. Down the pipe at the end, if you didn't already miss it."),
    ("legend of zelda", "The first dungeon is the tree near the start of the overworld. If you're already past that, tell me the screen and I'll look again."),
)


def known_help(game: str, question: str) -> str:
    blob = f"{game} {question}".lower()
    if any(word in blob for word in ("cheat", "code", "konami", "lives")):
        for name, answer in KNOWN_CODES:
            if name in blob or (name.split()[0] in blob and "code" in blob):
                return answer
        if "contra" in blob:
            return KNOWN_CODES[0][1]
    for name, answer in KNOWN_CODES:
        if name in blob:
            return answer
    return ""


def lookup_help(game: str, question: str, fetch=None) -> tuple[str, str]:
    """Return (line, source). source is known, web, or unsure."""
    remembered = known_help(game, question)
    if remembered:
        return remembered, "known"
    query = " ".join(part for part in (game, question, "walkthrough") if part).strip()
    if not query:
        return "I'm not sure what you're asking. Say the game and where you're stuck.", "unsure"
    getter = fetch if fetch is not None else _duckduckgo
    try:
        snippet = getter(query)
    except Exception:
        snippet = ""
    if not snippet:
        return (
            f"Let me look it up. I couldn't find a clear answer for {game or 'this game'}. "
            "I'm not sure, so I won't invent the path.",
            "unsure",
        )
    return f"Let me look it up. {snippet} If that doesn't match your screen, I'm not sure.", "web"


def _duckduckgo(query: str) -> str:
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query[:180],
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    })
    request = urllib.request.Request(url, headers={"User-Agent": "BuddyOverlay"})
    with urllib.request.urlopen(request, timeout=4) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    text = str(payload.get("AbstractText") or "").strip()
    if not text:
        related = payload.get("RelatedTopics") or []
        if related and isinstance(related[0], dict):
            text = str(related[0].get("Text") or "").strip()
    return text[:280]
