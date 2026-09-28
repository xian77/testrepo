"""Greenhouse: board pubblici delle aziende (boards-api.greenhouse.io)."""
from __future__ import annotations

import html

from ..models import Job, find_apply_email, strip_html
from .http import get_json

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


def parse(board: str, data: dict) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        desc = strip_html(html.unescape(j.get("content", "")))
        loc = (j.get("location") or {}).get("name", "")
        jobs.append(Job(
            source=f"greenhouse:{board}", external_id=str(j["id"]), title=j.get("title", ""),
            company=j.get("company_name") or board, url=j.get("absolute_url", ""), description=desc,
            location=loc, remote="remote" in loc.lower(), apply_email=find_apply_email(desc),
            posted_at=j.get("updated_at"),
        ))
    return jobs


def fetch(boards: list[str]) -> list[Job]:
    jobs: list[Job] = []
    for board in boards:
        jobs.extend(parse(board, get_json(API.format(board=board), content="true")))
    return jobs
