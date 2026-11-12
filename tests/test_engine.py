"""Motor: validación de plausibilidad (→ SUSPECT) y estado de estación."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from connectors.base import Reading
from engine.status import UMBRAL_NO_PUBLICADO, station_status
from engine.validation import violations

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def lectura(**kw) -> Reading:
    base = dict(
        station_id="t:1", source="t", name="Test", lat=43.0, lon=-5.0, river="Río",
        flow_m3s=10.0, level_m=1.0, rain_1h_mm=0.0, rain_24h_mm=2.0,
        reservoir_pct=None, reservoir_hm3=None,
        thresholds={"yellow": 2.0, "orange": 3.0, "red": 4.0, "variable": "level_m"},
        timestamp_utc=NOW - timedelta(minutes=5), fetched_at_utc=NOW, quality="OK",
    )
    base.update(kw)
    return Reading(**base)


def test_lectura_normal_no_tiene_violaciones():
    assert violations(lectura(), NOW) == []


@pytest.mark.parametrize(
    "campos, ley",
    [
        (dict(flow_m3s=-0.1), "L1"),
        (dict(flow_m3s=15000.1), "L1"),
        (dict(flow_m3s=float("nan")), "L1"),
        (dict(level_m=-2.1), "L2"),
        (dict(level_m=60.1), "L2"),
        (dict(rain_1h_mm=-1.0), "L3"),
        (dict(rain_1h_mm=5.0, rain_24h_mm=4.0), "L3"),
        (dict(lat=27.4), "L4"),
        (dict(lat=44.0), "L4"),
        (dict(lon=-18.6), "L4"),
        (dict(lon=4.6), "L4"),
        (dict(lat=None), "L4"),
        (dict(thresholds={"yellow": 3.0, "orange": 3.0, "red": 4.0, "variable": "level_m"}), "L5"),
        (dict(thresholds={"yellow": 5.0, "orange": None, "red": 4.0, "variable": "level_m"}), "L5"),
        (dict(timestamp_utc=NOW + timedelta(minutes=6)), "L6"),
        (dict(timestamp_utc=NOW - timedelta(days=7, minutes=1)), "L6"),
        (dict(reservoir_hm3=-0.02), "R1"),
    ],
)
def test_cada_ley_detecta_su_violacion(campos, ley):
    assert any(v.startswith(ley) for v in violations(lectura(**campos), NOW))


@pytest.mark.parametrize(
    "campos",
    [
        dict(flow_m3s=0.0),
        dict(flow_m3s=15000.0),
        dict(level_m=-2.0),
        dict(level_m=60.0),
        dict(flow_m3s=None, level_m=None, rain_1h_mm=None, rain_24h_mm=None),
        dict(rain_1h_mm=3.0, rain_24h_mm=3.0),
        dict(rain_1h_mm=3.0, rain_24h_mm=None),
        dict(thresholds=None),
        dict(thresholds={"yellow": 2.0, "orange": None, "red": None, "variable": "level_m"}),
        dict(timestamp_utc=NOW + timedelta(minutes=5)),
        dict(timestamp_utc=NOW - timedelta(days=7)),
    ],
)
def test_valores_en_el_limite_o_nulos_son_validos(campos):
    assert violations(lectura(**campos), NOW) == []


# ------------------------------------------------------------------- estado

@pytest.mark.parametrize(
    "nivel, esperado",
    [(1.99, "NORMAL"), (2.0, "VIGILANCIA"), (2.99, "VIGILANCIA"), (3.0, "PREALERTA"), (4.0, "ALERTA"), (9.0, "ALERTA")],
)
def test_estado_segun_umbrales_oficiales(nivel, esperado):
    s = station_status(lectura(level_m=nivel), NOW)
    assert s["status"] == esperado
    assert s["threshold_note"] is None


def test_umbrales_sobre_caudal_usan_el_caudal():
    th = {"yellow": 100.0, "orange": 200.0, "red": 300.0, "variable": "flow_m3s"}
    assert station_status(lectura(flow_m3s=250.0, level_m=0.1, thresholds=th), NOW)["status"] == "PREALERTA"


def test_umbrales_parciales_solo_comparan_los_publicados():
    th = {"yellow": 2.0, "orange": None, "red": None, "variable": "level_m"}
    assert station_status(lectura(level_m=50.0, thresholds=th), NOW)["status"] == "VIGILANCIA"


def test_sin_umbral_oficial_el_estado_es_sin_umbral_y_nunca_normal():
    s = station_status(lectura(thresholds=None), NOW)
    assert s["status"] == "SIN_UMBRAL" != "SIN_DATOS"
    assert s["threshold_note"] == UMBRAL_NO_PUBLICADO == "umbral no publicado"


def test_mas_de_60_min_es_dato_obsoleto_aunque_supere_umbral():
    r = lectura(level_m=9.0, timestamp_utc=NOW - timedelta(minutes=61))
    assert station_status(r, NOW)["status"] == "DATO_OBSOLETO"


def test_justo_60_min_todavia_no_es_obsoleto():
    r = lectura(timestamp_utc=NOW - timedelta(minutes=60))
    assert station_status(r, NOW)["status"] == "NORMAL"


def test_suspect_se_excluye_de_alertas_y_nunca_es_normal():
    r = lectura(level_m=9.0, quality="SUSPECT")
    assert station_status(r, NOW)["status"] == "SIN_DATOS"
    r = lectura(level_m=0.1, quality="SUSPECT")
    assert station_status(r, NOW)["status"] == "SIN_DATOS"


def test_missing_y_ausencia_de_lectura_son_sin_datos():
    r = lectura(quality="MISSING", timestamp_utc=None, flow_m3s=None, level_m=None)
    assert station_status(r, NOW)["status"] == "SIN_DATOS"
    assert station_status(None, NOW)["status"] == "SIN_DATOS"


def test_si_la_fuente_ha_fallado_es_sin_datos_aunque_el_ultimo_dato_sea_reciente():
    assert station_status(lectura(), NOW, source_ok=False)["status"] == "SIN_DATOS"


def test_variable_del_umbral_sin_valor_es_sin_datos():
    assert station_status(lectura(level_m=None), NOW)["status"] == "SIN_DATOS"


def test_umbrales_sin_variable_declarada_nunca_dan_verde():
    th = {"yellow": 2.0, "orange": 3.0, "red": 4.0}
    assert station_status(lectura(level_m=0.1, thresholds=th), NOW)["status"] == "SIN_DATOS"


@pytest.mark.parametrize(
    "source, minutos, esperado",
    [("aemet", 100, "NORMAL"), ("aemet", 120, "NORMAL"), ("aemet", 121, "DATO_OBSOLETO"),
     ("saih_cantabrico", 60, "NORMAL"), ("saih_cantabrico", 61, "DATO_OBSOLETO"),
     ("aca", 61, "DATO_OBSOLETO"), ("fuente_nueva", 61, "DATO_OBSOLETO")],
)
def test_frescura_configurable_por_fuente(source, minutos, esperado):
    r = lectura(source=source, timestamp_utc=NOW - timedelta(minutes=minutos))
    assert station_status(r, NOW)["status"] == esperado


def test_el_estado_informa_de_la_edad_real_y_del_limite_de_su_fuente():
    s = station_status(lectura(source="aemet", timestamp_utc=NOW - timedelta(minutes=85)), NOW)
    assert s["age_minutes"] == 85 and s["fresh_limit_minutes"] == 120
    assert station_status(None, NOW)["age_minutes"] is None
