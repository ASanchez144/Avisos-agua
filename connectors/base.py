"""Esquema común de lectura y errores de conector.

Todo conector devuelve una lista de `Reading`. Ningún conector corrige ni
recorta valores: si algo no es plausible, la lectura sale con quality=SUSPECT.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

QUALITY_OK = "OK"
QUALITY_SUSPECT = "SUSPECT"
QUALITY_MISSING = "MISSING"


class ConnectorError(Exception):
    """Fallo de una fuente. El sistema debe mostrar SIN_DATOS."""


class SourceUnavailableError(ConnectorError):
    """Timeout, error de red o HTTP no-2xx."""


class SourceFormatError(ConnectorError):
    """La fuente respondió, pero no con el formato verificado en la Fase 0."""


class RateLimitedError(ConnectorError):
    """Límite de 1 petición/15 min por recurso: esta vuelta no se pide (no es un fallo)."""


class RobotsDisallowedError(ConnectorError):
    """robots.txt de la fuente no permite pedir ese recurso."""


def iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_utc(text: Optional[str]) -> Optional[datetime]:
    if text is None:
        return None
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@dataclass
class Reading:
    station_id: str
    source: str
    name: str
    lat: Optional[float]
    lon: Optional[float]
    river: Optional[str]
    flow_m3s: Optional[float]
    level_m: Optional[float]
    rain_1h_mm: Optional[float]
    rain_24h_mm: Optional[float]
    reservoir_pct: Optional[float]
    reservoir_hm3: Optional[float]
    # {"yellow", "orange", "red"} (cada uno puede ser None) + "variable":
    # campo del esquema al que se aplican. None = la fuente no publica umbral.
    thresholds: Optional[dict[str, Any]]
    timestamp_utc: Optional[datetime]
    fetched_at_utc: datetime
    quality: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "station_id": self.station_id,
            "source": self.source,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "river": self.river,
            "flow_m3s": self.flow_m3s,
            "level_m": self.level_m,
            "rain_1h_mm": self.rain_1h_mm,
            "rain_24h_mm": self.rain_24h_mm,
            "reservoir_pct": self.reservoir_pct,
            "reservoir_hm3": self.reservoir_hm3,
            "thresholds": dict(self.thresholds) if self.thresholds else None,
            "timestamp_utc": iso_utc(self.timestamp_utc),
            "fetched_at_utc": iso_utc(self.fetched_at_utc),
            "quality": self.quality,
        }


class Connector(Protocol):
    source: str

    def fetch(self) -> list[Reading]:
        """Devuelve lecturas con el esquema común o lanza ConnectorError."""
        ...
