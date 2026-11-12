"""Estado de la imagen de una cámara: solo `HEAD` (nunca se descarga la imagen) y caché de 2 minutos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Optional

import httpx

from connectors.base import iso_utc
from connectors.http import DEFAULT_USER_AGENT

CACHE = timedelta(seconds=120)  # coincide con el cache-control: max-age=120 de la DGT
SIN_SENAL = "Cámara sin señal"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CameraChecker:
    def __init__(self, stale_after_minutes: int = 20, transport: Optional[httpx.BaseTransport] = None,
                 now: Callable[[], datetime] = _utcnow) -> None:
        self.stale_after = timedelta(minutes=stale_after_minutes)
        self._now = now
        self._client = httpx.Client(headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=10, transport=transport, follow_redirects=True)
        self._cache: dict[str, tuple[datetime, dict[str, Any]]] = {}

    def status(self, url: str) -> dict[str, Any]:
        cached = self._cache.get(url)
        if cached and self._now() - cached[0] < CACHE:
            return cached[1]
        result = self._check(url)
        self._cache[url] = (self._now(), result)
        return result

    def _check(self, url: str) -> dict[str, Any]:
        checked = iso_utc(self._now())

        def bad(why: str, **extra: Any) -> dict[str, Any]:
            return {"status": "SIN_SENAL", "message": f"{SIN_SENAL}: {why}", "checked_at_utc": checked,
                    "last_modified_utc": None, "age_minutes": None, **extra}

        try:
            resp = self._client.head(url)
        except httpx.HTTPError:
            return bad("no responde")
        if resp.status_code != 200:
            return bad(f"la fuente devolvió HTTP {resp.status_code}")
        header = resp.headers.get("Last-Modified")
        if not header:
            return bad("la fuente no dice cuándo se hizo la imagen")
        try:
            modified = parsedate_to_datetime(header).astimezone(timezone.utc)
        except (TypeError, ValueError):
            return bad("fecha de la imagen ilegible")
        age = self._now() - modified
        if age < -timedelta(minutes=5):
            return bad("la fecha de la imagen no es creíble")
        minutes = max(0, int(age.total_seconds() // 60))
        info = {"checked_at_utc": checked, "last_modified_utc": iso_utc(modified), "age_minutes": minutes}
        if age > self.stale_after:
            return {"status": "SIN_SENAL", "message": f"{SIN_SENAL}: la última imagen tiene {minutes} min", **info}
        return {"status": "OK", "message": None, **info}
