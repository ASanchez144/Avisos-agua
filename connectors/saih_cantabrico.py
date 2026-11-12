"""Conector del SAI de la Confederación Hidrográfica del Cantábrico.

Fuente verificada en docs/SOURCES_REPORT.md (Fase 0):
  POST https://visor.saichcantabrico.es/wp-admin/admin-ajax.php
  cuerpo: action=peticion_cincominutal&tipo=todas
  respuesta: {"success": true, "data": <GeoJSON FeatureCollection>}

Decisiones (todas respaldadas por el dato real):
- Las fechas de la fuente son hora local peninsular sin zona → Europe/Madrid.
- "1970-01-01 00:00:00" es el centinela de "sin dato" de la fuente.
- Cada variable trae su propia fecha. Una variable más de 60 min por detrás
  de la más reciente de su estación se descarta (no se muestra como actual).
  timestamp_utc es el MÁS ANTIGUO de las variables incluidas.
- Umbrales oficiales: seguimiento → yellow, prealerta → orange, alerta → red.
  Se usan los de nivel si existen; si no, los de caudal.
- nivel_embalse es una cota (msnm) y no se mapea a level_m.
- Piezómetros y nivómetros no tienen campos en el esquema común: se omiten.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from connectors.base import (
    QUALITY_MISSING,
    QUALITY_OK,
    QUALITY_SUSPECT,
    Reading,
    SourceFormatError,
)
from connectors.http import PoliteHttpClient
from engine.validation import violations

log = logging.getLogger(__name__)

SOURCE = "saih_cantabrico"
URL = "https://visor.saichcantabrico.es/wp-admin/admin-ajax.php"
FORM = {"action": "peticion_cincominutal", "tipo": "todas"}

SOURCE_TZ = ZoneInfo("Europe/Madrid")
INCLUDED_TYPES = {"cauce", "embalse", "meteorologica"}
SENTINELS = {-999.0, -9999.0, -99999.0}
MAX_LAG_BETWEEN_VARIABLES = timedelta(minutes=60)

# grupo -> (campo de fecha, {campo del esquema: campo de la fuente})
GROUPS: dict[str, tuple[str, dict[str, str]]] = {
    "flow": ("fecha_caudal", {"flow_m3s": "caudal"}),
    "level": ("fecha_nivel", {"level_m": "nivel"}),
    "rain": ("fecha_precipitacion", {"rain_1h_mm": "precipit_1h", "rain_24h_mm": "precipit_24h"}),
    "reservoir": (
        "fecha_embalse",
        {"reservoir_pct": "porcentaje_llenado_embalse", "reservoir_hm3": "volumen_embalse"},
    ),
}
THRESHOLD_SETS = (
    ("level_m", ("seguimiento_nivel", "prealerta_nivel", "alerta_nivel")),
    ("flow_m3s", ("seguimiento_caudal", "prealerta_caudal", "alerta_caudal")),
)


def _number(value: Any) -> tuple[Optional[float], bool]:
    """(valor, es_ilegible). Centinelas y vacíos → (None, False). Nunca inventa."""
    if value is None or isinstance(value, bool):
        return None, isinstance(value, bool)
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            return None, False
        try:
            value = float(text)
        except ValueError:
            return None, True
    if not isinstance(value, (int, float)):
        return None, True
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None, True
    if number in SENTINELS:
        return None, False
    return number, False


def _timestamp(value: Any) -> tuple[Optional[datetime], bool]:
    """(fecha UTC, es_ilegible). Vacío o centinela 1970 → (None, False)."""
    if value is None or value == "":
        return None, False
    try:
        local = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None, True
    if local.year <= 1970:
        return None, False
    return local.replace(tzinfo=SOURCE_TZ).astimezone(timezone.utc), False


def _coordinates(feature: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    props = feature.get("properties") or {}
    lat, _ = _number(props.get("lat"))
    lon, _ = _number(props.get("lon"))
    if lat is None or lon is None:
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        if len(coords) >= 2:
            lon, _ = _number(coords[0])
            lat, _ = _number(coords[1])
    if lat is None or lon is None:
        return None, None
    return lat, lon


def _thresholds(props: dict[str, Any]) -> tuple[Optional[dict[str, Any]], bool]:
    unreadable = False
    for variable, keys in THRESHOLD_SETS:
        values = []
        for key in keys:
            number, bad = _number(props.get(key))
            unreadable = unreadable or bad
            values.append(number)
        if any(v is not None for v in values):
            return {"yellow": values[0], "orange": values[1], "red": values[2], "variable": variable}, unreadable
    return None, unreadable


def _reading(feature: dict[str, Any], fetched_at_utc: datetime) -> Optional[Reading]:
    props = feature.get("properties")
    if not isinstance(props, dict) or props.get("tipo_estacion") not in INCLUDED_TYPES:
        return None
    code = props.get("codigo_general")
    if code is None or str(code).strip() == "":
        log.warning("saih_cantabrico: estación sin codigo_general omitida (%r)", props.get("nombre"))
        return None

    unreadable = False
    out_of_service = str(props.get("fuera_servicio")).strip().lower() in ("1", "true")
    groups: dict[str, tuple[datetime, dict[str, float]]] = {}
    if not out_of_service:
        for name, (date_key, mapping) in GROUPS.items():
            values: dict[str, float] = {}
            for field, source_key in mapping.items():
                number, bad = _number(props.get(source_key))
                unreadable = unreadable or bad
                if number is not None:
                    values[field] = number
            if not values:
                continue
            ts, bad = _timestamp(props.get(date_key))
            unreadable = unreadable or bad
            if ts is not None:
                groups[name] = (ts, values)

    fields: dict[str, Optional[float]] = {
        f: None for _, mapping in GROUPS.values() for f in mapping
    }
    timestamp: Optional[datetime] = None
    if groups:
        freshest = max(ts for ts, _ in groups.values())
        included = [(ts, v) for ts, v in groups.values() if freshest - ts <= MAX_LAG_BETWEEN_VARIABLES]
        timestamp = min(ts for ts, _ in included)
        for _, values in included:
            fields.update(values)

    thresholds, bad = _thresholds(props)
    unreadable = unreadable or bad
    lat, lon = _coordinates(feature)

    reading = Reading(
        station_id=f"{SOURCE}:{str(code).strip()}",
        source=SOURCE,
        name=str(props.get("nombre") or "").strip(),
        lat=lat,
        lon=lon,
        river=(str(props["rio"]).strip() or None) if props.get("rio") else None,
        thresholds=thresholds,
        timestamp_utc=timestamp,
        fetched_at_utc=fetched_at_utc,
        quality=QUALITY_OK if timestamp is not None else QUALITY_MISSING,
        **fields,
    )
    if unreadable or violations(reading, fetched_at_utc):
        reading.quality = QUALITY_SUSPECT
    return reading


def parse(raw: bytes, fetched_at_utc: datetime) -> list[Reading]:
    """Convierte la respuesta cruda en lecturas. Lanza SourceFormatError si la
    respuesta no tiene el formato verificado (HTML, JSON distinto, vacía...)."""
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceFormatError(f"saih_cantabrico: la respuesta no es JSON ({exc})") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise SourceFormatError("saih_cantabrico: falta success=true en la respuesta")
    data = payload.get("data")
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list) or not features:
        raise SourceFormatError("saih_cantabrico: no hay data.features en la respuesta")

    readings = []
    for feature in features:
        if isinstance(feature, dict):
            reading = _reading(feature, fetched_at_utc)
            if reading is not None:
                readings.append(reading)
    if not readings:
        raise SourceFormatError("saih_cantabrico: ninguna estación reconocible en la respuesta")
    return readings


class SaihCantabricoConnector:
    source = SOURCE

    def __init__(self, client: Optional[PoliteHttpClient] = None) -> None:
        self.client = client or PoliteHttpClient()

    def fetch(self) -> list[Reading]:
        result = self.client.request("POST", URL, data=FORM)
        return parse(result.body, result.fetched_at_utc)
