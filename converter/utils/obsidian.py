"""Obsidian integration utilities."""
from __future__ import annotations

import subprocess


def pick_folder(vault_path: str) -> str | None:
    """Show a macOS native folder picker pre-navigated to the Obsidian vault.

    Returns the selected folder path, or ``None`` if cancelled / unavailable.
    """
    script = (
        f'tell application "Finder"\n'
        f'  set vaultFolder to POSIX file "{vault_path}" as alias\n'
        f'  set chosen to choose folder with prompt '
        f'"选择 Obsidian 保存位置" default location vaultFolder\n'
        f'  POSIX path of chosen\n'
        f'end tell'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60,
        )
        path = result.stdout.strip()
        return path if path else None
    except Exception:
        return None
