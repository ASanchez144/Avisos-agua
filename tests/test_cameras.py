"""Cámaras solo para ver: feed DATEX II real de la DGT, lista curada, estado de la imagen y endpoints."""
from __future__ import annotations

import glob
import gzip
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.cameras import CameraChecker
from backend.db import Database
from connectors.base import Reading, SourceFormatError
from connectors.dgt_cameras import parse_cameras
from engine.cameras import CameraConfig, load_cameras, nearby

ROOT = Path(__file__).resolve().parent.parent
FEED = gzip.open(sorted(glob.glob(str(ROOT / "tests/fixtures/dgt/probe_*camaras*.xml.gz")))[-1]).read()
NOW = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)


def test_feed_real_de_la_dgt_1975_camaras():
    cams = parse_cameras(FEED)
    assert len(cams) == 1975
    c = next(x for x in cams if x.id == "176130")
    assert (c.lat, c.lon, c.road) == (42.2624, -3.9403, "A-62") and c.province == "BURGOS"
    assert c.image_url == "https://etraffic.dgt.es/camarasEtraffic/176130.jpg"
    assert all(x.image_url.startswith("https://etraffic.dgt.es/") for x in cams)


@pytest.mark.parametrize("cuerpo", [b"", b"<html/>", b"<d2:payload/>"])
def test_feed_inesperado_da_error_de_formato(cuerpo):
    with pytest.raises(SourceFormatError):
        parse_cameras(cuerpo)


def test_candidatas_a_menos_de_3_km_con_su_distancia():
    cams = parse_cameras(FEED)
    cerca = nearby(39.47537, -0.5818, cams, max_km=3)         # aforo de la Rambla del Poyo
    assert cerca[0][1].id == "112" and cerca[0][0] == pytest.approx(0.69, abs=0.05)
    assert all(d <= 3 for d, _ in cerca) and cerca == sorted(cerca, key=lambda x: x[0])
    assert nearby(43.1795, -7.1995, cams, max_km=3) == []     # Eo en Ribera de Piquín: nada cerca


def test_la_lista_curada_del_repositorio_esta_vacia_porque_ninguna_camara_enfoca_el_cauce():
    cfg = load_cameras(ROOT / "engine" / "cameras.yaml")
    assert cfg.cameras == () and cfg.max_distance_km == 3.0 and cfg.stale_after_minutes > 0


def yaml_text(extra=""):
    return f"""
max_distance_km: 3
stale_after_minutes: 20
cameras:
  - id: "112"
    station_id: "saih_jucar:rambla_poyo"
    lat: 39.4800
    lon: -0.5818
    image_url: https://etraffic.dgt.es/camarasEtraffic/112.jpg
    origin_url: https://infocar.dgt.es/etraffic/
    focus_verified: true
    verified_by: "revisión visual"
    verified_on: "2026-11-12"
{extra}"""


def cargar(tmp_path, text):
    p = tmp_path / "c.yaml"
    p.write_text(text)
    return load_cameras(p)


def test_carga_una_camara_curada(tmp_path):
    cfg = cargar(tmp_path, yaml_text())
    assert cfg.cameras[0].station_id == "saih_jucar:rambla_poyo" and cfg.cameras[0].focus_verified


@pytest.mark.parametrize("cambio", [
    ("focus_verified: true", "focus_verified: false"),
    ("https://etraffic.dgt.es/camarasEtraffic/112.jpg", "https://malo.example/x.jpg"),
    ("verified_by: \"revisión visual\"", ""),
])
def test_una_camara_curada_invalida_se_rechaza(tmp_path, cambio):
    with pytest.raises(ValueError):
        cargar(tmp_path, yaml_text().replace(*cambio))


# ------------------------------------------------------------- estado de imagen

