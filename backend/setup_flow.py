"""Wizard decisions: install, games folder, secrets, and the saved step.

The window can close. The step is written to disk and opened again later.
No ROM is downloaded here.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

from .setup_catalog import (
    ARTIFACTS,
    SYSTEM_FOLDERS,
    blocked_cores,
    core_by_filename,
    default_cores,
)

log = logging.getLogger("buddy.setup")

STEPS = ("welcome", "install", "games", "overlays", "ai", "buddy", "done")
SECRET_NAME = "buddy-chat-api-key"

GAMES_COPY = """You need games you already own.

Buddy does not download ROMs. This setup does not link to ROM sites.

If you own a cartridge, dump it with hardware you own, or copy a ROM file you already made. Put each file in the folder for that system.

NES, Super NES, and Genesis do not need a BIOS for the cores Buddy installs.

Buddy creates a Buddy Games folder with NES, SNES, and Genesis inside it, and can open that folder for you.
"""

DEFAULT_STATE = {
    "version": 1,
    "step": "welcome",
    "completed": False,
    "install_mode": "portable",
    "retroarch_path": "",
    "cores_installed": [],
    "cores_skipped": [],
    "install_error": "",
    "progress": "",
    "games_dir": "",
    "scan": {"nes": [], "snes": [], "genesis": []},
    "frames": {"nes": "nes", "snes": "snes", "genesis": "genesis"},
    "personality": "sassy",
    "extreme_confirmed": False,
    "api_base_url": "https://api.meta.ai/v1",
    "api_key_stored": False,
    "character": "male",
    "license_hook": "not_built",
    "sign_hook": "not_built",
}


def fresh_state() -> dict:
    state = json.loads(json.dumps(DEFAULT_STATE))
    return state


def state_path(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root) / "setup-state.json"
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Buddy" / "setup-state.json"


def log_path(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root) / "logs" / "setup.log"
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Buddy" / "logs" / "setup.log"


def setup_log(message: str, root: Path | None = None) -> None:
    path = log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")
    log.info("%s", message)


def load_state(path: Path | None = None) -> dict:
    chosen = path or state_path()
    state = fresh_state()
    if not chosen.is_file():
        return state
    try:
        saved = json.loads(chosen.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return state
    if isinstance(saved, dict):
        state.update(saved)
    if state.get("step") not in STEPS:
        state["step"] = "welcome"
    return state


def save_state(state: dict, path: Path | None = None) -> Path:
    chosen = path or state_path()
    chosen.parent.mkdir(parents=True, exist_ok=True)
    # The API key is never part of this file.
    safe = dict(state)
    safe.pop("api_key", None)
    chosen.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    return chosen


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> str:
    """Empty string when the file matches. A sentence when it does not."""
    pinned = (expected or "").strip().lower()
    if len(pinned) != 64:
        return f"Checksum for {Path(path).name} is not pinned, so Buddy did not install it."
    if not Path(path).is_file():
        return f"{Path(path).name} is missing. Nothing was installed."
    actual = sha256_file(path)
    if actual != pinned:
        return (
            f"{Path(path).name} did not match its checksum. "
            "Buddy kept the old files and did not install this copy."
        )
    return ""


def artifact_by_id(artifact_id: str) -> dict:
    for item in ARTIFACTS:
        if item["id"] == artifact_id:
            return dict(item)
    raise KeyError(artifact_id)


def fetch_verified(artifact: dict, dest: Path, fetch, progress) -> str:
    """Download one file and keep it only when the pinned checksum matches."""
    name = artifact.get("name") or artifact.get("filename") or "file"
    expected = str(artifact.get("sha256") or "").strip().lower()
    progress(0.1, f"Downloading {name} {artifact.get('version', '')}".strip())
    if len(expected) != 64:
        message = f"Checksum for {name} is not pinned, so Buddy did not download it."
        progress(1.0, message)
        return message
    try:
        data = fetch(artifact["url"])
    except Exception as exc:
        message = f"Could not download {name}. {exc}"
        progress(1.0, message)
        return message
    if not isinstance(data, (bytes, bytearray)):
        message = f"The download for {name} was empty. Nothing was installed."
        progress(1.0, message)
        return message
    actual = sha256_bytes(bytes(data))
    progress(0.7, f"Checksum {actual[:12]}")
    if actual != expected:
        message = f"The download for {name} did not match its checksum. Nothing was kept."
        progress(1.0, message)
        return message
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(bytes(data))
    progress(1.0, f"{name} is ready.")
    return ""


def adopt_retroarch(exe: Path) -> str:
    path = Path(exe)
    if not path.is_file():
        return "That folder does not contain RetroArch. Pick retroarch.exe, or install a new copy."
    if path.name.lower() != "retroarch.exe":
        return "That file is not retroarch.exe. Buddy did not adopt it."
    return ""


def install_default_cores(bundle: Path, cores_dir: Path, checksums: dict[str, str], progress) -> tuple[list[str], list[str], str]:
    """Copy the default GPL cores. Non-commercial cores are skipped even if present."""
    installed: list[str] = []
    skipped = [f"{core.name} ({core.license})" for core in blocked_cores()]
    cores_dir.mkdir(parents=True, exist_ok=True)
    for core in default_cores():
        source = Path(bundle) / core.filename
        progress(0.5, f"Checking {core.name}")
        if not source.is_file():
            return installed, skipped, f"{core.name} was not in the package. Buddy did not finish the core install."
        pinned = checksums.get(core.filename, "")
        error = verify_sha256(source, pinned)
        if error:
            return installed, skipped, error
        shutil.copy2(source, cores_dir / core.filename)
        installed.append(core.filename)
        setup_log(f"Installed core {core.name} ({core.license}) -> {cores_dir / core.filename}")
    for core in blocked_cores():
        setup_log(f"Skipped {core.name}: {core.note}")
    progress(1.0, "Cores are in place.")
    return installed, skipped, ""


def create_games_tree(root: Path) -> Path:
    root = Path(root)
    for folder in SYSTEM_FOLDERS.values():
        (root / folder).mkdir(parents=True, exist_ok=True)
    note = root / "README.txt"
    note.write_text(GAMES_COPY, encoding="utf-8")
    return root


_EXTENSIONS = {
    "nes": {".nes", ".unf", ".fds", ".zip"},
    "snes": {".sfc", ".smc", ".fig", ".zip"},
    "genesis": {".md", ".gen", ".smd", ".zip", ".bin"},
}


def scan_games(root: Path) -> dict[str, list[str]]:
    """List ROM filenames the user put in each system folder. Does not open archives."""
    found = {"nes": [], "snes": [], "genesis": []}
    root = Path(root)
    for system, folder_name in SYSTEM_FOLDERS.items():
        folder = root / folder_name
        if not folder.is_dir():
            continue
        names = []
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() in _EXTENSIONS[system]:
                names.append(path.name)
        found[system] = names
    return found


def games_list_rect(buddy: dict) -> dict[str, int]:
    """Lower part of Buddy's box. It does not cover the game hole."""
    height = max(28, int(buddy["height"] * 0.42))
    return {
        "x": int(buddy["x"]) + 4,
        "y": int(buddy["y"]) + int(buddy["height"]) - height,
        "width": max(1, int(buddy["width"]) - 8),
        "height": max(1, height - 4),
    }


