"""Conector de AEMET OpenData.

Fuente verificada en docs/SOURCES_REPORT.md. Flujo en dos pasos: la llamada a
la API (cabecera `api_key`) devuelve un sobre JSON con la URL temporal `datos`.

Trampas reales de la API que este módulo trata como error (nunca como dato):
- sin clave: HTTP 200 con cuerpo vacío;
- clave inválida: `"estado": 401`;
- recurso con problemas: HTTP 200 con `"estado": 404` dentro del JSON.

Qué aporta al esquema común: solo rain_1h_mm (`prec`: mm en los 60 min
anteriores a `fint`, que ya viene en UTC). La API trae ~12 h por estación, así
que NO se calcula rain_24h_mm. No hay umbrales por estación.

Además: avisos CAP (Meteoalerta, con polígonos) e inventario de estaciones
(coordenadas en grados-minutos-segundos) para enlazar por cercanía.
"""
from __future__ import annotations

import io
import json
import os
import tarfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from connectors.base import (
    QUALITY_MISSING, QUALITY_OK, QUALITY_SUSPECT, Reading, SourceFormatError, SourceUnavailableError, iso_utc,
)
from connectors.common import decode, number
from connectors.http import PoliteHttpClient
from engine.geo import haversine_km
from engine.validation import violations

SOURCE = "aemet"
API = "https://opendata.aemet.es/opendata/api/"
OBSERVATIONS = API + "observacion/convencional/todas"
WARNINGS = API + "avisos_cap/ultimoelaborado/area/esp"
INVENTORY = API + "valores/climatologicos/inventarioestaciones/todasestaciones"
API_KEY_ENV = "AEMET_API_KEY"
CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def parse_envelope(raw: bytes) -> str:
    """Valida el sobre del paso 1 y devuelve la URL de `datos`."""
    if not raw.strip():
        raise SourceUnavailableError("aemet: respuesta 200 con cuerpo vacío (falta la API key)")
    try:
        payload = json.loads(decode(raw))
    except ValueError as exc:
        raise SourceFormatError(f"aemet: el sobre no es JSON ({exc})") from exc
    if not isinstance(payload, dict) or "estado" not in payload:
        raise SourceFormatError("aemet: el sobre no trae `estado`")
    if payload["estado"] != 200:
        raise SourceUnavailableError(f"aemet: estado {payload['estado']}: {payload.get('descripcion')}")
    url = payload.get("datos")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise SourceFormatError("aemet: el sobre no trae la URL de datos")
    return url


