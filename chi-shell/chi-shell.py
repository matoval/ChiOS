#!/usr/bin/env python3
"""
chi-shell — Custom GTK4 desktop panel for chiOS.

A bottom-anchored Wayland layer-shell panel providing:
  - App dock (pinned app icons, click to launch)
  - chi AI button (opens chi-overlay)
  - Clock and chi-agent status indicator
"""

import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("GtkLayerShell", "1.0")
from gi.repository import Gdk, GLib, Gio, Gtk, GtkLayerShell

APPS_CONFIG = Path.home() / ".config/chi-shell/apps.json"
CSS_FILE = "/usr/share/chi-shell/chi-shell.css"
PANEL_HEIGHT = 56

DEFAULT_APPS = [
    {"name": "Files", "icon": "system-file-manager", "exec": "nautilus"},
    {"name": "Browser", "icon": "firefox", "exec": "firefox"},
    {"name": "Terminal", "icon": "utilities-terminal", "exec": "kitty"},
    {"name": "Code", "icon": "codium", "exec": "codium"},
]


class ChiPanel(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app)
        self.set_name("chi-panel")
        self.set_decorated(False)

        # Pin to bottom of screen as a Wayland layer-shell surface
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        GtkLayerShell.auto_exclusive_zone_enable(self)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        self.set_default_size(-1, PANEL_HEIGHT)

        # Root layout
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.set_name("panel-root")
        self.set_child(root)

        # Left: app dock
        self._dock = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._dock.set_name("panel-dock")
        self._dock.set_margin_start(8)
        self._dock.set_valign(Gtk.Align.CENTER)
        root.append(self._dock)

        # Expand spacer left
        spacer_l = Gtk.Box()
        spacer_l.set_hexpand(True)
        root.append(spacer_l)

        # Center: chi button
        chi_btn = Gtk.Button()
        chi_btn.set_name("chi-button")
        chi_btn.set_valign(Gtk.Align.CENTER)
        chi_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        chi_icon = Gtk.Label(label="✦")
        chi_icon.set_name("chi-icon")
        chi_text = Gtk.Label(label="Ask chi…")
        chi_text.set_name("chi-label")
        chi_content.append(chi_icon)
        chi_content.append(chi_text)
        chi_btn.set_child(chi_content)
        chi_btn.connect("clicked", self._on_chi_clicked)
        root.append(chi_btn)

        # Expand spacer right
        spacer_r = Gtk.Box()
        spacer_r.set_hexpand(True)
        root.append(spacer_r)

        # Right: system area (status + clock)
        sys_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        sys_box.set_name("panel-sys")
        sys_box.set_margin_end(14)
        sys_box.set_valign(Gtk.Align.CENTER)

        self._status_dot = Gtk.Label(label="●")
        self._status_dot.set_name("status-dot")
        self._status_dot.add_css_class("status-offline")
        self._status_dot.set_tooltip_text("chi-agent: offline")
        sys_box.append(self._status_dot)

        self._clock = Gtk.Label()
        self._clock.set_name("panel-clock")
        sys_box.append(self._clock)

        root.append(sys_box)

        self._load_apps()
        self._tick()
        GLib.timeout_add(1000, self._tick)
        GLib.timeout_add(3000, self._poll_status)

    def _load_apps(self) -> None:
        apps = DEFAULT_APPS
        if APPS_CONFIG.exists():
            try:
                apps = json.loads(APPS_CONFIG.read_text())
            except Exception:
                pass

        for a in apps:
            btn = Gtk.Button()
            btn.set_name("dock-btn")
            btn.set_tooltip_text(a["name"])

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            icon = Gtk.Image.new_from_icon_name(a.get("icon", "application-x-executable"))
            icon.set_pixel_size(20)
            lbl = Gtk.Label(label=a["name"])
            lbl.set_name("dock-label")
            box.append(icon)
            box.append(lbl)
            btn.set_child(box)
            btn.connect("clicked", self._on_app_clicked, a["exec"])
            self._dock.append(btn)

    def _on_app_clicked(self, _btn, exec_cmd: str) -> None:
        try:
            subprocess.Popen(exec_cmd.split(), start_new_session=True)
        except Exception as e:
            print(f"[chi-shell] launch failed: {exec_cmd}: {e}", file=sys.stderr)

    def _on_chi_clicked(self, _btn) -> None:
        # Launch or re-activate chi-overlay (GTK IS_SERVICE handles singleton)
        subprocess.Popen(
            ["python3", "/usr/lib/chi-overlay/overlay.py"],
            start_new_session=True,
        )

    def _tick(self) -> bool:
        self._clock.set_text(datetime.now().strftime("%-I:%M %p"))
        return True

    def _poll_status(self) -> bool:
        def _check():
            try:
                from pydbus import SessionBus
                bus = SessionBus()
                agent = bus.get("io.chios.Agent", "/io/chios/Agent")
                status = agent.GetStatus()
            except Exception:
                status = "offline"
            GLib.idle_add(self._update_status, status)

        threading.Thread(target=_check, daemon=True).start()
        return True

    def _update_status(self, status: str) -> None:
        css_classes = ["status-ready", "status-thinking", "status-error", "status-offline"]
        for c in css_classes:
            self._status_dot.remove_css_class(c)
        self._status_dot.add_css_class(f"status-{status}")
        self._status_dot.set_tooltip_text(f"chi-agent: {status}")


class ChiShellApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="io.chios.Shell",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_activate(self):
        css = Gtk.CssProvider()
        css_path = Path(CSS_FILE)
        if css_path.exists():
            css.load_from_path(str(css_path))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        win = ChiPanel(self)
        win.present()


if __name__ == "__main__":
    app = ChiShellApp()
    sys.exit(app.run(sys.argv))
