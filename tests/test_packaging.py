"""Contracts for the one-click Windows installer."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_installer_workflow_publishes_buddysetup():
    text = (ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    assert "BuddySetup.exe" in text
    assert "windows-latest" in text
    assert "workflow_dispatch" in text
    assert "cursor/buddy-windows-companion-25cc" in text
    assert "pyinstaller" in text.lower()


def test_inno_script_is_per_user_with_shortcuts():
    text = (ROOT / "packaging/BuddySetup.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in text
    assert "Launch Buddy" in text
    assert "{autodesktop}" in text
    assert "{autoprograms}" in text
    assert "OutputBaseFilename=BuddySetup" in text
    assert "Buddy.exe" in text


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
