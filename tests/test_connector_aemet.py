"""Conector AEMET OpenData contra fixtures reales (2026-11-11)."""
from __future__ import annotations

import gzip
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from connectors.aemet import (
    SOURCE, AemetConnector, nearest_station, parse_envelope, parse_inventory, parse_observations, parse_warnings,
)
from connectors.base import SourceFormatError, SourceUnavailableError
from connectors.http import PoliteHttpClient

FIX = Path(__file__).resolve().parent / "fixtures" / "aemet"
NOW = datetime(2026, 11, 11, 12, 3, 30, tzinfo=timezone.utc)
OBS = gzip.open(FIX / "observacion_convencional_todas_datos.json.gz").read()
STEP1 = (FIX / "observacion_convencional_todas_CON_KEY_paso1.json").read_bytes()


def obs_json() -> list[dict]:
    return json.loads(OBS.decode("iso-8859-15"))


def by_id(readings):
    return {r.station_id: r for r in readings}


# ------------------------------------------------------------ paso 1 (sobre)

def test_sobre_correcto_devuelve_url_de_datos():
    assert parse_envelope(STEP1) == "https://opendata.aemet.es/opendata/sh/d6aa6708"


def test_200_con_cuerpo_vacio_es_error_no_exito():
    with pytest.raises(SourceUnavailableError, match="vacío"):
        parse_envelope((FIX / "observacion_convencional_todas_SIN_KEY.body.txt").read_bytes())


def test_estado_401_dentro_del_json_es_error():
    with pytest.raises(SourceUnavailableError, match="401"):
        parse_envelope((FIX / "observacion_convencional_todas_KEY_INVALIDA.body.txt").read_bytes())


def test_estado_404_con_http_200_es_error():
    with pytest.raises(SourceUnavailableError, match="404"):
        parse_envelope((FIX / "red_radar_nacional_CON_KEY_paso1.json").read_bytes())


def test_sobre_ilegible_es_error_de_formato():
    with pytest.raises(SourceFormatError):
        parse_envelope(b"<html>mantenimiento</html>")


# -------------------------------------------------------------- observación

def test_una_lectura_por_estacion_con_su_ultima_hora():
    datos = obs_json()
    readings = parse_observations(OBS, NOW)
    assert len(readings) == len({d["idema"] for d in datos}) == 855
    ultima = max((d for d in datos if d["idema"] == "3526X"), key=lambda d: d["fint"])
    r = by_id(readings)["aemet:3526X"]
    assert r.rain_1h_mm == ultima["prec"] == 10.8
    assert r.timestamp_utc == datetime(2026, 11, 11, 11, 0, tzinfo=timezone.utc)  # fint ya es UTC
    assert r.name == "CORIA" and r.lat == 40.003539 and r.lon == -6.557527
    assert r.source == SOURCE == "aemet"


def test_no_inventa_lluvia_de_24h_ni_otras_variables():
    for r in parse_observations(OBS, NOW):
        assert r.rain_24h_mm is None  # la API solo trae ~12 h por estación
        assert (r.flow_m3s, r.level_m, r.reservoir_pct, r.reservoir_hm3, r.thresholds, r.river) == (None,) * 6


def test_nombres_con_acentos_se_decodifican_bien():
    nombres = {r.name for r in parse_observations(OBS, NOW)}
    assert "VANDELLÓS" in nombres


def test_estacion_sin_precipitacion_da_missing():
    datos = [d for d in obs_json() if d["idema"] == "3526X"]
    for d in datos:
        d.pop("prec", None)
    r = parse_observations(json.dumps(datos).encode(), NOW)[0]
    assert r.quality == "MISSING" and r.rain_1h_mm is None and r.timestamp_utc is None


def test_lluvia_negativa_no_se_corrige_y_marca_suspect():
    datos = [max((d for d in obs_json() if d["idema"] == "3526X"), key=lambda d: d["fint"])]
    datos[0]["prec"] = -1.5
    r = parse_observations(json.dumps(datos).encode(), NOW)[0]
    assert r.rain_1h_mm == -1.5 and r.quality == "SUSPECT"


@pytest.mark.parametrize("cuerpo", [b"", b"<html></html>", b"{}", b"[]", b'[{"ubi": "sin idema"}]'])
def test_datos_inesperados_lanzan_error_de_formato(cuerpo):
    with pytest.raises(SourceFormatError):
        parse_observations(cuerpo, NOW)


# --------------------------------------------------------------- avisos CAP

