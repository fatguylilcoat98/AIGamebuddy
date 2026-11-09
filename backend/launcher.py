"""One entry point. Starts Buddy, the local API, and the overlay."""
from __future__ import annotations

import logging
import os
import threading

from . import app_state
from .buddy_session import BuddySession
from .config_loader import load_config, default_data_dir
from .overlay_app import run_overlay


def _dpi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            logging.getLogger("buddy.launcher").warning("Could not set Windows DPI awareness.")


def _serve(port: int) -> None:
    import uvicorn
    from .main import app
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def main() -> int:
    config = load_config()
    data_dir = default_data_dir(config)
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(data_dir / "buddy.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    log = logging.getLogger("buddy.launcher")
    for warning in config.warnings:
        log.warning("%s", warning)
    _dpi()
    session = BuddySession(config)
    app_state.SESSION = session
    started = session.start()
    log.info("%s", started.message)
    port = int(config.get("port") or 8766)
    thread = threading.Thread(target=_serve, args=(port,), name="buddy-api", daemon=True)
    thread.start()
    log.info("Local API at http://127.0.0.1:%s", port)
    try:
        run_overlay(session)
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
