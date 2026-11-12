"""scripts/probe_sources.py con una sesión simulada (sin red)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import requests

SPEC = importlib.util.spec_from_file_location("probe_sources", Path(__file__).resolve().parent.parent / "scripts" / "probe_sources.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

HOME = '<html><a href="/tabla-aforos">Tabla de aforos</a><a href="/aviso-legal">Aviso</a><a href="https://otro.test/aforo">Fuera</a><a href="/x.css">css</a></html>' + "x" * 600


class Falsa:
    """Sesión falsa: devuelve respuestas prefabricadas por URL."""

    def __init__(self, routes):
        self.routes, self.headers, self.calls = routes, {}, []

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def request(self, method, url, data=None, timeout=None):
        self.calls.append((method, url))
        r = self.routes.get(url)
        if isinstance(r, Exception):
            raise r
        if r is None:
            r = (404, "text/html", b"nada")
        status, ctype, body = r
        resp = requests.Response()
        resp.status_code, resp._content = status, body
        resp.headers["Content-Type"] = ctype
        resp.request = requests.Request(method, url).prepare()
        from datetime import timedelta
        resp.elapsed = timedelta(milliseconds=120)
        return resp


def prober(tmp_path, routes):
    p = probe.Prober(session=Falsa(routes), root=tmp_path, pause=0)
    return p


def test_guarda_la_respuesta_real_con_url_y_fecha(tmp_path):
    p = prober(tmp_path, {"https://saih.chj.es/": (200, "text/html", HOME.encode())})
    report = p.run(["saih_jucar"])
    files = list((tmp_path / "tests" / "fixtures" / "saih_jucar").iterdir())
    metas = [json.loads(f.read_text()) for f in files if f.name.endswith(".meta.json")]
    assert any(m["url"] == "https://saih.chj.es/" and m["status"] == 200 and m["fetched_at_utc"] == p.stamp for m in metas)
    assert any(f.suffix == ".html" and f.read_bytes() == HOME.encode() for f in files)
    assert report["sources"]["saih_jucar"]["results"][0]["result"] == "OK"


def test_descubre_solo_enlaces_del_mismo_sitio_con_palabras_clave(tmp_path):
    routes = {"https://www.saihebro.com/": (200, "text/html", HOME.encode()),
              "https://www.saihebro.com/tabla-aforos": (200, "text/html", b"<html>" + b"y" * 500)}
    p = prober(tmp_path, routes)
    p.run(["saih_ebro"])
    pedidas = [u for _, u in p.session.calls if "robots" not in u]
    assert pedidas == ["https://www.saihebro.com/", "https://www.saihebro.com/tabla-aforos"]  # ni aviso-legal, ni otro host, ni .css


def test_respeta_robots_y_no_pide_lo_prohibido(tmp_path):
    routes = {"https://saihtajo.chtajo.es/robots.txt": (200, "text/plain", b"User-agent: *\nDisallow: /\n"),
              "https://saihtajo.chtajo.es/": (200, "text/html", HOME.encode())}
    p = prober(tmp_path, routes)
    r = p.run(["saih_tajo"])
    assert r["sources"]["saih_tajo"]["results"][0]["result"].startswith("OMITIDA")
    assert ("GET", "https://saihtajo.chtajo.es/") not in p.session.calls


def test_un_fallo_de_red_se_anota_y_no_tumba_el_resto(tmp_path):
    routes = {"https://www.saihduero.es/": requests.ConnectTimeout("timeout"),
              "https://saih.chminosil.es/": (200, "text/html", HOME.encode())}
    r = prober(tmp_path, routes).run(["saih_duero", "saih_minosil"])
    assert r["sources"]["saih_duero"]["results"][0]["result"].startswith("FALLO DE RED")
    assert r["sources"]["saih_minosil"]["ok"] >= 1


def test_un_rechazo_del_servidor_se_anota_sin_insistir(tmp_path):
    p = prober(tmp_path, {"https://saih.chj.es/": (403, "text/html", b"<html>Request Rejected</html>")})
    r = p.run(["saih_jucar"])
    assert r["sources"]["saih_jucar"]["results"][0]["result"] == "HTTP 403"
    assert [u for _, u in p.session.calls].count("https://saih.chj.es/") == 1


def test_respuesta_grande_se_comprime(tmp_path):
    p = prober(tmp_path, {"https://nap.dgt.es/datex2/v3/dgt/DevicePublication/camaras_datex2_v37.xml": (200, "text/xml", b"<a/>" * 400_000)})
    p.run(["dgt"])
    assert any(f.name.endswith(".xml.gz") for f in (tmp_path / "tests" / "fixtures" / "dgt").iterdir())


def test_el_script_no_usa_cookies_ni_claves():
    text = (Path(probe.__file__)).read_text()
    assert "api_key" not in text.lower() and "cookie" not in text.lower().replace("sin cookies", "")


def test_fuentes_desconocidas_dan_error(capsys):
    assert probe.main(["no_existe"]) == 2
