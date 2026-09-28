import pytest
import yaml

from jobpilot.config import load_settings
from jobpilot.db import Tracker


@pytest.fixture
def settings(tmp_path):
    cfg = {
        "profile": {"name": "Anna Bianchi", "skills": ["python", "django", "postgresql", "docker"],
                    "summary": "Sviluppatrice backend.", "availability": "martedì o giovedì mattina"},
        "criteria": {"keywords": ["python", "backend", "django"], "required_any": ["python"],
                     "exclude": ["php"], "locations": ["milano"], "remote_ok": True, "min_score": 50},
        "sources": [],
        "apply": {"mode": "auto", "auto_min_score": 55, "max_per_day": 5, "followup_after_days": 7},
        "email": {"address": "anna@example.com"},
        "llm": {"enabled": False},
        "db_path": "test.db",
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return load_settings(path)


@pytest.fixture
def tracker(settings):
    return Tracker(settings.db_path)
