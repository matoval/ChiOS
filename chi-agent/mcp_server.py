#!/usr/bin/env python3
"""
MCP server for chi-agent.

Exposes chi tools as an MCP (Model Context Protocol) server so
Claude Code (pre-installed) can use them natively.

Claude Code users can add this server in their MCP config:
  {
    "mcpServers": {
      "chi": {
        "command": "python3",
        "args": ["/usr/lib/chi-agent/mcp_server.py", "--standalone"]
      }
    }
  }
"""

import json
import logging
import sys
from typing import Any

log = logging.getLogger("chi-agent.mcp")


def run_mcp_server() -> None:
    """Run MCP server over stdio. Blocks until stdin closes."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError:
        log.error("mcp package not installed. Run: pip install mcp")
        return

    from tools.apps import launch_app
    from tools.packages import install_app, install_system, remove_app
    from tools.shell import run_shell
    from tools.system import get_network_status, set_network, manage_service
    from tools.envclone import envclone_init, envclone_up, envclone_down, envclone_code

    server = Server("chi-agent")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="chi_launch_app",
                description="Launch a desktop application on chiOS",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app": {"type": "string", "description": "App name (e.g. firefox, kitty, codium)"},
                    },
                    "required": ["app"],
                },
            ),
            types.Tool(
                name="chi_install_app",
                description="Install a GUI app via flatpak (immediate) or rpm-ostree (staged)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "App or package name"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="chi_install_system",
                description="Install a system package via rpm-ostree (requires reboot)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "RPM package name"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="chi_remove_app",
                description="Remove an installed application",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "App or package name"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="chi_run_shell",
                description="Run a shell command on chiOS (30s timeout, user namespace)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command"},
                    },
                    "required": ["command"],
                },
            ),
            types.Tool(
                name="chi_get_network_status",
                description="Get current network connection status",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="chi_manage_service",
                description="Start, stop, restart, or get status of a systemd service",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "action": {"type": "string", "enum": ["start", "stop", "restart", "status"]},
                    },
                    "required": ["service", "action"],
                },
            ),
            types.Tool(
                name="chi_envclone_init",
                description="Initialize a new dev environment with envclone",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "env_type": {"type": "string", "description": "e.g. python, node, rust"},
                        "name": {"type": "string", "description": "Project name"},
                    },
                    "required": ["env_type", "name"],
                },
            ),
            types.Tool(
                name="chi_envclone_up",
                description="Start an envclone dev environment",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="chi_envclone_down",
                description="Stop an envclone dev environment",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="chi_envclone_code",
                description="Open VSCodium in an envclone dev environment",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        dispatch = {
            "chi_launch_app": lambda a: launch_app(a["app"]),
            "chi_install_app": lambda a: install_app(a["name"]),
            "chi_install_system": lambda a: install_system(a["name"]),
            "chi_remove_app": lambda a: remove_app(a["name"]),
            "chi_run_shell": lambda a: run_shell(a["command"]),
            "chi_get_network_status": lambda a: get_network_status(),
            "chi_manage_service": lambda a: manage_service(a["service"], a["action"]),
            "chi_envclone_init": lambda a: envclone_init(a["env_type"], a["name"]),
            "chi_envclone_up": lambda a: envclone_up(a["name"]),
            "chi_envclone_down": lambda a: envclone_down(a["name"]),
            "chi_envclone_code": lambda a: envclone_code(a["name"]),
        }

        handler = dispatch.get(name)
        if not handler:
            result = {"error": f"Unknown tool: {name}"}
        else:
            try:
                result = handler(arguments)
            except Exception as e:
                result = {"error": str(e)}

        text = json.dumps(result) if not isinstance(result, str) else result
        return [types.TextContent(type="text", text=text)]

    import asyncio

    async def _main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    log.info("MCP server starting on stdio")
    asyncio.run(_main())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_mcp_server()
