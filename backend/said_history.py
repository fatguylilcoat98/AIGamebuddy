"""Everything Buddy has said this session, and a gate for repeats.

Exact copies are refused. Near-duplicates are refused with a word-overlap
score (character n-grams via the sequence matcher, plus token Jaccard).
A fresh phrasing is picked from the remaining candidates.
"""
from __future__ import annotations

from .novelty import similarity

# Two lines at or above this are the same joke in different clothes.
NEAR_DUP = 0.58


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


class SaidHistory:
    """Per-session record of spoken lines."""

    def __init__(self, threshold: float = NEAR_DUP) -> None:
        self.threshold = threshold
        self.lines: list[str] = []
        self.exact_rejects = 0
        self.near_rejects = 0

    def clash(self, text: str) -> str:
        """'exact', 'near', or '' if this line is new enough to say."""
        cleaned = _norm(text)
        if not cleaned:
            return "exact"
        for previous in self.lines:
            if _norm(previous) == cleaned:
                return "exact"
        for previous in self.lines:
            if similarity(text, previous) >= self.threshold:
                return "near"
        return ""

    def pick(self, candidates: list[str]) -> str:
        """First candidate that is not a repeat. Falls back to a numbered aside."""
        for cand in candidates:
            why = self.clash(cand)
            if why == "exact":
                self.exact_rejects += 1
                continue
            if why == "near":
                self.near_rejects += 1
                continue
            return cand.strip()
        seed = (candidates[-1] if candidates else "I'm still here").strip()
        n = len(self.lines) + 1
        while True:
            line = f"{seed} Take {n}."
            if not self.clash(line):
                return line
            n += 1
            if n > len(self.lines) + 8:
                return f"Still watching. Mark {len(self.lines) + 1}."

    def add(self, text: str) -> None:
        cleaned = " ".join((text or "").split())
        if cleaned:
            self.lines.append(cleaned)

    def repetition(self) -> dict[str, float]:
        """Exact repeats and the near-duplicate rate across the spoken lines."""
        exact = 0
        near_pairs = 0
        pairs = 0
        for index, line in enumerate(self.lines):
            for earlier in self.lines[:index]:
                pairs += 1
                if _norm(line) == _norm(earlier):
                    exact += 1
                elif similarity(line, earlier) >= self.threshold:
                    near_pairs += 1
        return {
            "spoken": float(len(self.lines)),
            "exact_repeats": float(exact),
            "near_dup_pairs": float(near_pairs),
            "comparisons": float(pairs),
            "near_dup_rate": (near_pairs / pairs) if pairs else 0.0,
        }
