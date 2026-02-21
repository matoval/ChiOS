#!/usr/bin/env python3
"""
D-Bus session service: io.chios.Agent

Exposes chi-agent to the desktop session so chi-overlay and waybar
can communicate with it via IPC without needing a network socket.

Interface methods:
  - Ask(prompt: str) -> str           blocking, returns final response
  - AskAsync(prompt: str) -> str      returns job ID, emits ResponseReady
  - GetStatus() -> str                "ready" | "thinking" | "error"

Signals:
  - ResponseReady(job_id: str, response: str)
  - StatusChanged(status: str)
"""

import json
import logging
import threading
import uuid
from typing import Callable

from pydbus import SessionBus
from pydbus.generic import signal
from gi.repository import GLib

import history as hist

log = logging.getLogger("chi-agent.dbus")

DBUS_NAME = "io.chios.Agent"
DBUS_PATH = "/io/chios/Agent"

DBUS_XML = """
<node>
  <interface name='io.chios.Agent'>

    <method name='Ask'>
      <arg type='s' name='prompt' direction='in'/>
      <arg type='s' name='response' direction='out'/>
    </method>

    <method name='AskAsync'>
      <arg type='s' name='prompt' direction='in'/>
      <arg type='s' name='job_id' direction='out'/>
    </method>

    <method name='GetStatus'>
      <arg type='s' name='status' direction='out'/>
    </method>

    <method name='GetHistory'>
      <arg type='i' name='limit' direction='in'/>
      <arg type='s' name='json' direction='out'/>
    </method>

    <method name='GetData'>
      <arg type='i' name='limit' direction='in'/>
      <arg type='s' name='json' direction='out'/>
    </method>

    <method name='DeleteConversation'>
      <arg type='i' name='conv_id' direction='in'/>
      <arg type='b' name='deleted' direction='out'/>
    </method>

    <method name='ClearAllHistory'>
    </method>

    <method name='ClearData'>
    </method>

    <signal name='ResponseReady'>
      <arg type='s' name='job_id'/>
      <arg type='s' name='response'/>
    </signal>

    <signal name='StatusChanged'>
      <arg type='s' name='status'/>
    </signal>

  </interface>
</node>
"""


class ChiAgentService:
    dbus = DBUS_XML

    ResponseReady = signal()
    StatusChanged = signal()

    def __init__(self, chat_fn: Callable):
        self._chat = chat_fn
        self._status = "ready"
        self._history: list[dict] = []
        self._lock = threading.Lock()

    def Ask(self, prompt: str) -> str:
        with self._lock:
            self._set_status("thinking")
            try:
                hist.append_message("user", prompt)
                response, self._history = self._chat(prompt, self._history)
                hist.append_message("assistant", response)
                self._set_status("ready")
                return response
            except Exception as e:
                self._set_status("error")
                log.error(f"D-Bus Ask error: {e}")
                return f"Error: {e}"

    def AskAsync(self, prompt: str) -> str:
        job_id = str(uuid.uuid4())[:8]

        def _worker():
            with self._lock:
                self._set_status("thinking")
                try:
                    hist.append_message("user", prompt)
                    response, self._history = self._chat(prompt, self._history)
                    hist.append_message("assistant", response)
                    self._set_status("ready")
                except Exception as e:
                    response = f"Error: {e}"
                    self._set_status("error")
                    log.error(f"D-Bus AskAsync error: {e}")
            GLib.idle_add(self.ResponseReady, job_id, response)

        threading.Thread(target=_worker, daemon=True).start()
        return job_id

    def GetStatus(self) -> str:
        return self._status

    def GetHistory(self, limit: int) -> str:
        try:
            return json.dumps(hist.get_history(limit))
        except Exception as e:
            log.error(f"GetHistory error: {e}")
            return "[]"

    def GetData(self, limit: int) -> str:
        try:
            return json.dumps(hist.get_data(limit))
        except Exception as e:
            log.error(f"GetData error: {e}")
            return "[]"

    def DeleteConversation(self, conv_id: int) -> bool:
        try:
            return hist.delete_conversation(conv_id)
        except Exception as e:
            log.error(f"DeleteConversation error: {e}")
            return False

    def ClearAllHistory(self) -> None:
        try:
            hist.clear_all_history()
        except Exception as e:
            log.error(f"ClearAllHistory error: {e}")

    def ClearData(self) -> None:
        try:
            hist.clear_data()
        except Exception as e:
            log.error(f"ClearData error: {e}")

    def _set_status(self, status: str) -> None:
        self._status = status
        # Emit signal safely from the GLib main loop thread
        GLib.idle_add(self.StatusChanged, status)


def run_dbus_service() -> None:
    """Register chi-agent on session D-Bus. Blocks until GLib loop exits."""
    from agent import chat  # lazy import to avoid circular

    bus = SessionBus()
    service = ChiAgentService(chat_fn=chat)

    try:
        bus.publish(DBUS_NAME, (DBUS_PATH, service))
        log.info(f"D-Bus service registered: {DBUS_NAME}")
        loop = GLib.MainLoop()
        loop.run()
    except Exception as e:
        log.error(f"D-Bus service failed: {e}")
        raise
