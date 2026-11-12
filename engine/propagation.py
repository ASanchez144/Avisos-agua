"""Motor de propagación cabecera -> valle.

Disparadores (configurables en river_links.yaml):
  - lluvia >= N mm en 1 h en la cabecera (estación de origen o su estación de lluvia enlazada);
  - subida de caudal >= P % en 1 h en la estación de origen.

ETA = distancia / velocidad de onda. La velocidad es un RANGO (por régimen: río o
rambla), así que la llegada es siempre un RANGO de horas, nunca una hora exacta,
y lleva la etiqueta "estimación orientativa". Las distancias y velocidades no
verificadas viajan marcadas ESTIMADA hasta la UI.

Solo disparan lecturas quality=OK y recientes: un dato SUSPECT, MISSING u
obsoleto no genera propagación.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from connectors.base import QUALITY_OK, Reading, iso_utc
from engine.geo import haversine_km

LABEL = "estimación orientativa"
ESTIMADA = "ESTIMADA"
VERIFICADA = "VERIFICADA"


@dataclass(frozen=True)
class Triggers:
    rain_mm_h: float
    flow_rise_pct_1h: float
    min_flow_m3s: float
    max_age_minutes: float
    hour_tolerance_minutes: float


@dataclass(frozen=True)
class Regime:
    speed_kmh_min: float
    speed_kmh_max: float
    status: str
    source: str


@dataclass(frozen=True)
class Point:
    name: str
    station_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    elevation_m: Optional[float] = None
    coord_source: Optional[str] = None


@dataclass(frozen=True)
class Link:
    id: str
    river: str
    regime: str
    origin: Point
    destination: Point
    distance_km: float
    distance_status: str
    distance_source: str
    rain_station_id: Optional[str] = None
    note: Optional[str] = None

    @property
    def slope_m_per_km(self) -> Optional[float]:
        a, b = self.origin.elevation_m, self.destination.elevation_m
        return round((a - b) / self.distance_km, 2) if a is not None and b is not None else None


@dataclass(frozen=True)
class LinkTable:
    triggers: Triggers
    regimes: dict[str, Regime]
    links: tuple[Link, ...]

    def with_triggers(self, **changes: float) -> "LinkTable":
        return replace(self, triggers=replace(self.triggers, **changes))


def _point(raw: dict[str, Any]) -> Point:
    return Point(**{k: raw.get(k) for k in ("name", "station_id", "lat", "lon", "elevation_m", "coord_source")})


def _polyline_km(points: list[Point]) -> float:
    if any(p.lat is None or p.lon is None for p in points):
        raise ValueError("faltan coordenadas para calcular la distancia: indica distance_km")
    return sum(haversine_km(a.lat, a.lon, b.lat, b.lon) for a, b in zip(points, points[1:]))


def load_links(path: str | Path) -> LinkTable:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    regimes = {name: Regime(**values) for name, values in raw["regimes"].items()}
    links = []
    for item in raw["links"]:
        origin, destination = _point(item["origin"]), _point(item["destination"])
        if item["regime"] not in regimes:
            raise ValueError(f"régimen desconocido en {item['id']}: {item['regime']}")
        if item.get("distance_km") is not None:
            distance = float(item["distance_km"])
            status = item.get("distance_status", ESTIMADA)
            source = " ".join(str(item["distance_source"]).split())
        else:
            via = [_point(p) for p in item.get("via", [])]
            distance = round(_polyline_km([origin, *via, destination]), 1)
            status = ESTIMADA
            names = ", ".join(sorted({p.coord_source for p in (origin, *via, destination) if p.coord_source}))
            source = (
                "Poligonal en línea recta entre coordenadas oficiales "
                f"({names}). Cota inferior: el cauce real es más largo."
            )
        if status not in (ESTIMADA, VERIFICADA) or distance <= 0:
            raise ValueError(f"distancia no válida en {item['id']}")
        links.append(Link(
            id=item["id"], river=item["river"], regime=item["regime"], origin=origin, destination=destination,
            distance_km=distance, distance_status=status, distance_source=source,
            rain_station_id=item.get("rain_station_id"), note=item.get("note"),
        ))
    if len({l.id for l in links}) != len(links):
        raise ValueError("ids de enlace repetidos")
    return LinkTable(triggers=Triggers(**raw["triggers"]), regimes=regimes, links=tuple(links))


# ------------------------------------------------------------ disparadores

History = Callable[[str], list[Reading]]


def _usable(readings: list[Reading], now: datetime, max_age: timedelta) -> list[Reading]:
    return [
        r for r in readings
        if r.quality == QUALITY_OK and r.timestamp_utc is not None and timedelta(0) <= now - r.timestamp_utc <= max_age
    ]


def _rain_trigger(link: Link, history: History, now: datetime, cfg: Triggers) -> Optional[dict[str, Any]]:
    for station in (link.origin.station_id, link.rain_station_id):
        if not station:
            continue
        fresh = [r for r in _usable(history(station), now, timedelta(minutes=cfg.max_age_minutes)) if r.rain_1h_mm is not None]
        if fresh and fresh[0].rain_1h_mm >= cfg.rain_mm_h:
            return {
                "type": "lluvia", "value": fresh[0].rain_1h_mm, "threshold": cfg.rain_mm_h, "unit": "mm/h",
                "station_id": station, "observed_at_utc": iso_utc(fresh[0].timestamp_utc),
            }
    return None


def _flow_trigger(link: Link, history: History, now: datetime, cfg: Triggers) -> Optional[dict[str, Any]]:
    station = link.origin.station_id
    if not station:
        return None
    readings = [r for r in history(station) if r.quality == QUALITY_OK and r.timestamp_utc and r.flow_m3s is not None]
    fresh = _usable(readings, now, timedelta(minutes=cfg.max_age_minutes))
    if not fresh or fresh[0].flow_m3s < cfg.min_flow_m3s:
        return None
    current = fresh[0]
    target = current.timestamp_utc - timedelta(hours=1)
    tolerance = timedelta(minutes=cfg.hour_tolerance_minutes)
    candidates = [r for r in readings if abs(r.timestamp_utc - target) <= tolerance]
    if not candidates:
        return None  # sin lectura de hace una hora no se inventa la subida
    previous = min(candidates, key=lambda r: abs(r.timestamp_utc - target))
    if previous.flow_m3s > 0:
        rise: Optional[float] = (current.flow_m3s - previous.flow_m3s) / previous.flow_m3s * 100
        if rise < cfg.flow_rise_pct_1h:
            return None
    else:
        rise = None  # cauce seco que empieza a correr: subida no expresable en %
    return {
        "type": "subida_caudal", "value": rise, "threshold": cfg.flow_rise_pct_1h, "unit": "% en 1 h",
        "station_id": station, "observed_at_utc": iso_utc(current.timestamp_utc),
        "flow_m3s": current.flow_m3s, "flow_1h_before_m3s": previous.flow_m3s,
    }


# --------------------------------------------------------------------- ETA

def _eta(link: Link, regime: Regime) -> tuple[float, float]:
    return link.distance_km / regime.speed_kmh_max, link.distance_km / regime.speed_kmh_min


def _estimate(table: LinkTable, link: Link, trigger: dict[str, Any], lo: float, hi: float, via: list[str]) -> dict[str, Any]:
    regime = table.regimes[link.regime]
    return {
        "link_id": link.id,
        "river": link.river,
        "origin": {"station_id": link.origin.station_id, "name": link.origin.name, "lat": link.origin.lat, "lon": link.origin.lon},
        "destination": {
            "station_id": link.destination.station_id, "name": link.destination.name,
            "lat": link.destination.lat, "lon": link.destination.lon,
        },
        "trigger": trigger,
        "distance_km": link.distance_km,
        "distance_status": link.distance_status,
        "distance_source": link.distance_source,
        "regime": link.regime,
        "speed_kmh": [regime.speed_kmh_min, regime.speed_kmh_max],
        "speed_status": regime.status,
        "speed_source": " ".join(regime.source.split()),
        "slope_m_per_km": link.slope_m_per_km,
        # redondeo hacia fuera: el rango nunca se estrecha al redondear
        "eta_hours_min": math.floor(lo * 100) / 100,
        "eta_hours_max": math.ceil(hi * 100) / 100,
        "via": via,
        "label": LABEL,
        "note": link.note,
    }


def evaluate(table: LinkTable, history: History, now: datetime) -> list[dict[str, Any]]:
    """Estimaciones activas. Cada enlace disparado se propaga aguas abajo acumulando el rango."""
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for link in table.links:
        trigger = _rain_trigger(link, history, now, table.triggers) or _flow_trigger(link, history, now, table.triggers)
        if trigger is None:
            continue
        lo = hi = 0.0
        via: list[str] = []
        current: Optional[Link] = link
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            step_lo, step_hi = _eta(current, table.regimes[current.regime])
            lo, hi = lo + step_lo, hi + step_hi
            estimate = _estimate(table, current, trigger, lo, hi, list(via))
            if current.id not in best:
                order.append(current.id)
                best[current.id] = estimate
            elif estimate["eta_hours_min"] < best[current.id]["eta_hours_min"]:
                best[current.id] = estimate
            via.append(current.id)
            station = current.destination.station_id
            current = next((l for l in table.links if station and l.origin.station_id == station), None)
    return [best[i] for i in order]


def describe_links(table: LinkTable) -> list[dict[str, Any]]:
    """Tabla de enlaces para la API/UI, con sus marcas de ESTIMADA."""
    out = []
    for link in table.links:
        regime = table.regimes[link.regime]
        lo, hi = _eta(link, regime)
        out.append({
            "link_id": link.id, "river": link.river, "regime": link.regime,
            "origin": {"station_id": link.origin.station_id, "name": link.origin.name, "lat": link.origin.lat, "lon": link.origin.lon},
            "destination": {
                "station_id": link.destination.station_id, "name": link.destination.name,
                "lat": link.destination.lat, "lon": link.destination.lon,
            },
            "distance_km": link.distance_km, "distance_status": link.distance_status,
            "distance_source": link.distance_source,
            "speed_kmh": [regime.speed_kmh_min, regime.speed_kmh_max], "speed_status": regime.status,
            "speed_source": " ".join(regime.source.split()),
            "slope_m_per_km": link.slope_m_per_km,
            "eta_hours_min": math.floor(lo * 100) / 100, "eta_hours_max": math.ceil(hi * 100) / 100,
            "rain_station_id": link.rain_station_id, "label": LABEL, "note": link.note,
        })
    return out
