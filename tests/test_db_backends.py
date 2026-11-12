"""Capa de base de datos: SQLite siempre; PostgreSQL si HIDRORED_TEST_PG_URL está definida."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.db import Database, normalize_url
from connectors.base import RateLimitedError, Reading, SourceUnavailableError
from connectors.http import PoliteHttpClient
from backend.scheduler import run_cycle

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
PG = os.environ.get("HIDRORED_TEST_PG_URL")


def lectura(station="t:1", minutes_ago=5, now=T0, **kw) -> Reading:
    base = dict(
        station_id=station, source="t", name="Est " + station, lat=43.0, lon=-5.0, river="Río",
        flow_m3s=10.0, level_m=1.0, rain_1h_mm=0.0, rain_24h_mm=2.0, reservoir_pct=None, reservoir_hm3=None,
        thresholds={"yellow": 2.0, "orange": 3.0, "red": 4.0, "variable": "level_m"},
        timestamp_utc=now - timedelta(minutes=minutes_ago), fetched_at_utc=now, quality="OK",
    )
    base.update(kw)
    return Reading(**base)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(not PG, reason="sin HIDRORED_TEST_PG_URL"))])
def db(request, tmp_path):
    if request.param == "sqlite":
        yield Database(tmp_path / "x.sqlite")
        return
    import sqlalchemy as sa
    engine = sa.create_engine(normalize_url(PG))
    with engine.begin() as c:
        c.execute(sa.text("DROP SCHEMA public CASCADE"))
        c.execute(sa.text("CREATE SCHEMA public"))
    engine.dispose()
    yield Database(PG)


def test_normaliza_urls_de_neon_y_rutas():
    assert normalize_url("postgresql://u:p@h/db?sslmode=require").startswith("postgresql+psycopg://")
    assert normalize_url("postgres://u:p@h/db").startswith("postgresql+psycopg://")
    assert normalize_url("/tmp/x.sqlite") == "sqlite:////tmp/x.sqlite"
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_guarda_recupera_y_no_duplica(db):
    r = lectura()
    db.record_success("t", [r], started_at=T0, finished_at=T0)
    db.record_success("t", [r], started_at=T0, finished_at=T0)
    assert db.latest("t:1") == r
    assert len(db.history("t:1")) == 1


def test_historico_orden_y_limite(db):
    for m in (30, 20, 10):
        db.record_success("t", [lectura(minutes_ago=m, level_m=m / 10)], started_at=T0, finished_at=T0)
    assert [h.level_m for h in db.history("t:1")] == [1.0, 2.0, 3.0]
    assert len(db.history("t:1", limit=2)) == 2


def test_fallos_avisos_y_estaciones(db):
    db.record_success("t", [lectura()], started_at=T0, finished_at=T0)
    db.record_failure("t", "SourceUnavailableError: x", started_at=T0, finished_at=T0)
    assert db.last_run("t")["ok"] is False and len(db.failures("t")) == 1
    db.replace_warnings("aemet", [{"level": "rojo", "polygons": [[[1.0, 2.0]]]}], fetched_at=T0)
    db.replace_warnings("aemet", [{"level": "naranja"}], fetched_at=T0)
    assert db.warnings("aemet") == [{"level": "naranja"}]
    assert [s["station_id"] for s in db.stations()] == ["t:1"]
    assert db.station("no") is None


def test_retencion_borra_lecturas_de_mas_de_7_dias_y_conserva_el_resto(db):
    db.record_success("t", [lectura(minutes_ago=60 * 24 * 8)], started_at=T0, finished_at=T0)
    db.record_success("t", [lectura(minutes_ago=60 * 24 * 6)], started_at=T0, finished_at=T0)
    db.record_success("t", [lectura(minutes_ago=5)], started_at=T0, finished_at=T0)
    borradas = db.purge_older_than(T0, days=7)
    assert borradas["readings"] == 1
    assert len(db.history("t:1")) == 2


def test_retencion_tambien_limpia_el_registro_de_ejecuciones_antiguo(db):
    old = T0 - timedelta(days=9)
    db.record_failure("t", "x", started_at=old, finished_at=old)
    db.record_success("t", [lectura()], started_at=T0, finished_at=T0)
    assert db.purge_older_than(T0, days=7)["source_runs"] == 1
    assert db.last_run("t")["ok"] is True


def test_limite_por_recurso_se_guarda_en_la_base_de_datos(db):
    assert db.last_request("k") is None
    db.mark_request("k", T0)
    db.mark_request("k", T0 + timedelta(minutes=1))
    assert db.last_request("k") == T0 + timedelta(minutes=1)


def test_el_limite_sobrevive_a_un_reinicio_del_cliente(db):
    llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request.url.path)
        return httpx.Response(404) if request.url.path == "/robots.txt" else httpx.Response(200, content=b"x")

    now = [T0]
    def cliente():  # un cliente nuevo = proceso reiniciado (sin caché en memoria)
        return PoliteHttpClient(transport=httpx.MockTransport(handler), now=lambda: now[0], store=db)

    cliente().request("GET", "https://e.test/datos")
    now[0] = T0 + timedelta(minutes=10)
    with pytest.raises(RateLimitedError):
        cliente().request("GET", "https://e.test/datos")
    assert llamadas.count("/datos") == 1
    now[0] = T0 + timedelta(minutes=15, seconds=1)
    cliente().request("GET", "https://e.test/datos")
    assert llamadas.count("/datos") == 2


def test_un_ciclo_limitado_no_se_registra_como_fallo_ni_borra_datos(db):
    class Limitada:
        source = "t"
        def fetch(self):
            raise RateLimitedError("quedan 5 min")

    db.record_success("t", [lectura()], started_at=T0, finished_at=T0)
    out = run_cycle([Limitada()], db, now=lambda: T0)
    assert out["t"] == {"ok": True, "readings": 0, "error": None, "skipped": "límite de 15 min"}
    assert db.last_run("t")["ok"] is True and db.latest("t:1") is not None


def test_el_ciclo_purga_la_base_de_datos(db):
    db.record_success("t", [lectura(minutes_ago=60 * 24 * 9)], started_at=T0, finished_at=T0)

    class Vacia:
        source = "t"
        def fetch(self):
            return [lectura(minutes_ago=1)]

    run_cycle([Vacia()], db, now=lambda: T0)
    assert len(db.history("t:1")) == 1
