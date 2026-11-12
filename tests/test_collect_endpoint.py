"""POST /collect: la web pide un ciclo si los datos tienen más de ~15 min (respaldo del cron)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.db import Database

T0 = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
FUENTES = ["saih_cantabrico", "aca", "aemet"]


def app(db, llamadas, now=T0):
    def collector():
        llamadas.append(1)
        for s in FUENTES:
            db.record_failure(s, "x", started_at=now, finished_at=now)
        return {s: {"ok": True} for s in FUENTES}
    return TestClient(create_app(db, now=lambda: now, collector=collector, collector_sources=FUENTES))


def test_sin_datos_lanza_un_ciclo(tmp_path):
    db, llamadas = Database(tmp_path / "a.sqlite"), []
    body = app(db, llamadas).post("/collect").json()
    assert body["ran"] is True and llamadas == [1] and set(body["summary"]) == set(FUENTES)


def test_con_datos_recientes_no_hace_nada(tmp_path):
    db, llamadas = Database(tmp_path / "a.sqlite"), []
    for s in FUENTES:
        db.record_failure(s, "x", started_at=T0 - timedelta(minutes=5), finished_at=T0 - timedelta(minutes=5))
    body = app(db, llamadas).post("/collect").json()
    assert body["ran"] is False and llamadas == [] and body["oldest_minutes"] == 5
    assert body["sources"] == list(FUENTES)  # solo nombres de fuente, nunca claves


def test_si_una_fuente_lleva_mas_de_14_min_se_lanza(tmp_path):
    db, llamadas = Database(tmp_path / "a.sqlite"), []
    db.record_failure("aca", "x", started_at=T0 - timedelta(minutes=30), finished_at=T0 - timedelta(minutes=30))
    for s in ("saih_cantabrico", "aemet"):
        db.record_failure(s, "x", started_at=T0 - timedelta(minutes=2), finished_at=T0 - timedelta(minutes=2))
    assert app(db, llamadas).post("/collect").json()["ran"] is True


def test_sin_colector_configurado_no_hace_nada(tmp_path):
    body = TestClient(create_app(Database(tmp_path / "a.sqlite"), now=lambda: T0)).post("/collect").json()
    assert body == {"ran": False, "reason": "recogida no disponible en este despliegue", **{k: body[k] for k in ("disclaimer", "generated_at_utc", "demo")}}


def test_un_fallo_del_colector_no_tumba_la_api(tmp_path):
    def roto():
        raise RuntimeError("boom")
    c = TestClient(create_app(Database(tmp_path / "a.sqlite"), now=lambda: T0, collector=roto, collector_sources=FUENTES))
    body = c.post("/collect").json()
    assert body["ran"] is False and "RuntimeError" in body["reason"]
    assert c.get("/stations").status_code == 200


def test_collect_acepta_get_para_programadores_externos(tmp_path):
    db, llamadas = Database(tmp_path / "a.sqlite"), []
    body = app(db, llamadas).get("/collect").json()
    assert body["ran"] is True and llamadas == [1]
