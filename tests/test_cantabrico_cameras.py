"""Cámaras oficiales de la CHC en las estaciones de aforo (respuestas reales del visor SAI)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.db import Database
from connectors.base import Reading, SourceFormatError
from connectors.http import PoliteHttpClient
from connectors.saih_cantabrico_cameras import SaiCameraService, parse_camera_image, parse_camera_list

FIX = Path(__file__).resolve().parent / "fixtures" / "saih_cantabrico"
NOW = datetime(2026, 11, 12, 11, 55, tzinfo=timezone.utc)


def test_lista_real_de_camaras():
    cams = parse_camera_list((FIX / "camaras_lista.json").read_bytes())
    assert len(cams) == 147
    assert cams["saih_cantabrico:1424"] == {"code": "1424", "name": "1424 EO", "lat": 43.17949624557935, "lon": -7.199463048291921}


def test_imagen_real_con_su_fecha_y_tolerando_lineas_en_blanco():
    raw = (FIX / "camara_imagen_1424.json").read_bytes()
    assert raw.lstrip() != raw  # la respuesta real trae líneas en blanco delante
    img = parse_camera_image(raw)
    assert img["url"] == "https://visor.saichcantabrico.es/meteorologia-files/camaras/1424EO/202611121240.jpg"
    assert img["taken_at"] == datetime(2026, 11, 12, 11, 40, 49, tzinfo=timezone.utc)


def test_camara_inexistente_no_da_imagen():
    assert parse_camera_image((FIX / "camara_imagen_inexistente.json").read_bytes()) is None


@pytest.mark.parametrize("cuerpo", [b"", b"<html>", b'{"success": true, "data": {"url": "http://otro.sitio/x.jpg", "fecha": "2026-11-12T11:40:49+00:00"}}'])
def test_respuesta_rara_o_url_ajena_es_error(cuerpo):
    with pytest.raises(SourceFormatError):
        parse_camera_image(cuerpo)


# ------------------------------------------------------------------ servicio

def servicio(db, respuestas, now=lambda: NOW, llamadas=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=(FIX / "robots.txt").read_bytes())
        body = request.content.decode()
        if llamadas is not None:
            llamadas.append(body)
        code = body.split("code=")[-1]
        return httpx.Response(200, content=respuestas.get(code, (FIX / "camara_imagen_inexistente.json").read_bytes()))
    client = PoliteHttpClient(transport=httpx.MockTransport(handler), now=now)
    return SaiCameraService(db, client=client, now=now)


@pytest.fixture()
def db(tmp_path):
    return Database(tmp_path / "c.sqlite")


def test_estado_ok_con_la_edad_real_de_la_imagen(db):
    s = servicio(db, {"1424": (FIX / "camara_imagen_1424.json").read_bytes()})
    cam = s.camera("saih_cantabrico:1424")
    assert cam["image_url"].endswith("/1424EO/202611121240.jpg")
    assert cam["status"]["status"] == "OK" and cam["status"]["age_minutes"] == 14
    assert cam["kind"] == "aforo" and cam["origin_url"] == "https://visor.saichcantabrico.es/"


def test_imagen_de_julio_es_camara_sin_senal(db):
    s = servicio(db, {"1414": (FIX / "camara_imagen_1414_antigua.json").read_bytes()})
    st = s.camera("saih_cantabrico:1414")["status"]
    assert st["status"] == "SIN_SENAL" and "sin señal" in st["message"].lower()


def test_estacion_sin_camara_o_de_otra_fuente_no_pide_nada(db):
    llamadas = []
    s = servicio(db, {}, llamadas=llamadas)
    assert s.camera("aca:080060-001") is None
    assert llamadas == []


def test_se_cachea_15_min_en_la_base_de_datos_y_sobrevive_a_reinicios(db):
    llamadas, reloj = [], [NOW]
    resp = {"1424": (FIX / "camara_imagen_1424.json").read_bytes()}
    servicio(db, resp, now=lambda: reloj[0], llamadas=llamadas).camera("saih_cantabrico:1424")
    reloj[0] = NOW + timedelta(minutes=10)
    otra = servicio(db, resp, now=lambda: reloj[0], llamadas=llamadas)  # proceso nuevo
    assert otra.camera("saih_cantabrico:1424")["status"]["age_minutes"] == 24
    assert len(llamadas) == 1
    reloj[0] = NOW + timedelta(minutes=16)
    servicio(db, resp, now=lambda: reloj[0], llamadas=llamadas).camera("saih_cantabrico:1424")
    assert len(llamadas) == 2


def test_si_la_fuente_falla_es_sin_senal_nunca_la_foto_vieja_como_actual(db):
    def boom(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectTimeout("t", request=request)
    s = SaiCameraService(db, client=PoliteHttpClient(transport=httpx.MockTransport(boom), now=lambda: NOW), now=lambda: NOW)
    cam = s.camera("saih_cantabrico:1424")
    assert cam["status"]["status"] == "SIN_SENAL" and cam["image_url"] is None


def test_api_devuelve_la_camara_oficial_de_la_estacion(db):
    db.record_success("saih_cantabrico", [Reading("saih_cantabrico:1424", "saih_cantabrico", "Ribera de Piquín", 43.18, -7.2, "Eo",
                      0.7, 0.14, None, None, None, None, None, NOW - timedelta(minutes=5), NOW, "OK")], NOW, NOW)
    s = servicio(db, {"1424": (FIX / "camara_imagen_1424.json").read_bytes()})
    body = TestClient(create_app(db, now=lambda: NOW, sai_cameras=s)).get("/stations/saih_cantabrico:1424/camera").json()
    assert body["camera"]["kind"] == "aforo" and body["camera"]["status"]["status"] == "OK"
    assert "Confederación Hidrográfica del Cantábrico" in body["camera"]["source_label"]


def test_lista_de_estaciones_con_camara_se_cachea_6_horas(db):
    llamadas, reloj = [], [NOW]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=(FIX / "robots.txt").read_bytes())
        llamadas.append(request.content.decode())
        return httpx.Response(200, content=(FIX / "camaras_lista.json").read_bytes())

    mk = lambda: SaiCameraService(db, client=PoliteHttpClient(transport=httpx.MockTransport(handler), now=lambda: reloj[0]), now=lambda: reloj[0])
    ids = mk().station_ids()
    assert len(ids) == 147 and "saih_cantabrico:1424" in ids
    reloj[0] = NOW + timedelta(hours=5)
    assert mk().station_ids() == ids and len(llamadas) == 1
    reloj[0] = NOW + timedelta(hours=7)
    mk().station_ids()
    assert len(llamadas) == 2 and "tipo=camaras" in llamadas[0]


def test_si_la_lista_falla_nadie_tiene_camara_pero_la_api_sigue(db):
    def boom(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectTimeout("t", request=request)
    s = SaiCameraService(db, client=PoliteHttpClient(transport=httpx.MockTransport(boom), now=lambda: NOW), now=lambda: NOW)
    assert s.station_ids() == set()


def test_stations_marca_las_que_tienen_camara(db):
    db.record_success("t", [Reading("saih_cantabrico:1424", "saih_cantabrico", "Ribera", 43.18, -7.2, "Eo", 0.7, 0.14, None, None, None, None, None, NOW - timedelta(minutes=5), NOW, "OK"),
                           Reading("aca:1", "aca", "X", 41.5, 2.0, None, 1.0, None, None, None, None, None, None, NOW - timedelta(minutes=5), NOW, "OK")], NOW, NOW)

    class Fake:
        def station_ids(self):
            return {"saih_cantabrico:1424"}

        def camera(self, sid):
            return None
    st = {s["station_id"]: s["has_camera"] for s in TestClient(create_app(db, now=lambda: NOW, sai_cameras=Fake())).get("/stations").json()["stations"]}
    assert st == {"saih_cantabrico:1424": True, "aca:1": False}
