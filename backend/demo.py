"""Modo demostración (DEMO_LIVE_FALLBACK=true).

Sirve datos de EJEMPLO generados en memoria, relativos a la hora actual. No toca
la base de datos real ni llama a ninguna fuente. Todas las respuestas llevan
`demo: true` y `demo_notice`, todos los nombres empiezan por "DEMO · " y la
fuente es "demo": no pueden confundirse con datos reales.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import FastAPI

from backend.app import DEMO_NOTICE, create_app
from connectors.base import Reading, iso_utc
from engine.propagation import ESTIMADA, LevelCfg, Link, LinkTable, Point, Regime, Triggers
from engine.geo import haversine_km

SOURCE = "demo"
STEP = timedelta(minutes=5)
HISTORY_HOURS = 12
TH = {"yellow": 2.0, "orange": 3.0, "red": 4.0, "variable": "level_m"}

# id -> (nombre, lat, lon, río, tipo)
STATIONS: dict[str, tuple[str, float, float, Optional[str], str]] = {
    "demo:cabecera": ("DEMO · Río Ejemplo en Cabecera", 40.42, -3.95, "Río Ejemplo", "cabecera"),
    "demo:medio": ("DEMO · Río Ejemplo en Tramo Medio", 40.36, -3.70, "Río Ejemplo", "medio"),
    "demo:valle": ("DEMO · Río Ejemplo en Valle", 40.30, -3.45, "Río Ejemplo", "valle"),
    "demo:ciudad": ("DEMO · Río Ejemplo en Ciudad", 40.25, -3.20, "Río Ejemplo", "ciudad"),
    "demo:embalse": ("DEMO · Embalse de Ejemplo", 40.50, -3.60, "Río Afluente", "embalse"),
    "demo:sin_umbral": ("DEMO · Arroyo sin umbral publicado", 40.18, -3.80, "Arroyo Ejemplo", "sin_umbral"),
    "demo:obsoleta": ("DEMO · Estación con dato antiguo", 40.55, -3.25, "Río Afluente", "obsoleta"),
    "demo:sin_datos": ("DEMO · Estación sin datos", 40.12, -3.40, "Arroyo Ejemplo", "sin_datos"),
}


def _wave(hours_ago: float, peak_hours_ago: float, base: float, peak: float) -> float:
    """Onda de crecida suave centrada hace `peak_hours_ago` horas."""
    return base + (peak - base) * math.exp(-((hours_ago - peak_hours_ago) ** 2) / 2.5)


class DemoData:
    """Misma interfaz de lectura que backend.db.Database."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now

    def _tick(self) -> datetime:
        now = self._now()
        return now - timedelta(minutes=now.minute % 5, seconds=now.second, microseconds=now.microsecond)

    def _reading(self, station_id: str, ts: datetime, tick: datetime) -> Reading:
        name, lat, lon, river, kind = STATIONS[station_id]
        h = (tick - ts).total_seconds() / 3600
        values: dict[str, Optional[float]] = dict.fromkeys(
            ("flow_m3s", "level_m", "rain_1h_mm", "rain_24h_mm", "reservoir_pct", "reservoir_hm3")
        )
        thresholds: Optional[dict[str, Any]] = dict(TH)
        quality, timestamp = "OK", ts
        if kind == "cabecera":
            values.update(flow_m3s=_wave(h, -0.5, 8, 95), level_m=_wave(h, -0.5, 0.5, 1.6),
                          rain_1h_mm=round(_wave(h, 0.5, 0, 26), 1), rain_24h_mm=round(48 - 2.5 * h, 1))
        elif kind == "medio":
            values.update(flow_m3s=_wave(h, -1, 20, 150), level_m=_wave(h, -1, 0.9, 3.2), rain_1h_mm=round(_wave(h, 1, 0, 9), 1))
        elif kind == "valle":
            values.update(flow_m3s=_wave(h, 0.5, 60, 310), level_m=_wave(h, 0.5, 1.4, 3.6))
        elif kind == "ciudad":
            values.update(flow_m3s=_wave(h, 0, 90, 520), level_m=_wave(h, 0, 1.8, 4.3))
        elif kind == "embalse":
            values.update(reservoir_pct=round(71.0 - 0.35 * h, 2), reservoir_hm3=round(142.0 - 0.7 * h, 2),
                          flow_m3s=_wave(h, 0, 6, 9))
            thresholds = None
        elif kind == "sin_umbral":
            values.update(flow_m3s=_wave(h, 2, 1.5, 4), level_m=_wave(h, 2, 0.3, 0.6))
            thresholds = None
        elif kind == "obsoleta":
            timestamp = ts - timedelta(hours=3)
            values.update(flow_m3s=12.0, level_m=1.1)
        elif kind == "sin_datos":
            quality, timestamp = "MISSING", None
        values = {k: (round(v, 3) if v is not None else None) for k, v in values.items()}
        return Reading(station_id=station_id, source=SOURCE, name=name, lat=lat, lon=lon, river=river,
                       thresholds=thresholds, timestamp_utc=timestamp, fetched_at_utc=ts, quality=quality, **values)

    def stations(self) -> list[dict[str, Any]]:
        return [
            {"station_id": sid, "source": SOURCE, "name": name, "lat": lat, "lon": lon, "river": river}
            for sid, (name, lat, lon, river, _) in STATIONS.items()
        ]

    def station(self, station_id: str) -> Optional[dict[str, Any]]:
        return next((s for s in self.stations() if s["station_id"] == station_id), None)

    def history(self, station_id: str, limit: int = 100) -> list[Reading]:
        if station_id not in STATIONS:
            return []
        tick = self._tick()
        steps = min(limit, int(timedelta(hours=HISTORY_HOURS) / STEP))
        if STATIONS[station_id][4] == "sin_datos":
            steps = 1
        return [self._reading(station_id, tick - i * STEP, tick) for i in range(steps)]

    def latest(self, station_id: str) -> Optional[Reading]:
        history = self.history(station_id, limit=1)
        return history[0] if history else None

    def last_run(self, source: str) -> Optional[dict[str, Any]]:
        return {"source": source, "ok": True, "error": None}

    def warnings(self, source: str) -> list[dict[str, Any]]:
        tick = self._tick()
        return [{
            "identifier": "demo-aviso-1", "sent": iso_utc(tick - timedelta(hours=2)),
            "event": "DEMO · Aviso de lluvias de nivel naranja", "level": "naranja", "phenomenon": "Lluvias",
            "severity": "Severe", "onset": iso_utc(tick - timedelta(hours=1)), "expires": iso_utc(tick + timedelta(hours=9)),
            "headline": "DEMO · Aviso de lluvias de nivel naranja. Zona de ejemplo",
            "description": "DEMO · Precipitación acumulada en una hora: 30 mm.", "probability": "40%-70%",
            "area": "DEMO · Zona de ejemplo", "zone": "000000",
            "polygons": [[(40.60, -4.10), (40.60, -3.50), (40.25, -3.50), (40.25, -4.10), (40.60, -4.10)]],
        }]


