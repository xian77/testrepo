"""Orchestrazione: ricerca → valutazione → candidatura → monitoraggio email → follow-up."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import applier, inbox, matcher, sources
from .config import Settings
from .db import Tracker
from .mailer import Mailer

log = logging.getLogger(__name__)


def scan(settings: Settings, tracker: Tracker, llm=None, jobs=None) -> list[str]:
    """Scarica le nuove offerte, le valuta e salva quelle nuove. Ritorna gli uid compatibili."""
    jobs = sources.fetch_all(settings.sources) if jobs is None else jobs
    matched = []
    seen = set()
    for job in jobs:
        if job.uid in seen or tracker.has_job(job.uid):
            continue
        seen.add(job.uid)
        m = matcher.evaluate(job, settings.criteria, settings.profile, llm)
        status = "matched" if m.passed else "discarded"
        tracker.add_job(job, m.score, m.reasons, status)
        if m.passed:
            matched.append(job.uid)
    return matched


def auto_approve(settings: Settings, tracker: Tracker) -> list[str]:
    """In modalità auto approva le offerte con punteggio sopra soglia."""
    if settings.mode != "auto":
        return []
    threshold = float(settings.apply.get("auto_min_score", settings.criteria.min_score + 10))
    approved = []
    for row in tracker.list("matched"):
        if row["score"] >= threshold:
            tracker.set_status(row["uid"], "approved", "auto")
            approved.append(row["uid"])
    return approved


def apply_approved(settings: Settings, tracker: Tracker, mailer: Mailer, llm=None) -> dict[str, str]:
    limit = int(settings.apply.get("max_per_day", 10))
    done: dict[str, str] = {}
    for row in tracker.list("approved"):
        if applier.applied_today(tracker) >= limit:
            log.info("limite giornaliero di %d candidature raggiunto", limit)
            break
        try:
            done[row["uid"]] = applier.apply(settings, tracker, row["uid"], mailer, llm)
        except Exception as exc:
            log.error("candidatura %s fallita: %s", row["uid"], exc)
            tracker.log(row["uid"], "error", str(exc))
    return done


def check_mail(settings: Settings, tracker: Tracker, mailer: Mailer, llm=None) -> list[dict]:
    if not settings.email.get("imap_host"):
        log.info("IMAP non configurato: salto il controllo email")
        return []
    msgs = inbox.fetch_imap(settings.email, int(settings.email.get("lookback_days", 14)))
    return inbox.process(msgs, tracker, settings.profile, settings.email, mailer, llm)


def followups(settings: Settings, tracker: Tracker, mailer: Mailer, send: bool = False) -> list[str]:
    """Sollecito cortese per le candidature via email senza risposta dopo N giorni (una sola volta)."""
    days = int(settings.apply.get("followup_after_days", 0))
    if not days:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out = []
    for row in tracker.list("applied"):
        if not row["apply_email"] or not row["applied_at"] or row["applied_at"] > cutoff:
            continue
        if any(e["kind"] == "followup" for e in tracker.events(row["uid"])):
            continue
        name = settings.profile.get("name", "")
        body = (f"Gentile team di {row['company']},\n\nvi scrivo per un breve aggiornamento sulla mia candidatura "
                f"alla posizione di {row['title']}, inviata il {row['applied_at'][:10]}. Sono ancora molto interessato/a "
                f"e disponibile per un confronto.\n\nCordiali saluti,\n{name}")
        if send:
            mailer.send(row["apply_email"], f"Follow-up candidatura: {row['title']} - {name}", body)
            tracker.log(row["uid"], "followup", "inviato")
        out.append(row["uid"])
    return out


def run_cycle(settings: Settings, tracker: Tracker, mailer: Mailer, llm=None) -> dict:
    summary = {"matched": scan(settings, tracker, llm)}
    summary["auto_approved"] = auto_approve(settings, tracker)
    summary["applied"] = apply_approved(settings, tracker, mailer, llm)
    try:
        summary["emails"] = check_mail(settings, tracker, mailer, llm)
    except Exception as exc:
        log.error("controllo email fallito: %s", exc)
        summary["emails"] = []
    summary["followups"] = followups(settings, tracker, mailer, send=settings.mode == "auto")
    return summary
