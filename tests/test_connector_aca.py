"""Conector ACA (API SDIM2) contra fixtures reales capturadas el 2026-11-11."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from connectors.aca import SOURCE, AcaConnector, parse
from connectors.base import SourceFormatError, SourceUnavailableError
from connectors.http import PoliteHttpClient

FIX = Path(__file__).resolve().parent / "fixtures" / "aca"
NOW = datetime(2026, 11, 11, 12, 16, 4, tzinfo=timezone.utc)
NAMES = ("catalog_aforament", "data_AFORAMENT-EST", "catalog_embassament", "data_EMBASSAMENT-EST")


def raw() -> dict[str, dict]:
    return {n: json.loads((FIX / f"live_{n}.json").read_bytes()) for n in NAMES}


def run(payloads: dict[str, dict]):
    b = {k: json.dumps(v).encode() for k, v in payloads.items()}
    return parse(
        [b["catalog_aforament"], b["catalog_embassament"]],
        [b["data_AFORAMENT-EST"], b["data_EMBASSAMENT-EST"]],
        NOW,
    )


def by_id(readings):
    return {r.station_id: r for r in readings}


def sensor_value(payloads, sensor):
    for key in ("data_AFORAMENT-EST", "data_EMBASSAMENT-EST"):
        for s in payloads[key]["sensors"]:
            if s["sensor"] == sensor:
                return s["observations"][0]
    raise KeyError(sensor)


def test_una_lectura_por_componente_con_esquema_y_sin_umbrales():
    p = raw()
    readings = run(p)
    componentes = {
        s["component"] for k in ("catalog_aforament", "catalog_embassament") for s in p[k]["providers"][0]["sensors"]
    }
    assert {r.station_id for r in readings} == {f"aca:{c}" for c in componentes}
    assert all(r.source == SOURCE == "aca" and r.thresholds is None for r in readings)
    assert sum(r.quality == "OK" for r in readings) > 70


def test_aforo_mapea_caudal_y_convierte_nivel_de_cm_a_m():
    p = raw()
    r = by_id(run(p))["aca:080060-001"]
    nivel_cm = float(sensor_value(p, "080060-001-ANA01")["value"])
    caudal = float(sensor_value(p, "CALC001658")["value"])
    assert r.level_m == pytest.approx(nivel_cm / 100)
    assert r.flow_m3s == caudal
    assert r.name == "Arenys de Munt (riera d'Arenys)"
    assert r.river == "RIERA ARENYS"
    assert (r.lat, r.lon) == (41.592783082, 2.542640569)
    epoch_ms = sensor_value(p, "080060-001-ANA01")["time"]
    assert r.timestamp_utc == datetime.fromtimestamp(epoch_ms / 1000, timezone.utc)


def test_embalse_mapea_volumen_y_porcentaje_pero_no_cota():
    p = raw()
    r = by_id(run(p))["aca:080581-002"]
    assert r.reservoir_hm3 is not None and 0 <= r.reservoir_pct <= 100
    assert r.level_m is None  # "Nivell absolut" es cota msnm


def test_embalse_con_aforo_de_salida_en_el_mismo_componente():
    """Dato real: el componente 080581-002 aparece en los dos catálogos (embalse de
    Foix y su aforo "Q sortida"). Es una sola estación: embalse + caudal de salida."""
    p = raw()
    salida = next(
        s for s in p["catalog_aforament"]["providers"][0]["sensors"]
        if s["component"] == "080581-002" and s["description"] == "Cabal riu"
    )
    r = by_id(run(p))["aca:080581-002"]
    assert r.name == "Embassament de Foix (Foix)"
    assert r.flow_m3s == float(sensor_value(p, salida["sensor"])["value"])


def test_caudal_de_canal_en_litros_no_se_confunde_con_caudal_de_rio():
    p = raw()
    for s in p["catalog_aforament"]["providers"][0]["sensors"]:
        if s["component"] == "080180-005" and s["description"] == "Cabal riu":
            s["description"] = "Cabal canal"
    assert by_id(run(p))["aca:080180-005"].flow_m3s is None


def test_sensor_sin_observaciones_no_inventa_valor():
    p = raw()
    for s in p["data_AFORAMENT-EST"]["sensors"]:
        if s["sensor"] in ("080060-001-ANA01", "CALC001658"):
            s["observations"] = []
    r = by_id(run(p))["aca:080060-001"]
    assert r.quality == "MISSING" and r.timestamp_utc is None and r.flow_m3s is None


def test_sensor_rezagado_no_se_presenta_como_actual():
    p = raw()
    sensor_value(p, "CALC001658")["time"] -= 3 * 3600 * 1000
    r = by_id(run(p))["aca:080060-001"]
    assert r.flow_m3s is None and r.level_m is not None


@pytest.mark.parametrize("valor", ["-999", "-9999"])
def test_centinela_se_trata_como_ausente(valor):
    p = raw()
    sensor_value(p, "CALC001658")["value"] = valor
    r = by_id(run(p))["aca:080060-001"]
    assert r.flow_m3s is None and r.quality == "OK"


def test_valor_fuera_de_rango_no_se_recorta():
    p = raw()
    sensor_value(p, "CALC001658")["value"] = "15000.5"
    r = by_id(run(p))["aca:080060-001"]
    assert r.flow_m3s == 15000.5 and r.quality == "SUSPECT"


def test_valor_ilegible_marca_suspect():
    p = raw()
    sensor_value(p, "CALC001658")["value"] = "ERR"
    r = by_id(run(p))["aca:080060-001"]
    assert r.flow_m3s is None and r.quality == "SUSPECT"


@pytest.mark.parametrize("cuerpo", [b"", b"<html>error</html>", b"{}", b'{"providers": []}', b'{"sensors": "x"}'])
def test_respuesta_inesperada_lanza_error_de_formato(cuerpo):
    good = {n: (FIX / f"live_{n}.json").read_bytes() for n in NAMES}
    with pytest.raises(SourceFormatError):
        parse([cuerpo, good["catalog_embassament"]], [good["data_AFORAMENT-EST"], good["data_EMBASSAMENT-EST"]], NOW)
    with pytest.raises(SourceFormatError):
        parse([good["catalog_aforament"], good["catalog_embassament"]], [cuerpo, good["data_EMBASSAMENT-EST"]], NOW)


def test_fetch_pide_los_cuatro_recursos_verificados():
    vistos = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        tipo = request.url.params.get("componentType")
        if tipo:
            return httpx.Response(200, content=(FIX / f"live_catalog_{tipo}.json").read_bytes())
        return httpx.Response(200, content=(FIX / f"live_data_{request.url.path.rsplit('/', 1)[1]}.json").read_bytes())

    readings = AcaConnector(PoliteHttpClient(transport=httpx.MockTransport(handler))).fetch()
    assert len(readings) > 80
    base = "https://aplicacions.aca.gencat.cat/sdim2/apirest/"
    assert set(vistos) - {"https://aplicacions.aca.gencat.cat/robots.txt"} == {
        base + "catalog?componentType=aforament", base + "catalog?componentType=embassament",
        base + "data/AFORAMENT-EST", base + "data/EMBASSAMENT-EST",
    }


def test_timeout_lanza_fuente_no_disponible():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(SourceUnavailableError):
        AcaConnector(PoliteHttpClient(transport=httpx.MockTransport(handler))).fetch()
