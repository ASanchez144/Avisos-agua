"""Conector Hidrosur: fixture real (tabla de ríos + capa de aforos) y casos límite."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from connectors import hidrosur
from connectors.base import SourceFormatError
from engine.status import station_status

FIX = Path(__file__).parent / "fixtures" / "hidrosur"
NOW = datetime(2026, 11, 12, 13, 42, 58, tzinfo=timezone.utc)


def readings():
    return {r.station_id: r for r in hidrosur.parse(
        (FIX / "resumen_rios.html").read_bytes(), (FIX / "capa_aforos.json").read_bytes(), NOW)}


def test_fixture_real():
    rs = readings()
    assert len(rs) == 32
    r = rs["hidrosur:11"]
    assert (r.level_m, r.flow_m3s, r.river) == (0.58, 9.48, "R. Guadiaro")
    # "Datos actualizados a: 12-11-2026 14:00:00" (hora local) = 13:00 UTC
    assert r.timestamp_utc == datetime(2026, 11, 12, 13, tzinfo=timezone.utc)
    assert r.thresholds == {"yellow": 3.0, "orange": 4.0, "red": 5.0, "variable": "level_m"}


def test_estacion_sin_umbral_en_la_capa_no_tiene_semaforo():
    r = readings()["hidrosur:302"]  # la capa pone 0/0/0
    assert r.thresholds is None
    assert station_status(r, NOW)["status"] == "SIN_UMBRAL"


def test_fila_repetida_con_valores_distintos_es_suspect():
    r = readings()["hidrosur:86"]  # la tabla trae "0,00" y "n/d" para la misma estación
    assert r.quality == "SUSPECT"
    assert station_status(r, NOW)["status"] not in ("NORMAL", "VIGILANCIA", "PREALERTA", "ALERTA")


def test_sin_coordenadas_no_se_inventa_ubicacion():
    rs = readings()
    for code in ("34", "46", "58", "90", "103", "164"):
        assert f"hidrosur:{code}" not in rs
    assert all(r.lat is not None and r.lon is not None for r in rs.values())


def test_n_d_es_sin_dato_no_cero():
    table = (FIX / "resumen_rios.html").read_text(encoding="utf-8")
    _, rows = hidrosur.parse_table(table.encode())
    assert any(r["level"] == "n/d" for r in rows)
    assert hidrosur._value("n/d") == (None, False)


def test_formato_desconocido():
    with pytest.raises(SourceFormatError):
        hidrosur.parse_table(b"<html>mantenimiento</html>")
    with pytest.raises(SourceFormatError):
        hidrosur.parse_layer(b"{}")


def test_apagado_salvo_que_se_active(monkeypatch, tmp_path):
    from backend.db import Database
    from collector import run_once
    db = Database(str(tmp_path / "t.sqlite"))
    monkeypatch.delenv("HIDROSUR_ENABLED", raising=False)
    assert "hidrosur" not in [c.source for c in run_once.build_connectors(db, include_aemet=False)]
    monkeypatch.setenv("HIDROSUR_ENABLED", "1")
    assert "hidrosur" in [c.source for c in run_once.build_connectors(db, include_aemet=False)]
