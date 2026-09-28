"""Lever: pagine carriere pubbliche (api.lever.co/v0/postings)."""
from __future__ import annotations

from ..models import Job, find_apply_email
from .http import get_json

API = "https://api.lever.co/v0/postings/{company}"


def parse(company: str, data: list) -> list[Job]:
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        desc = j.get("descriptionPlain", "") + "\n" + "\n".join(
            f"{l.get('text', '')}: {l.get('content', '')}" for l in j.get("lists", []))
        loc = cats.get("location", "") or ""
        jobs.append(Job(
            source=f"lever:{company}", external_id=j["id"], title=j.get("text", ""), company=company,
            url=j.get("hostedUrl", ""), description=desc, location=loc,
            remote=j.get("workplaceType") == "remote" or "remote" in loc.lower(),
            tags=[t for t in (cats.get("team"), cats.get("commitment")) if t],
            apply_email=find_apply_email(desc), posted_at=str(j.get("createdAt", "")),
        ))
    return jobs


def fetch(companies: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for c in companies:
        jobs.extend(parse(c, get_json(API.format(company=c), mode="json")))
    return jobs