def demo_links() -> LinkTable:
    chain = ["demo:cabecera", "demo:medio", "demo:valle", "demo:ciudad"]
    links = []
    for a, b in zip(chain, chain[1:]):
        (na, la, lo, _, _), (nb, lb, lob, _, _) = STATIONS[a], STATIONS[b]
        links.append(Link(
            id=f"demo-{a.split(':')[1]}-{b.split(':')[1]}", river="DEMO · Río Ejemplo", regime="rio",
            origin=Point(name=na, station_id=a, lat=la, lon=lo), destination=Point(name=nb, station_id=b, lat=lb, lon=lob),
            distance_km=round(haversine_km(la, lo, lb, lob), 1), distance_status=ESTIMADA, lower_bound=True,
            distance_source="DEMO · distancia de ejemplo", note="DEMO · enlace de ejemplo",
        ))
    return LinkTable(
        triggers=Triggers(consecutive_readings=2, max_age_minutes=120, hour_tolerance_minutes=15, max_gap_minutes=90,
                          levels={"VIGILANCIA": LevelCfg(20.0, 30.0, 5.0), "ALERTA": LevelCfg(40.0, 100.0, 50.0)}),
        regimes={"rio": Regime(6.0, 14.0, ESTIMADA, "DEMO · rango de ejemplo 6-14 km/h")},
        links=tuple(links),
    )


def create_demo_app(now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), lifespan: Any = None) -> FastAPI:
    return create_app(DemoData(now), now=now, lifespan=lifespan, links=demo_links(), demo=True)
