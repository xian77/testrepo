"""Remotive: offerte remote (https://remotive.com/api/remote-jobs)."""
from __future__ import annotations

from ..models import Job, find_apply_email, strip_html
from .http import get_json

API = "https://remotive.com/api/remote-jobs"


def parse(data: dict) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        desc = strip_html(j.get("description", ""))
        jobs.append(Job(
            source="remotive", external_id=str(j["id"]), title=j.get("title", ""),
            company=j.get("company_name", ""), url=j.get("url", ""), description=desc,
            location=j.get("candidate_required_location", ""), remote=True,
            tags=list(j.get("tags") or []) + [j.get("category", "")],
            apply_email=find_apply_email(desc), posted_at=j.get("publication_date"),
        ))
    return jobs


def fetch(search: str = "", category: str = "", limit: int = 100) -> list[Job]:
    params = {k: v for k, v in {"search": search, "category": category, "limit": limit}.items() if v}
    return parse(get_json(API, **params))
