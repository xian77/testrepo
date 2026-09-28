"""Feed RSS/Atom generici (molti portali permettono di salvare una ricerca come feed)."""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

from ..models import Job, find_apply_email, strip_html
from .http import get_text

ATOM = "{http://www.w3.org/2005/Atom}"


def parse(xml_text: str, name: str = "rss") -> list[Job]:
    root = ET.fromstring(xml_text)
    jobs = []
    items = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    for it in items:
        def t(tag):
            el = it.find(tag)
            if el is None:
                el = it.find(ATOM + tag)
            return (el.text or "") if el is not None else ""
        link = t("link")
        if not link:
            el = it.find(ATOM + "link")
            link = el.get("href", "") if el is not None else ""
        title = t("title")
        desc = strip_html(t("description") or t("summary") or t("content"))
        company = ""
        if " at " in title:
            title, company = title.rsplit(" at ", 1)
        ext = t("guid") or t("id") or hashlib.sha1(link.encode()).hexdigest()
        jobs.append(Job(
            source=f"rss:{name}", external_id=ext, title=title.strip(), company=company.strip(), url=link,
            description=desc, remote="remote" in (title + desc).lower(), apply_email=find_apply_email(desc),
            posted_at=t("pubDate") or t("updated"),
        ))
    return jobs


def fetch(url: str, name: str = "rss") -> list[Job]:
    return parse(get_text(url), name)
