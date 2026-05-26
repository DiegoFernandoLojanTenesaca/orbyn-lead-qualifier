"""Persistencia local en SQLite. Es la fuente autoritativa de auditoria.

Lo guardamos SIEMPRE aqui, incluso si Google Sheets esta caido o no configurado:
asi nunca se pierde un lead y se puede re-sincronizar despues.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.config import REPO_ROOT
from app.schemas.lead import LeadRecord

_DB_PATH = REPO_ROOT / "leads.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at     TEXT    NOT NULL,
    chat_id         INTEGER NOT NULL,
    user_id         INTEGER,
    username        TEXT,
    text            TEXT    NOT NULL,
    qualified       INTEGER NOT NULL,
    reason          TEXT    NOT NULL,
    confidence      REAL    NOT NULL,
    provider_used   TEXT    NOT NULL,
    model_used      TEXT    NOT NULL,
    latency_ms      INTEGER NOT NULL,
    prompt_version  TEXT    NOT NULL,
    synced_to_sheet INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leads_chat  ON leads(chat_id);
CREATE INDEX IF NOT EXISTS idx_leads_synced ON leads(synced_to_sheet);
"""


def _connect(path: Path = _DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.executescript(_SCHEMA)
    return conn


def insert_lead(record: LeadRecord, path: Path = _DB_PATH) -> int:
    with _connect(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO leads (
                received_at, chat_id, user_id, username, text,
                qualified, reason, confidence,
                provider_used, model_used, latency_ms, prompt_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.received_at.isoformat(timespec="seconds"),
                record.chat_id,
                record.user_id,
                record.username,
                record.text,
                int(record.qualified),
                record.reason,
                record.confidence,
                record.provider_used,
                record.model_used,
                record.latency_ms,
                record.prompt_version,
            ),
        )
        return int(cur.lastrowid or 0)


def mark_synced(lead_id: int, path: Path = _DB_PATH) -> None:
    with _connect(path) as conn:
        conn.execute("UPDATE leads SET synced_to_sheet = 1 WHERE id = ?", (lead_id,))


def count_recent(chat_id: int, seconds: int = 60, path: Path = _DB_PATH) -> int:
    """Cuenta cuantos leads ha mandado este chat en los ultimos `seconds`."""
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE chat_id = ? AND received_at >= ?",
            (chat_id, cutoff),
        ).fetchone()
        return int(row[0])
