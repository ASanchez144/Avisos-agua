"""Conector de la Agència Catalana de l'Aigua (API SDIM2).

Fuente verificada en docs/SOURCES_REPORT.md:
  GET https://aplicacions.aca.gencat.cat/sdim2/apirest/catalog?componentType=<aforament|embassament>
  GET https://aplicacions.aca.gencat.cat/sdim2/apirest/data/<AFORAMENT-EST|EMBASSAMENT-EST>

Decisiones respaldadas por el dato real:
- Una estación = un `component` del catálogo; sus sensores aportan las variables.
- "Cabal riu" (m³/s) → flow_m3s; "Nivell riu" (cm) → level_m (÷100);
  "Volum embassat" (hm³) → reservoir_hm3; "Percentatge volum embassat" (%) → reservoir_pct.
- No se mapean: caudales de canal (l/s), cota absoluta de embalse (msnm) ni la
  intensidad de lluvia (mm/h instantánea; no es un acumulado de 1 h).
- La fecha se toma de `time` (epoch ms, UTC).
- La API no publica umbrales → thresholds=None ("umbral no publicado").
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from connectors.base import QUALITY_MISSING, QUALITY_OK, QUALITY_SUSPECT, Reading, SourceFormatError
from connectors.common import merge_variables, number
from connectors.http import PoliteHttpClient
from engine.validation import violations

SOURCE = "aca"
BASE = "https://aplicacions.aca.gencat.cat/sdim2/apirest/"
CATALOGS = ("catalog?componentType=aforament", "catalog?componentType=embassament")
DATA = ("data/AFORAMENT-EST", "data/EMBASSAMENT-EST")

# (descripción, unidad) → (campo del esquema, divisor de conversión)
SENSOR_MAP: dict[tuple[str, str], tuple[str, float]] = {
    ("Cabal riu", "m³/s"): ("flow_m3s", 1.0),
    ("Nivell riu", "cm"): ("level_m", 100.0),
    ("Volum embassat", "hm³"): ("reservoir_hm3", 1.0),
    ("Percentatge volum embassat", "%"): ("reservoir_pct", 1.0),
}
FIELDS = ("flow_m3s", "level_m", "rain_1h_mm", "rain_24h_mm", "reservoir_pct", "reservoir_hm3")


def _json(raw: bytes, what: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceFormatError(f"aca: {what} no es JSON ({exc})") from exc


def _catalog_sensors(raw: bytes) -> list[dict[str, Any]]:
    payload = _json(raw, "el catálogo")
    providers = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(providers, list) or not providers:
        raise SourceFormatError("aca: el catálogo no trae providers")
    sensors = [s for p in providers if isinstance(p, dict) for s in (p.get("sensors") or []) if isinstance(s, dict)]
    if not sensors:
        raise SourceFormatError("aca: el catálogo no trae sensores")
    return sensors


def _observations(raw: bytes) -> dict[str, dict[str, Any]]:
    payload = _json(raw, "la respuesta de datos")
    sensors = payload.get("sensors") if isinstance(payload, dict) else None
    if not isinstance(sensors, list):
        raise SourceFormatError("aca: la respuesta de datos no trae sensors")
    latest: dict[str, dict[str, Any]] = {}
    for s in sensors:
        obs = s.get("observations") if isinstance(s, dict) else None
        if isinstance(obs, list) and obs and isinstance(obs[0], dict):
            latest[str(s.get("sensor"))] = obs[0]
    return latest


def _coordinates(location: Any) -> tuple[Optional[float], Optional[float]]:
    parts = str(location or "").split()
    if len(parts) != 2:
        return None, None
    lat, _ = number(parts[0])
    lon, _ = number(parts[1])
    return (lat, lon) if lat is not None and lon is not None else (None, None)


def parse(catalogs: list[bytes], data: list[bytes], fetched_at_utc: datetime) -> list[Reading]:
    sensors = [s for raw in catalogs for s in _catalog_sensors(raw)]
    observations: dict[str, dict[str, Any]] = {}
    for raw in data:
        observations.update(_observations(raw))

    components: dict[str, dict[str, Any]] = {}
    for s in sensors:
        code = str(s.get("component") or "").strip()
        if not code:
            continue
        comp = components.setdefault(code, {"meta": s, "groups": {}, "unreadable": False})
        if s.get("componentType") == "embassament":
            comp["meta"] = s  # un embalse con aforo de salida se presenta como embalse
        mapping = SENSOR_MAP.get((str(s.get("description") or "").strip(), str(s.get("unit") or "").strip()))
        if mapping is None or mapping[0] in comp["groups"]:
            continue
        field, divisor = mapping
        obs = observations.get(str(s.get("sensor")))
        if obs is None:
            continue
        value, bad = number(obs.get("value"))
        epoch_ms, bad_time = number(obs.get("time"))
        comp["unreadable"] = comp["unreadable"] or bad or bad_time
        if value is None or epoch_ms is None:
            continue
        ts = datetime.fromtimestamp(epoch_ms / 1000, timezone.utc)
        comp["groups"][field] = (ts, {field: value / divisor})

    if not components:
        raise SourceFormatError("aca: ningún componente reconocible en el catálogo")

    readings = []
    for code, comp in components.items():
        meta = comp["meta"]
        values, timestamp = merge_variables(comp["groups"])
        lat, lon = _coordinates(meta.get("location"))
        river = (meta.get("componentAdditionalInfo") or {}).get("Riu")
        reading = Reading(
            station_id=f"{SOURCE}:{code}",
            source=SOURCE,
            name=str(meta.get("componentDesc") or code).strip(),
            lat=lat,
            lon=lon,
            river=str(river).strip() or None if river else None,
            thresholds=None,
            timestamp_utc=timestamp,
            fetched_at_utc=fetched_at_utc,
            quality=QUALITY_OK if timestamp is not None else QUALITY_MISSING,
            **{f: values.get(f) for f in FIELDS},
        )
        if comp["unreadable"] or violations(reading, fetched_at_utc):
            reading.quality = QUALITY_SUSPECT
        readings.append(reading)
    return readings


class AcaConnector:
    source = SOURCE

    def __init__(self, client: Optional[PoliteHttpClient] = None) -> None:
        self.client = client or PoliteHttpClient()

    def fetch(self) -> list[Reading]:
        catalogs = [self.client.request("GET", BASE + path) for path in CATALOGS]
        data = [self.client.request("GET", BASE + path) for path in DATA]
        fetched_at = min(r.fetched_at_utc for r in data)
        return parse([r.body for r in catalogs], [r.body for r in data], fetched_at)
