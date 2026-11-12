"""Modo DEMO_LIVE_FALLBACK: datos de ejemplo, siempre marcados, nunca mezclados con reales."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.db import Database
from backend.demo import DEMO_NOTICE, create_demo_app

NOW = datetime(2026, 11, 11, 12, 7, 30, tzinfo=timezone.utc)


def demo() -> TestClient:
    return TestClient(create_demo_app(now=lambda: NOW))


def test_la_api_real_dice_demo_false(tmp_path):
    body = TestClient(create_app(Database(tmp_path / "x.sqlite"), now=lambda: NOW)).get("/stations").json()
    assert body["demo"] is False


def test_todas_las_respuestas_demo_van_marcadas():
    c = demo()
    for ruta in ("/stations", "/stations/demo:cabecera", "/stations/demo:cabecera/history", "/alerts", "/propagation"):
        body = c.get(ruta).json()
        assert body["demo"] is True, ruta
        assert body["demo_notice"] == DEMO_NOTICE == "DATOS DE DEMOSTRACIÓN"


def test_las_estaciones_demo_no_pueden_confundirse_con_reales():
    estaciones = demo().get("/stations").json()["stations"]
    assert len(estaciones) >= 8
    assert all(s["source"] == "demo" and s["station_id"].startswith("demo:") for s in estaciones)
    assert all(s["name"].startswith("DEMO · ") for s in estaciones)


def test_la_demo_ensena_todos_los_estados_posibles():
    estados = {s["status"] for s in demo().get("/stations").json()["stations"]}
    assert estados == {"NORMAL", "VIGILANCIA", "PREALERTA", "ALERTA", "SIN_DATOS", "DATO_OBSOLETO", "SIN_UMBRAL"}


def test_la_demo_tiene_historico_con_lluvia_y_caudal_reciente():
    lecturas = demo().get("/stations/demo:cabecera/history?limit=200").json()["readings"]
    assert len(lecturas) >= 24
    assert lecturas[0]["timestamp_utc"] == "2026-11-11T12:05:00Z"  # relativo a "ahora"
    assert any(r["rain_1h_mm"] for r in lecturas) and all(r["flow_m3s"] is not None for r in lecturas)


def test_la_demo_tiene_alerta_temprana_con_rango_y_aviso_meteorologico():
    body = demo().get("/alerts").json()
    assert [p["link_id"] for p in body["propagation"]][:1] == ["demo-cabecera-medio"]
    assert body["propagation"][0]["eta_hours_min"] < body["propagation"][0]["eta_hours_max"]
    assert body["station_alerts"][0]["status"] == "ALERTA"
    aviso = body["weather_warnings"]["items"][0]
    assert aviso["headline"].startswith("DEMO · ") and aviso["polygons"]


def test_main_en_modo_demo_no_arranca_conectores(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_LIVE_FALLBACK", "true")
    monkeypatch.setenv("HIDRORED_DB", str(tmp_path / "no-debe-usarse.sqlite"))
    import importlib

    import backend.main as main
    main = importlib.reload(main)
    try:
        assert main.DEMO is True and main.connectors == []
        with TestClient(main.app) as c:
            assert c.get("/stations").json()["demo"] is True
    finally:
        monkeypatch.delenv("DEMO_LIVE_FALLBACK")
        importlib.reload(main)
