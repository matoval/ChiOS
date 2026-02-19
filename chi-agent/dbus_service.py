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

import logging
import threading
import uuid
from typing import Callable

from pydbus import SessionBus
from gi.repository import GLib

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

    def __init__(self, chat_fn: Callable):
        self._chat = chat_fn
        self._status = "ready"
        self._history: list[dict] = []
        self._lock = threading.Lock()

    def Ask(self, prompt: str) -> str:
        with self._lock:
            self._set_status("thinking")
            try:
                response, self._history = self._chat(prompt, self._history)
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
                    response, self._history = self._chat(prompt, self._history)
                    self._set_status("ready")
                except Exception as e:
                    response = f"Error: {e}"
                    self._set_status("error")
                    log.error(f"D-Bus AskAsync error: {e}")
            self.ResponseReady(job_id, response)

        threading.Thread(target=_worker, daemon=True).start()
        return job_id

    def GetStatus(self) -> str:
        return self._status

    def ResponseReady(self, job_id: str, response: str) -> None:
        # Signal emission handled by pydbus automatically via annotation
        pass

    def StatusChanged(self, status: str) -> None:
        pass

    def _set_status(self, status: str) -> None:
        self._status = status
        self.StatusChanged(status)


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