def scan_summary(found: dict[str, list[str]]) -> str:
    from .setup_catalog import SYSTEM_LABELS
    lines = []
    for system in ("nes", "snes", "genesis"):
        names = found.get(system) or []
        label = SYSTEM_LABELS[system]
        if not names:
            lines.append(f"{label}: no games in this folder yet.")
        else:
            preview = ", ".join(names[:4])
            extra = f" (+{len(names) - 4} more)" if len(names) > 4 else ""
            lines.append(f"{label}: {len(names)} — {preview}{extra}")
    return "\n".join(lines)


def can_leave(state: dict, step: str | None = None) -> str:
    current = step or state.get("step")
    if current == "install" and not state.get("retroarch_path"):
        return "Install RetroArch, or choose an existing one, before continuing."
    if current == "games" and not state.get("games_dir"):
        return "Create the Buddy Games folder before continuing."
    if current == "ai" and state.get("personality") == "extreme" and not state.get("extreme_confirmed"):
        return "Extreme uses profanity. Confirm you are 18 or older, or pick another mode."
    if current == "buddy" and state.get("character") not in {"male", "female"}:
        return "Pick Male or Female."
    return ""


def move(state: dict, delta: int) -> str:
    step = state.get("step") or "welcome"
    index = STEPS.index(step) if step in STEPS else 0
    if delta > 0:
        error = can_leave(state, step)
        if error:
            return error
        if step == "done":
            state["completed"] = True
            return ""
    index = min(len(STEPS) - 1, max(0, index + delta))
    state["step"] = STEPS[index]
    return ""


