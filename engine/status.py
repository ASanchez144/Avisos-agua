"""Estado de una estación.

Estados: NORMAL, VIGILANCIA, PREALERTA, ALERTA, SIN_DATOS, DATO_OBSOLETO, SIN_UMBRAL.
Si la fuente no publica umbral oficial, no hay semáforo: status="SIN_UMBRAL" y
threshold_note="umbral no publicado". Nunca se devuelve NORMAL por defecto.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml

from connectors.base import QUALITY_MISSING, QUALITY_SUSPECT, Reading

NORMAL = "NORMAL"
VIGILANCIA = "VIGILANCIA"
PREALERTA = "PREALERTA"
ALERTA = "ALERTA"
SIN_DATOS = "SIN_DATOS"
DATO_OBSOLETO = "DATO_OBSOLETO"

SIN_UMBRAL = "SIN_UMBRAL"
SOURCES_FILE = Path(__file__).with_name("sources.yaml")
FRESHNESS = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))["freshness_minutes"]


def fresh_limit_minutes(source: Optional[str]) -> int:
    return int(FRESHNESS.get(source, FRESHNESS["default"]))

UMBRAL_NO_PUBLICADO = "umbral no publicado"


def station_status(reading: Optional[Reading], now: datetime, source_ok: bool = True) -> dict[str, Any]:
    note = None
    if reading is not None and not reading.thresholds:
        note = UMBRAL_NO_PUBLICADO
    age = None
    limit = fresh_limit_minutes(reading.source) if reading is not None else None
    if reading is not None and reading.timestamp_utc is not None:
        age = max(0, int((now - reading.timestamp_utc).total_seconds() // 60))

    def result(status: str) -> dict[str, Any]:
        return {"status": status, "threshold_note": note, "age_minutes": age, "fresh_limit_minutes": limit}

    if reading is None or not source_ok:
        return result(SIN_DATOS)
    if reading.quality == QUALITY_MISSING or reading.timestamp_utc is None:
        return result(SIN_DATOS)
    if now - reading.timestamp_utc > timedelta(minutes=limit):
        return result(DATO_OBSOLETO)
    if reading.quality == QUALITY_SUSPECT:
        return result(SIN_DATOS)  # excluida de alertas; tampoco puede salir en verde
    if not reading.thresholds:
        return result(SIN_UMBRAL)  # hay dato, pero sin umbral oficial no se calcula semáforo

    variable = reading.thresholds.get("variable")
    value = getattr(reading, variable, None) if variable else None
    if value is None:  # sin valor (o sin saber a qué variable aplica el umbral) no hay semáforo fiable
        return result(SIN_DATOS)
    status = NORMAL
    for key, name in (("yellow", VIGILANCIA), ("orange", PREALERTA), ("red", ALERTA)):
        limit_value = reading.thresholds.get(key)
        if limit_value is not None and value >= limit_value:
            status = name
    return result(status)
