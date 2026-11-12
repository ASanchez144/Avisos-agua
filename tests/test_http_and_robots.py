"""Cliente HTTP responsable: robots.txt (RFC 9309), caché y límite por recurso."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from connectors.base import RobotsDisallowedError, SourceUnavailableError
from connectors.http import PoliteHttpClient
from connectors.robots import is_allowed

FIX = Path(__file__).resolve().parent / "fixtures"
UA = "HidroRed/0.1"


def test_robots_real_cantabrico_permite_admin_ajax():
    txt = (FIX / "saih_cantabrico" / "robots.txt").read_text()
    assert is_allowed(txt, UA, "/wp-admin/admin-ajax.php") is True
    assert is_allowed(txt, UA, "/wp-admin/options.php") is False
    assert is_allowed(txt, UA, "/informe.pdf") is False
    assert is_allowed(txt, UA, "/") is True


def test_robots_real_tajo_bloquea_php_final_y_w():
    txt = (FIX / "saih_tajo" / "robots.txt").read_text()
    assert is_allowed(txt, UA, "/manifest.php") is False
    assert is_allowed(txt, UA, "/?w=get-menu") is False
    assert is_allowed(txt, UA, "/que-es-saih") is True


def test_robots_grupo_especifico_gana_al_comodin():
    txt = "User-agent: *\nDisallow:\n\nUser-agent: hidrored\nDisallow: /privado\n"
    assert is_allowed(txt, "HidroRed/0.1 (x)", "/privado/a") is False
    assert is_allowed(txt, "OtroBot/1.0", "/privado/a") is True


def test_robots_vacio_permite_todo():
    assert is_allowed("", UA, "/cualquier/cosa") is True


class Reloj:
    def __init__(self):
        self.t = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.t

    def avanza(self, **kw):
        self.t += timedelta(**kw)


def _contador(robots=b"User-agent: *\nDisallow:\n", status=200, body=b"hola"):
    llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append((request.method, request.url.path))
        if request.url.path == "/robots.txt":
            if robots is None:
                return httpx.Response(404)
            return httpx.Response(200, content=robots)
        return httpx.Response(status, content=body)

    return llamadas, handler


def test_no_repite_peticion_al_mismo_recurso_antes_de_15_min():
    reloj = Reloj()
    llamadas, handler = _contador()
    c = PoliteHttpClient(transport=httpx.MockTransport(handler), now=reloj)
    r1 = c.request("GET", "https://ejemplo.test/datos")
    reloj.avanza(minutes=14)
    r2 = c.request("GET", "https://ejemplo.test/datos")
    assert llamadas.count(("GET", "/datos")) == 1
    assert r2.from_cache is True and r1.from_cache is False
    assert r2.body == r1.body
    assert r2.fetched_at_utc == r1.fetched_at_utc  # no finge que el dato es nuevo


def test_pasados_15_min_vuelve_a_pedir():
    reloj = Reloj()
    llamadas, handler = _contador()
    c = PoliteHttpClient(transport=httpx.MockTransport(handler), now=reloj)
    c.request("GET", "https://ejemplo.test/datos")
    reloj.avanza(minutes=15, seconds=1)
    r = c.request("GET", "https://ejemplo.test/datos")
    assert llamadas.count(("GET", "/datos")) == 2
    assert r.from_cache is False


def test_robots_se_descarga_una_sola_vez_por_host():
    reloj = Reloj()
    llamadas, handler = _contador()
    c = PoliteHttpClient(transport=httpx.MockTransport(handler), now=reloj)
    c.request("GET", "https://ejemplo.test/a")
    c.request("GET", "https://ejemplo.test/b")
    assert llamadas.count(("GET", "/robots.txt")) == 1


def test_ruta_prohibida_por_robots_no_se_pide():
    llamadas, handler = _contador(robots=b"User-agent: *\nDisallow: /datos\n")
    c = PoliteHttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RobotsDisallowedError):
        c.request("GET", "https://ejemplo.test/datos")
    assert ("GET", "/datos") not in llamadas


def test_robots_404_se_interpreta_como_sin_restricciones():
    llamadas, handler = _contador(robots=None)
    c = PoliteHttpClient(transport=httpx.MockTransport(handler))
    assert c.request("GET", "https://ejemplo.test/datos").body == b"hola"


def test_error_http_no_se_cachea_como_dato():
    reloj = Reloj()
    llamadas, handler = _contador(status=502)
    c = PoliteHttpClient(transport=httpx.MockTransport(handler), now=reloj)
    with pytest.raises(SourceUnavailableError):
        c.request("GET", "https://ejemplo.test/datos")
    # dentro de la ventana no se reintenta, pero tampoco se devuelve un dato falso
    with pytest.raises(SourceUnavailableError):
        c.request("GET", "https://ejemplo.test/datos")
    assert llamadas.count(("GET", "/datos")) == 1


def test_el_jitter_del_planificador_no_deja_un_ciclo_con_dato_cacheado():
    """El planificador dispara cada 15 min exactos; si un disparo llega unos
    milisegundos antes, no debe perderse el ciclo (el dato quedaría 30 min viejo)."""
    reloj = Reloj()
    llamadas, handler = _contador()
    c = PoliteHttpClient(transport=httpx.MockTransport(handler), now=reloj)
    c.request("GET", "https://ejemplo.test/datos")
    reloj.avanza(minutes=14, seconds=59, milliseconds=500)
    assert c.request("GET", "https://ejemplo.test/datos").from_cache is False
    assert llamadas.count(("GET", "/datos")) == 2


def test_la_holgura_de_jitter_es_de_solo_dos_segundos():
    reloj = Reloj()
    llamadas, handler = _contador()
    c = PoliteHttpClient(transport=httpx.MockTransport(handler), now=reloj)
    c.request("GET", "https://ejemplo.test/datos")
    reloj.avanza(minutes=14, seconds=57)
    assert c.request("GET", "https://ejemplo.test/datos").from_cache is True
    assert llamadas.count(("GET", "/datos")) == 1
