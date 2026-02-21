#!/usr/bin/env python3
"""
chi-greeter — Custom GTK4 login screen for chiOS.

Works with greetd via its JSON IPC protocol over a Unix socket.
Must be launched inside a Wayland compositor (e.g. cage):
    greetd config: command = "cage -s -- chi-greeter"
"""

import json
import os
import pwd
import socket
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gio, Gtk

GREETD_SOCK = os.environ.get("GREETD_SOCK", "")
SESSION_CMD = ["labwc"]
CSS_FILE = "/usr/share/chi-greeter/chi-greeter.css"


# ---------------------------------------------------------------------------
# greetd IPC client
# ---------------------------------------------------------------------------

class GreetdClient:
    """Minimal greetd IPC client (length-prefixed JSON over Unix socket)."""

    def __init__(self, sock_path: str):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(sock_path)

    def _send(self, msg: dict) -> dict:
        data = json.dumps(msg).encode()
        self._sock.sendall(len(data).to_bytes(4, "little") + data)
        raw_len = self._recv_exact(4)
        length = int.from_bytes(raw_len, "little")
        return json.loads(self._recv_exact(length))

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("greetd closed the connection")
            buf += chunk
        return buf

    def create_session(self, username: str) -> dict:
        return self._send({"type": "create_session", "username": username})

    def post_auth_message_response(self, response: str | None) -> dict:
        return self._send({"type": "post_auth_message_response", "response": response})

    def start_session(self, cmd: list[str], env: list[str]) -> dict:
        return self._send({"type": "start_session", "cmd": cmd, "env": env})

    def cancel_session(self) -> dict:
        return self._send({"type": "cancel_session"})

    def close(self):
        self._sock.close()


# ---------------------------------------------------------------------------
# GTK4 greeter window
# ---------------------------------------------------------------------------

