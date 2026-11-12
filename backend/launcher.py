"""One entry point. Starts Buddy, the local API, and the overlay."""
from __future__ import annotations

import logging
import os
import threading

from . import app_state
from .buddy_session import BuddySession
from .config_loader import load_config, default_data_dir
from .overlay_app import run_overlay

# Console control events that mean the window or the machine is going away.
_CONSOLE_STOP = {0, 1, 2, 5, 6}


def _dpi() -> None:
    from .display_info import enable_per_monitor_dpi
    enable_per_monitor_dpi()


def _serve(port: int) -> None:
    import sys
    # pythonw has no stdout. uvicorn's default log formatter calls isatty on it and dies,
    # which is why the local API never listened on 8766.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    import uvicorn
    from .main import app
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="info", log_config=None, access_log=False,
    )
    server = uvicorn.Server(config)
    app_state.api_server = server
    server.run()


def _install_console_stop() -> None:
    """Closing the console, Ctrl+C, and logoff must stop the overlay thread too."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def _handle(ctrl_type):
            if int(ctrl_type) not in _CONSOLE_STOP:
                return False
            quit_ui = app_state.request_quit
            if quit_ui is not None:
                try:
                    quit_ui()
                except Exception:
                    os._exit(0)
                return True
            os._exit(0)

        # Keep a reference so ctypes does not collect the callback.
        _install_console_stop._callback = handler_type(_handle)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_install_console_stop._callback, True)
    except Exception:
        logging.getLogger("buddy.launcher").warning("Could not install the console close handler.")


def main() -> int:
    from .diagnostics import install
    install()
    config = load_config()
    data_dir = default_data_dir(config)
    data_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("buddy.launcher")
    log.info("startup: config loaded from %s", getattr(config, "path", ""))
    for warning in config.warnings:
        log.warning("%s", warning)
    _dpi()
    _install_console_stop()
    try:
        from .setup_flow import load_secrets_into_env
        load_secrets_into_env()
    except Exception:
        log.warning("Could not load a stored API key. The config was not changed.")
    session = BuddySession(config)
    app_state.SESSION = session
    started = session.start()
    log.info("%s", started.message)
    port = int(config.get("port") or 8766)
    thread = threading.Thread(target=_serve, args=(port,), name="buddy-api", daemon=True)
    thread.start()
    log.info("Local API at http://127.0.0.1:%s", port)
    log.info("startup: overlay opening")
    try:
        run_overlay(session)
    finally:
        session.safety.disable("launcher exit", quiet=True)
        session.close()
        server = app_state.api_server
        if server is not None:
            server.should_exit = True
        thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
