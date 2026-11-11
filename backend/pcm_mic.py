"""Write 16 kHz mono PCM to stdout. A crash stays in this process."""
from __future__ import annotations

import sys


def main() -> int:
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    out = sys.stdout.buffer
    try:
        with sd.RawInputStream(samplerate=16000, channels=1, dtype="int16", blocksize=640) as stream:
            while True:
                data, _overflow = stream.read(640)
                out.write(bytes(data))
                out.flush()
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
