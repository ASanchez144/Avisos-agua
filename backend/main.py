"""Punto de entrada: uvicorn backend.main:app

DEMO_LIVE_FALLBACK=true  -> datos de demostración (sin fuentes reales, sin base de datos).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from backend.app import create_app
from backend.db import Database
from backend.demo import create_demo_app
from backend.scheduler import build_scheduler
from connectors.aca import AcaConnector
from connectors.aemet import AemetConnector
from connectors.http import PoliteHttpClient
from connectors.saih_cantabrico import SaihCantabricoConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DEMO = os.environ.get("DEMO_LIVE_FALLBACK", "").strip().lower() in ("1", "true", "yes", "si", "sí")

if DEMO:
    logging.getLogger(__name__).warning("MODO DEMOSTRACIÓN: no se consultan fuentes reales")
    db = None
    connectors: list = []
    app = create_demo_app()
else:
    db = Database(os.environ.get("DATABASE_URL") or os.environ.get("HIDRORED_DB", "data/hidrored.sqlite"))
    client = PoliteHttpClient(store=db)
    # AEMET necesita AEMET_API_KEY; sin ella su ciclo queda registrado como fallo (SIN_DATOS), no se oculta.
    connectors = [SaihCantabricoConnector(client), AcaConnector(client), AemetConnector(client)]

    @asynccontextmanager
    async def lifespan(_app):
        scheduler = None
        if os.environ.get("HIDRORED_DISABLE_SCHEDULER") != "1":
            scheduler = build_scheduler(connectors, db)
            scheduler.start()
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = create_app(db, lifespan=lifespan)
