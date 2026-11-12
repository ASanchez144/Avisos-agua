"""Conectores PENDIENTES: SAIH Ebro y SAIH Júcar.

No contienen parser: nunca se ha visto una respuesta real de estas fuentes desde el entorno de desarrollo
(inalcanzables o rechazadas). Escribir un parser a ciegas sería inventar campos.

Cuando existan muestras reales (scripts/probe_sources.py desde una IP española, en
tests/fixtures/saih_ebro/ y tests/fixtures/saih_jucar/), se escribe cada conector con TDD sobre ellas,
se mueve a su propio módulo con `SOURCE = "..."` y se registra en tests/harness_connectors.py.
Mientras tanto NO están en la lista de conectores activos (backend/main.py, collector/run_once.py).

(Esta constante se llama deliberadamente PENDING_SOURCES y no SOURCE para que el arnés no exija
registrar algo que todavía no emite lecturas.)
"""
from __future__ import annotations

from connectors.base import SourceFormatError

# Estaciones que interesan, solo con identificadores verificados en MITECO-ROEA (SOURCES_REPORT.md).
PENDING_SOURCES = {
    "saih_ebro": {
        "home": "https://www.saihebro.com/",
        "wanted": {"A018": "Aragón en Jaca", "A101": "Aragón en Yesa", "A005": "Aragón en Caparroso", "A011": "Ebro en Zaragoza"},
    },
    "saih_jucar": {
        "home": "https://saih.chj.es/",
        "wanted": {"AFORO RAMBLA POYO": "Rambla del Poyo (MITECO-SAIH)", "Turia": "sin código verificado todavía"},
    },
}


class PendingConnector:
    """Falla de forma explícita: una fuente sin parser no puede dar datos (ni verde)."""

    def __init__(self, source: str) -> None:
        self.source = source

    def fetch(self):
        raise SourceFormatError(
            f"{self.source}: conector pendiente. Faltan muestras reales: ejecuta scripts/probe_sources.py "
            f"desde una IP española y devuelve tests/fixtures/{self.source}/"
        )
