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

-- Idempotencia: Telegram reentrega updates en caso de timeout. Si el bot
-- ya proceso este update_id, no volvemos a clasificar ni a escribir en la
-- Sheet. La frase de PRODUCTION.md sobre dedup ya esta implementada aqui.
CREATE TABLE IF NOT EXISTS processed_updates (
    update_id  INTEGER PRIMARY KEY,
    seen_at    TEXT NOT NULL
);
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


def claim_update(update_id: int, path: Path = _DB_PATH) -> bool:
    """Reserva un update_id. Devuelve True si es la primera vez que lo vemos
    (=> hay que procesarlo); False si ya estaba (=> skip por idempotencia).

    Usa INSERT OR IGNORE: atomico y barato. La clave primaria evita duplicados
    incluso si dos handlers concurrentes intentan claimar el mismo update.
    """
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")
    with _connect(path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO processed_updates (update_id, seen_at) VALUES (?, ?)",
            (update_id, now),
        )
        return cur.rowcount == 1


def stats_recent(chat_id: int | None = None, hours: int = 24, path: Path = _DB_PATH) -> dict:
    """Devuelve estadisticas para el comando /stats.

    Si chat_id es None, agrega global; si no, filtra por chat_id.
    """
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    with _connect(path) as conn:
        if chat_id is None:
            row = conn.execute(
                """SELECT COUNT(*), SUM(qualified), AVG(latency_ms), AVG(confidence)
                   FROM leads WHERE received_at >= ?""",
                (cutoff,),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT COUNT(*), SUM(qualified), AVG(latency_ms), AVG(confidence)
                   FROM leads WHERE received_at >= ? AND chat_id = ?""",
                (cutoff, chat_id),
            ).fetchone()
    total = int(row[0] or 0)
    qual = int(row[1] or 0)
    avg_lat = float(row[2] or 0.0)
    avg_conf = float(row[3] or 0.0)
    return {
        "hours": hours,
        "total": total,
        "qualified": qual,
        "not_qualified": total - qual,
        "qualified_pct": (qual / total * 100.0) if total else 0.0,
        "avg_latency_ms": int(avg_lat),
        "avg_confidence": avg_conf,
    }
