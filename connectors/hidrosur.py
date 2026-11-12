"""Conector de la Red Hidrosur (SAIH de las Cuencas Mediterráneas Andaluzas, Junta de Andalucía).

Fuentes verificadas con peticiones reales el 2026-11-12 (robots.txt sin restricciones):
- GET https://www.redhidrosurmedioambiente.es/saih/resumen/rios
  Tabla oficial "Resumen niveles de ríos": Número · Nombre · Nivel medio (m) · Caudal medio (m³/s) · …
  y una sola hora para toda la tabla: "Datos actualizados a: DD-MM-AAAA HH:MM:SS" (hora local peninsular).
- GET https://www.redhidrosurmedioambiente.es/saih/assets/visorSAIH/capas/Aforos.json
  Capa del visor oficial: código de estación (COD_), Latitud, Longitud y Río.

Decisiones:
- Estación = fila de la tabla; se une a la capa por Número == COD_. Sin coordenadas en la capa → se omite
  (no se puede situar en el mapa); el número de omitidas queda en docs/SOURCES_REPORT.md.
- "n/d" o vacío → sin dato (None). Nunca se rellena.
- Estación repetida en la tabla con valores distintos (visto: 86 Serón, "0,00" y "n/d") → una lectura SUSPECT.
- Umbrales de nivel: campos Aviso/Prealerta/Alerta de la capa. Verificados con la gráfica oficial de cada estación
  (/saih/mapa/tiempo/real/grafica/<código>): dibuja "Nivel 1/2/3" con esos mismos valores en el eje del nivel (m.),
  y la tabla oficial colorea Nivel 1 amarillo, Nivel 2 naranja, Nivel 3 rojo. 0/0/0 = sin umbral → None.
- La tabla da medias horarias con la hora de la tabla; no hay lluvia en esta tabla.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from connectors.base import QUALITY_MISSING, QUALITY_OK, QUALITY_SUSPECT, Reading, SourceFormatError
from connectors.common import decode, number
from connectors.http import PoliteHttpClient
from engine.validation import violations

SOURCE = "hidrosur"
BASE = "https://www.redhidrosurmedioambiente.es/saih/"
TABLE = BASE + "resumen/rios"
LAYER = BASE + "assets/visorSAIH/capas/Aforos.json"
MADRID = ZoneInfo("Europe/Madrid")
_UPDATED = re.compile(r"Datos actualizados a:\s*(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_NO_DATA = {"", "-", "n/d"}


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _value(text: str) -> tuple[Optional[float], bool]:
    return (None, False) if text.lower() in _NO_DATA else number(text)


def parse_table(raw: bytes) -> tuple[datetime, list[dict[str, Any]]]:
    page = decode(raw)
    stamp = _UPDATED.search(page)
    start = page.find("resumen-rios-table")
    if stamp is None or start < 0:
        raise SourceFormatError("hidrosur: la tabla de ríos no tiene el formato verificado")
    ts = datetime.strptime(stamp.group(1), "%d-%m-%Y %H:%M:%S").replace(tzinfo=MADRID).astimezone(timezone.utc)
    rows = []
    for row in _ROW.findall(page[start:page.find("</table>", start)]):
        cells = [_text(c) for c in _CELL.findall(row)]
        if len(cells) < 4 or not cells[0].isdigit():
            continue  # cabecera
        rows.append({"code": cells[0], "name": cells[1], "level": cells[2], "flow": cells[3]})
    if not rows:
        raise SourceFormatError("hidrosur: la tabla de ríos está vacía")
    return ts, rows


def parse_layer(raw: bytes) -> dict[str, dict[str, Any]]:
    try:
        features = json.loads(raw)["features"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceFormatError(f"hidrosur: la capa de aforos no tiene el formato verificado ({exc})") from exc
    out = {}
    for f in features:
        props = f.get("properties") or {}
        code = str(props.get("COD_", "")).strip()
        if code and code != "0":
            out[code] = props
    return out


def _thresholds(place: dict[str, Any]) -> tuple[Optional[dict[str, Any]], bool]:
    values = {}
    bad = False
    for colour, key in (("yellow", "Aviso"), ("orange", "Prealerta"), ("red", "Alerta")):
        value, unreadable = number(place.get(key))
        bad = bad or unreadable
        values[colour] = value
    if all(v in (None, 0.0) for v in values.values()):
        return None, bad  # la capa pone 0 en las estaciones sin umbral
    return {**values, "variable": "level_m"}, bad


def parse(table: bytes, layer: bytes, fetched_at_utc: datetime) -> list[Reading]:
    ts, rows = parse_table(table)
    places = parse_layer(layer)
    readings = []
    seen: dict[str, Reading] = {}
    for row in rows:
        place = places.get(row["code"])
        if place is None:
            continue
        if row["code"] in seen:
            # La fuente repite la estación con otros valores: no se elige ninguno como bueno.
            first = seen[row["code"]]
            if (_value(row["level"])[0], _value(row["flow"])[0]) != (first.level_m, first.flow_m3s):
                first.quality = QUALITY_SUSPECT
            continue
        level, bad_level = _value(row["level"])
        flow, bad_flow = _value(row["flow"])
        lat, _ = number(place.get("Latitud"))
        lon, _ = number(place.get("Longitud"))
        river = str(place.get("Río") or "").strip() or None
        has_value = level is not None or flow is not None
        thresholds, bad_thresholds = _thresholds(place)
        reading = Reading(
            station_id=f"{SOURCE}:{row['code']}", source=SOURCE, name=row["name"], lat=lat, lon=lon, river=river,
            flow_m3s=flow, level_m=level, rain_1h_mm=None, rain_24h_mm=None, reservoir_pct=None, reservoir_hm3=None,
            thresholds=thresholds, timestamp_utc=ts if has_value else None, fetched_at_utc=fetched_at_utc,
            quality=QUALITY_OK if has_value else QUALITY_MISSING,
        )
        if bad_level or bad_flow or bad_thresholds or violations(reading, fetched_at_utc):
            reading.quality = QUALITY_SUSPECT
        seen[row["code"]] = reading
        readings.append(reading)
    if not readings:
        raise SourceFormatError("hidrosur: ninguna estación de la tabla tiene coordenadas en la capa")
    return readings


class HidrosurConnector:
    source = SOURCE

    def __init__(self, client: Optional[PoliteHttpClient] = None) -> None:
        self.client = client or PoliteHttpClient()

    def fetch(self) -> list[Reading]:
        table = self.client.request("GET", TABLE)
        layer = self.client.request("GET", LAYER)
        return parse(table.body, layer.body, table.fetched_at_utc)
