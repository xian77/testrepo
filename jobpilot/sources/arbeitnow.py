"""Arbeitnow: offerte in Europa (https://www.arbeitnow.com/api/job-board-api)."""
from __future__ import annotations

from ..models import Job, find_apply_email, strip_html
from .http import get_json

API = "https://www.arbeitnow.com/api/job-board-api"


def parse(data: dict) -> list[Job]:
    jobs = []
    for j in data.get("data", []):
        desc = strip_html(j.get("description", ""))
        jobs.append(Job(
            source="arbeitnow", external_id=j["slug"], title=j.get("title", ""),
            company=j.get("company_name", ""), url=j.get("url", ""), description=desc,
            location=j.get("location", ""), remote=bool(j.get("remote")),
            tags=list(j.get("tags") or []) + list(j.get("job_types") or []),
            apply_email=find_apply_email(desc), posted_at=str(j.get("created_at", "")),
        ))
    return jobs


def fetch(pages: int = 2) -> list[Job]:
    jobs: list[Job] = []
    for page in range(1, pages + 1):
        jobs.extend(parse(get_json(API, page=page)))
    return jobs