def head_handler(last_modified=None, status=200, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append((request.method, str(request.url)))
        headers = {"Last-Modified": format_datetime(last_modified, usegmt=True)} if last_modified else {}
        return httpx.Response(status, headers=headers)
    return handler


def checker(handler, now=lambda: NOW, stale=20):
    return CameraChecker(transport=httpx.MockTransport(handler), now=now, stale_after_minutes=stale)


URL = "https://etraffic.dgt.es/camarasEtraffic/112.jpg"


def test_imagen_reciente_da_ok_con_su_edad():
    r = checker(head_handler(NOW - timedelta(minutes=9))).status(URL)
    assert r["status"] == "OK" and r["age_minutes"] == 9 and r["last_modified_utc"] == "2026-11-12T07:51:00Z"


def test_imagen_antigua_es_camara_sin_senal_nunca_imagen_vieja():
    r = checker(head_handler(NOW - timedelta(minutes=21))).status(URL)
    assert r["status"] == "SIN_SENAL" and "sin señal" in r["message"].lower() and r["age_minutes"] == 21


@pytest.mark.parametrize("handler", [head_handler(None), head_handler(NOW, status=404), head_handler(NOW, status=503)])
def test_sin_fecha_o_con_error_http_es_sin_senal(handler):
    assert checker(handler).status(URL)["status"] == "SIN_SENAL"


def test_un_timeout_es_sin_senal():
    def boom(request):
        raise httpx.ReadTimeout("t", request=request)
    assert checker(boom).status(URL)["status"] == "SIN_SENAL"


def test_fecha_en_el_futuro_no_es_creible():
    assert checker(head_handler(NOW + timedelta(hours=2))).status(URL)["status"] == "SIN_SENAL"


def test_cache_de_2_minutos_limita_las_peticiones_a_la_dgt():
    llamadas, reloj = [], [NOW]
    c = checker(head_handler(NOW - timedelta(minutes=3), calls=llamadas), now=lambda: reloj[0])
    c.status(URL); c.status(URL)
    reloj[0] = NOW + timedelta(seconds=119); c.status(URL)
    assert len(llamadas) == 1 and llamadas[0][0] == "HEAD"
    reloj[0] = NOW + timedelta(seconds=121); c.status(URL)
    assert len(llamadas) == 2


def test_solo_hace_head_nunca_descarga_la_imagen():
    llamadas = []
    checker(head_handler(NOW, calls=llamadas)).status(URL)
    assert {m for m, _ in llamadas} == {"HEAD"}


# ----------------------------------------------------------------------- API

def lectura(**kw):
    base = dict(station_id="saih_jucar:rambla_poyo", source="t", name="Aforo Poyo", lat=39.47537, lon=-0.5818, river="Poyo",
                flow_m3s=1.0, level_m=None, rain_1h_mm=None, rain_24h_mm=None, reservoir_pct=None, reservoir_hm3=None,
                thresholds=None, timestamp_utc=NOW - timedelta(minutes=5), fetched_at_utc=NOW, quality="OK")
    base.update(kw)
    return Reading(**base)


@pytest.fixture()
def api(tmp_path):
    def make(cameras_cfg, handler=None):
        db = Database(tmp_path / "x.sqlite")
        db.record_success("t", [lectura(), lectura(station_id="t:lejos", lat=41.0, lon=-1.0, name="Lejos")], NOW, NOW)
        chk = checker(handler or head_handler(NOW - timedelta(minutes=4)))
        return TestClient(create_app(db, now=lambda: NOW, cameras=cameras_cfg, camera_checker=chk))
    return make


def test_sin_camara_curada_la_api_dice_que_no_hay(api, tmp_path):
    body = api(load_cameras(ROOT / "engine" / "cameras.yaml")).get("/stations/saih_jucar:rambla_poyo/camera").json()
    assert body["camera"] is None and "ninguna cámara verificada" in body["reason"]
    assert api(load_cameras(ROOT / "engine" / "cameras.yaml")).get("/stations/no-existe/camera").status_code == 404


def test_con_camara_curada_devuelve_hotlink_distancia_y_enlace_al_origen(api, tmp_path):
    cfg = cargar(tmp_path, yaml_text())
    body = api(cfg).get("/stations/saih_jucar:rambla_poyo/camera").json()
    c = body["camera"]
    assert c["image_url"] == URL and c["origin_url"] == "https://infocar.dgt.es/etraffic/"
    assert 0.5 < c["distance_km"] < 1.5 and c["focus_verified"] is True
    assert c["status"]["status"] == "OK" and c["status"]["age_minutes"] == 4
    assert c["refresh_seconds"] == 120 and body["disclaimer"]


def test_camara_a_mas_de_3_km_de_la_estacion_no_se_ofrece(api, tmp_path):
    cfg = cargar(tmp_path, yaml_text().replace("saih_jucar:rambla_poyo", "t:lejos"))
    assert api(cfg).get("/stations/t:lejos/camera").json()["camera"] is None


def test_la_api_devuelve_sin_senal_si_la_imagen_es_vieja(api, tmp_path):
    cfg = cargar(tmp_path, yaml_text())
    body = api(cfg, head_handler(NOW - timedelta(hours=3))).get("/stations/saih_jucar:rambla_poyo/camera").json()
    assert body["camera"]["status"]["status"] == "SIN_SENAL"


def test_la_api_no_es_un_proxy_abierto(api, tmp_path):
    c = api(cargar(tmp_path, yaml_text()))
    assert c.get("/cameras/999/status").status_code == 404
    assert c.get("/cameras/112/status").json()["status"] == "OK"
    assert c.get("/cameras/https:__malo/status").status_code == 404
