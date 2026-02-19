#!/usr/bin/env python3
"""
Waybar custom module — chi AI status indicator.

Polls io.chios.Agent D-Bus service for current status.
Outputs JSON for waybar's return-type: json.

Status dots:
  ● green  = ready
  ● yellow = thinking
  ● red    = error
  ○ grey   = offline
"""

import json
import sys


STATUS_ICONS = {
    "ready": ("●", "#5a8a6a", "chi ready"),
    "thinking": ("●", "#d4a85a", "chi thinking…"),
    "error": ("●", "#c05050", "chi error"),
    "offline": ("○", "#555566", "chi offline"),
}


def get_status() -> str:
    try:
        from pydbus import SessionBus
        bus = SessionBus()
        agent = bus.get("io.chios.Agent", "/io/chios/Agent")
        return agent.GetStatus()
    except Exception:
        return "offline"


def main() -> None:
    status = get_status()
    icon, color, tooltip = STATUS_ICONS.get(status, STATUS_ICONS["offline"])

    output = {
        "text": f'<span color="{color}">{icon}</span>',
        "tooltip": tooltip,
        "class": f"chi-{status}",
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
