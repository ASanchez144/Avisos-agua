"""Ebro y Júcar: sin parser hasta que haya muestras reales. Estos tests se activan solos cuando aparecen."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from connectors.base import SourceFormatError
from connectors.pending import PENDING_SOURCES, PendingConnector

FIX = Path(__file__).resolve().parent / "fixtures"


def real_samples(source: str) -> list[Path]:
    """Respuestas reales guardadas por probe_sources.py: HTTP 200 y con contenido."""
    out = []
    for meta in (FIX / source).glob("probe_*.meta.json"):
        m = json.loads(meta.read_text())
        if m["status"] == 200 and m["bytes"] > 400:
            out.append(meta)
    return out


@pytest.mark.parametrize("source", sorted(PENDING_SOURCES))
def test_un_conector_pendiente_nunca_da_datos(source):
    with pytest.raises(SourceFormatError, match="pendiente"):
        PendingConnector(source).fetch()


def test_los_pendientes_no_estan_en_los_conectores_activos():
    for path in (Path("backend/main.py"), Path("collector/run_once.py")):
        text = (Path(__file__).resolve().parent.parent / path).read_text()
        assert "PendingConnector" not in text and "pending" not in text


def test_las_estaciones_deseadas_tienen_origen_verificado():
    assert set(PENDING_SOURCES["saih_ebro"]["wanted"]) == {"A018", "A101", "A005", "A011"}


@pytest.mark.parametrize("source", sorted(PENDING_SOURCES))
def test_hay_muestras_reales_listas_para_escribir_el_parser(source):
    samples = real_samples(source)
    if not samples:
        pytest.skip(f"{source}: esperando muestras reales (scripts/probe_sources.py desde una IP española)")
    pytest.fail(
        f"{source}: ya hay {len(samples)} muestras reales en tests/fixtures/{source}/. Escribe el parser con TDD "
        "sobre ellas (connectors/<fuente>.py con SOURCE), regístralo en tests/harness_connectors.py y elimina este aviso."
    )
