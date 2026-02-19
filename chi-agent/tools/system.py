"""
Tool: get_network_status, set_network, manage_service

System management via:
- pydbus → NetworkManager (D-Bus)
- pydbus → systemd (D-Bus)
"""

import logging
import subprocess
import shutil
from typing import Any

log = logging.getLogger("chi-agent.system")


def get_network_status() -> dict[str, Any]:
    """Return current network connections and state."""
    try:
        from pydbus import SystemBus

        bus = SystemBus()
        nm = bus.get("org.freedesktop.NetworkManager")
        state = nm.State

        STATE_MAP = {
            20: "disconnected",
            30: "disconnected",
            40: "connecting",
            50: "connected_local",
            60: "connected_site",
            70: "connected_global",
        }

        connections = []
        for ac_path in nm.ActiveConnections:
            try:
                ac = bus.get("org.freedesktop.NetworkManager", ac_path)
                connections.append({
                    "id": ac.Id,
                    "type": ac.Type,
                    "state": ac.State,
                })
            except Exception:
                pass

        return {
            "state": STATE_MAP.get(state, f"unknown({state})"),
            "active_connections": connections,
        }
    except Exception as e:
        log.warning(f"D-Bus NetworkManager unavailable, falling back to nmcli: {e}")
        return _nmcli_status()


def _nmcli_status() -> dict[str, Any]:
    """Fallback: parse nmcli output."""
    if not shutil.which("nmcli"):
        return {"error": "NetworkManager not available"}
    result = subprocess.run(
        ["nmcli", "-t", "connection", "show", "--active"],
        capture_output=True, text=True, timeout=5,
    )
    connections = []
    for line in result.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 2:
            connections.append({"id": parts[0], "type": parts[2] if len(parts) > 2 else "unknown"})
    return {"active_connections": connections}


def set_network(connection: str, enable: bool) -> dict[str, Any]:
    """Enable or disable a NetworkManager connection."""
    if not shutil.which("nmcli"):
        return {"error": "nmcli not available"}

    action = "up" if enable else "down"
    result = subprocess.run(
        ["nmcli", "connection", action, connection],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        return {"status": "success", "connection": connection, "enabled": enable}
    return {"error": result.stderr.strip() or result.stdout.strip()}


def manage_service(service: str, action: str) -> dict[str, Any]:
    """
    Manage systemd services.
    action: "start" | "stop" | "restart" | "status"
    Tries user units first, falls back to system units.
    """
    if action not in ("start", "stop", "restart", "status"):
        return {"error": f"Invalid action: {action}"}

    # Ensure .service suffix
    if not service.endswith(".service"):
        service_unit = f"{service}.service"
    else:
        service_unit = service

    # Try user unit first
    for scope in ("--user", "--system"):
        cmd = ["systemctl", scope, action, service_unit]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if action == "status":
                return {"service": service_unit, "status": output, "scope": scope}
            return {"status": "success", "service": service_unit, "action": action, "scope": scope}

    # Both failed — return combined error
    return {
        "error": f"Could not {action} {service_unit}",
        "hint": "Check if the service exists: systemctl list-units --all",
    }
