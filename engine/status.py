"""Estado de una estación.

Estados: NORMAL, VIGILANCIA, PREALERTA, ALERTA, SIN_DATOS, DATO_OBSOLETO.
Si la fuente no publica umbral oficial, no hay semáforo: status=None y
threshold_note="umbral no publicado". Nunca se devuelve NORMAL por defecto.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from connectors.base import QUALITY_MISSING, QUALITY_SUSPECT, Reading

NORMAL = "NORMAL"
VIGILANCIA = "VIGILANCIA"
PREALERTA = "PREALERTA"
ALERTA = "ALERTA"
SIN_DATOS = "SIN_DATOS"
DATO_OBSOLETO = "DATO_OBSOLETO"

OBSOLETE_AFTER = timedelta(minutes=60)
UMBRAL_NO_PUBLICADO = "umbral no publicado"


def station_status(reading: Optional[Reading], now: datetime, source_ok: bool = True) -> dict[str, Any]:
    note = None
    if reading is not None and not reading.thresholds:
        note = UMBRAL_NO_PUBLICADO

    def result(status: Optional[str]) -> dict[str, Any]:
        return {"status": status, "threshold_note": note}

    if reading is None or not source_ok:
        return result(SIN_DATOS)
    if reading.quality == QUALITY_MISSING or reading.timestamp_utc is None:
        return result(SIN_DATOS)
    if now - reading.timestamp_utc > OBSOLETE_AFTER:
        return result(DATO_OBSOLETO)
    if reading.quality == QUALITY_SUSPECT:
        return result(SIN_DATOS)  # excluida de alertas; tampoco puede salir en verde
    if not reading.thresholds:
        return result(None)

    variable = reading.thresholds.get("variable")
    value = getattr(reading, variable, None) if variable else None
    if value is None:  # sin valor (o sin saber a qué variable aplica el umbral) no hay semáforo fiable
        return result(SIN_DATOS)
    status = NORMAL
    for key, name in (("yellow", VIGILANCIA), ("orange", PREALERTA), ("red", ALERTA)):
        limit = reading.thresholds.get(key)
        if limit is not None and value >= limit:
            status = name
    return result(status)
