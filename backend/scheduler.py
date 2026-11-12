"""Planificador: un ciclo cada 15 minutos, con registro de fallos por fuente."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.db import Database
from connectors.base import Connector

log = logging.getLogger(__name__)

INTERVAL_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_cycle(
    connectors: Sequence[Connector], db: Database, now: Callable[[], datetime] = _utcnow
) -> dict[str, dict[str, Any]]:
    """Ejecuta todos los conectores. El fallo de uno se registra y no afecta al resto."""
    summary: dict[str, dict[str, Any]] = {}
    for connector in connectors:
        started = now()
        try:
            readings = connector.fetch()
        except Exception as exc:  # cualquier fallo de una fuente es SIN_DATOS, nunca una caída
            error = f"{type(exc).__name__}: {exc}"
            log.error("fuente %s falló: %s", connector.source, error)
            db.record_failure(connector.source, error, started_at=started, finished_at=now())
            summary[connector.source] = {"ok": False, "readings": 0, "error": error}
            continue
        db.record_success(connector.source, readings, started_at=started, finished_at=now())
        log.info("fuente %s: %d lecturas", connector.source, len(readings))
        summary[connector.source] = {"ok": True, "readings": len(readings), "error": None}
    for connector in connectors:
        if hasattr(connector, "fetch_warnings"):
            summary[f"{connector.source}:avisos"] = _warnings_cycle(connector, db, now)
    return summary


def _warnings_cycle(connector: Any, db: Database, now: Callable[[], datetime]) -> dict[str, Any]:
    """Avisos oficiales (p. ej. CAP de AEMET). Se registran como fuente "<source>:avisos"."""
    name, started = f"{connector.source}:avisos", now()
    try:
        warnings = [w.to_dict() for w in connector.fetch_warnings()]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.error("fuente %s falló: %s", name, error)
        db.record_failure(name, error, started_at=started, finished_at=now())
        return {"ok": False, "readings": 0, "error": error}
    db.replace_warnings(connector.source, warnings, fetched_at=now())
    db.record_success(name, [], started_at=started, finished_at=now())
    return {"ok": True, "readings": len(warnings), "error": None}


def build_scheduler(connectors: Sequence[Connector], db: Database) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.add_job(
        run_cycle,
        IntervalTrigger(minutes=INTERVAL_MINUTES, timezone=timezone.utc),
        args=[connectors, db],
        id="ciclo_fuentes",
        next_run_time=_utcnow(),  # primer ciclo al arrancar
        max_instances=1,
        coalesce=True,
    )
    return scheduler
