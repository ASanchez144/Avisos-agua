"""Función serverless de Vercel: API FastAPI de solo lectura sobre la base de datos (Neon).

No arranca ningún planificador: la recogida de datos la hace GitHub Actions (collector.run_once).
`/api/...` y `/...` llegan al mismo sitio, por si Vercel conserva o recorta el prefijo.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.db import Database  # noqa: E402
from backend.demo import create_demo_app  # noqa: E402


def build() -> FastAPI:
    if os.environ.get("DEMO_LIVE_FALLBACK", "").strip().lower() in ("1", "true", "yes"):
        inner = create_demo_app()
    else:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("Falta DATABASE_URL (cadena de Neon con pooler)")
        db = Database(url, migrate=False)  # las migraciones las aplica el colector

        def collector():
            # Respaldo del cron de GitHub: un ciclo dentro de la función (≈10-20 s). Abre una conexión que sí migra.
            from backend.scheduler import run_cycle
            from collector.run_once import build_connectors
            rw = Database(url)
            return run_cycle(build_connectors(rw, include_aemet=has_aemet), rw)

        # Sin AEMET_API_KEY en Vercel no se intenta AEMET (no se marca como caída: la recoge GitHub Actions).
        has_aemet = bool(os.environ.get("AEMET_API_KEY"))
        from collector.run_once import has_euskalmet
        sources = ("saih_cantabrico", "aca") + (("aemet",) if has_aemet else ()) + (("euskalmet",) if has_euskalmet() else ())
        from connectors.saih_cantabrico_cameras import SaiCameraService
        inner = create_app(db, collector=collector, collector_sources=sources, sai_cameras=SaiCameraService(db))
    outer = FastAPI(title="HidroRed España", docs_url=None, redoc_url=None)
    outer.mount("/api", inner)
    outer.mount("/", inner)
    return outer


app = build()
