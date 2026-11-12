"""Endpoints GET /alerts y GET /propagation, y avisos AEMET en el ciclo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import DISCLAIMER, create_app
from backend.db import Database
from backend.scheduler import run_cycle
from connectors.aemet import parse_warnings
from connectors.base import Reading, SourceUnavailableError

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
FIX = Path(__file__).resolve().parent / "fixtures" / "aemet"


def lectura(station, minutes_ago=5, now=T0, **kw) -> Reading:
    base = dict(
        station_id=station, source=station.split(":")[0], name="Est " + station, lat=43.0, lon=-5.0, river="Río",
        flow_m3s=None, level_m=1.0, rain_1h_mm=None, rain_24h_mm=None, reservoir_pct=None, reservoir_hm3=None,
        thresholds={"yellow": 2.0, "orange": 3.0, "red": 4.0, "variable": "level_m"},
        timestamp_utc=now - timedelta(minutes=minutes_ago), fetched_at_utc=now, quality="OK",
    )
    base.update(kw)
    return Reading(**base)


@pytest.fixture()
def db(tmp_path) -> Database:
    return Database(tmp_path / "h.sqlite")


def cliente(db, now=T0) -> TestClient:
    return TestClient(create_app(db, now=lambda: now))


def guarda(db, *readings, now=T0):
    for source in {r.source for r in readings}:
        db.record_success(source, [r for r in readings if r.source == source], started_at=now, finished_at=now)


# ------------------------------------------------------------------ /alerts

def test_alerts_solo_lista_estaciones_por_encima_de_umbral_oficial(db):
    guarda(db, lectura("t:normal", level_m=1.0), lectura("t:amarilla", level_m=2.5), lectura("t:roja", level_m=9.0),
           lectura("t:sin_umbral", level_m=50.0, thresholds=None), lectura("t:sospechosa", level_m=9.0, quality="SUSPECT"))
    body = cliente(db).get("/alerts").json()
    assert body["disclaimer"] == DISCLAIMER
    assert {s["station_id"]: s["status"] for s in body["station_alerts"]} == {"t:amarilla": "VIGILANCIA", "t:roja": "ALERTA"}
    assert body["station_alerts"][0]["station_id"] == "t:roja"  # lo más grave primero


def test_alerts_incluye_avisos_aemet_vigentes_y_no_los_verdes_ni_los_caducados(db):
    avisos = [a.to_dict() for a in parse_warnings((FIX / "avisos_cap.tar.gz").read_bytes())]
    db.replace_warnings("aemet", avisos, fetched_at=T0)
    w = cliente(db).get("/alerts").json()["weather_warnings"]
    assert w["status"] == "OK" and w["source"] == "AEMET"
    assert 0 < len(w["items"]) < len(avisos)
    assert {i["level"] for i in w["items"]} <= {"amarillo", "naranja", "rojo"}
    assert all(i["expires"] > "2026-11-11T12:00:00Z" for i in w["items"])
    assert all(i["polygons"] for i in w["items"])
    tarde = cliente(db, now=T0 + timedelta(days=10)).get("/alerts").json()["weather_warnings"]
    assert tarde["items"] == []


def test_alerts_sin_avisos_descargados_dice_sin_datos_no_cero_avisos(db):
    w = cliente(db).get("/alerts").json()["weather_warnings"]
    assert w == {"status": "SIN_DATOS", "source": "AEMET", "items": []}


def test_si_falla_la_descarga_de_avisos_el_estado_pasa_a_sin_datos(db):
    db.replace_warnings("aemet", [], fetched_at=T0)
    db.record_failure("aemet:avisos", "SourceUnavailableError: x", started_at=T0, finished_at=T0)
    assert cliente(db).get("/alerts").json()["weather_warnings"]["status"] == "SIN_DATOS"


def test_alerts_incluye_la_propagacion_activa(db):
    k = "saih_cantabrico:1424"
    guarda(db, lectura(k, minutes_ago=80, flow_m3s=10.0, thresholds=None), lectura(k, minutes_ago=65, flow_m3s=12.0, thresholds=None),
           lectura(k, minutes_ago=20, flow_m3s=15.0, thresholds=None), lectura(k, minutes_ago=5, flow_m3s=18.0, thresholds=None))
    body = cliente(db).get("/alerts").json()
    assert [p["link_id"] for p in body["propagation"]] == ["eo-ribera-pontenova", "eo-pontenova-santirso"]
    assert body["propagation"][0]["label"] == "estimación orientativa"


# ------------------------------------------------------------- /propagation

def test_propagation_devuelve_tabla_de_enlaces_con_marcas_de_estimada(db):
    body = cliente(db).get("/propagation").json()
    assert body["disclaimer"] == DISCLAIMER and body["label"] == "estimación orientativa"
    assert body["active"] == []
    ids = [l["link_id"] for l in body["links"]]
    assert "aragon-jaca-yesa" in ids and "poyo-aforo-paiporta" in ids
    assert all(l["distance_status"] in ("ESTIMADA", "SIN_DISTANCIA") and l["distance_source"] for l in body["links"])
    assert all(l["eta_hours_min"] < l["eta_hours_max"] for l in body["links"] if l["eta_available"])
    assert [l["link_id"] for l in body["links"] if not l["eta_available"]] == ["poyo-chiva-aforo", "poyo-aforo-paiporta"]
    assert body["triggers"]["levels"]["VIGILANCIA"]["rain_mm_h"] == 20.0 and body["triggers"]["consecutive_readings"] == 2


def test_propagation_activa_por_lluvia_en_estacion_aemet_enlazada(db):
    guarda(db, lectura("aemet:9201X", minutes_ago=130, level_m=None, rain_1h_mm=30.0, thresholds=None),
           lectura("aemet:9201X", minutes_ago=70, level_m=None, rain_1h_mm=32.5, thresholds=None))
    activos = cliente(db).get("/propagation").json()["active"]
    assert activos[0]["link_id"] == "aragon-jaca-yesa"
    assert activos[0]["trigger"]["type"] == "lluvia" and activos[0]["trigger"]["station_id"] == "aemet:9201X"
    assert set(activos[0]) >= {"eta_hours_min", "eta_hours_max", "distance_status", "speed_status"}


# -------------------------------------------------------------------- ciclo

class ConAvisos:
    source = "aemet"

    def __init__(self, avisos):
        self._avisos = avisos

    def fetch(self):
        return [lectura("aemet:1", level_m=None, rain_1h_mm=1.0, thresholds=None)]

    def fetch_warnings(self):
        if isinstance(self._avisos, Exception):
            raise self._avisos
        return self._avisos


def test_ciclo_guarda_avisos_del_conector_que_los_ofrece(db):
    avisos = parse_warnings((FIX / "avisos_cap.tar.gz").read_bytes())
    resumen = run_cycle([ConAvisos(avisos)], db, now=lambda: T0)
    assert resumen["aemet:avisos"] == {"ok": True, "readings": 515, "error": None}
    assert len(db.warnings("aemet")) == 515


def test_fallo_de_avisos_se_registra_sin_perder_las_lecturas(db):
    resumen = run_cycle([ConAvisos(SourceUnavailableError("tar roto"))], db, now=lambda: T0)
    assert resumen["aemet"]["ok"] is True and resumen["aemet:avisos"]["ok"] is False
    assert db.last_run("aemet:avisos")["ok"] is False
