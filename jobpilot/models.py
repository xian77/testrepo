from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    description: str = ""
    location: str = ""
    remote: bool = False
    salary_min: int | None = None
    salary_max: int | None = None
    tags: list[str] = field(default_factory=list)
    apply_email: str | None = None
    posted_at: str | None = None

    @property
    def uid(self) -> str:
        raw = f"{self.source}:{self.external_id}".encode()
        return hashlib.sha1(raw).hexdigest()[:16]

    def text(self) -> str:
        return " ".join([self.title, self.company, self.location, " ".join(self.tags), self.description]).lower()


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'"), ("&quot;", '"')):
        text = text.replace(a, b)
    return re.sub(r"[ \t]+", " ", text).strip()


def find_apply_email(text: str) -> str | None:
    """Return an application email address mentioned in a job description, if any."""
    candidates = EMAIL_RE.findall(text or "")
    for c in candidates:
        low = c.lower()
        if any(k in low for k in ("job", "career", "hr", "recruit", "talent", "hiring", "apply", "lavora", "candidat", "cv")):
            return c
    return candidates[0] if candidates else None