def _utc(text: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(text).replace("+0000", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _records(raw: bytes, what: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(decode(raw))
    except ValueError as exc:
        raise SourceFormatError(f"aemet: {what} no es JSON ({exc})") from exc
    if not isinstance(payload, list) or not payload:
        raise SourceFormatError(f"aemet: {what} no es una lista con datos")
    return [r for r in payload if isinstance(r, dict)]


def parse_observations(raw: bytes, fetched_at_utc: datetime) -> list[Reading]:
    latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for record in _records(raw, "la observación"):
        code, ts = record.get("idema"), _utc(record.get("fint"))
        if not code or ts is None:
            continue
        if code not in latest or ts > latest[code][0]:
            latest[code] = (ts, record)
    if not latest:
        raise SourceFormatError("aemet: ninguna estación reconocible en la observación")

    readings = []
    for code, (ts, record) in latest.items():
        rain, unreadable = number(record.get("prec"))
        lat, _ = number(record.get("lat"))
        lon, _ = number(record.get("lon"))
        reading = Reading(
            station_id=f"{SOURCE}:{code}", source=SOURCE, name=str(record.get("ubi") or code).strip(),
            lat=lat, lon=lon, river=None, flow_m3s=None, level_m=None, rain_1h_mm=rain, rain_24h_mm=None,
            reservoir_pct=None, reservoir_hm3=None, thresholds=None,
            timestamp_utc=ts if rain is not None else None, fetched_at_utc=fetched_at_utc,
            quality=QUALITY_OK if rain is not None else QUALITY_MISSING,
        )
        if unreadable or violations(reading, fetched_at_utc):
            reading.quality = QUALITY_SUSPECT
        readings.append(reading)
    return readings


# ----------------------------------------------------------------- avisos CAP

@dataclass(frozen=True)
class Warning:
    identifier: str
    sent: Optional[datetime]
    event: str
    level: str            # verde | amarillo | naranja | rojo (parámetro "AEMET-Meteoalerta nivel")
    phenomenon: str       # p. ej. "Lluvias"
    severity: str
    onset: Optional[datetime]
    expires: Optional[datetime]
    headline: str
    description: str
    probability: Optional[str]
    area: str
    zone: Optional[str]
    polygons: list[list[tuple[float, float]]]  # [(lat, lon), ...]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in ("sent", "onset", "expires"):
            d[key] = iso_utc(d[key])
        return d


def _text(node: Optional[ET.Element], path: str) -> str:
    found = node.find(path, CAP_NS) if node is not None else None
    return (found.text or "").strip() if found is not None else ""


def _named(info: ET.Element, tag: str, name: str) -> Optional[str]:
    for node in info.iter(f"{{{CAP_NS['cap']}}}{tag}"):
        if _text(node, "cap:valueName") == name:
            return _text(node, "cap:value") or None
    return None


def _polygon(text: str) -> list[tuple[float, float]]:
    points = []
    for pair in text.split():
        lat, _, lon = pair.partition(",")
        points.append((float(lat), float(lon)))
    return points


def _warning(xml: bytes) -> Optional[Warning]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    infos = root.findall("cap:info", CAP_NS)
    info = next((i for i in infos if _text(i, "cap:language").lower().startswith("es")), infos[0] if infos else None)
    level = _named(info, "parameter", "AEMET-Meteoalerta nivel") if info is not None else None
    if info is None or not level:
        return None
    area = info.find("cap:area", CAP_NS)
    try:
        polygons = [_polygon(p.text or "") for p in info.iter(f"{{{CAP_NS['cap']}}}polygon") if (p.text or "").strip()]
    except ValueError:
        return None
    phenomenon = (_named(info, "eventCode", "AEMET-Meteoalerta fenomeno") or "").partition(";")[2]
    return Warning(
        identifier=_text(root, "cap:identifier"), sent=_utc(_text(root, "cap:sent")), event=_text(info, "cap:event"),
        level=level.lower(), phenomenon=phenomenon, severity=_text(info, "cap:severity"),
        onset=_utc(_text(info, "cap:onset")), expires=_utc(_text(info, "cap:expires")),
        headline=_text(info, "cap:headline"), description=_text(info, "cap:description"),
        probability=_named(info, "parameter", "AEMET-Meteoalerta probabilidad"),
        area=_text(area, "cap:areaDesc"), zone=_named(info, "geocode", "AEMET-Meteoalerta zona"), polygons=polygons,
    )


def parse_warnings(raw: bytes) -> list[Warning]:
    """Lee el tar (comprimido o no) de ficheros CAP v1.2. Un XML ilegible se omite."""
    try:
        tar = tarfile.open(fileobj=io.BytesIO(raw), mode="r:*")
    except tarfile.TarError as exc:
        raise SourceFormatError(f"aemet: los avisos no son un tar ({exc})") from exc
    warnings = []
    with tar:
        for member in tar:
            handle = tar.extractfile(member) if member.isfile() else None  # se lee en memoria, sin extraer a disco
            warning = _warning(handle.read()) if handle else None
            if warning is not None:
                warnings.append(warning)
    return warnings


# ----------------------------------------------------------------- inventario

def _dms(text: Any) -> Optional[float]:
    s = str(text or "").strip().upper()
    if len(s) < 7 or s[-1] not in "NSEW" or not s[:-1].isdigit():
        return None
    value = int(s[:-5]) + int(s[-5:-3]) / 60 + int(s[-3:-1]) / 3600
    return -value if s[-1] in "SW" else value


def parse_inventory(raw: bytes) -> list[dict[str, Any]]:
    stations = []
    for record in _records(raw, "el inventario"):
        lat, lon = _dms(record.get("latitud")), _dms(record.get("longitud"))
        if record.get("indicativo") and lat is not None and lon is not None:
            stations.append({
                "indicativo": record["indicativo"], "nombre": record.get("nombre"),
                "provincia": record.get("provincia"), "altitud": number(record.get("altitud"))[0],
                "lat": lat, "lon": lon,
            })
    if not stations:
        raise SourceFormatError("aemet: ninguna estación reconocible en el inventario")
    return stations


def nearest_station(
    lat: float, lon: float, stations: list[dict[str, Any]], max_km: Optional[float] = None
) -> Optional[dict[str, Any]]:
    """Estación del inventario más cercana a un punto, con su distancia en km."""
    best = min(stations, key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]), default=None)
    if best is None:
        return None
    distance = haversine_km(lat, lon, best["lat"], best["lon"])
    if max_km is not None and distance > max_km:
        return None
    return {**best, "distance_km": round(distance, 2)}


# ------------------------------------------------------------------- conector

class AemetConnector:
    source = SOURCE

    def __init__(self, client: Optional[PoliteHttpClient] = None) -> None:
        self.client = client or PoliteHttpClient()

    def _two_step(self, url: str):
        key = os.environ.get(API_KEY_ENV)
        if not key:
            raise SourceUnavailableError(f"aemet: falta la variable {API_KEY_ENV}")
        envelope = self.client.request("GET", url, headers={"api_key": key})
        return self.client.request("GET", parse_envelope(envelope.body))  # la URL de datos no lleva clave

    def fetch(self) -> list[Reading]:
        result = self._two_step(OBSERVATIONS)
        return parse_observations(result.body, result.fetched_at_utc)

    def fetch_warnings(self) -> list[Warning]:
        return parse_warnings(self._two_step(WARNINGS).body)

    def fetch_inventory(self) -> list[dict[str, Any]]:
        return parse_inventory(self._two_step(INVENTORY).body)
