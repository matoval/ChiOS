"""
Tool: launch_app

Launches desktop applications via:
1. Hyprland IPC dispatch (hyprctl dispatch exec)
2. xdg-open fallback for files/URLs
"""

import subprocess
import shutil
from pathlib import Path


# Map friendly names to actual binary/desktop entry names
APP_ALIASES = {
    "browser": "firefox",
    "web": "firefox",
    "terminal": "kitty",
    "term": "kitty",
    "editor": "codium",
    "vscode": "codium",
    "code": "codium",
    "files": "nautilus",
    "file manager": "nautilus",
}


def _find_desktop_entry(app: str) -> str | None:
    """Search XDG application dirs for a .desktop entry matching app name."""
    search_dirs = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local/share/applications",
    ]
    app_lower = app.lower()
    for d in search_dirs:
        if not d.exists():
            continue
        for entry in d.glob("*.desktop"):
            if app_lower in entry.stem.lower():
                return entry.stem
    return None


def launch_app(app: str) -> dict:
    """
    Launch an application. Returns {"status": "launched", "app": name} or {"error": ...}.
    """
    # Resolve alias
    resolved = APP_ALIASES.get(app.lower(), app)

    # Try direct binary first
    binary = shutil.which(resolved)
    if binary:
        try:
            subprocess.Popen(
                [binary],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"status": "launched", "app": resolved, "method": "binary"}
        except Exception as e:
            return {"error": f"Failed to launch {resolved}: {e}"}

    # Try via Hyprland IPC (dispatch exec)
    hyprctl = shutil.which("hyprctl")
    if hyprctl:
        try:
            result = subprocess.run(
                [hyprctl, "dispatch", "exec", resolved],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return {"status": "launched", "app": resolved, "method": "hyprctl"}
        except subprocess.TimeoutExpired:
            pass

    # Try desktop entry via xdg-open / gtk-launch
    entry = _find_desktop_entry(resolved)
    if entry:
        gtk_launch = shutil.which("gtk-launch")
        if gtk_launch:
            try:
                subprocess.Popen(
                    [gtk_launch, entry],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"status": "launched", "app": entry, "method": "gtk-launch"}
            except Exception as e:
                return {"error": f"gtk-launch failed: {e}"}

    return {"error": f"Could not find or launch '{app}'. Is it installed?"}
