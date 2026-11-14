"""One microphone snippet and a transcript. A crash stays in this process."""
from __future__ import annotations

import sys
import time


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    seconds = 2.2
    if args:
        try:
            seconds = max(0.4, min(8.0, float(args[0])))
        except ValueError:
            seconds = 2.2
    try:
        from backend.buddy_ears import BuddyEars
        ears = BuddyEars(max_seconds=max(4.0, seconds + 1))
        ears.start()
        time.sleep(seconds)
        heard = ears.stop_and_transcribe()
    except Exception as exc:
        print(f"ERROR {exc}")
        return 1
    if getattr(heard, "error", ""):
        print(f"ERROR {heard.error}")
        return 1
    print((getattr(heard, "text", "") or "").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
