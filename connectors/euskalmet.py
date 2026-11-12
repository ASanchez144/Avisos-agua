"""Conector de Euskalmet (Agencia Vasca de Meteorología): nivel de los ríos del País Vasco.

API oficial (con clave gratuita): https://api.euskadi.eus/euskalmet — autenticación JWT RS256
(connectors/euskalmet_auth.py). Verificado con peticiones reales el 2026-11-12:

- GET /euskalmet/readings/forStation/{estación}/{sensor}/measures/measuresForWater/{medida}/at/AAAA/MM/DD/HH
  → una hora UTC (`dateRange` en epoch ms, inicio en la hora en punto) en 6 tramos de 10 min
  (`slots`) con `values`; `null` = tramo sin dato.
- La unidad de `sheet_level_*` (nivel de la lámina de agua) es METERS (GET /euskalmet/measures/...).
- La web oficial (www.euskalmet.euskadi.eus, /vamet/stations/readings/.../webmet00-readingsData.json)
  muestra el mismo valor con la hora LOCAL del inicio del tramo: 13:00 UTC → "14:00" en invierno.
- El endpoint agregado por día rellena con 0.0 los tramos sin dato: NO se usa (un 0 falso parecería real).

No se publican (y por tanto no se emiten):
- Caudal: "flow_*_computed" existe, pero la API no publica su unidad → NO VERIFICADO.
- Lluvia: hay precipitación por tramo de 10 min (mm); sumarla en 1 h/24 h no está verificado aún.
- Umbrales: la API no los publica → "umbral no publicado" (SIN_UMBRAL).

Inventario de estaciones (sensor de nivel de cada una): engine/euskalmet_stations.json,
generado con scripts/euskalmet_inventory.py desde la API real.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from connectors.base import (
    QUALITY_MISSING, QUALITY_OK, QUALITY_SUSPECT, RateLimitedError, Reading, SourceFormatError,
    SourceUnavailableError,
)
from connectors.common import number
from connectors.euskalmet_auth import build_jwt
from connectors.http import DEFAULT_USER_AGENT, PoliteHttpClient
from engine.validation import violations

SOURCE = "euskalmet"
BASE = "https://api.euskadi.eus/euskalmet"
USER_AGENT = DEFAULT_USER_AGENT
INVENTORY = Path(__file__).resolve().parent.parent / "engine" / "euskalmet_stations.json"
SLOT = timedelta(minutes=10)
_RANGE = re.compile(r"^Date:\((\d+)\.\.(\d+)\)$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def auth_headers(env: Mapping[str, str] = os.environ) -> dict[str, str]:
    """Cabecera Authorization. En producción se firma un JWT nuevo con la clave privada;
    EUSKALMET_JWT sirve para un token ya generado (pruebas). Sin credenciales: SIN DATOS."""
    key, email = env.get("EUSKALMET_PRIVATE_KEY"), env.get("EUSKALMET_EMAIL")
    if key and email:
        return {"Authorization": f"Bearer {build_jwt(key, email)}"}
    token = (env.get("EUSKALMET_JWT") or "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    raise SourceUnavailableError("euskalmet: faltan credenciales (EUSKALMET_PRIVATE_KEY y EUSKALMET_EMAIL)")


def load_inventory(path: Path = INVENTORY) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["stations"]


def hour_path(station: Mapping[str, Any], hour: datetime) -> str:
    return (f"/readings/forStation/{station['id']}/{station['level_sensor']}/measures/measuresForWater/"
            f"{station['level_measure']}/at/{hour:%Y/%m/%d/%H}")


def latest_slot(raw: bytes) -> tuple[Optional[datetime], Optional[float], bool]:
    """(inicio del último tramo con dato, valor, ilegible) de una hora de lecturas."""
    try:
        payload = json.loads(raw.decode("iso-8859-1"))
    except ValueError as exc:
        raise SourceFormatError(f"euskalmet: la lectura no es JSON ({exc})") from exc
    match = _RANGE.match(str(payload.get("dateRange", ""))) if isinstance(payload, dict) else None
    values, slots = (payload.get("values"), payload.get("slots")) if isinstance(payload, dict) else (None, None)
    if match is None or not isinstance(values, list) or not isinstance(slots, list) or len(values) != len(slots):
        raise SourceFormatError("euskalmet: la lectura no trae dateRange/slots/values con el formato verificado")
    start = datetime.fromtimestamp(int(match.group(1)) / 1000, timezone.utc)
    unreadable = False
    for index in range(len(values) - 1, -1, -1):
        value, bad = number(values[index])
        unreadable = unreadable or bad
        if value is not None:
            return start + index * SLOT, value, unreadable
    return None, None, unreadable


def parse(inventory: list[dict[str, Any]], payloads: Mapping[str, list[bytes]], fetched_at_utc: datetime) -> list[Reading]:
    """`payloads[id]`: horas de lecturas de la estación, de la más reciente a la más antigua."""
    readings = []
    for station in inventory:
        ts, value, unreadable = None, None, False
        for raw in payloads.get(station["id"], []):
            ts, value, bad = latest_slot(raw)
            unreadable = unreadable or bad
            if value is not None:
                break
        reading = Reading(
            station_id=f"{SOURCE}:{station['id']}", source=SOURCE, name=station["name"],
            lat=station["lat"], lon=station["lon"], river=None,
            flow_m3s=None, level_m=value, rain_1h_mm=None, rain_24h_mm=None, reservoir_pct=None, reservoir_hm3=None,
            thresholds=None, timestamp_utc=ts, fetched_at_utc=fetched_at_utc,
            quality=QUALITY_OK if value is not None else QUALITY_MISSING,
        )
        if unreadable or violations(reading, fetched_at_utc):
            reading.quality = QUALITY_SUSPECT
        readings.append(reading)
    return readings


class EuskalmetConnector:
    source = SOURCE

    def __init__(self, client: Optional[PoliteHttpClient] = None, inventory: Optional[list[dict[str, Any]]] = None,
                 now=_utcnow, env: Mapping[str, str] = os.environ) -> None:
        self.client = client or PoliteHttpClient()
        self.inventory = inventory if inventory is not None else load_inventory()
        self._now = now
        self.env = env

    def fetch(self) -> list[Reading]:
        headers = auth_headers(self.env)
        hour = self._now().astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        payloads: dict[str, list[bytes]] = {}
        fetched, failures = [], []
        for station in self.inventory:
            for h in (hour, hour - timedelta(hours=1)):  # la hora anterior solo si la actual aún no tiene dato
                try:
                    result = self.client.request("GET", BASE + hour_path(station, h), headers=headers)
                except RateLimitedError:
                    raise
                except SourceUnavailableError as exc:
                    failures.append(str(exc))
                    continue
                payloads.setdefault(station["id"], []).append(result.body)
                fetched.append(result.fetched_at_utc)
                if latest_slot(result.body)[1] is not None:
                    break
        if not payloads:
            raise SourceUnavailableError(f"euskalmet: ninguna estación respondió ({failures[:1]})")
        return parse(self.inventory, payloads, min(fetched))
