"""Reglas de plausibilidad de una lectura.

Una lectura con alguna violación NO se corrige ni se recorta: el conector la
marca quality=SUSPECT y el motor de estado la excluye de alertas.

L1–L6 son las leyes del proyecto. R1 es una regla adicional de este módulo
para embalses (volumen o porcentaje negativos), que las leyes no cubren.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

from connectors.base import Reading

FLOW_MAX_M3S = 15000.0
LEVEL_MIN_M, LEVEL_MAX_M = -2.0, 60.0
LAT_MIN, LAT_MAX = 27.5, 43.9
LON_MIN, LON_MAX = -18.5, 4.5
FUTURE_TOLERANCE = timedelta(minutes=5)
MAX_AGE = timedelta(days=7)


def _nan(value: Optional[float]) -> bool:
    return value is not None and math.isnan(value)


def violations(reading: Reading, now: datetime) -> list[str]:
    """Lista de violaciones ("L1: ...") de una lectura respecto a `now` (UTC)."""
    out: list[str] = []

    flow = reading.flow_m3s
    if flow is not None and (_nan(flow) or flow < 0 or flow > FLOW_MAX_M3S):
        out.append(f"L1: flow_m3s={flow} fuera de [0, {FLOW_MAX_M3S}]")

    level = reading.level_m
    if level is not None and (_nan(level) or level < LEVEL_MIN_M or level > LEVEL_MAX_M):
        out.append(f"L2: level_m={level} fuera de [{LEVEL_MIN_M}, {LEVEL_MAX_M}]")

    r1, r24 = reading.rain_1h_mm, reading.rain_24h_mm
    if r1 is not None and (_nan(r1) or r1 < 0):
        out.append(f"L3: rain_1h_mm={r1} negativo")
    if r24 is not None and (_nan(r24) or r24 < 0):
        out.append(f"L3: rain_24h_mm={r24} negativo")
    if r1 is not None and r24 is not None and not _nan(r1) and not _nan(r24) and r24 < r1:
        out.append(f"L3: rain_24h_mm={r24} < rain_1h_mm={r1}")

    lat, lon = reading.lat, reading.lon
    if lat is None or _nan(lat) or not (LAT_MIN <= lat <= LAT_MAX):
        out.append(f"L4: lat={lat} fuera de [{LAT_MIN}, {LAT_MAX}]")
    if lon is None or _nan(lon) or not (LON_MIN <= lon <= LON_MAX):
        out.append(f"L4: lon={lon} fuera de [{LON_MIN}, {LON_MAX}]")

    if reading.thresholds:
        levels = [reading.thresholds.get(k) for k in ("yellow", "orange", "red")]
        present = [v for v in levels if v is not None]
        if any(_nan(v) for v in present) or any(a >= b for a, b in zip(present, present[1:])):
            out.append(f"L5: umbrales no crecientes {levels}")

    ts = reading.timestamp_utc
    if ts is not None:
        if ts.tzinfo is None:
            out.append("L6: timestamp_utc sin zona horaria")
        elif ts > now + FUTURE_TOLERANCE:
            out.append(f"L6: timestamp_utc={ts.isoformat()} en el futuro")
        elif ts < now - MAX_AGE:
            out.append(f"L6: timestamp_utc={ts.isoformat()} con más de 7 días")

    for name in ("reservoir_hm3", "reservoir_pct"):
        value = getattr(reading, name)
        if value is not None and (_nan(value) or value < 0):
            out.append(f"R1: {name}={value} negativo")

    return out
