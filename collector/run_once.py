"""Un ciclo de recogida y termina (para GitHub Actions). `python -m collector.run_once`

Un fallo de un conector no aborta el ciclo: se registra y se sigue. Solo falla (código 1)
si no se puede usar la base de datos.
"""
from __future__ import annotations

import json
import logging
import os
import sys

from backend.db import Database
from backend.scheduler import run_cycle
from connectors.aca import AcaConnector
from connectors.aemet import AemetConnector
from connectors.euskalmet import EuskalmetConnector
from connectors.hidrosur import HidrosurConnector
from connectors.http import PoliteHttpClient
from connectors.saih_cantabrico import SaihCantabricoConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def database_url() -> str:
    return os.environ.get("DATABASE_URL") or os.environ.get("HIDRORED_DB") or "data/hidrored.sqlite"


def has_euskalmet(env=os.environ) -> bool:
    """Euskalmet necesita clave propia: sin ella no se intenta (no se pinta como caída)."""
    return bool(env.get("EUSKALMET_PRIVATE_KEY") and env.get("EUSKALMET_EMAIL")) or bool(env.get("EUSKALMET_JWT"))


def has_hidrosur(env=os.environ) -> bool:
    """Hidrosur no da permiso expreso de reutilización (docs/LEGAL.md): solo si se activa a propósito."""
    return env.get("HIDROSUR_ENABLED", "").strip() == "1"


def build_connectors(db: Database, include_aemet: bool = True, include_euskalmet: bool | None = None) -> list:
    client = PoliteHttpClient(store=db)
    connectors = [SaihCantabricoConnector(client), AcaConnector(client)]
    if include_aemet:
        connectors.append(AemetConnector(client))
    if has_euskalmet() if include_euskalmet is None else include_euskalmet:
        connectors.append(EuskalmetConnector(client))
    if has_hidrosur():
        connectors.append(HidrosurConnector(client))
    return connectors


def main() -> int:
    try:
        db = Database(database_url())
    except Exception as exc:  # sin base de datos no hay nada que hacer
        logging.error("no se pudo abrir la base de datos: %s: %s", type(exc).__name__, type(exc).__doc__ or exc)
        return 1
    summary = run_cycle(build_connectors(db), db)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
