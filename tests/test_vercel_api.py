"""api/index.py: la función serverless responde bajo /api y bajo /, sin planificador."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def cargar(monkeypatch, **env):
    for k in ("DATABASE_URL", "DEMO_LIVE_FALLBACK"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("api.index", None)
    spec = importlib.util.spec_from_file_location("api_index", ROOT / "api" / "index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sirve_bajo_api_y_bajo_raiz(monkeypatch, tmp_path):
    from backend.db import Database
    Database(tmp_path / "v.sqlite")  # crea el esquema, como haría el colector
    mod = cargar(monkeypatch, DATABASE_URL=str(tmp_path / "v.sqlite"))
    c = TestClient(mod.app)
    for ruta in ("/api/stations", "/stations", "/api/alerts", "/api/propagation"):
        r = c.get(ruta)
        assert r.status_code == 200 and r.json()["disclaimer"].startswith("Información no oficial"), ruta
    assert c.get("/api/stations").json()["demo"] is False


def test_sin_database_url_falla_en_claro(monkeypatch):
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        cargar(monkeypatch)


def test_modo_demo_en_vercel(monkeypatch):
    mod = cargar(monkeypatch, DEMO_LIVE_FALLBACK="true")
    body = TestClient(mod.app).get("/api/stations").json()
    assert body["demo"] is True and body["demo_notice"] == "DATOS DE DEMOSTRACIÓN"


def test_no_arranca_un_planificador_permanente():
    text = (ROOT / "api" / "index.py").read_text()
    assert "apscheduler" not in text.lower() and "build_scheduler" not in text


def test_collect_con_datos_recientes_no_hace_nada(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from backend.db import Database
    db = Database(tmp_path / "v.sqlite")
    t = datetime.now(timezone.utc)
    for s in ("saih_cantabrico", "aca", "aemet"):
        db.record_failure(s, "x", started_at=t, finished_at=t)
    mod = cargar(monkeypatch, DATABASE_URL=str(tmp_path / "v.sqlite"))
    body = TestClient(mod.app).post("/api/collect").json()
    assert body["ran"] is False and body["reason"] == "datos recientes"
