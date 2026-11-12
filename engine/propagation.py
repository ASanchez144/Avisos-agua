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


LEVELS = ("ALERTA", "VIGILANCIA")  # de mayor a menor


@dataclass(frozen=True)
class LevelCfg:
    rain_mm_h: float
    flow_rise_pct_1h: float
    min_flow_m3s: float


@dataclass(frozen=True)
class Triggers:
    consecutive_readings: int      # lecturas consecutivas que deben cumplir la condición
    max_age_minutes: float         # antigüedad máxima de la última lectura
    hour_tolerance_minutes: float  # margen para encontrar la lectura de "hace 1 h"
    max_gap_minutes: float         # separación máxima entre lecturas consecutivas
    levels: dict[str, LevelCfg]    # "VIGILANCIA" y "ALERTA"


@dataclass(frozen=True)
class Regime:
    speed_kmh_min: Optional[float]   # None = sin referencia verificable: no se da rango horario
    speed_kmh_max: Optional[float]
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
    distance_km: Optional[float]
    distance_status: str
    distance_source: str
    lower_bound: bool = False
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

    def with_level(self, name: str, **changes: float) -> "LinkTable":
        levels = {**self.triggers.levels, name: replace(self.triggers.levels[name], **changes)}
        return replace(self, triggers=replace(self.triggers, levels=levels))

    def with_triggers(self, **changes: Any) -> "LinkTable":
        return replace(self, triggers=replace(self.triggers, **changes))


def _point(raw: dict[str, Any]) -> Point:
    return Point(**{k: raw.get(k) for k in ("name", "station_id", "lat", "lon", "elevation_m", "coord_source")})


def _polyline_km(points: list[Point]) -> float:
    if any(p.lat is None or p.lon is None for p in points):
        raise ValueError("faltan coordenadas para calcular la distancia: indica distance_km")
    return sum(haversine_km(a.lat, a.lon, b.lat, b.lon) for a, b in zip(points, points[1:]))


SIN_DISTANCIA = "SIN_DISTANCIA"


def load_links(path: str | Path) -> LinkTable:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    regimes = {name: Regime(**values) for name, values in raw["regimes"].items()}
    links = []
    for item in raw["links"]:
        origin, destination = _point(item["origin"]), _point(item["destination"])
        if item["regime"] not in regimes:
            raise ValueError(f"régimen desconocido en {item['id']}: {item['regime']}")
        lower_bound = False
        if item.get("distance_km") is not None:
            distance: Optional[float] = float(item["distance_km"])
            status = item.get("distance_status", ESTIMADA)
            source = " ".join(str(item["distance_source"]).split())
        elif item.get("no_distance"):
            distance, status = None, SIN_DISTANCIA
            source = " ".join(str(item["no_distance"]).split())
        else:
            via = [_point(p) for p in item.get("via", [])]
            distance = round(_polyline_km([origin, *via, destination]), 1)
            status, lower_bound = ESTIMADA, True
            names = ", ".join(sorted({p.coord_source for p in (origin, *via, destination) if p.coord_source}))
            source = (
                "Poligonal en línea recta entre coordenadas oficiales "
                f"({names}). Cota inferior: el cauce real es más largo, así que la llegada real puede ser "
                "MÁS TARDÍA que la estimada (el ETA puede ser menor que el real)."
            )
        if status not in (ESTIMADA, VERIFICADA, SIN_DISTANCIA) or (distance is not None and distance <= 0):
            raise ValueError(f"distancia no válida en {item['id']}")
        links.append(Link(
            id=item["id"], river=item["river"], regime=item["regime"], origin=origin, destination=destination,
            distance_km=distance, distance_status=status, distance_source=source, lower_bound=lower_bound,
            rain_station_id=item.get("rain_station_id"), note=item.get("note"),
        ))
    if len({l.id for l in links}) != len(links):
        raise ValueError("ids de enlace repetidos")
    t = raw["triggers"]
    triggers = Triggers(
        consecutive_readings=int(t["consecutive_readings"]), max_age_minutes=t["max_age_minutes"],
        hour_tolerance_minutes=t["hour_tolerance_minutes"], max_gap_minutes=t["max_gap_minutes"],
        levels={"VIGILANCIA": LevelCfg(**t["vigilancia"]), "ALERTA": LevelCfg(**t["alerta"])},
    )
    return LinkTable(triggers=triggers, regimes=regimes, links=tuple(links))