class ChiGreeter(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app)
        self.set_name("chi-greeter-window")
        self.fullscreen()

        self._auth_pending = False
        self._build_ui()
        self._update_clock()
        GLib.timeout_add(1000, self._update_clock)

    def _build_ui(self) -> None:
        overlay = Gtk.Overlay()
        self.set_child(overlay)

        # Full-screen background
        bg = Gtk.Box()
        bg.set_name("greeter-bg")
        bg.set_hexpand(True)
        bg.set_vexpand(True)
        overlay.set_child(bg)

        # Centered login card
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(outer)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.set_name("greeter-card")
        outer.append(card)

        # Logo block
        logo_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        logo_box.set_name("greeter-logo-block")
        logo_box.set_halign(Gtk.Align.CENTER)
        logo_box.set_margin_bottom(28)

        icon_lbl = Gtk.Label(label="✦")
        icon_lbl.set_name("greeter-logo-icon")

        brand_lbl = Gtk.Label(label="chiOS")
        brand_lbl.set_name("greeter-brand")

        tagline_lbl = Gtk.Label(label="Your AI-native OS")
        tagline_lbl.set_name("greeter-tagline")

        logo_box.append(icon_lbl)
        logo_box.append(brand_lbl)
        logo_box.append(tagline_lbl)
        card.append(logo_box)

        # Clock
        self._clock_lbl = Gtk.Label()
        self._clock_lbl.set_name("greeter-clock")
        self._clock_lbl.set_halign(Gtk.Align.CENTER)
        card.append(self._clock_lbl)

        self._date_lbl = Gtk.Label()
        self._date_lbl.set_name("greeter-date")
        self._date_lbl.set_halign(Gtk.Align.CENTER)
        self._date_lbl.set_margin_bottom(28)
        card.append(self._date_lbl)

        # Login form
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        form.set_name("greeter-form")
        form.set_margin_bottom(8)
        card.append(form)

        self._user_entry = Gtk.Entry()
        self._user_entry.set_name("greeter-entry")
        self._user_entry.set_placeholder_text("Username")
        self._user_entry.connect("activate", lambda _: self._pass_entry.grab_focus())
        form.append(self._user_entry)

        self._pass_entry = Gtk.Entry()
        self._pass_entry.set_name("greeter-entry")
        self._pass_entry.set_placeholder_text("Password")
        self._pass_entry.set_visibility(False)
        self._pass_entry.connect("activate", self._on_login)
        form.append(self._pass_entry)

        # Error label
        self._error_lbl = Gtk.Label(label="")
        self._error_lbl.set_name("greeter-error")
        self._error_lbl.set_halign(Gtk.Align.CENTER)
        self._error_lbl.set_margin_bottom(4)
        card.append(self._error_lbl)

        # Login button
        login_btn = Gtk.Button(label="Login")
        login_btn.set_name("greeter-login-btn")
        login_btn.connect("clicked", self._on_login)
        card.append(login_btn)

        # Power buttons
        power_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        power_box.set_name("greeter-power")
        power_box.set_halign(Gtk.Align.CENTER)
        power_box.set_margin_top(28)
        card.append(power_box)

        shutdown_btn = Gtk.Button(label="⏻  Shutdown")
        shutdown_btn.set_name("power-btn")
        shutdown_btn.connect("clicked", lambda _: subprocess.run(["loginctl", "poweroff"]))
        power_box.append(shutdown_btn)

        restart_btn = Gtk.Button(label="↺  Restart")
        restart_btn.set_name("power-btn")
        restart_btn.connect("clicked", lambda _: subprocess.run(["loginctl", "reboot"]))
        power_box.append(restart_btn)

    def _update_clock(self) -> bool:
        now = datetime.now()
        self._clock_lbl.set_text(now.strftime("%-I:%M %p"))
        self._date_lbl.set_text(now.strftime("%A, %B %-d %Y"))
        return True

    def _on_login(self, *_) -> None:
        if self._auth_pending:
            return
        username = self._user_entry.get_text().strip()
        password = self._pass_entry.get_text()
        if not username:
            self._show_error("Please enter your username.")
            return
        self._auth_pending = True
        self._error_lbl.set_text("")
        threading.Thread(
            target=self._do_login, args=(username, password), daemon=True
        ).start()

    def _do_login(self, username: str, password: str) -> None:
        if not GREETD_SOCK:
            GLib.idle_add(self._show_error, "greetd socket not found (GREETD_SOCK unset)")
            return
        try:
            client = GreetdClient(GREETD_SOCK)
            resp = client.create_session(username)

            # Walk through PAM auth messages
            while resp.get("type") == "auth_message":
                msg_type = resp.get("auth_message_type", "")
                if msg_type == "secret":
                    resp = client.post_auth_message_response(password)
                elif msg_type == "visible":
                    resp = client.post_auth_message_response(username)
                else:
                    resp = client.post_auth_message_response(None)

            if resp.get("type") == "success":
                try:
                    uid = pwd.getpwnam(username).pw_uid
                except KeyError:
                    uid = 1000
                env = [
                    "XDG_SESSION_TYPE=wayland",
                    f"XDG_RUNTIME_DIR=/run/user/{uid}",
                    "GDK_BACKEND=wayland",
                    "MOZ_ENABLE_WAYLAND=1",
                ]
                resp2 = client.start_session(SESSION_CMD, env)
                if resp2.get("type") != "success":
                    GLib.idle_add(
                        self._show_error,
                        resp2.get("description", "Failed to start session"),
                    )
            else:
                client.cancel_session()
                GLib.idle_add(self._show_error, "Incorrect username or password.")

            client.close()
        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _show_error(self, msg: str) -> None:
        self._error_lbl.set_text(msg)
        self._pass_entry.set_text("")
        self._auth_pending = False
        self._pass_entry.grab_focus()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class ChiGreeterApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="io.chios.Greeter",
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
        win = ChiGreeter(self)
        win.present()


if __name__ == "__main__":
    app = ChiGreeterApp()
    sys.exit(app.run(sys.argv))
