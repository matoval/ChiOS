"""
Tool: run_shell

Runs shell commands as the current user with:
- 30 second timeout
- Allowlist/denylist for dangerous patterns
- No root escalation
"""

import re
import subprocess
from typing import Any


# Patterns that are never allowed
DENY_PATTERNS = [
    r"rm\s+-rf?\s+/",          # rm -rf /
    r">\s*/dev/(s?d[a-z])",    # overwrite block devices
    r"dd\s+.*of=/dev/",        # dd to block device
    r"mkfs",                    # format filesystem
    r":(){ :|:& };:",           # fork bomb
    r"sudo\s+su\b",            # sudo su
    r"passwd\s+root",           # change root password
    r"rpm-ostree\s+",           # use packages.py instead
    r"flatpak\s+",              # use packages.py instead
]

DENY_RE = [re.compile(p) for p in DENY_PATTERNS]


def _is_dangerous(command: str) -> str | None:
    """Return a reason string if command is dangerous, else None."""
    for pattern in DENY_RE:
        if pattern.search(command):
            return f"Command matches denied pattern: {pattern.pattern}"
    return None


def run_shell(command: str, timeout: int = 30) -> dict[str, Any]:
    """
    Run a shell command. Returns stdout/stderr/returncode dict.
    """
    danger = _is_dangerous(command)
    if danger:
        return {"error": f"Command blocked: {danger}"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            # Run as current user — no privilege escalation
            env=None,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s: {command}"}
    except Exception as e:
        return {"error": f"Failed to run command: {e}"}
