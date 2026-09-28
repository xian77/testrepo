"""Preparazione e invio delle candidature."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .db import Tracker, now
from .mailer import Mailer

log = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """Gentile team di {company},

vi scrivo per candidarmi alla posizione di {title}. {summary}

Tra le competenze richieste, porto esperienza concreta in {skills}. Sarei felice di approfondire in un colloquio come posso contribuire al vostro team.

In allegato trovate il mio CV. Resto a disposizione per qualsiasi informazione.

Cordiali saluti,
{name}
{phone}
"""


def build_cover_letter(settings: Settings, job, llm=None) -> str:
    p = settings.profile
    job_text = f"{job['title']} @ {job['company']}\n{job['location']}\n{job['description']}"
    if llm is not None and llm.enabled:
        text = llm.cover_letter(p, job_text, settings.apply.get("language", "italiano"))
        if text:
            return text.strip()
    template = DEFAULT_TEMPLATE
    tpl_file = settings.apply.get("cover_letter_template")
    if tpl_file and (settings.base_dir / tpl_file).exists():
        template = (settings.base_dir / tpl_file).read_text(encoding="utf-8")
    matched = [s for s in p.get("skills", []) if s.lower() in (job["description"] or "").lower()] or p.get("skills", [])[:3]
    return template.format(
        company=job["company"] or "selezione", title=job["title"], name=p.get("name", ""),
        phone=p.get("phone", ""), summary=p.get("summary", ""), skills=", ".join(matched[:5]) or "questo ambito",
    ).strip()


def applied_today(tracker: Tracker) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    return tracker.conn.execute("SELECT COUNT(*) FROM jobs WHERE applied_at LIKE ?", (today + "%",)).fetchone()[0]


def apply(settings: Settings, tracker: Tracker, uid: str, mailer: Mailer, llm=None) -> str:
    """Candida l'utente a un'offerta approvata. Ritorna il nuovo stato."""
    job = tracker.get(uid)
    if job is None:
        raise KeyError(uid)
    uid = job["uid"]
    letter = job["cover_letter"] or build_cover_letter(settings, job, llm)
    tracker.update(uid, cover_letter=letter)

    p = settings.profile
    cv = settings.base_dir / p["cv_file"] if p.get("cv_file") else None
    attachments = [cv] if cv and cv.exists() else []

    if job["apply_email"] and settings.apply.get("email_applications", True):
        subject = settings.apply.get("subject", "Candidatura: {title} - {name}").format(title=job["title"], name=p.get("name", ""))
        msg_id = mailer.send(job["apply_email"], subject, letter, attachments)
        tracker.update(uid, applied_at=now())
        tracker.set_status(uid, "applied", f"email a {job['apply_email']} ({msg_id})")
        return "applied"

    # Nessun canale automatico affidabile: prepara un pacchetto pronto da incollare nel form del sito
    out = settings.base_dir / settings.apply.get("packets_dir", "packets")
    out.mkdir(parents=True, exist_ok=True)
    packet = out / f"{uid}.md"
    answers = settings.apply.get("standard_answers", {})
    packet.write_text(
        f"# {job['title']} — {job['company']}\n\nLink: {job['url']}\n\n## Lettera di presentazione\n\n{letter}\n\n"
        "## Risposte standard\n\n" + "\n".join(f"- **{k}**: {v}" for k, v in answers.items()) +
        f"\n\n## Perché è compatibile\n\n" + "\n".join(f"- {r}" for r in json.loads(job["reasons"] or "[]")) + "\n",
        encoding="utf-8",
    )
    tracker.set_status(uid, "manual_pending", f"pacchetto: {packet}")
    return "manual_pending"
