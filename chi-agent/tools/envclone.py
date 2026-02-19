"""
Tool: envclone_init, envclone_up, envclone_down, envclone_code

Wrappers around the envclone CLI tool.
envclone manages containerized dev environments using nerdctl/containerd.

Docs: https://github.com/matoval/envclone
"""

import subprocess
import shutil
from typing import Any


def _envclone(*args: str, timeout: int = 60) -> dict[str, Any]:
    """Run envclone with given args."""
    binary = shutil.which("envclone")
    if not binary:
        return {"error": "envclone not installed. Expected at /usr/local/bin/envclone"}

    result = subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode == 0:
        return {"status": "success", "output": result.stdout.strip()}
    return {
        "error": result.stderr.strip() or result.stdout.strip() or f"envclone exited {result.returncode}",
    }


def envclone_init(env_type: str, name: str) -> dict[str, Any]:
    """
    Initialize a new dev environment.
    env_type: python | node | rust | go | ruby | java | etc.
    name: project/environment name
    """
    return _envclone("init", env_type, name, timeout=120)


def envclone_up(name: str) -> dict[str, Any]:
    """Start an existing envclone environment."""
    return _envclone("up", name, timeout=60)


def envclone_down(name: str) -> dict[str, Any]:
    """Stop an envclone environment."""
    return _envclone("down", name, timeout=30)


def envclone_code(name: str) -> dict[str, Any]:
    """Open VSCodium in an envclone environment."""
    return _envclone("code", name, timeout=30)
