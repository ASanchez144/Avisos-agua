"""Cliente HTTP responsable (regla 4 del proyecto).

- User-Agent identificable y genérico; nunca se suplanta un navegador.
- Respeta robots.txt (RFC 9309).
- Como máximo 1 petición por recurso cada 15 minutos: dentro de la ventana se
  devuelve la respuesta cacheada con su `fetched_at_utc` ORIGINAL (no se
  finge que el dato es nuevo). Un error tampoco se reintenta en la ventana.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from urllib.parse import urlencode, urlsplit

import httpx

from connectors.base import RobotsDisallowedError, SourceUnavailableError
from connectors.robots import is_allowed

DEFAULT_USER_AGENT = "HidroRed/0.1 (radar ciudadano hidrologico no oficial; scraping responsable)"
MIN_INTERVAL = timedelta(minutes=15)
ROBOTS_TTL = timedelta(hours=24)
# El planificador dispara cada 15 min exactos; un disparo puede llegar unos ms
# antes que el anterior. Sin esta holgura ese ciclo se serviría de caché y el
# dato quedaría 30 min sin renovar. No aumenta el nº de peticiones: lo fija el
# planificador (96 al día por recurso).
SCHEDULER_JITTER = timedelta(seconds=2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class HttpResult:
    body: bytes
    fetched_at_utc: datetime
    from_cache: bool = False


class PoliteHttpClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval: timedelta = MIN_INTERVAL,
        timeout_s: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.user_agent = user_agent
        self.min_interval = min_interval
        self._now = now
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_s,
            transport=transport,
            follow_redirects=True,
        )
        # clave de recurso -> (instante, HttpResult | SourceUnavailableError)
        self._last: dict[tuple[str, str, str], tuple[datetime, object]] = {}
        self._robots: dict[str, tuple[datetime, Optional[str]]] = {}

    # ------------------------------------------------------------- robots
    def _robots_txt(self, scheme: str, host: str) -> Optional[str]:
        cached = self._robots.get(host)
        if cached and self._now() - cached[0] < ROBOTS_TTL:
            return cached[1]
        url = f"{scheme}://{host}/robots.txt"
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"no se pudo leer robots.txt de {host}: {exc!r}") from exc
        if resp.status_code == 200:
            text: Optional[str] = resp.text
        elif 400 <= resp.status_code < 500:
            text = None  # sin robots.txt: no hay restricciones declaradas
        else:
            raise SourceUnavailableError(f"robots.txt de {host} devolvió HTTP {resp.status_code}")
        self._robots[host] = (self._now(), text)
        return text

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        text = self._robots_txt(parts.scheme, parts.netloc)
        if text is None:
            return
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        if not is_allowed(text, self.user_agent, path):
            raise RobotsDisallowedError(f"robots.txt de {parts.netloc} no permite {path}")

    # ------------------------------------------------------------ request
    def request(
        self, method: str, url: str, data: Optional[dict[str, str]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> HttpResult:
        key = (method.upper(), url, urlencode(data or {}))
        previous = self._last.get(key)
        if previous and self._now() - previous[0] < self.min_interval - SCHEDULER_JITTER:
            outcome = previous[1]
            if isinstance(outcome, SourceUnavailableError):
                raise SourceUnavailableError(f"{outcome} (sin reintento: límite de 1 petición/15 min)")
            assert isinstance(outcome, HttpResult)
            return replace(outcome, from_cache=True)

        started = self._now()
        self._check_robots(url)
        try:
            resp = self._client.request(method, url, data=data, headers=headers)
            if resp.status_code != 200:
                raise SourceUnavailableError(f"{method} {url} devolvió HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            error = SourceUnavailableError(f"{method} {url} falló: {exc!r}")
            self._last[key] = (started, error)
            raise error from exc
        except SourceUnavailableError as error:
            self._last[key] = (started, error)
            raise
        result = HttpResult(body=resp.content, fetched_at_utc=self._now())
        self._last[key] = (started, result)
        return result

    def close(self) -> None:
        self._client.close()