def frame_for_assignment(config, system: str) -> str:
    frames = {}
    if config is not None:
        frames = config.get("overlay", "frames") or {}
    if isinstance(frames, dict) and frames.get(system) in {"nes", "snes", "genesis"}:
        return str(frames[system])
    from .frame_library import frame_for_system
    return frame_for_system(system) or ""


def apply_config(config, state: dict) -> None:
    """Write wizard choices into the user config. The API key stays out."""
    data = config.data
    retro = data.setdefault("retroarch", {})
    if not isinstance(retro, dict):
        retro = {}
        data["retroarch"] = retro
    if state.get("retroarch_path"):
        retro["path"] = state["retroarch_path"]
    retro["command_host"] = "127.0.0.1"
    retro["command_port"] = 55355
    retro["command_enabled"] = True
    retro["close_on_quit"] = bool(retro.get("close_on_quit", False))
    data["games_dir"] = state.get("games_dir") or ""
    data["personality"] = state.get("personality") or "sassy"
    data["buddy_character"] = state.get("character") or "male"
    data["provider"] = data.get("provider") or "offline"
    overlay = data.setdefault("overlay", {})
    if isinstance(overlay, dict):
        overlay["theme"] = "auto"
        overlay["frames"] = dict(state.get("frames") or DEFAULT_STATE["frames"])
    libraries = []
    games = state.get("games_dir") or ""
    if games:
        exe = state.get("retroarch_path") or ""
        core_dir = Path(exe).resolve().parent / "cores" if exe else None
        for system, folder in SYSTEM_FOLDERS.items():
            core = ""
            if core_dir is not None:
                candidate = core_dir / f"{_core_file(system)}"
                if candidate.is_file():
                    core = str(candidate)
            libraries.append({
                "system": system,
                "path": str(Path(games) / folder),
                "core": core,
            })
    data["libraries"] = libraries
    blob = json.dumps(data)
    if "api_key" in data or "BEGIN API" in blob:
        raise RuntimeError("Refusing to write a config that contains an API key.")


def _core_file(system: str) -> str:
    from .setup_catalog import default_core_filename
    return default_core_filename(system)


def config_contains_secret(config_text: str, secret: str) -> bool:
    if not secret:
        return False
    return secret in config_text


class MemoryVault:
    """Test double. Production on Windows uses WindowsVault."""

    def __init__(self):
        self.data: dict[str, str] = {}

    def put(self, name: str, value: str) -> str:
        if not value:
            return "There is no key to store."
        self.data[name] = value
        return ""

    def get(self, name: str) -> str:
        return self.data.get(name, "")


class WindowsVault:
    """Credential Manager first, then DPAPI. The key is never returned in a log."""

    def __init__(self, folder: Path | None = None):
        base = folder
        if base is None:
            root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            base = Path(root) / "Buddy" / "secrets"
        self.folder = Path(base)

    def put(self, name: str, value: str) -> str:
        if os.name != "nt":
            return "API keys are stored with Windows Credential Manager. This machine is not Windows, so the key was not saved."
        if not value:
            return "There is no key to store."
        cred_error = _cred_write(name, value)
        if not cred_error:
            setup_log(f"Stored {name} in Credential Manager. Length {len(value)}.")
            return ""
        dpapi_error = _dpapi_write(self.folder / f"{name}.bin", value)
        if not dpapi_error:
            setup_log(f"Stored {name} with DPAPI. Length {len(value)}.")
            return ""
        return f"Could not store the key. It was not written to the config. {cred_error} {dpapi_error}"

    def get(self, name: str) -> str:
        if os.name != "nt":
            return ""
        value = _cred_read(name)
        if value:
            return value
        return _dpapi_read(self.folder / f"{name}.bin")


def load_secrets_into_env(vault=None) -> None:
    """Put the stored chat key into the process environment. Do not log the value."""
    if os.environ.get("BUDDY_CHAT_API_KEY") or os.environ.get("BUDDY_META_API_KEY"):
        return
    store = vault if vault is not None else WindowsVault()
    try:
        value = store.get(SECRET_NAME)
    except Exception:
        log.info("Could not read the stored API key.")
        return
    if value:
        os.environ["BUDDY_META_API_KEY"] = value
        os.environ["BUDDY_CHAT_API_KEY"] = value
        log.info("Loaded the stored API key into this process. It was not printed.")


