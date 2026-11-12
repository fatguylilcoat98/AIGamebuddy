"""Contracts for the one-click Windows installer."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_installer_workflow_publishes_buddysetup():
    text = (ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    assert "BuddySetup.exe" in text
    assert "windows-latest" in text
    assert "workflow_dispatch" in text
    assert "cursor/buddy-windows-companion-25cc" in text
    assert "pyinstaller" in text.lower()
    assert "contents: write" in text
    assert "--self-test" in text
    assert "portaudio" in text.lower()


def test_inno_script_is_per_user_with_shortcuts():
    text = (ROOT / "packaging/BuddySetup.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in text
    assert "Launch Buddy" in text
    assert "{autodesktop}" in text
    assert "{autoprograms}" in text
    assert "OutputBaseFilename=BuddySetup" in text
    assert "Buddy.exe" in text


def test_buddy_entry_version_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "packaging" / "buddy_entry.py"), "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Buddy Overlay 0.9.0" in proc.stdout


def test_spec_refuses_to_ship_without_portaudio():
    text = (ROOT / "packaging" / "buddy.spec").read_text(encoding="utf-8")
    assert "portaudio" in text.lower()
    assert "ctranslate2" in text.lower()
    assert "Buddy bundle is missing" in text


def test_first_run_doc_is_download_double_click_play():
    text = (ROOT / "WINDOWS_FIRST_RUN.md").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) <= 4
    lowered = text.lower()
    assert "download" in lowered
    assert "double-click" in lowered
    assert "play" in lowered
    assert "python.org" not in lowered
    assert "Add python.exe to PATH" not in text
    assert "releases/" not in lowered
    assert "http" not in lowered


def test_shipped_package_can_import_backend_and_does_not_reinstall():
    build = (ROOT / "packaging/build-windows.ps1").read_text(encoding="utf-8")
    assert 'Buddy.iss' in build
    assert 'BuddySetup.iss' not in build
    assert '$final.Add("..")' in build
    assert "_tkinter.pyd" in build
    assert "tcl86t.dll" in build
    assert "python-3.12.8-amd64.zip" in build
    assert "snes9x_libretro.dll" in build
    assert "UTF8Encoding" in build
    assert "fceumm_libretro.dll" not in build
    pins = (ROOT / "packaging/checksums.pinned.json").read_text(encoding="utf-8")
    assert "python-full" in pins
    iss = (ROOT / "packaging/Buddy.iss").read_text(encoding="utf-8")
    assert "pythonw.exe" in iss
    assert "backend.wizard_app" in iss
    assert "Buddy.exe" not in iss
    bat = (ROOT / "Start-Buddy.bat").read_text(encoding="utf-8")
    assert "pythonw.exe" in bat
    assert "powershell" not in bat.lower()
    assert "{srcexe}" not in iss
    launcher = (ROOT / "Start-Buddy.ps1").read_text(encoding="utf-8")
    assert "startup.log" in launcher
    assert "pythonw.exe" in launcher
    lowered = launcher.lower()
    assert "github.com" not in lowered
    assert "buddysetup" not in lowered
    assert "invoke-webrequest" not in lowered
    assert "releases/" not in lowered
