from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .models import Job

# Ciclo di vita di un'offerta/candidatura
STATUSES = (
    "discarded",       # non compatibile
    "matched",         # compatibile, in attesa di approvazione
    "approved",        # approvata, pronta per l'invio
    "manual_pending",  # materiali pronti, la candidatura va completata sul sito
    "applied",         # candidatura inviata
    "acknowledged",    # conferma di ricezione
    "info_requested",  # l'azienda chiede documenti/informazioni
    "assessment",      # test/esercizio tecnico
    "interview",       # invito a colloquio
    "rejected",        # esito negativo
    "offer",           # offerta ricevuta
    "withdrawn",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid TEXT PRIMARY KEY,
    source TEXT, external_id TEXT, title TEXT, company TEXT, url TEXT,
    description TEXT, location TEXT, remote INTEGER, salary_min INTEGER, salary_max INTEGER,
    tags TEXT, apply_email TEXT, posted_at TEXT,
    score REAL, reasons TEXT, status TEXT,
    cover_letter TEXT, applied_at TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS emails (
    message_id TEXT PRIMARY KEY,
    job_uid TEXT, sender TEXT, subject TEXT, received_at TEXT, body TEXT,
    category TEXT, summary TEXT, draft_reply TEXT, reply_sent INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT, kind TEXT, detail TEXT, created_at TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Tracker:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # --- jobs -----------------------------------------------------------
    def has_job(self, uid: str) -> bool:
        return self.conn.execute("SELECT 1 FROM jobs WHERE uid=?", (uid,)).fetchone() is not None

    def add_job(self, job: Job, score: float, reasons: list[str], status: str) -> None:
        ts = now()
        self.conn.execute(
            """INSERT OR IGNORE INTO jobs (uid, source, external_id, title, company, url, description, location,
               remote, salary_min, salary_max, tags, apply_email, posted_at, score, reasons, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job.uid, job.source, job.external_id, job.title, job.company, job.url, job.description, job.location,
             int(job.remote), job.salary_min, job.salary_max, json.dumps(job.tags), job.apply_email, job.posted_at,
             score, json.dumps(reasons, ensure_ascii=False), status, ts, ts),
        )
        self.conn.commit()
        self.log(job.uid, "found", f"score={score:.0f} status={status}")

    def get(self, uid: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM jobs WHERE uid=? OR uid LIKE ?", (uid, uid + "%")).fetchone()

    def list(self, status: str | None = None) -> list[sqlite3.Row]:
        if status:
            return self.conn.execute("SELECT * FROM jobs WHERE status=? ORDER BY score DESC", (status,)).fetchall()
        return self.conn.execute(
            "SELECT * FROM jobs WHERE status!='discarded' ORDER BY updated_at DESC").fetchall()

    def set_status(self, uid: str, status: str, detail: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(f"stato sconosciuto: {status}")
        self.conn.execute("UPDATE jobs SET status=?, updated_at=? WHERE uid=?", (status, now(), uid))
        self.conn.commit()
        self.log(uid, "status", f"{status} {detail}".strip())

    def update(self, uid: str, **fields) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE jobs SET {cols}, updated_at=? WHERE uid=?", (*fields.values(), now(), uid))
        self.conn.commit()

    def active_applications(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM jobs WHERE status IN ('applied','manual_pending','acknowledged','info_requested','assessment','interview')"
        ).fetchall()

    # --- emails ---------------------------------------------------------
    def has_email(self, message_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM emails WHERE message_id=?", (message_id,)).fetchone() is not None

    def add_email(self, **row) -> None:
        row.setdefault("created_at", now())
        cols = ", ".join(row)
        self.conn.execute(f"INSERT OR IGNORE INTO emails ({cols}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))
        self.conn.commit()

    def emails(self, pending_only: bool = False) -> list[sqlite3.Row]:
        q = "SELECT * FROM emails"
        if pending_only:
            q += " WHERE draft_reply IS NOT NULL AND reply_sent=0"
        return self.conn.execute(q + " ORDER BY received_at DESC").fetchall()

    def mark_reply_sent(self, message_id: str) -> None:
        self.conn.execute("UPDATE emails SET reply_sent=1 WHERE message_id=?", (message_id,))
        self.conn.commit()

    # --- events ---------------------------------------------------------
    def log(self, uid: str | None, kind: str, detail: str = "") -> None:
        self.conn.execute("INSERT INTO events (job_uid, kind, detail, created_at) VALUES (?,?,?,?)", (uid, kind, detail, now()))
        self.conn.commit()

    def events(self, uid: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM events WHERE job_uid=? ORDER BY id", (uid,)).fetchall()

    def stats(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rows}
