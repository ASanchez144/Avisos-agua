"""Persistencia SQLite, API mínima y planificador."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import DISCLAIMER, create_app
from backend.db import Database
from backend.scheduler import INTERVAL_MINUTES, build_scheduler, run_cycle
from connectors.base import Reading, SourceFormatError, SourceUnavailableError
from connectors.saih_cantabrico import parse

T0 = datetime(2026, 11, 11, 11, 50, 56, tzinfo=timezone.utc)


def lectura(station="t:1", minutes_ago=5, now=T0, **kw) -> Reading:
    base = dict(
        station_id=station, source="t", name="Estación " + station, lat=43.0, lon=-5.0, river="Río",
        flow_m3s=10.0, level_m=1.0, rain_1h_mm=0.0, rain_24h_mm=2.0,
        reservoir_pct=None, reservoir_hm3=None,
        thresholds={"yellow": 2.0, "orange": 3.0, "red": 4.0, "variable": "level_m"},
        timestamp_utc=now - timedelta(minutes=minutes_ago), fetched_at_utc=now, quality="OK",
    )
    base.update(kw)
    return Reading(**base)


@pytest.fixture()
def db(tmp_path) -> Database:
    return Database(tmp_path / "hidrored.sqlite")


# ------------------------------------------------------------------ SQLite

def test_guarda_y_recupera_una_lectura_identica(db):
    r = lectura()
    db.record_success("t", [r], started_at=T0, finished_at=T0)
    assert db.latest("t:1") == r


def test_el_historico_acumula_lecturas_nuevas_y_no_duplica_la_misma(db):
    db.record_success("t", [lectura(minutes_ago=10)], started_at=T0, finished_at=T0)
    db.record_success("t", [lectura(minutes_ago=10)], started_at=T0, finished_at=T0)
    db.record_success("t", [lectura(minutes_ago=5, level_m=1.2)], started_at=T0, finished_at=T0)
    history = db.history("t:1")
    assert [h.level_m for h in history] == [1.2, 1.0]  # más reciente primero
    assert db.latest("t:1").level_m == 1.2


def test_historico_respeta_limit(db):
    for m in (30, 20, 10):
        db.record_success("t", [lectura(minutes_ago=m)], started_at=T0, finished_at=T0)
    assert len(db.history("t:1", limit=2)) == 2


def test_lectura_missing_se_guarda_y_es_la_ultima(db):
    db.record_success("t", [lectura(minutes_ago=20)], started_at=T0, finished_at=T0)
    later = T0 + timedelta(minutes=15)
    missing = lectura(now=later, quality="MISSING", timestamp_utc=None, flow_m3s=None, level_m=None,
                      rain_1h_mm=None, rain_24h_mm=None)
    db.record_success("t", [missing], started_at=later, finished_at=later)
    assert db.latest("t:1").quality == "MISSING"
    assert len(db.history("t:1")) == 2


def test_registra_fallos_por_fuente(db):
    db.record_success("t", [lectura()], started_at=T0, finished_at=T0)
    t1 = T0 + timedelta(minutes=15)
    db.record_failure("t", "SourceUnavailableError: timeout", started_at=t1, finished_at=t1)
    last = db.last_run("t")
    assert last["ok"] is False and "timeout" in last["error"]
    failures = db.failures("t")
    assert len(failures) == 1 and failures[0]["source"] == "t"
    assert db.last_run("otra") is None


def test_persiste_la_fixture_real_completa(db, cantabrico_raw, cantabrico_fetched_at):
    readings = parse(cantabrico_raw, cantabrico_fetched_at)
    db.record_success("saih_cantabrico", readings, started_at=T0, finished_at=T0)
    assert len(db.stations()) == len(readings)
    assert db.latest("saih_cantabrico:1424") == [r for r in readings if r.station_id.endswith(":1424")][0]


# --------------------------------------------------------------------- API

def cliente(db, now=T0) -> TestClient:
    return TestClient(create_app(db, now=lambda: now))


def test_stations_lista_estaciones_con_estado_y_aviso(db):
    db.record_success("t", [lectura("t:1"), lectura("t:2", level_m=3.5)], started_at=T0, finished_at=T0)
    body = cliente(db).get("/stations").json()
    assert body["disclaimer"] == DISCLAIMER == (
        "Información no oficial. En emergencia llama al 112 y sigue a AEMET y Protección Civil."
    )
    estados = {s["station_id"]: s["status"] for s in body["stations"]}
    assert estados == {"t:1": "NORMAL", "t:2": "PREALERTA"}
    assert body["stations"][0]["latest"]["level_m"] in (1.0, 3.5)


def test_station_por_id_y_404(db):
    db.record_success("t", [lectura()], started_at=T0, finished_at=T0)
    c = cliente(db)
    ok = c.get("/stations/t:1")
    assert ok.status_code == 200
    assert ok.json()["station"]["name"] == "Estación t:1"
    assert ok.json()["station"]["latest"]["timestamp_utc"] == "2026-11-11T11:45:56Z"
    assert c.get("/stations/no-existe").status_code == 404


def test_history_devuelve_lecturas_y_404(db):
    db.record_success("t", [lectura(minutes_ago=10)], started_at=T0, finished_at=T0)
    db.record_success("t", [lectura(minutes_ago=5)], started_at=T0, finished_at=T0)
    c = cliente(db)
    body = c.get("/stations/t:1/history").json()
    assert [r["timestamp_utc"] for r in body["readings"]] == ["2026-11-11T11:45:56Z", "2026-11-11T11:40:56Z"]
    assert len(c.get("/stations/t:1/history?limit=1").json()["readings"]) == 1
    assert c.get("/stations/no-existe/history").status_code == 404


def test_dato_de_hace_mas_de_60_min_sale_como_obsoleto_no_como_normal(db):
    db.record_success("t", [lectura()], started_at=T0, finished_at=T0)
    body = cliente(db, now=T0 + timedelta(minutes=70)).get("/stations/t:1").json()
    assert body["station"]["status"] == "DATO_OBSOLETO"


def test_si_la_ultima_ejecucion_de_la_fuente_fallo_todo_es_sin_datos(db):
    db.record_success("t", [lectura()], started_at=T0, finished_at=T0)
    t1 = T0 + timedelta(minutes=15)
    db.record_failure("t", "SourceUnavailableError: timeout", started_at=t1, finished_at=t1)
    s = cliente(db, now=t1).get("/stations/t:1").json()["station"]
    assert s["status"] == "SIN_DATOS"
    assert s["source_ok"] is False
    assert s["latest"]["level_m"] == 1.0  # se enseña con su fecha, pero no como estado vigente


def test_sin_umbral_oficial_la_api_dice_umbral_no_publicado(db):
    db.record_success("t", [lectura(thresholds=None)], started_at=T0, finished_at=T0)
    s = cliente(db).get("/stations/t:1").json()["station"]
    assert s["status"] == "SIN_UMBRAL"
    assert s["threshold_note"] == "umbral no publicado"


def test_suspect_no_genera_alerta_en_la_api(db):
    db.record_success("t", [lectura(level_m=9.0, quality="SUSPECT")], started_at=T0, finished_at=T0)
    assert cliente(db).get("/stations/t:1").json()["station"]["status"] == "SIN_DATOS"


# ------------------------------------------------------------ planificador

class Falso:
    def __init__(self, source, result):
        self.source, self._result = source, result

    def fetch(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_ciclo_guarda_lecturas_y_registra_exito(db):
    resumen = run_cycle([Falso("t", [lectura()])], db, now=lambda: T0)
    assert resumen == {"t": {"ok": True, "readings": 1, "error": None}}
    assert db.last_run("t")["ok"] is True
    assert db.latest("t:1") is not None


@pytest.mark.parametrize(
    "error",
    [SourceUnavailableError("timeout"), SourceFormatError("HTML cambiado"), ValueError("bug inesperado")],
)
def test_un_fallo_se_registra_y_no_detiene_a_las_demas_fuentes(db, error):
    resumen = run_cycle([Falso("mala", error), Falso("t", [lectura()])], db, now=lambda: T0)
    assert resumen["mala"]["ok"] is False
    assert type(error).__name__ in resumen["mala"]["error"]
    assert resumen["t"]["ok"] is True
    assert db.last_run("mala")["ok"] is False
    assert db.failures("mala")[0]["error"] == resumen["mala"]["error"]


def test_planificador_ejecuta_cada_15_minutos(db):
    scheduler = build_scheduler([Falso("t", [lectura()])], db)
    jobs = scheduler.get_jobs()
    assert INTERVAL_MINUTES == 15
    assert len(jobs) == 1
    assert jobs[0].trigger.interval == timedelta(minutes=15)
