"""Monitoraggio della casella email: collega le risposte alle candidature e gestisce i primi passi."""
from __future__ import annotations

import email
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from .db import Tracker
from .mailer import Mailer
from .models import strip_html

log = logging.getLogger(__name__)

RULES: list[tuple[str, list[str]]] = [
    ("offer", ["pleased to offer", "offer letter", "job offer", "proposta di assunzione", "lieti di offrirle", "proposta contrattuale"]),
    ("rejected", ["unfortunately", "purtroppo", "not to move forward", "not moving forward", "other candidates",
                  "altri candidati", "not been selected", "non è stat", "non proseguire", "decided to pursue",
                  "position has been filled", "posizione è stata chiusa"]),
    ("assessment", ["assessment", "coding challenge", "take-home", "take home", "hackerrank", "codility",
                    "technical test", "test tecnico", "esercizio"]),
    ("interview", ["interview", "colloquio", "schedule a call", "fissare una call", "calendly", "your availability",
                   "sua disponibilità", "tua disponibilità", "meet the team"]),
    ("info_requested", ["could you send", "please provide", "please send", "potrebbe inviare", "potresti inviare",
                        "ci invii", "references", "referenze", "portfolio", "documenti"]),
    ("acknowledged", ["received your application", "thank you for applying", "thanks for applying",
                      "abbiamo ricevuto", "grazie per la candidatura", "grazie per averci inviato"]),
]

# ordine di avanzamento: un'email non fa mai "tornare indietro" una candidatura
PROGRESS = {"manual_pending": 0, "applied": 0, "acknowledged": 1, "info_requested": 2, "assessment": 3,
            "interview": 4, "offer": 6, "rejected": 5}

GENERIC_DOMAINS = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "libero.it", "icloud.com",
                   "greenhouse.io", "lever.co", "workable.com", "smartrecruiters.com", "myworkday.com", "ashbyhq.com"}


@dataclass
class Incoming:
    message_id: str
    sender: str
    subject: str
    date: str
    body: str

    @property
    def domain(self) -> str:
        return parseaddr(self.sender)[1].rsplit("@", 1)[-1].lower()


def classify_rules(msg: Incoming) -> str:
    text = f"{msg.subject}\n{msg.body}".lower()
    for category, terms in RULES:
        if any(t in text for t in terms):
            return category
    return "other"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def match_application(msg: Incoming, apps: list) -> str | None:
    """Trova la candidatura a cui si riferisce l'email (dominio mittente, azienda o titolo)."""
    text = _norm(msg.subject + " " + msg.body[:3000] + " " + msg.sender)
    dom = msg.domain
    best, best_score = None, 0
    for a in apps:
        score = 0
        comp = _norm(a["company"])
        if comp and len(comp) >= 3 and dom not in GENERIC_DOMAINS and comp in _norm(dom):
            score += 3
        if a["apply_email"] and a["apply_email"].lower().endswith("@" + dom) and dom not in GENERIC_DOMAINS:
            score += 3
        if comp and len(comp) >= 3 and comp in text:
            score += 2
        if _norm(a["title"]) and _norm(a["title"]) in text:
            score += 2
        if score > best_score:
            best, best_score = a["uid"], score
    return best if best_score >= 2 else None


def template_reply(category: str, profile: dict, msg: Incoming) -> str | None:
    name = profile.get("name", "")
    if category == "interview":
        slots = profile.get("availability", "nei prossimi giorni lavorativi, in qualsiasi fascia oraria")
        return (f"Gentile {parseaddr(msg.sender)[0] or 'team'},\n\ngrazie per il vostro riscontro, sono molto "
                f"interessato/a a proseguire. Sono disponibile per un colloquio {slots}.\n"
                f"Resto in attesa di una vostra conferma.\n\nCordiali saluti,\n{name}\n{profile.get('phone', '')}")
    if category == "info_requested":
        return (f"Gentile {parseaddr(msg.sender)[0] or 'team'},\n\ngrazie per il messaggio. Vi invierò al più presto "
                f"quanto richiesto.\n\nCordiali saluti,\n{name}")
    return None


