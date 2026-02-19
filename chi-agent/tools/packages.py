"""
Tool: install_app, install_system, remove_app

Three-tier package management:
  1. flatpak  — GUI apps, immediate, no reboot
  2. rpm-ostree — system packages, staged, reboot required
  3. (envclone for dev envs is in envclone.py)

Safety: rpm-ostree changes always note "reboot required".
"""

import subprocess
import shutil
from typing import Any


# Flatpak remote to use
FLATPAK_REMOTE = "flathub"

# Known flatpak app IDs for common names
FLATPAK_IDS = {
    "firefox": "org.mozilla.firefox",
    "gimp": "org.gimp.GIMP",
    "obs": "com.obsproject.Studio",
    "obs-studio": "com.obsproject.Studio",
    "vlc": "org.videolan.VLC",
    "htop": "io.github.htop-dev.htop",
    "discord": "com.discordapp.Discord",
    "slack": "com.slack.Slack",
    "zoom": "us.zoom.Zoom",
    "libreoffice": "org.libreoffice.LibreOffice",
    "signal": "org.signal.Signal",
    "telegram": "org.telegram.desktop",
    "spotify": "com.spotify.Client",
    "inkscape": "org.inkscape.Inkscape",
    "blender": "org.blender.Blender",
}


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _flatpak_install(name: str) -> dict[str, Any]:
    """Try to install via flatpak. Returns result dict."""
    if not shutil.which("flatpak"):
        return {"error": "flatpak not available"}

    # Resolve app ID
    app_id = FLATPAK_IDS.get(name.lower(), name)

    # Ensure flathub remote exists
    _run(["flatpak", "remote-add", "--if-not-exists", "--user",
          FLATPAK_REMOTE, "https://dl.flathub.org/repo/flathub.flatpakrepo"])

    rc, out, err = _run(
        ["flatpak", "install", "--user", "--noninteractive", FLATPAK_REMOTE, app_id],
        timeout=300,
    )
    if rc == 0:
        return {"status": "installed", "name": name, "app_id": app_id, "method": "flatpak"}
    return {"error": f"flatpak install failed: {err or out}"}


def _rpm_ostree_install(name: str) -> dict[str, Any]:
    """Install via rpm-ostree. Staged — requires reboot."""
    if not shutil.which("rpm-ostree"):
        return {"error": "rpm-ostree not available"}

    rc, out, err = _run(
        ["rpm-ostree", "install", "--idempotent", name],
        timeout=300,
    )
    if rc == 0:
        return {
            "status": "staged",
            "name": name,
            "method": "rpm-ostree",
            "note": "Reboot required to apply. Run: systemctl reboot",
        }
    return {"error": f"rpm-ostree install failed: {err or out}"}


def install_app(name: str) -> dict[str, Any]:
    """
    Install a GUI application.
    Strategy: flatpak first (immediate), fallback to rpm-ostree (staged).
    """
    # Try flatpak
    result = _flatpak_install(name)
    if "error" not in result:
        return result

    flatpak_err = result["error"]

    # Fallback to rpm-ostree
    result2 = _rpm_ostree_install(name)
    if "error" not in result2:
        result2["flatpak_attempted"] = flatpak_err
        return result2

    return {
        "error": f"Could not install '{name}'",
        "flatpak_error": flatpak_err,
        "rpm_ostree_error": result2["error"],
    }


def install_system(name: str) -> dict[str, Any]:
    """
    Install a system-level package via rpm-ostree.
    Always staged — reboot required.
    """
    return _rpm_ostree_install(name)


def remove_app(name: str) -> dict[str, Any]:
    """
    Remove an application.
    Tries flatpak uninstall first, then rpm-ostree override remove.
    """
    app_id = FLATPAK_IDS.get(name.lower(), name)

    # Try flatpak
    if shutil.which("flatpak"):
        rc, out, err = _run(
            ["flatpak", "uninstall", "--user", "--noninteractive", app_id],
            timeout=120,
        )
        if rc == 0:
            return {"status": "removed", "name": name, "method": "flatpak"}

    # Try rpm-ostree override remove (for layered packages)
    if shutil.which("rpm-ostree"):
        rc, out, err = _run(
            ["rpm-ostree", "override", "remove", name],
            timeout=120,
        )
        if rc == 0:
            return {
                "status": "staged_removal",
                "name": name,
                "method": "rpm-ostree",
                "note": "Reboot required to apply removal.",
            }

    return {"error": f"Could not remove '{name}'. Is it installed?"}
