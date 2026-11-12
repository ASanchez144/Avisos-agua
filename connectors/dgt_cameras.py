"""Catálogo de cámaras de la DGT (DATEX II v3, NAP). SOLO el listado de cámaras: no hay lecturas hidrológicas.

Feed verificado (probe_sources.py): GET https://nap.dgt.es/datex2/v3/dgt/DevicePublication/camaras_datex2_v37.xml
Se usa para encontrar candidatas cerca de una estación; la imagen se enlaza directamente (hotlink),
nunca se descarga ni se guarda. No se analiza el contenido de la imagen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from connectors.base import SourceFormatError


@dataclass(frozen=True)
class Camera:
    id: str
    lat: float
    lon: float
    road: str
    km: Optional[str]
    province: str
    image_url: str


def _first(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def parse_cameras(raw: bytes) -> list[Camera]:
    try:
        xml = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceFormatError(f"dgt: el feed no es UTF-8 ({exc})") from exc
    if "DevicePublication" not in xml:
        raise SourceFormatError("dgt: el feed no es una DevicePublication de DATEX II")
    cameras = []
    for block in re.findall(r"<ns2:device .*?</ns2:device>", xml, re.S):
        if _first(r"<ns2:typeOfDevice>([^<]+)", block) != "camera":
            continue
        url = _first(r"<fse:deviceUrl>([^<]+)", block)
        try:
            lat, lon = float(_first(r"<loc:latitude>([-\d.]+)", block)), float(_first(r"<loc:longitude>([-\d.]+)", block))
        except ValueError:
            continue  # sin coordenadas no sirve para enlazar por cercanía
        if url:
            cameras.append(Camera(_first(r'id="(\d+)"', block), lat, lon, _first(r"<loc:roadName>([^<]+)", block),
                                  _first(r"<lse:kilometerPoint>([^<]+)", block) or None, _first(r"<lse:province>([^<]+)", block), url))
    if not cameras:
        raise SourceFormatError("dgt: ninguna cámara reconocible en el feed")
    return cameras
