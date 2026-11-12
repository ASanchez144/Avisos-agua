"""Conector SAI Cantábrico contra la fixture real de la Fase 0."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import httpx
import pytest

from conftest import feature_by_code, only_feature
from connectors.base import Reading, SourceFormatError, SourceUnavailableError
from connectors.http import PoliteHttpClient
from connectors.saih_cantabrico import SOURCE, SaihCantabricoConnector, parse

SCHEMA_FIELDS = {
    "station_id", "source", "name", "lat", "lon", "river", "flow_m3s", "level_m",
    "rain_1h_mm", "rain_24h_mm", "reservoir_pct", "reservoir_hm3", "thresholds",
    "timestamp_utc", "fetched_at_utc", "quality",
}


def by_id(readings: list[Reading]) -> dict[str, Reading]:
    return {r.station_id: r for r in readings}


def test_parsea_todas_las_estaciones_hidrologicas_de_la_fixture(cantabrico_raw, cantabrico_fetched_at):
    raw = json.loads(cantabrico_raw)
    esperadas = [
        f for f in raw["data"]["features"]
        if f["properties"].get("tipo_estacion") in {"cauce", "embalse", "meteorologica"}
    ]
    readings = parse(cantabrico_raw, cantabrico_fetched_at)
    assert len(readings) == len(esperadas) > 150
    assert len({r.station_id for r in readings}) == len(readings)


def test_cada_lectura_respeta_el_esquema_comun(cantabrico_raw, cantabrico_fetched_at):
    for r in parse(cantabrico_raw, cantabrico_fetched_at):
        d = r.to_dict()
        assert set(d) == SCHEMA_FIELDS
        assert d["source"] == SOURCE
        assert d["quality"] in {"OK", "SUSPECT", "MISSING"}
        assert d["fetched_at_utc"] == "2026-11-11T11:50:56Z"


def test_estacion_de_cauce_1424_coincide_con_el_dato_crudo(cantabrico_raw, cantabrico_fetched_at):
    r = by_id(parse(cantabrico_raw, cantabrico_fetched_at))["saih_cantabrico:1424"]
    assert r.name == "Ribera de Piquín"
    assert r.river == "Eo"
    assert r.lat == pytest.approx(43.17949624557935)
    assert r.lon == pytest.approx(-7.199463048291921)
    assert r.flow_m3s == 0.75
    assert r.level_m == 0.14
    # "2026-11-11 12:45:00" es hora local peninsular (CET, UTC+1 en noviembre).
    assert r.timestamp_utc == datetime(2026, 11, 11, 11, 45, tzinfo=timezone.utc)
    assert r.thresholds == {"yellow": 2.1, "orange": 2.6, "red": 3.5, "variable": "level_m"}
    assert r.quality == "OK"


def test_lluvia_1h_y_24h_se_copian_del_dato_crudo(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.rain_1h_mm == props["precipit_1h"]
    assert r.rain_24h_mm == props["precipit_24h"]


def test_embalse_mapea_volumen_y_porcentaje_y_no_usa_cota_como_nivel(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1406")["properties"]
    r = parse(only_feature(cantabrico_payload, "1406"), cantabrico_fetched_at)[0]
    assert r.reservoir_hm3 == props["volumen_embalse"]
    assert r.reservoir_pct == props["porcentaje_llenado_embalse"]
    assert r.level_m is None  # nivel_embalse es cota msnm, no altura de lámina en río
    assert r.thresholds is None


def test_umbrales_parciales_se_conservan_con_nulos(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["prealerta_nivel"] = None
    props["alerta_nivel"] = None
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.thresholds == {"yellow": 2.1, "orange": None, "red": None, "variable": "level_m"}


def test_sin_umbrales_de_nivel_usa_los_de_caudal(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    for k in ("seguimiento_nivel", "prealerta_nivel", "alerta_nivel"):
        props[k] = None
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.thresholds == {"yellow": 147.0, "orange": 208.0, "red": 307.0, "variable": "flow_m3s"}


def test_sin_ningun_umbral_publicado_thresholds_es_none(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    for v in ("nivel", "caudal"):
        for k in ("seguimiento_", "prealerta_", "alerta_"):
            props[k + v] = None
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.thresholds is None
    assert r.quality == "OK"


def test_fecha_centinela_1970_descarta_esa_variable(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["fecha_caudal"] = "1970-01-01 00:00:00"
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.flow_m3s is None
    assert r.level_m == 0.14
    assert r.timestamp_utc == datetime(2026, 11, 11, 11, 45, tzinfo=timezone.utc)
    assert r.quality == "OK"


def test_variable_rezagada_mas_de_60_min_no_se_presenta_como_actual(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["fecha_caudal"] = "2026-11-11 03:40:00"
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.flow_m3s is None
    assert r.level_m == 0.14


def test_timestamp_es_el_mas_antiguo_de_las_variables_incluidas(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["fecha_caudal"] = "2026-11-11 12:30:00"
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.flow_m3s == 0.75
    assert r.timestamp_utc == datetime(2026, 11, 11, 11, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("centinela", [-999, -999.0, -9999, "-999"])
def test_valor_centinela_se_trata_como_ausente(cantabrico_payload, cantabrico_fetched_at, centinela):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["caudal"] = centinela
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.flow_m3s is None
    assert r.level_m == 0.14
    assert r.quality == "OK"


def test_todas_las_variables_vacias_da_missing_sin_timestamp(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    for k in ("caudal", "nivel", "precipit_1h", "precipit_24h"):
        props[k] = None
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.quality == "MISSING"
    assert r.timestamp_utc is None
    assert (r.flow_m3s, r.level_m, r.rain_1h_mm, r.rain_24h_mm) == (None, None, None, None)


def test_estacion_fuera_de_servicio_da_missing(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["fuera_servicio"] = 1
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.quality == "MISSING"
    assert r.flow_m3s is None and r.level_m is None


def test_valor_fuera_de_rango_no_se_recorta_y_marca_suspect(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["caudal"] = 20000.5
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.flow_m3s == 20000.5
    assert r.quality == "SUSPECT"


def test_valor_no_numerico_marca_suspect_y_no_inventa_numero(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["nivel"] = "N/D"
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.level_m is None
    assert r.quality == "SUSPECT"


def test_nan_marca_suspect(cantabrico_payload, cantabrico_fetched_at):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    props["caudal"] = "NaN"
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.quality == "SUSPECT"
    assert r.flow_m3s is None or math.isnan(r.flow_m3s)


def test_coordenadas_ilegibles_marcan_suspect(cantabrico_payload, cantabrico_fetched_at):
    feat = feature_by_code(cantabrico_payload, "1424")
    feat["properties"]["lat"] = ""
    feat["geometry"]["coordinates"] = ["", ""]
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.lat is None
    assert r.quality == "SUSPECT"


def test_hora_de_verano_se_convierte_con_utc_mas_2(cantabrico_payload):
    props = feature_by_code(cantabrico_payload, "1424")["properties"]
    for k in ("fecha", "fecha_caudal", "fecha_nivel", "fecha_precipitacion"):
        props[k] = "2026-07-01 12:00:00"
    fetched = datetime(2026, 7, 1, 10, 5, tzinfo=timezone.utc)
    r = parse(only_feature(cantabrico_payload, "1424"), fetched)[0]
    assert r.timestamp_utc == datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)


def test_estacion_sin_codigo_se_omite_sin_romper_el_resto(cantabrico_payload, cantabrico_fetched_at):
    feats = cantabrico_payload["data"]["features"]
    total = len(parse(json.dumps(cantabrico_payload).encode(), cantabrico_fetched_at))
    del feature_by_code(cantabrico_payload, "1424")["properties"]["codigo_general"]
    readings = parse(json.dumps(cantabrico_payload).encode(), cantabrico_fetched_at)
    assert len(readings) == total - 1
    assert len(feats) > 0


@pytest.mark.parametrize(
    "cuerpo",
    [
        b"",
        b"<html><body>Mantenimiento</body></html>",
        b'{"success": false, "data": "error"}',
        b'{"success": true, "data": {"type": "FeatureCollection"}}',
        b'{"success": true, "data": {"type": "FeatureCollection", "features": []}}',
        b'{"success": true, "data": {"features": [{"properties": {"nombre": "x"}}]}}',
        b"[1, 2, 3]",
    ],
)
def test_respuesta_inesperada_lanza_error_de_formato(cuerpo, cantabrico_fetched_at):
    with pytest.raises(SourceFormatError):
        parse(cuerpo, cantabrico_fetched_at)


# ---------------------------------------------------------------- red (falsa)

ROBOTS_OK = b"User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n"


def _client(handler) -> PoliteHttpClient:
    return PoliteHttpClient(transport=httpx.MockTransport(handler))


def test_fetch_hace_post_con_user_agent_identificable(cantabrico_raw):
    vistos = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=ROBOTS_OK)
        return httpx.Response(200, content=cantabrico_raw)

    readings = SaihCantabricoConnector(_client(handler)).fetch()
    assert len(readings) > 150
    post = [r for r in vistos if r.method == "POST"][0]
    assert str(post.url) == "https://visor.saichcantabrico.es/wp-admin/admin-ajax.php"
    assert post.content == b"action=peticion_cincominutal&tipo=todas"
    assert post.headers["user-agent"].startswith("HidroRed/")
    assert "Mozilla" not in post.headers["user-agent"]


def test_timeout_lanza_fuente_no_disponible():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=ROBOTS_OK)
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(SourceUnavailableError):
        SaihCantabricoConnector(_client(handler)).fetch()


def test_http_500_lanza_fuente_no_disponible():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=ROBOTS_OK)
        return httpx.Response(503, content=b"Service Unavailable")

    with pytest.raises(SourceUnavailableError):
        SaihCantabricoConnector(_client(handler)).fetch()


def test_html_de_mantenimiento_lanza_error_de_formato():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=ROBOTS_OK)
        return httpx.Response(200, content=b"<!DOCTYPE html><html>nuevo visor</html>")

    with pytest.raises(SourceFormatError):
        SaihCantabricoConnector(_client(handler)).fetch()


@pytest.mark.parametrize("flag", [1, "1", True])
def test_fuera_de_servicio_en_cualquier_formato_da_missing(cantabrico_payload, cantabrico_fetched_at, flag):
    feature_by_code(cantabrico_payload, "1424")["properties"]["fuera_servicio"] = flag
    r = parse(only_feature(cantabrico_payload, "1424"), cantabrico_fetched_at)[0]
    assert r.quality == "MISSING"
