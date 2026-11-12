"""Cámaras oficiales de la Confederación Hidrográfica del Cantábrico en sus estaciones de aforo.

Verificado el 2026-11-12 (visor oficial https://visor.saichcantabrico.es/, pestaña "Cámaras"):
  POST /wp-admin/admin-ajax.php  action=peticion_cincominutal&tipo=camaras   -> GeoJSON con 147 cámaras
  POST /wp-admin/admin-ajax.php  action=get_camera_image&code=<Cod_Roea>     -> {"url": ".../AAAAMMDDHHMM.jpg", "fecha": ISO}
robots.txt permite /wp-admin/admin-ajax.php. Las imágenes enfocan el cauce y la regla de nivel
(revisado a ojo: 1424 Eo, 1383 Narcea). Solo se muestran: no se descargan, no se guardan, no se analizan.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from connectors.base import ConnectorError, SourceFormatError, iso_utc
from connectors.common import number
from connectors.http import PoliteHttpClient

URL = "https://visor.saichcantabrico.es/wp-admin/admin-ajax.php"
ORIGIN = "https://visor.saichcantabrico.es/"
IMAGE_HOST = "visor.saichcantabrico.es"
PREFIX = "saih_cantabrico:"
LIST_CACHE = timedelta(hours=6)       # la lista de cámaras casi no cambia
CACHE = timedelta(minutes=15)          # 1 petición por cámara cada 15 min
STALE_AFTER = timedelta(minutes=120)   # las fotos se renuevan cada 20-60 min según la estación
SOURCE_LABEL = "Cámara oficial de la Confederación Hidrográfica del Cantábrico en la estación de aforo"


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8").strip())
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceFormatError(f"saih_cantabrico cámaras: respuesta no JSON ({exc})") from exc


def parse_camera_list(raw: bytes) -> dict[str, dict[str, Any]]:
    payload = _json(raw)
    feats = (payload.get("data") or {}).get("features") if isinstance(payload, dict) else None
    if not isinstance(feats, list) or not feats:
        raise SourceFormatError("saih_cantabrico cámaras: lista vacía o con otro formato")
    out = {}
    for f in feats:
        p = f.get("properties") or {}
        code = str(p.get("codigo_general") or p.get("Cod_Roea") or "").strip()
        if code:
            out[PREFIX + code] = {"code": str(p.get("Cod_Roea") or code), "name": p.get("nombre_camara"),
                                  "lat": number(p.get("lat"))[0], "lon": number(p.get("lon"))[0]}
    return out


def parse_camera_image(raw: bytes) -> Optional[dict[str, Any]]:
    payload = _json(raw)
    if not isinstance(payload, dict) or "success" not in payload:
        raise SourceFormatError("saih_cantabrico cámaras: falta success")
    if payload["success"] is not True:
        return None  # p. ej. "No folder for 9999": la estación no tiene cámara
    data = payload.get("data") or {}
    url, fecha = data.get("url"), data.get("fecha")
    if not url or urlsplit(url).hostname != IMAGE_HOST or not urlsplit(url).path.endswith(".jpg"):
        raise SourceFormatError("saih_cantabrico cámaras: URL de imagen inesperada")
    try:
        taken = datetime.fromisoformat(fecha).astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise SourceFormatError("saih_cantabrico cámaras: fecha ilegible") from exc
    return {"url": url, "taken_at": taken}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SaiCameraService:
    def __init__(self, db: Any, client: Optional[PoliteHttpClient] = None, now: Callable[[], datetime] = _utcnow) -> None:
        self.db, self.client, self._now = db, client or PoliteHttpClient(min_interval=CACHE, now=now), now

    def _fetch(self, code: str) -> dict[str, Any]:
        cached = self.db.camera_cache_get(code) if hasattr(self.db, "camera_cache_get") else None
        if cached and self._now() - cached[0] < CACHE:
            return cached[1]
        try:
            img = parse_camera_image(self.client.request("POST", URL, data={"action": "get_camera_image", "code": code}).body)
            payload = {"has_camera": img is not None, "url": img and img["url"], "taken_at_utc": img and iso_utc(img["taken_at"]), "error": None}
        except ConnectorError as exc:
            payload = {"has_camera": True, "url": None, "taken_at_utc": None, "error": f"{type(exc).__name__}"}
        if hasattr(self.db, "camera_cache_put"):
            self.db.camera_cache_put(code, payload, self._now())
        return payload

    def station_ids(self) -> set[str]:
        """Estaciones del Cantábrico que tienen cámara (lista oficial, 1 petición cada 6 h)."""
        cached = self.db.camera_cache_get("__lista__") if hasattr(self.db, "camera_cache_get") else None
        if cached and self._now() - cached[0] < LIST_CACHE:
            return set(cached[1]["ids"])
        try:
            raw = self.client.request("POST", URL, data={"action": "peticion_cincominutal", "tipo": "camaras"}).body
            ids = sorted(parse_camera_list(raw))
        except ConnectorError:
            return set(cached[1]["ids"]) if cached else set()
        if hasattr(self.db, "camera_cache_put"):
            self.db.camera_cache_put("__lista__", {"ids": ids}, self._now())
        return set(ids)

    def camera(self, station_id: str) -> Optional[dict[str, Any]]:
        if not station_id.startswith(PREFIX):
            return None
        info = self._fetch(station_id[len(PREFIX):])
        if not info["has_camera"]:
            return None
        base = {"id": station_id[len(PREFIX):], "kind": "aforo", "source_label": SOURCE_LABEL, "origin_url": ORIGIN,
                "distance_km": 0.0, "focus_verified": True, "verified_by": SOURCE_LABEL, "refresh_seconds": 120}
        checked = iso_utc(self._now())
        if info["url"] is None:
            return {**base, "image_url": None, "status": {"status": "SIN_SENAL", "message": "Cámara sin señal: la fuente no responde",
                                                         "checked_at_utc": checked, "last_modified_utc": None, "age_minutes": None}}
        taken = datetime.strptime(info["taken_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        age = self._now() - taken
        minutes = max(0, int(age.total_seconds() // 60))
        ok = timedelta(minutes=-5) <= age <= STALE_AFTER
        status = {"status": "OK" if ok else "SIN_SENAL",
                  "message": None if ok else f"Cámara sin señal: la última imagen tiene {minutes} min",
                  "checked_at_utc": checked, "last_modified_utc": info["taken_at_utc"], "age_minutes": minutes}
        return {**base, "image_url": info["url"], "status": status}
