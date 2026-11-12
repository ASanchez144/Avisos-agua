"""Conector Euskalmet: fixture real (API) frente a la web oficial y casos límite."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import harness_connectors as h
from connectors import euskalmet
from connectors.base import RateLimitedError, SourceFormatError, SourceUnavailableError
from connectors.http import HttpResult

FIX = Path(__file__).parent / "fixtures" / "euskalmet"
NOW = h._eus_now()


def fixture_readings():
    return {r.station_id: r for r in h._eus_parse(h._eus_responses(), euskalmet.load_inventory())}


def hour_payload(start: datetime, values: list) -> bytes:
    ms = int(start.timestamp() * 1000)
    slots = [{"rangeDesc": f"{start.hour:02d}:{m:02d}"} for m in range(0, 60, 10)]
    return json.dumps({"dateRange": f"Date:({ms}..{ms + 3599999})", "slots": slots, "values": values}).encode()


def test_fixture_real_48_estaciones_de_nivel():
    readings = fixture_readings()
    assert len(readings) == 48
    ok = [r for r in readings.values() if r.quality == "OK"]
    assert len(ok) == 47
    for r in readings.values():
        assert r.flow_m3s is None and r.rain_1h_mm is None and r.rain_24h_mm is None and r.thresholds is None
        assert r.timestamp_utc is not None and r.timestamp_utc.minute % 10 == 0


def test_cota_absoluta_no_se_corrige_y_queda_suspect():
    r = fixture_readings()["euskalmet:C00B"]  # Tobillas publica 694.13 m: cota, no calado
    assert r.level_m == 694.13 and r.quality == "SUSPECT"


def test_todos_los_tramos_comunes_coinciden_con_la_web_oficial():
    api: dict[tuple[str, datetime], float] = {}
    for path, payload in h._eus_responses().items():
        start = datetime.fromtimestamp(int(payload["dateRange"][6:-1].split("..")[0]) / 1000, timezone.utc)
        for i, v in enumerate(payload["values"]):
            if v is not None:
                api[(f"euskalmet:{path.split('/')[3]}", start + timedelta(minutes=10 * i))] = v
    compared = 0
    for official in h._eus_official_values():
        key = (official.station_id, official.timestamp_utc)
        if key in api:
            assert api[key] == float(official.shown), f"{key}: API={api[key]} web={official.shown}"
            compared += 1
    assert compared >= 8, compared


def test_ultimo_tramo_con_dato_y_su_hora_utc():
    start = datetime(2026, 11, 12, 13, tzinfo=timezone.utc)
    ts, value, bad = euskalmet.latest_slot(hour_payload(start, [2.63, 2.76, None, None, None, None]))
    assert (ts, value, bad) == (start + timedelta(minutes=10), 2.76, False)


def test_hora_sin_datos_no_inventa_nada():
    start = datetime(2026, 11, 12, 13, tzinfo=timezone.utc)
    assert euskalmet.latest_slot(hour_payload(start, [None] * 6)) == (None, None, False)


def test_formato_desconocido_es_error_de_formato():
    with pytest.raises(SourceFormatError):
        euskalmet.latest_slot(b'{"values": [1.0]}')
    with pytest.raises(SourceFormatError):
        euskalmet.latest_slot(b"<html>")


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def request(self, method, url, data=None, headers=None):
        self.calls.append((url, headers))
        outcome = self.responses(url)
        if isinstance(outcome, Exception):
            raise outcome
        return HttpResult(outcome, NOW)


STATION = {"id": "C084", "name": "Behobia", "municipality": "Irun", "lat": 43.346, "lon": -1.76117,
           "level_sensor": "RA01", "level_measure": "sheet_level_3"}
ENV = {"EUSKALMET_JWT": "a.b.c"}


def test_si_la_hora_actual_aun_no_tiene_dato_usa_la_anterior():
    now = datetime(2026, 11, 12, 13, 3, tzinfo=timezone.utc)
    current, previous = now.replace(minute=0), now.replace(minute=0) - timedelta(hours=1)

    def answer(url):
        return hour_payload(current, [None] * 6) if url.endswith("/13") else hour_payload(previous, [2.0] * 6)
    client = FakeClient(answer)
    [r] = euskalmet.EuskalmetConnector(client, [STATION], now=lambda: now, env=ENV).fetch()
    assert r.level_m == 2.0 and r.timestamp_utc == previous + timedelta(minutes=50)
    assert [u.rsplit("/", 1)[1] for u, _ in client.calls] == ["13", "12"]
    assert client.calls[0][1] == {"Authorization": "Bearer a.b.c"}


def test_con_dato_en_la_hora_actual_no_pide_la_anterior():
    now = datetime(2026, 11, 12, 13, 25, tzinfo=timezone.utc)
    client = FakeClient(lambda url: hour_payload(now.replace(minute=0), [1.0, 1.1, None, None, None, None]))
    [r] = euskalmet.EuskalmetConnector(client, [STATION], now=lambda: now, env=ENV).fetch()
    assert len(client.calls) == 1 and r.level_m == 1.1


def test_si_ninguna_estacion_responde_es_sin_datos():
    client = FakeClient(lambda url: SourceUnavailableError("HTTP 503"))
    with pytest.raises(SourceUnavailableError):
        euskalmet.EuskalmetConnector(client, [STATION], env=ENV).fetch()


def test_limite_de_peticiones_se_propaga_para_saltar_el_ciclo():
    client = FakeClient(lambda url: RateLimitedError("15 min"))
    with pytest.raises(RateLimitedError):
        euskalmet.EuskalmetConnector(client, [STATION], env=ENV).fetch()


def test_sin_credenciales_no_hay_peticion_y_es_sin_datos():
    client = FakeClient(lambda url: AssertionError("no debía pedir"))
    with pytest.raises(SourceUnavailableError):
        euskalmet.EuskalmetConnector(client, [STATION], env={}).fetch()
    assert client.calls == []


def test_con_clave_privada_firma_un_jwt_nuevo():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    header = euskalmet.auth_headers({"EUSKALMET_PRIVATE_KEY": pem, "EUSKALMET_EMAIL": "a@b.es"})["Authorization"]
    assert header.startswith("Bearer ey") and header.count(".") == 2


def test_inventario_sin_claves_y_coordenadas_en_euskadi():
    text = (euskalmet.INVENTORY).read_text()
    assert "BEGIN" not in text and "Bearer" not in text
    for s in euskalmet.load_inventory():
        assert 42.4 < s["lat"] < 43.5 and -3.5 < s["lon"] < -1.7, s
        assert s["level_measure"].startswith("sheet_level_")


def test_colector_solo_incluye_euskalmet_con_credenciales(monkeypatch, tmp_path):
    from backend.db import Database
    from collector import run_once
    db = Database(str(tmp_path / "t.sqlite"))
    for var in ("EUSKALMET_PRIVATE_KEY", "EUSKALMET_EMAIL", "EUSKALMET_JWT"):
        monkeypatch.delenv(var, raising=False)
    assert "euskalmet" not in [c.source for c in run_once.build_connectors(db, include_aemet=False)]
    monkeypatch.setenv("EUSKALMET_PRIVATE_KEY", "x")
    assert not run_once.has_euskalmet()  # falta el email
    monkeypatch.setenv("EUSKALMET_EMAIL", "a@b.es")
    assert "euskalmet" in [c.source for c in run_once.build_connectors(db, include_aemet=False)]
