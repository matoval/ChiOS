#!/usr/bin/env python3
"""
chi-agent — main AI orchestration loop.

Connects to Ollama, dispatches tool calls, and exposes two interfaces:
  - D-Bus session service (io.chios.Agent) for chi-overlay IPC
  - MCP server for Claude Code integration
"""

import argparse
import json
import logging
import sys
from typing import Any

import requests
from pydantic import BaseModel

from tools.apps import launch_app
from tools.packages import install_app, install_system, remove_app
from tools.shell import run_shell
from tools.system import get_network_status, set_network, manage_service
from tools.envclone import envclone_init, envclone_up, envclone_down, envclone_code

OLLAMA_HOST = "http://localhost:11434"
MODEL = "chi"  # loaded from Modelfile as 'chi' alias, falls back to qwen3:8b

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [chi-agent] %(levelname)s: %(message)s",
)
log = logging.getLogger("chi-agent")


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch a desktop application by name or .desktop entry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "App name, e.g. 'firefox', 'kitty', 'codium'"},
                },
                "required": ["app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_app",
            "description": "Install a GUI application. Tries flatpak first (immediate), falls back to rpm-ostree (staged, requires reboot).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Package or app name"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_system",
            "description": "Install a system-level package via rpm-ostree. Requires reboot to apply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "RPM package name"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_app",
            "description": "Remove an installed application (flatpak or rpm-ostree override).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "App or package name"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command as the current user. 30s timeout. Not for destructive operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_status",
            "description": "Get current network connection status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_network",
            "description": "Enable or disable a network connection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection": {"type": "string", "description": "Connection name"},
                    "enable": {"type": "boolean"},
                },
                "required": ["connection", "enable"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_service",
            "description": "Start, stop, restart, or get status of a systemd service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "systemd service name"},
                    "action": {"type": "string", "enum": ["start", "stop", "restart", "status"]},
                },
                "required": ["service", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "envclone_init",
            "description": "Initialize a new dev environment using envclone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "env_type": {"type": "string", "description": "Environment type, e.g. 'python', 'node', 'rust'"},
                    "name": {"type": "string", "description": "Project name"},
                },
                "required": ["env_type", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "envclone_up",
            "description": "Start an envclone dev environment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Environment name"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "envclone_down",
            "description": "Stop an envclone dev environment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Environment name"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "envclone_code",
            "description": "Open VSCodium in an envclone dev environment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Environment name"},
                },
                "required": ["name"],
            },
        },
    },
]

TOOL_MAP = {
    "launch_app": lambda args: launch_app(args["app"]),
    "install_app": lambda args: install_app(args["name"]),
    "install_system": lambda args: install_system(args["name"]),
    "remove_app": lambda args: remove_app(args["name"]),
    "run_shell": lambda args: run_shell(args["command"]),
    "get_network_status": lambda args: get_network_status(),
    "set_network": lambda args: set_network(args["connection"], args["enable"]),
    "manage_service": lambda args: manage_service(args["service"], args["action"]),
    "envclone_init": lambda args: envclone_init(args["env_type"], args["name"]),
    "envclone_up": lambda args: envclone_up(args["name"]),
    "envclone_down": lambda args: envclone_down(args["name"]),
    "envclone_code": lambda args: envclone_code(args["name"]),
}


# ---------------------------------------------------------------------------
# Ollama chat loop
# ---------------------------------------------------------------------------

def ensure_model() -> None:
    """Pull model if not present."""
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        tags = [m["name"] for m in resp.json().get("models", [])]
        if not any(t.startswith("chi") or t.startswith("qwen3") for t in tags):
            log.info("Model not found locally, pulling qwen3:8b...")
            requests.post(
                f"{OLLAMA_HOST}/api/pull",
                json={"name": "qwen3:8b"},
                timeout=600,
            )
    except requests.RequestException as e:
        log.warning(f"Could not verify model: {e}")


def chat(prompt: str, history: list[dict] | None = None) -> tuple[str, list[dict]]:
    """
    Send a prompt to Ollama with tool support.
    Returns (final_text_response, updated_history).
    """
    if history is None:
        history = []

    messages = history + [{"role": "user", "content": prompt}]

    while True:
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": MODEL,
                    "messages": messages,
                    "tools": TOOLS,
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            return f"Error connecting to Ollama: {e}", messages

        data = resp.json()
        message = data.get("message", {})
        messages.append(message)

        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            # No more tool calls — return final response
            return message.get("content", ""), messages

        # Dispatch tool calls
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"].get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except json.JSONDecodeError:
                    fn_args = {}

            log.info(f"Tool call: {fn_name}({fn_args})")

            handler = TOOL_MAP.get(fn_name)
            if handler:
                try:
                    result = handler(fn_args)
                except Exception as e:
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {fn_name}"}

            log.info(f"Tool result: {result}")

            # Persist tool data for the Data tab
            try:
                from history import record_tool_data
                record_tool_data(fn_name, result)
            except Exception:
                pass

            messages.append({
                "role": "tool",
                "content": json.dumps(result) if not isinstance(result, str) else result,
            })


# ---------------------------------------------------------------------------
# CLI / interactive mode
# ---------------------------------------------------------------------------

def run_interactive() -> None:
    """Simple REPL for testing chi-agent directly."""
    print("chi-agent interactive mode. Type 'quit' to exit.")
    history: list[dict] = []
    while True:
        try:
            user_input = input("\nchi> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break
        response, history = chat(user_input, history)
        print(f"\n{response}")


def run_daemon() -> None:
    """Run as daemon: expose D-Bus service and MCP server."""
    import threading

    from dbus_service import run_dbus_service
    from mcp_server import run_mcp_server

    ensure_model()
    log.info("Starting chi-agent daemon")

    # D-Bus in background thread
    dbus_thread = threading.Thread(target=run_dbus_service, daemon=True)
    dbus_thread.start()

    # MCP server blocks main thread
    run_mcp_server()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="chi-agent AI orchestration service")
    parser.add_argument(
        "--mode",
        choices=["interactive", "daemon"],
        default="interactive",
        help="Run mode (default: interactive)",
    )
    args = parser.parse_args()

    if args.mode == "daemon":
        run_daemon()
    else:
        ensure_model()
        run_interactive()