def test_avisos_cap_del_tar_real():
    avisos = parse_warnings((FIX / "avisos_cap.tar.gz").read_bytes())
    assert len(avisos) == 515
    niveles = {a.level for a in avisos}
    assert niveles <= {"verde", "amarillo", "naranja", "rojo"} and "amarillo" in niveles
    a = next(x for x in avisos if x.identifier == "2.49.0.0.724.0.ES.20261111102936.633302PRP213021794392976")
    assert a.level == "amarillo" and a.phenomenon == "Lluvias" and a.severity == "Moderate"
    assert a.event == "Aviso de lluvias de nivel amarillo"
    assert a.area == "Litoral oriental asturiano" and a.zone == "633302"
    assert a.description == "Precipitación acumulada en 12 horas: 40 mm."
    assert a.onset == datetime(2026, 11, 12, 23, 0, tzinfo=timezone.utc)
    assert a.expires == datetime(2026, 11, 13, 1, 59, 59, tzinfo=timezone.utc)
    assert a.polygons[0][0] == (43.59, -5.94) and a.polygons[0][-1] == (43.59, -5.94)
    assert len(a.polygons[0]) > 20


def test_aviso_en_tar_sin_comprimir_y_xml_roto_no_tumba_el_resto():
    xml = (FIX / "avisos_cap_muestra_Z_CAP_C_LEMM_20261111102936_AFAZ633302PRP21302.xml").read_bytes()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in (("a.xml", xml), ("roto.xml", b"<alert><info>")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    avisos = parse_warnings(buf.getvalue())
    assert len(avisos) == 1 and avisos[0].level == "amarillo"


def test_avisos_que_no_son_tar_lanzan_error_de_formato():
    with pytest.raises(SourceFormatError):
        parse_warnings(b"<html>no es un tar</html>")


# --------------------------------------------------------------- inventario

def test_inventario_convierte_grados_minutos_segundos():
    est = parse_inventory((FIX / "inventarioestaciones_todasestaciones_datos.json").read_bytes())
    assert len(est) == 926
    lluc = next(e for e in est if e["indicativo"] == "B013X")
    assert lluc["nombre"] == "ESCORCA, LLUC"
    assert lluc["lat"] == pytest.approx(39 + 49 / 60 + 24 / 3600)
    assert lluc["lon"] == pytest.approx(2 + 53 / 60 + 9 / 3600)
    assert any(e["lon"] < 0 for e in est)  # las del oeste ("W") son negativas


def test_enlace_por_coordenadas_devuelve_la_estacion_mas_cercana_y_su_distancia():
    est = parse_inventory((FIX / "inventarioestaciones_todasestaciones_datos.json").read_bytes())
    cerca = nearest_station(39.82, 2.88, est)
    assert cerca["indicativo"] == "B013X" and cerca["distance_km"] < 2
    assert nearest_station(39.82, 2.88, est, max_km=0.01) is None


# ---------------------------------------------------------------------- red

def _handler(vistos, datos=OBS, paso1=STEP1):
    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if "/opendata/api/" in request.url.path:
            return httpx.Response(200, content=paso1)
        return httpx.Response(200, content=datos)
    return handler


def test_fetch_hace_los_dos_pasos_y_envia_la_clave_solo_al_paso_1(monkeypatch):
    monkeypatch.setenv("AEMET_API_KEY", "clave-de-prueba")
    vistos = []
    readings = AemetConnector(PoliteHttpClient(transport=httpx.MockTransport(_handler(vistos)))).fetch()
    assert len(readings) == 855
    paso1 = next(r for r in vistos if "/opendata/api/" in r.url.path)
    paso2 = next(r for r in vistos if "/opendata/sh/" in r.url.path)
    assert str(paso1.url) == "https://opendata.aemet.es/opendata/api/observacion/convencional/todas"
    assert paso1.headers["api_key"] == "clave-de-prueba"
    assert "api_key" not in paso2.headers and "clave-de-prueba" not in str(paso2.url)


def test_sin_clave_configurada_falla_sin_hacer_peticiones(monkeypatch):
    monkeypatch.delenv("AEMET_API_KEY", raising=False)
    vistos = []
    with pytest.raises(SourceUnavailableError, match="AEMET_API_KEY"):
        AemetConnector(PoliteHttpClient(transport=httpx.MockTransport(_handler(vistos)))).fetch()
    assert vistos == []


def test_respuesta_vacia_en_vivo_es_fuente_no_disponible(monkeypatch):
    monkeypatch.setenv("AEMET_API_KEY", "x")
    with pytest.raises(SourceUnavailableError):
        AemetConnector(PoliteHttpClient(transport=httpx.MockTransport(_handler([], paso1=b"")))).fetch()