# ------------------------------------------------------------ disparadores

History = Callable[[str], list[Reading]]


def _series(readings: list[Reading], now: datetime, cfg: Triggers) -> list[Reading]:
    """Lecturas OK con fecha, de más reciente a más antigua. Vacío si la última es demasiado antigua."""
    ok = sorted(
        (r for r in readings if r.quality == QUALITY_OK and r.timestamp_utc is not None and r.timestamp_utc <= now),
        key=lambda r: r.timestamp_utc, reverse=True,
    )
    if not ok or now - ok[0].timestamp_utc > timedelta(minutes=cfg.max_age_minutes):
        return []
    return ok


def _consecutive(series: list[Reading], holds: Callable[[Reading], bool], cfg: Triggers) -> bool:
    """¿Las N lecturas más recientes cumplen la condición, sin huecos grandes entre ellas?"""
    n = cfg.consecutive_readings
    if len(series) < n:
        return False
    chosen = series[:n]
    gap = timedelta(minutes=cfg.max_gap_minutes)
    if any(a.timestamp_utc - b.timestamp_utc > gap for a, b in zip(chosen, chosen[1:])):
        return False
    return all(holds(r) for r in chosen)


def _flow_rise(series: list[Reading], r: Reading, cfg: Triggers) -> Optional[tuple[float, Optional[float]]]:
    """(caudal de hace 1 h, subida en %) o None si no hay lectura de hace una hora."""
    target = r.timestamp_utc - timedelta(hours=1)
    tolerance = timedelta(minutes=cfg.hour_tolerance_minutes)
    candidates = [p for p in series if p.flow_m3s is not None and abs(p.timestamp_utc - target) <= tolerance]
    if not candidates:
        return None
    previous = min(candidates, key=lambda p: abs(p.timestamp_utc - target))
    rise = (r.flow_m3s - previous.flow_m3s) / previous.flow_m3s * 100 if previous.flow_m3s > 0 else None
    return previous.flow_m3s, rise


def _rain_trigger(link: Link, history: History, now: datetime, cfg: Triggers, level: str) -> Optional[dict[str, Any]]:
    lv = cfg.levels[level]
    for station in (link.origin.station_id, link.rain_station_id):
        if not station:
            continue
        series = [r for r in _series(history(station), now, cfg) if r.rain_1h_mm is not None]
        if series and _consecutive(series, lambda r: r.rain_1h_mm >= lv.rain_mm_h, cfg):
            return {
                "type": "lluvia", "level": level, "value": series[0].rain_1h_mm, "threshold": lv.rain_mm_h, "unit": "mm/h",
                "consecutive_readings": cfg.consecutive_readings, "station_id": station,
                "observed_at_utc": iso_utc(series[0].timestamp_utc),
            }
    return None


def _flow_trigger(link: Link, history: History, now: datetime, cfg: Triggers, level: str) -> Optional[dict[str, Any]]:
    station = link.origin.station_id
    if not station:
        return None
    lv = cfg.levels[level]
    series = [r for r in _series(history(station), now, cfg) if r.flow_m3s is not None]
    if not series:
        return None

    def holds(r: Reading) -> bool:
        if r.flow_m3s < lv.min_flow_m3s:
            return False
        info = _flow_rise(series, r, cfg)
        if info is None:
            return False  # sin lectura de hace una hora no se inventa la subida
        _, rise = info
        return rise is None or rise >= lv.flow_rise_pct_1h  # cauce seco que empieza a correr: solo cuenta por encima del mínimo

    if not _consecutive(series, holds, cfg):
        return None
    previous, rise = _flow_rise(series, series[0], cfg)
    return {
        "type": "subida_caudal", "level": level, "value": rise, "threshold": lv.flow_rise_pct_1h, "unit": "% en 1 h",
        "consecutive_readings": cfg.consecutive_readings, "station_id": station,
        "observed_at_utc": iso_utc(series[0].timestamp_utc), "flow_m3s": series[0].flow_m3s,
        "flow_1h_before_m3s": previous, "min_flow_m3s": lv.min_flow_m3s,
    }


