"""Calcolo della compatibilità tra un'offerta e il profilo."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Criteria
from .models import Job


@dataclass
class Match:
    score: float
    reasons: list[str]
    passed: bool


def _has(text: str, term: str) -> bool:
    return re.search(r"(?<![\w+#])" + re.escape(term.lower()) + r"(?![\w+#])", text) is not None


def rule_score(job: Job, c: Criteria, skills: list[str]) -> Match:
    text = job.text()
    reasons: list[str] = []

    for bad in c.exclude:
        if _has(text, bad):
            return Match(0, [f"escluso: contiene '{bad}'"], False)

    if c.required_any and not any(_has(text, r) for r in c.required_any):
        return Match(0, ["nessuna parola chiave obbligatoria"], False)

    # sede / remoto
    loc_ok = not c.locations
    if c.locations:
        hit = [l for l in c.locations if _has((job.location + " " + job.title).lower(), l)]
        if hit:
            loc_ok = True
            reasons.append(f"sede: {hit[0]}")
    if job.remote and c.remote_ok:
        loc_ok = True
        reasons.append("remoto")
    if not loc_ok:
        return Match(0, [f"sede non compatibile: {job.location or 'n/d'}"], False)

    if c.min_salary and job.salary_max and job.salary_max < c.min_salary:
        return Match(0, [f"RAL massima {job.salary_max} sotto il minimo"], False)

    kw = [k for k in c.keywords if _has(text, k)]
    title_kw = [k for k in c.keywords if _has(job.title.lower(), k)]
    sk = [s for s in skills if _has(text, s)]

    score = 30.0  # ha superato i filtri obbligatori
    if c.keywords:
        score += 30 * len(kw) / len(c.keywords) + min(15, 7.5 * len(title_kw))
    else:
        score += 25
    if skills:
        score += 25 * min(1.0, len(sk) / max(3, len(skills) / 2))
    score = min(100.0, score)
    if kw:
        reasons.append("parole chiave: " + ", ".join(kw))
    if sk:
        reasons.append("competenze: " + ", ".join(sk))
    return Match(round(score, 1), reasons, score >= c.min_score)


def evaluate(job: Job, criteria: Criteria, profile: dict, llm=None) -> Match:
    m = rule_score(job, criteria, profile.get("skills", []))
    # Claude affina solo le offerte che passano i filtri, per contenere i costi
    if m.passed and llm is not None and llm.enabled:
        res = llm.evaluate_fit(profile, f"{job.title} @ {job.company}\n{job.location}\n{job.description}")
        if res:
            score = round(0.4 * m.score + 0.6 * float(res["score"]), 1)
            reasons = m.reasons + [f"AI: {r}" for r in res["reasons"]] + [f"dubbio: {r}" for r in res["concerns"]]
            return Match(score, reasons, score >= criteria.min_score)
    return m
