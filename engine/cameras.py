"""Cámaras de la lista curada: solo se enseña una cámara si una persona ha comprobado que enfoca el cauce o el puente."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence
from urllib.parse import urlsplit

import yaml

from connectors.dgt_cameras import Camera
from engine.geo import haversine_km

ALLOWED_IMAGE_HOSTS = {"etraffic.dgt.es"}


@dataclass(frozen=True)
class CuratedCamera:
    id: str
    station_id: str
    lat: float
    lon: float
    image_url: str
    origin_url: str
    focus_verified: bool
    verified_by: str
    verified_on: str


@dataclass(frozen=True)
class CameraConfig:
    max_distance_km: float
    stale_after_minutes: int
    cameras: tuple[CuratedCamera, ...]

    def get(self, camera_id: str) -> Optional[CuratedCamera]:
        return next((c for c in self.cameras if c.id == camera_id), None)

    def for_station(self, station_id: str) -> Optional[CuratedCamera]:
        return next((c for c in self.cameras if c.station_id == station_id), None)


def load_cameras(path: str | Path) -> CameraConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    cameras = []
    for item in raw.get("cameras") or []:
        if item.get("focus_verified") is not True:
            raise ValueError(f"cámara {item.get('id')}: solo entran cámaras con focus_verified: true")
        if not str(item.get("verified_by") or "").strip():
            raise ValueError(f"cámara {item.get('id')}: falta verified_by (quién comprobó que enfoca el cauce)")
        if urlsplit(item["image_url"]).hostname not in ALLOWED_IMAGE_HOSTS:
            raise ValueError(f"cámara {item['id']}: image_url fuera de {sorted(ALLOWED_IMAGE_HOSTS)}")
        cameras.append(CuratedCamera(
            id=str(item["id"]), station_id=item["station_id"], lat=float(item["lat"]), lon=float(item["lon"]),
            image_url=item["image_url"], origin_url=item["origin_url"], focus_verified=True,
            verified_by=item["verified_by"], verified_on=str(item.get("verified_on", "")),
        ))
    return CameraConfig(float(raw.get("max_distance_km", 3.0)), int(raw.get("stale_after_minutes", 20)), tuple(cameras))


def nearby(lat: float, lon: float, cameras: Sequence[Camera], max_km: float = 3.0) -> list[tuple[float, Camera]]:
    """Cámaras candidatas a menos de `max_km`, de más cerca a más lejos. Que enfoquen el cauce NO está comprobado."""
    found = [(haversine_km(lat, lon, c.lat, c.lon), c) for c in cameras]
    return sorted(((round(d, 2), c) for d, c in found if d <= max_km), key=lambda x: x[0])
