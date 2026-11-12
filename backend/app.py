"""API: GET /stations, /stations/{id}, /stations/{id}/history, /alerts, /propagation."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Query

from backend.db import Database
from connectors.base import iso_utc
from engine.propagation import LABEL, LinkTable, describe_links, evaluate, load_links
from engine.status import ALERTA, PREALERTA, VIGILANCIA, station_status

DEFAULT_LINKS = Path(__file__).resolve().parent.parent / "engine" / "river_links.yaml"
SEVERITY = {ALERTA: 0, PREALERTA: 1, VIGILANCIA: 2}
WARNING_LEVELS = {"rojo": 0, "naranja": 1, "amarillo": 2}
HISTORY_FOR_TRIGGERS = 60  # lecturas por estación que mira el motor de propagación

DEMO_NOTICE = "DATOS DE DEMOSTRACIÓN"
DISCLAIMER = "Información no oficial. En emergencia llama al 112 y sigue a AEMET y Protección Civil."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_app(
    db: Any, now: Callable[[], datetime] = _utcnow, lifespan: Any = None, links: Optional[LinkTable] = None,
    demo: bool = False,
) -> FastAPI:
    app = FastAPI(title="HidroRed España", description=DISCLAIMER, lifespan=lifespan)
    table = links or load_links(DEFAULT_LINKS)

    def propagation_now() -> list[dict[str, Any]]:
        return evaluate(table, lambda station_id: db.history(station_id, limit=HISTORY_FOR_TRIGGERS), now())

    def weather_warnings() -> dict[str, Any]:
        """Avisos AEMET vigentes (amarillo o superior). Sin descarga válida: SIN_DATOS, nunca "0 avisos"."""
        run = db.last_run("aemet:avisos")
        if run is None and not db.warnings("aemet"):
            return {"status": "SIN_DATOS", "source": "AEMET", "items": []}
        if run is not None and not run["ok"]:
            return {"status": "SIN_DATOS", "source": "AEMET", "items": []}
        current = iso_utc(now())
        items = [
            w for w in db.warnings("aemet")
            if w.get("level") in WARNING_LEVELS and (w.get("expires") or "") > current
        ]
        items.sort(key=lambda w: (WARNING_LEVELS[w["level"]], w.get("onset") or ""))
        return {"status": "OK", "source": "AEMET", "items": items}

    def source_ok(source: str, cache: dict[str, bool]) -> bool:
        if source not in cache:
            run = db.last_run(source)
            cache[source] = run is None or run["ok"]
        return cache[source]

    def view(station: dict[str, Any], cache: dict[str, bool]) -> dict[str, Any]:
        latest = db.latest(station["station_id"])
        ok = source_ok(station["source"], cache)
        return {
            **station,
            **station_status(latest, now(), source_ok=ok),
            "source_ok": ok,
            "latest": latest.to_dict() if latest else None,
        }

    def envelope(**payload: Any) -> dict[str, Any]:
        marks: dict[str, Any] = {"demo": demo}
        if demo:
            marks["demo_notice"] = DEMO_NOTICE
        return {"disclaimer": DISCLAIMER, "generated_at_utc": iso_utc(now()), **marks, **payload}

    def find(station_id: str) -> dict[str, Any]:
        station = db.station(station_id)
        if station is None:
            raise HTTPException(status_code=404, detail="estación no encontrada")
        return station

    @app.get("/stations")
    def stations() -> dict[str, Any]:
        cache: dict[str, bool] = {}
        return envelope(stations=[view(s, cache) for s in db.stations()])

    @app.get("/stations/{station_id}/history")
    def history(station_id: str, limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        find(station_id)
        readings = db.history(station_id, limit=limit)
        return envelope(station_id=station_id, readings=[r.to_dict() for r in readings])

    @app.get("/stations/{station_id}")
    def station(station_id: str) -> dict[str, Any]:
        return envelope(station=view(find(station_id), {}))

    @app.get("/alerts")
    def alerts() -> dict[str, Any]:
        cache: dict[str, bool] = {}
        views = [view(s, cache) for s in db.stations()]
        over = sorted((v for v in views if v["status"] in SEVERITY), key=lambda v: (SEVERITY[v["status"]], v["station_id"]))
        return envelope(station_alerts=over, weather_warnings=weather_warnings(), propagation=propagation_now())

    @app.get("/propagation")
    def propagation() -> dict[str, Any]:
        return envelope(
            label=LABEL, triggers=asdict(table.triggers), links=describe_links(table), active=propagation_now()
        )

    return app
