"""Utilidades comunes de test: carga de fixtures reales de la Fase 0."""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"
CANTABRICO_FIXTURE = FIXTURES / "saih_cantabrico" / "peticion_cincominutal_todas.json"
CANTABRICO_FETCHED_AT = FIXTURES / "saih_cantabrico" / "peticion_cincominutal_todas.fetched_at_utc.txt"


@pytest.fixture(scope="session")
def cantabrico_raw() -> bytes:
    return CANTABRICO_FIXTURE.read_bytes()


@pytest.fixture(scope="session")
def cantabrico_fetched_at() -> datetime:
    text = CANTABRICO_FETCHED_AT.read_text().strip()
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@pytest.fixture()
def cantabrico_payload(cantabrico_raw) -> dict:
    """Copia mutable del payload real, para inyectar casos límite."""
    return copy.deepcopy(json.loads(cantabrico_raw))


def feature_by_code(payload: dict, code: str) -> dict:
    for feat in payload["data"]["features"]:
        if feat["properties"].get("codigo_general") == code:
            return feat
    raise KeyError(code)


def only_feature(payload: dict, code: str) -> bytes:
    """Payload real reducido a una sola estación (ya modificada por el test)."""
    feat = feature_by_code(payload, code)
    payload["data"]["features"] = [feat]
    return json.dumps(payload).encode()
