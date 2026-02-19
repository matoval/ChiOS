#!/usr/bin/env python3
"""
chi-overlay — GTK4 AI prompt popup for chiOS.

Triggered by Super+Space (via Hyprland keybinding).
Floats above all windows, borderless, transparent.
Sends user input to chi-agent via D-Bus, streams response.

Usage:
  python3 overlay.py          # show overlay once
  python3 overlay.py --daemon # wait for D-Bus activation signals
"""

import argparse
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Gio


DBUS_NAME = "io.chios.Agent"
DBUS_PATH = "/io/chios/Agent"
CSS_FILE = "/usr/lib/chi-overlay/overlay.css"


class ChiOverlay(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app)
        self.set_title("chi")
        self.set_default_size(620, 80)
        self.set_decorated(False)
        self.set_resizable(False)

        # Load CSS
        css_provider = Gtk.CssProvider()
        try:
            css_provider.load_from_path(CSS_FILE)
        except Exception:
            css_provider.load_from_string(self._default_css())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.add_css_class("chi-overlay")

        # Layout
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._box.set_margin_start(16)
        self._box.set_margin_end(16)
        self._box.set_margin_top(12)
        self._box.set_margin_bottom(12)
        self.set_child(self._box)

        # Input row
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._box.append(input_row)

        label = Gtk.Label(label="chi")
        label.add_css_class("chi-label")
        input_row.append(label)

        self._entry = Gtk.Entry()
        self._entry.set_hexpand(True)
        self._entry.set_placeholder_text("Ask chi anything…")
        self._entry.add_css_class("chi-entry")
        self._entry.connect("activate", self._on_submit)
        input_row.append(self._entry)

        # Response area
        self._response_label = Gtk.Label()
        self._response_label.set_wrap(True)
        self._response_label.set_xalign(0)
        self._response_label.add_css_class("chi-response")
        self._response_label.set_visible(False)
        self._box.append(self._response_label)

        # Action log
        self._action_label = Gtk.Label()
        self._action_label.set_xalign(0)
        self._action_label.add_css_class("chi-action")
        self._action_label.set_visible(False)
        self._box.append(self._action_label)

        # Close on Escape
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        # Focus entry on show
        self._entry.grab_focus()

        # D-Bus proxy (lazy)
        self._agent_proxy = None

    def _default_css(self) -> str:
        return """
        .chi-overlay {
            background-color: rgba(15, 15, 20, 0.92);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .chi-label {
            color: #7c6af7;
            font-weight: bold;
            font-size: 14px;
            min-width: 30px;
        }
        .chi-entry {
            background: transparent;
            border: none;
            color: #e8e8f0;
            font-size: 15px;
            caret-color: #7c6af7;
        }
        entry { box-shadow: none; }
        .chi-response {
            color: #c8c8d8;
            font-size: 13px;
            padding-top: 4px;
        }
        .chi-action {
            color: #5a8a6a;
            font-size: 12px;
            font-style: italic;
        }
        """

    def _get_agent(self):
        if self._agent_proxy is not None:
            return self._agent_proxy
        try:
            from pydbus import SessionBus
            bus = SessionBus()
            self._agent_proxy = bus.get(DBUS_NAME, DBUS_PATH)
            return self._agent_proxy
        except Exception as e:
            return None

    def _on_submit(self, entry: Gtk.Entry) -> None:
        prompt = entry.get_text().strip()
        if not prompt:
            return

        entry.set_sensitive(False)
        self._show_action("Thinking…")
        self._response_label.set_visible(False)

        def _ask():
            agent = self._get_agent()
            if agent is None:
                GLib.idle_add(self._show_error, "chi-agent not running")
                return
            try:
                response = agent.Ask(prompt)
                GLib.idle_add(self._show_response, response)
            except Exception as e:
                GLib.idle_add(self._show_error, str(e))

        threading.Thread(target=_ask, daemon=True).start()

    def _show_action(self, text: str) -> None:
        self._action_label.set_text(text)
        self._action_label.set_visible(True)
        self._resize()

    def _show_response(self, text: str) -> None:
        self._action_label.set_visible(False)
        self._response_label.set_text(text)
        self._response_label.set_visible(True)
        self._entry.set_sensitive(True)
        self._entry.set_text("")
        self._entry.grab_focus()
        self._resize()
        # Auto-close after 8 seconds if no follow-up
        GLib.timeout_add_seconds(8, self._auto_close)

    def _show_error(self, error: str) -> None:
        self._action_label.set_visible(False)
        self._response_label.set_markup(f'<span color="#c05050">Error: {GLib.markup_escape_text(error)}</span>')
        self._response_label.set_visible(True)
        self._entry.set_sensitive(True)
        self._entry.grab_focus()
        self._resize()

    def _resize(self) -> None:
        # Expand height to fit content
        self.set_default_size(620, -1)

    def _auto_close(self) -> bool:
        if not self._entry.has_focus():
            self.close()
        return False  # don't repeat

    def _on_key(self, ctrl, keyval, keycode, state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False


class ChiOverlayApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="io.chios.Overlay",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._window = None

    def do_activate(self):
        if self._window is None:
            self._window = ChiOverlay(self)
        self._window.present()


def main():
    parser = argparse.ArgumentParser(description="chi-overlay GTK4 popup")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    args = parser.parse_args()

    app = ChiOverlayApp()
    sys.exit(app.run(None))


if __name__ == "__main__":
    main()
