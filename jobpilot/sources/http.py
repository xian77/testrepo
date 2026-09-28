from __future__ import annotations

import requests

session = requests.Session()
session.headers["User-Agent"] = "JobPilot/0.1 (personal job search assistant)"


def get_json(url: str, **params):
    resp = session.get(url, params=params or None, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_text(url: str) -> str:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text