def check_stored_key(vault, transport=None) -> str:
    value = vault.get(SECRET_NAME)
    if not value:
        return "No key is stored yet."
    if transport is None:
        return "The key is stored. Buddy did not print it."
    try:
        status, _body = transport("https://api.meta.ai/v1/models", value)
    except Exception as exc:
        return f"The key stayed in the credential store. The test call failed. {exc}"
    if int(status) != 200:
        return "The service rejected the key. It is still only in the credential store."
    return "The key worked. It is not in the config file."


def license_hook_status() -> str:
    """The license key is not built yet. This is the hook Chris can fill later."""
    return "not_built"


def sign_hook_status() -> str:
    return "not_built"


def _cred_write(name: str, value: str) -> str:
    try:
        import ctypes
        from ctypes import wintypes
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        blob = value.encode("utf-16-le")

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        buffer = ctypes.create_string_buffer(blob)
        cred = CREDENTIAL()
        cred.Type = 1  # CRED_TYPE_GENERIC
        cred.TargetName = f"Buddy/{name}"
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
        cred.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = "Buddy"
        advapi.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        advapi.CredWriteW.restype = wintypes.BOOL
        if not advapi.CredWriteW(ctypes.byref(cred), 0):
            return f"Credential Manager refused the key (error {ctypes.get_last_error()})."
        return ""
    except Exception as exc:
        return f"Credential Manager was not available ({exc})."


def _cred_read(name: str) -> str:
    try:
        import ctypes
        from ctypes import wintypes
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        advapi.CredReadW.restype = wintypes.BOOL
        advapi.CredFree.argtypes = [ctypes.c_void_p]
        pointer = ctypes.POINTER(CREDENTIAL)()
        if not advapi.CredReadW(f"Buddy/{name}", 1, 0, ctypes.byref(pointer)):
            return ""
        try:
            size = int(pointer.contents.CredentialBlobSize)
            raw = ctypes.string_at(pointer.contents.CredentialBlob, size)
            return raw.decode("utf-16-le")
        finally:
            advapi.CredFree(pointer)
    except Exception:
        return ""


def _dpapi_write(path: Path, value: str) -> str:
    try:
        import ctypes
        from ctypes import wintypes
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        raw = value.encode("utf-8")
        source_buf = ctypes.create_string_buffer(raw)
        source = DATA_BLOB(len(raw), ctypes.cast(source_buf, ctypes.POINTER(ctypes.c_byte)))
        output = DATA_BLOB()
        crypt.CryptProtectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt.CryptProtectData.restype = wintypes.BOOL
        if not crypt.CryptProtectData(ctypes.byref(source), "Buddy", None, None, None, 0, ctypes.byref(output)):
            return f"DPAPI failed (error {ctypes.get_last_error()})."
        try:
            blob = ctypes.string_at(output.pbData, output.cbData)
        finally:
            kernel.LocalFree(output.pbData)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        return ""
    except Exception as exc:
        return f"DPAPI was not available ({exc})."


def _dpapi_read(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        raw = path.read_bytes()
        source_buf = ctypes.create_string_buffer(raw)
        source = DATA_BLOB(len(raw), ctypes.cast(source_buf, ctypes.POINTER(ctypes.c_byte)))
        output = DATA_BLOB()
        crypt.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt.CryptUnprotectData.restype = wintypes.BOOL
        if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
            return ""
        try:
            return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
        finally:
            kernel.LocalFree(output.pbData)
    except Exception:
        return ""


def install_portable(bundle: Path, dest: Path, checksums: dict[str, str], progress) -> str:
    """Copy a prepared RetroArch folder after its exe checksum matches."""
    exe = Path(bundle) / "retroarch.exe"
    error = verify_sha256(exe, checksums.get("retroarch.exe", ""))
    if error:
        progress(1.0, error)
        return error
    progress(0.4, "Copying RetroArch into Buddy's folder.")
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(bundle, dest)
    if not (dest / "retroarch.exe").is_file():
        message = "RetroArch did not land in Buddy's folder. Nothing else was changed."
        progress(1.0, message)
        return message
    for core in blocked_cores():
        for leftover in dest.rglob(core.filename):
            leftover.unlink()
            setup_log(f"Removed {core.name} from the RetroArch folder. {core.note}")
    progress(0.8, f"Checksum {checksums.get('retroarch.exe', '')[:12]}")
    setup_log(f"Installed portable RetroArch at {dest / 'retroarch.exe'}")
    return ""


def reject_blocked_core(filename: str) -> str:
    core = core_by_filename(filename)
    if core and not core.commercial_ok:
        return f"{core.name} is {core.license}. Buddy did not install it."
    return ""