def _trigger(link: Link, history: History, now: datetime, cfg: Triggers) -> Optional[dict[str, Any]]:
    for level in LEVELS:  # el nivel más alto que se cumpla
        found = _rain_trigger(link, history, now, cfg, level) or _flow_trigger(link, history, now, cfg, level)
        if found:
            return found
    return None


# --------------------------------------------------------------------- ETA

def _eta(link: Link, regime: Regime) -> Optional[tuple[float, float]]:
    """Rango en horas, o None si falta distancia o velocidad verificables (no se inventa)."""
    if link.distance_km is None or regime.speed_kmh_min is None or regime.speed_kmh_max is None:
        return None
    return link.distance_km / regime.speed_kmh_max, link.distance_km / regime.speed_kmh_min


def _ends(link: Link) -> dict[str, Any]:
    return {
        "origin": {"station_id": link.origin.station_id, "name": link.origin.name, "lat": link.origin.lat, "lon": link.origin.lon},
        "destination": {
            "station_id": link.destination.station_id, "name": link.destination.name,
            "lat": link.destination.lat, "lon": link.destination.lon,
        },
    }


def _estimate(table: LinkTable, link: Link, trigger: dict[str, Any], eta: Optional[tuple[float, float]], via: list[str]) -> dict[str, Any]:
    regime = table.regimes[link.regime]
    available = eta is not None
    return {
        "link_id": link.id, "river": link.river, **_ends(link),
        "level": trigger["level"], "trigger": trigger,
        "distance_km": link.distance_km, "distance_status": link.distance_status, "distance_source": link.distance_source,
        "distance_is_lower_bound": link.lower_bound,
        "regime": link.regime,
        "speed_kmh": [regime.speed_kmh_min, regime.speed_kmh_max] if regime.speed_kmh_min is not None else None,
        "speed_status": regime.status, "speed_source": " ".join(regime.source.split()),
        "slope_m_per_km": link.slope_m_per_km,
        "eta_available": available,
        # redondeo hacia fuera: el rango nunca se estrecha al redondear
        "eta_hours_min": math.floor(eta[0] * 100) / 100 if available else None,
        "eta_hours_max": math.ceil(eta[1] * 100) / 100 if available else None,
        "message": None if available else "subida detectada en cabecera (sin estimación de llegada: falta distancia o velocidad verificada)",
        "via": via, "label": LABEL, "note": link.note,
    }


def evaluate(table: LinkTable, history: History, now: datetime) -> list[dict[str, Any]]:
    """Estimaciones activas. Cada enlace disparado se propaga aguas abajo acumulando el rango
    mientras haya ETA; sin ETA (rambla o distancia sin verificar) se avisa solo de la subida."""
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for link in table.links:
        trigger = _trigger(link, history, now, table.triggers)
        if trigger is None:
            continue
        lo = hi = 0.0
        via: list[str] = []
        current: Optional[Link] = link
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            step = _eta(current, table.regimes[current.regime])
            if step is None:
                estimate = _estimate(table, current, trigger, None, list(via))
                if current.id not in best:
                    order.append(current.id)
                    best[current.id] = estimate
                break  # no se puede acumular más allá de un tramo sin ETA
            lo, hi = lo + step[0], hi + step[1]
            estimate = _estimate(table, current, trigger, (lo, hi), list(via))
            if current.id not in best:
                order.append(current.id)
                best[current.id] = estimate
            elif (estimate["eta_hours_min"] or 0) < (best[current.id]["eta_hours_min"] or 1e9):
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
        eta = _eta(link, regime)
        out.append({
            "link_id": link.id, "river": link.river, "regime": link.regime, **_ends(link),
            "distance_km": link.distance_km, "distance_status": link.distance_status,
            "distance_source": link.distance_source, "distance_is_lower_bound": link.lower_bound,
            "speed_kmh": [regime.speed_kmh_min, regime.speed_kmh_max] if regime.speed_kmh_min is not None else None,
            "speed_status": regime.status, "speed_source": " ".join(regime.source.split()),
            "slope_m_per_km": link.slope_m_per_km, "eta_available": eta is not None,
            "eta_hours_min": math.floor(eta[0] * 100) / 100 if eta else None,
            "eta_hours_max": math.ceil(eta[1] * 100) / 100 if eta else None,
            "rain_station_id": link.rain_station_id, "label": LABEL, "note": link.note,
        })
    return out
