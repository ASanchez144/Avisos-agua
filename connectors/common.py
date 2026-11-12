"""Utilidades compartidas por conectores (no son parsers de ninguna fuente)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Optional

SENTINELS = {-999.0, -9999.0, -99999.0}
MAX_LAG_BETWEEN_VARIABLES = timedelta(minutes=60)


def number(value: Any) -> tuple[Optional[float], bool]:
    """(valor, es_ilegible). Vacíos y centinelas → (None, False). Nunca inventa ni recorta."""
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
    result = float(value)
    if math.isnan(result) or math.isinf(result):
        return None, True
    if result in SENTINELS:
        return None, False
    return result, False


def merge_variables(
    groups: dict[str, tuple[datetime, dict[str, float]]]
) -> tuple[dict[str, float], Optional[datetime]]:
    """Une variables con fecha propia. Las que van más de 60 min por detrás de la
    más reciente se descartan (no se presentan como actuales). Devuelve los campos
    incluidos y el timestamp MÁS ANTIGUO de ellos."""
    if not groups:
        return {}, None
    freshest = max(ts for ts, _ in groups.values())
    included = [(ts, v) for ts, v in groups.values() if freshest - ts <= MAX_LAG_BETWEEN_VARIABLES]
    fields: dict[str, float] = {}
    for _, values in included:
        fields.update(values)
    return fields, min(ts for ts, _ in included)


def decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("iso-8859-15")
