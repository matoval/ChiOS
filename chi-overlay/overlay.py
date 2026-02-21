#!/usr/bin/env python3
"""
chi-overlay v2 — Tabbed AI assistant window for chiOS.

Runs as a persistent GTK IS_SERVICE application (singleton).
Tabs: Chat | History | Data

Launched by chi-shell panel button or Super+Space keybinding.
Second launch activates (shows) the already-running instance.
"""

import json
import sys
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gio, Gtk

DBUS_AGENT = "io.chios.Agent"
DBUS_AGENT_PATH = "/io/chios/Agent"
CSS_FILE = "/usr/lib/chi-overlay/overlay.css"
WINDOW_WIDTH = 720
WINDOW_HEIGHT = 540


# ---------------------------------------------------------------------------
# Chat message row
# ---------------------------------------------------------------------------

class MessageRow(Gtk.Box):
    def __init__(self, role: str, content: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.add_css_class("msg-row")
        self.add_css_class(f"msg-{role}")

        who = Gtk.Label(label="You" if role == "user" else "chi")
        who.set_xalign(0)
        who.add_css_class("msg-who")
        self.append(who)

        text = Gtk.Label(label=content)
        text.set_xalign(0)
        text.set_wrap(True)
        text.set_wrap_mode(2)  # WORD_CHAR
        text.set_selectable(True)
        text.add_css_class("msg-text")
        self.append(text)


# ---------------------------------------------------------------------------
# Chat tab
# ---------------------------------------------------------------------------

class ChatTab(Gtk.Box):
    def __init__(self, overlay_win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = overlay_win

        # Message list in a scrolled window
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._msg_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._msg_list.set_name("msg-list")
        scroll.set_child(self._msg_list)
        self._scroll = scroll

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # Input bar
        input_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_bar.set_name("input-bar")
        input_bar.set_margin_start(12)
        input_bar.set_margin_end(12)
        input_bar.set_margin_top(10)
        input_bar.set_margin_bottom(10)
        self.append(input_bar)

        # Voice button
        voice_btn = Gtk.Button(label="🎤")
        voice_btn.set_name("voice-btn")
        voice_btn.set_tooltip_text("Push-to-talk (or hold Super+V)")
        voice_btn.connect("clicked", self._on_voice)
        input_bar.append(voice_btn)

        # Text entry
        self._entry = Gtk.Entry()
        self._entry.set_hexpand(True)
        self._entry.set_placeholder_text("Ask chi anything…")
        self._entry.set_name("chi-entry")
        self._entry.connect("activate", self._on_submit)
        input_bar.append(self._entry)

        # Send button
        send_btn = Gtk.Button(label="Send ▶")
        send_btn.set_name("send-btn")
        send_btn.connect("clicked", self._on_submit)
        input_bar.append(send_btn)

        # "Thinking…" indicator (hidden by default)
        self._thinking = Gtk.Label(label="Thinking…")
        self._thinking.set_name("thinking-label")
        self._thinking.set_halign(Gtk.Align.START)
        self._thinking.set_margin_start(12)
        self._thinking.set_margin_bottom(6)
        self._thinking.set_visible(False)
        self.append(self._thinking)

        self._agent = None

    def focus_entry(self) -> None:
        self._entry.grab_focus()

    def add_message(self, role: str, content: str) -> None:
        row = MessageRow(role, content)
        self._msg_list.append(row)
        # Scroll to bottom after GTK finishes layout
        GLib.idle_add(self._scroll_bottom)

    def _scroll_bottom(self) -> bool:
        adj = self._scroll.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False

    def _on_submit(self, *_) -> None:
        prompt = self._entry.get_text().strip()
        if not prompt:
            return
        self._entry.set_text("")
        self._entry.set_sensitive(False)
        self._thinking.set_visible(True)
        self.add_message("user", prompt)

        threading.Thread(target=self._ask, args=(prompt,), daemon=True).start()

    def _ask(self, prompt: str) -> None:
        agent = self._get_agent()
        if agent is None:
            GLib.idle_add(self._on_response, None, "chi-agent is not running.")
            return
        try:
            response = agent.Ask(prompt)
            GLib.idle_add(self._on_response, response, None)
        except Exception as e:
            GLib.idle_add(self._on_response, None, str(e))

    def _on_response(self, response: str | None, error: str | None) -> None:
        self._thinking.set_visible(False)
        self._entry.set_sensitive(True)
        self._entry.grab_focus()
        if response is not None:
            self.add_message("assistant", response)
        else:
            self.add_message("assistant", f"Error: {error}")

    def _get_agent(self):
        if self._agent:
            return self._agent
        try:
            from pydbus import SessionBus
            self._agent = SessionBus().get(DBUS_AGENT, DBUS_AGENT_PATH)
        except Exception:
            self._agent = None
        return self._agent

    def _on_voice(self, _btn) -> None:
        import subprocess
        subprocess.Popen(["/usr/lib/chi-voice/voice.sh"], start_new_session=True)


# ---------------------------------------------------------------------------
# History tab
# ---------------------------------------------------------------------------

class HistoryTab(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_name("tab-toolbar")
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)
        toolbar.set_margin_top(10)
        toolbar.set_margin_bottom(10)
        self.append(toolbar)

        title = Gtk.Label(label="Past conversations")
        title.set_name("tab-title")
        title.set_hexpand(True)
        title.set_xalign(0)
        toolbar.append(title)

        refresh_btn = Gtk.Button(label="↻")
        refresh_btn.set_name("refresh-btn")
        refresh_btn.set_tooltip_text("Refresh history")
        refresh_btn.connect("clicked", lambda _: self.refresh())
        toolbar.append(refresh_btn)

        clear_btn = Gtk.Button(label="🗑 Clear all")
        clear_btn.set_name("delete-btn")
        clear_btn.set_tooltip_text("Permanently delete all conversation history")
        clear_btn.connect("clicked", self._on_clear_all)
        toolbar.append(clear_btn)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._list.set_name("history-list")
        scroll.set_child(self._list)

    def refresh(self) -> None:
        # Clear existing rows
        while True:
            child = self._list.get_first_child()
            if child is None:
                break
            self._list.remove(child)

        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        try:
            from pydbus import SessionBus
            bus = SessionBus()
            agent = bus.get(DBUS_AGENT, DBUS_AGENT_PATH)
            raw = agent.GetHistory(30)
            conversations = json.loads(raw)
        except Exception as e:
            conversations = []
            GLib.idle_add(self._add_placeholder, f"Could not load history: {e}")
            return

        if not conversations:
            GLib.idle_add(self._add_placeholder, "No conversation history yet.")
            return

        for conv in conversations:
            GLib.idle_add(self._add_conv_row, conv)

    def _add_conv_row(self, conv: dict) -> None:
        # Outer wrapper holds the row + its separator so we can remove both
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        wrapper.set_name("history-wrapper")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_name("history-row")
        row.set_margin_start(12)
        row.set_margin_end(12)
        row.set_margin_top(6)
        row.set_margin_bottom(6)

        # Text block (date + preview)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)

        date_str = conv.get("updated_at", "")[:16].replace("T", "  ")
        count = conv.get("message_count", 0)
        header = Gtk.Label(label=f"{date_str}  ·  {count} messages")
        header.set_name("history-date")
        header.set_xalign(0)
        text_box.append(header)

        preview = Gtk.Label(label=conv.get("preview", ""))
        preview.set_name("history-preview")
        preview.set_xalign(0)
        preview.set_wrap(True)
        preview.set_max_width_chars(72)
        text_box.append(preview)

        row.append(text_box)

        # Delete button for this conversation
        conv_id = conv.get("id")
        del_btn = Gtk.Button(label="🗑")
        del_btn.set_name("row-delete-btn")
        del_btn.set_tooltip_text("Delete this conversation")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.connect("clicked", self._on_delete_conv, conv_id, wrapper)
        row.append(del_btn)

        wrapper.append(row)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        wrapper.append(sep)

        self._list.append(wrapper)

    def _on_delete_conv(self, _btn, conv_id: int, wrapper) -> None:
        def _do():
            try:
                from pydbus import SessionBus
                bus = SessionBus()
                agent = bus.get(DBUS_AGENT, DBUS_AGENT_PATH)
                agent.DeleteConversation(conv_id)
            except Exception as e:
                print(f"[chi-overlay] DeleteConversation error: {e}")
            GLib.idle_add(self._list.remove, wrapper)

        threading.Thread(target=_do, daemon=True).start()

    def _on_clear_all(self, _btn) -> None:
        def _do():
            try:
                from pydbus import SessionBus
                bus = SessionBus()
                agent = bus.get(DBUS_AGENT, DBUS_AGENT_PATH)
                agent.ClearAllHistory()
            except Exception as e:
                print(f"[chi-overlay] ClearAllHistory error: {e}")
            GLib.idle_add(self.refresh)

        threading.Thread(target=_do, daemon=True).start()

    def _add_placeholder(self, text: str) -> None:
        lbl = Gtk.Label(label=text)
        lbl.set_name("placeholder")
        lbl.set_margin_top(40)
        self._list.append(lbl)


# ---------------------------------------------------------------------------
# Data tab
# ---------------------------------------------------------------------------

class DataTab(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_name("tab-toolbar")
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)
        toolbar.set_margin_top(10)
        toolbar.set_margin_bottom(10)
        self.append(toolbar)

        title = Gtk.Label(label="Data collected by chi")
        title.set_name("tab-title")
        title.set_hexpand(True)
        title.set_xalign(0)
        toolbar.append(title)

        refresh_btn = Gtk.Button(label="↻")
        refresh_btn.set_name("refresh-btn")
        refresh_btn.set_tooltip_text("Refresh data")
        refresh_btn.connect("clicked", lambda _: self.refresh())
        toolbar.append(refresh_btn)

        export_btn = Gtk.Button(label="Export JSON")
        export_btn.set_name("export-btn")
        export_btn.set_tooltip_text("Save all data to ~/Downloads/chi-data.json")
        export_btn.connect("clicked", self._on_export)
        toolbar.append(export_btn)

        clear_btn = Gtk.Button(label="🗑 Clear data")
        clear_btn.set_name("delete-btn")
        clear_btn.set_tooltip_text("Permanently delete all collected tool data")
        clear_btn.connect("clicked", self._on_clear_data)
        toolbar.append(clear_btn)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._textview = Gtk.TextView()
        self._textview.set_name("data-view")
        self._textview.set_editable(False)
        self._textview.set_monospace(True)
        self._textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._buffer = self._textview.get_buffer()
        scroll.set_child(self._textview)

    def refresh(self) -> None:
        self._buffer.set_text("Loading…")
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        try:
            from pydbus import SessionBus
            bus = SessionBus()
            agent = bus.get(DBUS_AGENT, DBUS_AGENT_PATH)
            raw = agent.GetData(50)
            data = json.loads(raw)
            text = json.dumps(data, indent=2, ensure_ascii=False)
        except Exception as e:
            text = f"Could not load data: {e}"
        GLib.idle_add(self._buffer.set_text, text)

    def _on_export(self, _btn) -> None:
        def _do():
            try:
                from pydbus import SessionBus
                bus = SessionBus()
                agent = bus.get(DBUS_AGENT, DBUS_AGENT_PATH)
                raw = agent.GetData(1000)
                out = Path.home() / "Downloads" / "chi-data.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(raw)
                GLib.idle_add(self._buffer.set_text, f"Exported to {out}\n\n" + raw)
            except Exception as e:
                GLib.idle_add(self._buffer.set_text, f"Export failed: {e}")

        threading.Thread(target=_do, daemon=True).start()

    def _on_clear_data(self, _btn) -> None:
        def _do():
            try:
                from pydbus import SessionBus
                bus = SessionBus()
                agent = bus.get(DBUS_AGENT, DBUS_AGENT_PATH)
                agent.ClearData()
                GLib.idle_add(self._buffer.set_text, "All collected data has been deleted.")
            except Exception as e:
                GLib.idle_add(self._buffer.set_text, f"Clear failed: {e}")

        threading.Thread(target=_do, daemon=True).start()


# ---------------------------------------------------------------------------
# Main overlay window
# ---------------------------------------------------------------------------

class ChiOverlay(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app)
        self.set_title("chi")
        self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.set_resizable(True)
        self.add_css_class("chi-overlay-window")

        # Prevent window destruction on close — just hide it
        self.connect("close-request", self._on_close_request)

        # Close on Escape
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        # Header bar
        header = Gtk.HeaderBar()
        header.set_name("chi-header")
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon = Gtk.Label(label="✦")
        icon.set_name("header-icon")
        brand = Gtk.Label(label="chi")
        brand.set_name("header-brand")
        title_box.append(icon)
        title_box.append(brand)
        header.set_title_widget(title_box)
        self.set_titlebar(header)

        # Notebook (tabs)
        self._notebook = Gtk.Notebook()
        self._notebook.set_name("chi-notebook")
        self._notebook.connect("switch-page", self._on_tab_switch)
        self.set_child(self._notebook)

        # Chat tab
        self._chat = ChatTab(self)
        chat_lbl = Gtk.Label(label="Chat")
        self._notebook.append_page(self._chat, chat_lbl)

        # History tab
        self._history = HistoryTab()
        hist_lbl = Gtk.Label(label="History")
        self._notebook.append_page(self._history, hist_lbl)

        # Data tab
        self._data = DataTab()
        data_lbl = Gtk.Label(label="Data")
        self._notebook.append_page(self._data, data_lbl)

    def show_and_focus(self) -> None:
        self.present()
        self._chat.focus_entry()

    def _on_close_request(self, _win) -> bool:
        self.hide()
        return True  # Prevent destroy

    def _on_key(self, _ctrl, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _on_tab_switch(self, _nb, _page, page_num: int) -> None:
        if page_num == 1:
            self._history.refresh()
        elif page_num == 2:
            self._data.refresh()


# ---------------------------------------------------------------------------
# Application (singleton via IS_SERVICE)
# ---------------------------------------------------------------------------

class ChiOverlayApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="io.chios.Overlay",
            flags=Gio.ApplicationFlags.IS_SERVICE,
        )
        self._window: ChiOverlay | None = None

    def do_activate(self):
        if self._window is None:
            css = Gtk.CssProvider()
            css_path = Path(CSS_FILE)
            if css_path.exists():
                css.load_from_path(str(css_path))
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self._window = ChiOverlay(self)

        self._window.show_and_focus()


def main():
    app = ChiOverlayApp()
    sys.exit(app.run(None))


if __name__ == "__main__":
    main()
