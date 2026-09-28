from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Criteria:
    keywords: list[str] = field(default_factory=list)          # parole chiave che aumentano il punteggio
    required_any: list[str] = field(default_factory=list)      # almeno una deve comparire
    exclude: list[str] = field(default_factory=list)           # se compare, l'offerta viene scartata
    locations: list[str] = field(default_factory=list)
    remote_ok: bool = True
    min_salary: int | None = None
    min_score: float = 60.0


@dataclass
class Settings:
    profile: dict[str, Any]
    criteria: Criteria
    sources: list[dict[str, Any]]
    apply: dict[str, Any]
    email: dict[str, Any]
    llm: dict[str, Any]
    db_path: str
    base_dir: Path

    @property
    def mode(self) -> str:
        # "review": le candidature vanno approvate a mano; "auto": inviate automaticamente
        return self.apply.get("mode", "review")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_settings(path: str | Path) -> Settings:
    path = Path(path)
    data = _expand_env(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    base = path.parent
    profile = data.get("profile", {})
    cv_text_file = profile.get("cv_text_file")
    if cv_text_file and not profile.get("cv_text"):
        p = (base / cv_text_file)
        if p.exists():
            profile["cv_text"] = p.read_text(encoding="utf-8")
    return Settings(
        profile=profile,
        criteria=Criteria(**data.get("criteria", {})),
        sources=data.get("sources", []),
        apply=data.get("apply", {}),
        email=data.get("email", {}),
        llm=data.get("llm", {}),
        db_path=str(base / data.get("db_path", "jobpilot.db")),
        base_dir=base,
    )
