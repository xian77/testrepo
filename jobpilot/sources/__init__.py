"""Sorgenti di offerte di lavoro basate su API pubbliche e feed RSS."""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

from ..models import Job
from . import arbeitnow, greenhouse, lever, remotive, rss

log = logging.getLogger(__name__)

REGISTRY: dict[str, Callable[..., Iterable[Job]]] = {
    "remotive": remotive.fetch,
    "arbeitnow": arbeitnow.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "rss": rss.fetch,
}


def fetch_all(source_configs: list[dict[str, Any]]) -> list[Job]:
    jobs: list[Job] = []
    for cfg in source_configs:
        cfg = dict(cfg)
        kind = cfg.pop("type")
        if cfg.pop("enabled", True) is False:
            continue
        fn = REGISTRY.get(kind)
        if fn is None:
            log.warning("sorgente sconosciuta: %s", kind)
            continue
        try:
            found = list(fn(**cfg))
            log.info("%s: %d offerte", kind, len(found))
            jobs.extend(found)
        except Exception as exc:  # una sorgente che fallisce non blocca le altre
            log.error("errore nella sorgente %s: %s", kind, exc)
    return jobs
