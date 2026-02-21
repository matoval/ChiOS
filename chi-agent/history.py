"""
Persistent conversation history and tool data storage for chi-agent.
Stored in SQLite at ~/.local/share/chiOS/history.db
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DB_PATH = Path.home() / ".local/share/chiOS/history.db"
SESSION_GAP_HOURS = 2  # Start new conversation if gap > 2h

_con: sqlite3.Connection | None = None
_current_conv_id: int | None = None


def _get_con() -> sqlite3.Connection:
    global _con
    if _con is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _con.row_factory = sqlite3.Row
        _con.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                messages TEXT NOT NULL DEFAULT '[]'
            )
        """)
        _con.execute("""
            CREATE TABLE IF NOT EXISTS collected_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collected_at TEXT NOT NULL,
                tool TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        _con.commit()
    return _con


def _get_or_create_conversation() -> int:
    global _current_conv_id
    con = _get_con()
    now = datetime.now().isoformat()

    if _current_conv_id is not None:
        row = con.execute(
            "SELECT updated_at FROM conversations WHERE id=?",
            (_current_conv_id,)
        ).fetchone()
        if row:
            updated = datetime.fromisoformat(row["updated_at"])
            if datetime.now() - updated < timedelta(hours=SESSION_GAP_HOURS):
                return _current_conv_id

    cur = con.execute(
        "INSERT INTO conversations (started_at, updated_at, messages) VALUES (?,?,?)",
        (now, now, "[]")
    )
    con.commit()
    _current_conv_id = cur.lastrowid
    return _current_conv_id


def append_message(role: str, content: str) -> None:
    """Append a user or assistant message to the current conversation."""
    conv_id = _get_or_create_conversation()
    con = _get_con()
    now = datetime.now().isoformat()

    row = con.execute(
        "SELECT messages FROM conversations WHERE id=?", (conv_id,)
    ).fetchone()
    msgs = json.loads(row["messages"]) if row else []
    msgs.append({"role": role, "content": content, "at": now})

    con.execute(
        "UPDATE conversations SET messages=?, updated_at=? WHERE id=?",
        (json.dumps(msgs), now, conv_id)
    )
    con.commit()


def record_tool_data(tool: str, data: Any) -> None:
    """Record data returned by a tool call."""
    con = _get_con()
    con.execute(
        "INSERT INTO collected_data (collected_at, tool, data) VALUES (?,?,?)",
        (datetime.now().isoformat(), tool, json.dumps(data))
    )
    con.commit()


def get_history(limit: int = 30) -> list[dict]:
    """Return the most recent conversations, newest first."""
    con = _get_con()
    rows = con.execute(
        "SELECT id, started_at, updated_at, messages "
        "FROM conversations ORDER BY updated_at DESC LIMIT ?",
        (limit,)
    ).fetchall()

    result = []
    for row in rows:
        msgs = json.loads(row["messages"])
        user_msgs = [m for m in msgs if m["role"] == "user"]
        preview = user_msgs[0]["content"][:120] if user_msgs else "(empty)"
        result.append({
            "id": row["id"],
            "started_at": row["started_at"],
            "updated_at": row["updated_at"],
            "message_count": len(msgs),
            "preview": preview,
            "messages": msgs,
        })
    return result


def delete_conversation(conv_id: int) -> bool:
    """Delete a single conversation by ID. Returns True if a row was deleted."""
    global _current_conv_id
    con = _get_con()
    cur = con.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    con.commit()
    if _current_conv_id == conv_id:
        _current_conv_id = None
    return cur.rowcount > 0


def clear_all_history() -> None:
    """Permanently delete all conversations and collected data."""
    global _current_conv_id
    con = _get_con()
    con.execute("DELETE FROM conversations")
    con.execute("DELETE FROM collected_data")
    con.commit()
    _current_conv_id = None


def clear_data() -> None:
    """Permanently delete all collected tool data (keeps conversations)."""
    con = _get_con()
    con.execute("DELETE FROM collected_data")
    con.commit()


def get_data(limit: int = 50) -> list[dict]:
    """Return recently collected tool data, newest first."""
    con = _get_con()
    rows = con.execute(
        "SELECT tool, collected_at, data FROM collected_data "
        "ORDER BY collected_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [
        {
            "tool": r["tool"],
            "collected_at": r["collected_at"],
            "data": json.loads(r["data"]),
        }
        for r in rows
    ]