def fetch_imap(cfg: dict, days: int = 14) -> list[Incoming]:
    host = cfg["imap_host"]
    conn = imaplib.IMAP4_SSL(host, int(cfg.get("imap_port", 993)))
    conn.login(cfg.get("username", cfg["address"]), cfg["password"])
    try:
        conn.select(cfg.get("folder", "INBOX"), readonly=True)
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        _, data = conn.search(None, f"(SINCE {since})")
        out = []
        for num in data[0].split()[-int(cfg.get("max_messages", 200)):]:
            _, parts = conn.fetch(num, "(RFC822)")
            out.append(parse_message(parts[0][1]))
        return out
    finally:
        conn.logout()


def parse_message(raw: bytes) -> Incoming:
    m = email.message_from_bytes(raw)
    body = ""
    parts = m.walk() if m.is_multipart() else [m]
    plain = html = ""
    for part in parts:
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain" and not plain:
            plain = text
        elif part.get_content_type() == "text/html" and not html:
            html = strip_html(text)
    body = plain or html
    try:
        date = parsedate_to_datetime(m.get("Date")).isoformat()
    except Exception:
        date = m.get("Date", "")
    return Incoming(
        message_id=m.get("Message-ID", "").strip() or f"<noid-{hash(raw)}>",
        sender=str(make_header(decode_header(m.get("From", "")))),
        subject=str(make_header(decode_header(m.get("Subject", "")))),
        date=date, body=body.strip(),
    )


def process(messages: list[Incoming], tracker: Tracker, profile: dict, email_cfg: dict,
            mailer: Mailer | None = None, llm=None) -> list[dict]:
    """Classifica le nuove email, aggiorna gli stati e prepara (o invia) le risposte."""
    results = []
    auto_reply = set(email_cfg.get("auto_reply_categories", []))
    for msg in messages:
        if tracker.has_email(msg.message_id):
            continue
        if parseaddr(msg.sender)[1].lower() == email_cfg.get("address", "").lower():
            continue  # email inviate da noi
        apps = [dict(a) for a in tracker.active_applications()]
        uid = match_application(msg, apps)
        category, summary, draft = classify_rules(msg), msg.subject, None

        ai = None
        if llm is not None and llm.enabled and (uid or category != "other"):
            ai = llm.classify_email(profile, f"Da: {msg.sender}\nOggetto: {msg.subject}\n\n{msg.body}", apps)
        if ai:
            category = ai["category"]
            summary = ai["summary"]
            if ai["job_uid"] and any(a["uid"] == ai["job_uid"] for a in apps):
                uid = ai["job_uid"]
            draft = ai["reply_draft"] if ai["needs_reply"] and ai["reply_draft"] else None
        elif uid:
            draft = template_reply(category, profile, msg)

        if not uid and category == "other":
            continue  # email non pertinente
        tracker.add_email(message_id=msg.message_id, job_uid=uid, sender=msg.sender, subject=msg.subject,
                          received_at=msg.date, body=msg.body[:20000], category=category, summary=summary,
                          draft_reply=draft)
        if uid and category in PROGRESS:
            current = tracker.get(uid)["status"]
            if PROGRESS[category] >= PROGRESS.get(current, 0) and current not in ("rejected", "offer"):
                tracker.set_status(uid, category, f"email: {msg.subject}")
        if draft and mailer and category in auto_reply and uid:
            subj = msg.subject if msg.subject.lower().startswith("re:") else f"Re: {msg.subject}"
            mailer.send(parseaddr(msg.sender)[1], subj, draft, in_reply_to=msg.message_id)
            tracker.mark_reply_sent(msg.message_id)
            tracker.log(uid, "reply_sent", subj)
        results.append({"uid": uid, "category": category, "subject": msg.subject, "draft": bool(draft)})
    return results
