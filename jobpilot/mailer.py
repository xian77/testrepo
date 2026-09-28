"""Invio email via SMTP (candidature e risposte)."""
from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path


class Mailer:
    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run or not cfg.get("smtp_host")
        self.sender = cfg.get("address", "")

    def send(self, to: str, subject: str, body: str, attachments: list[Path] = (),
             in_reply_to: str | None = None) -> str:
        msg = EmailMessage()
        msg["From"] = self.cfg.get("from_name", "") and f"{self.cfg['from_name']} <{self.sender}>" or self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid()
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(body)
        for path in attachments:
            path = Path(path)
            ctype, _ = mimetypes.guess_type(path.name)
            maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
            msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)

        if self.dry_run:
            print(f"[dry-run] email a {to}: {subject}")
            return msg["Message-ID"]
        port = int(self.cfg.get("smtp_port", 587))
        if port == 465:
            server = smtplib.SMTP_SSL(self.cfg["smtp_host"], port, timeout=60)
        else:
            server = smtplib.SMTP(self.cfg["smtp_host"], port, timeout=60)
            server.starttls()
        with server:
            server.login(self.cfg.get("username", self.sender), self.cfg["password"])
            server.send_message(msg)
        return msg["Message-ID"]
