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
        inner = create_app(Database(url, migrate=False))  # las migraciones las aplica el colector
    outer = FastAPI(title="HidroRed España", docs_url=None, redoc_url=None)
    outer.mount("/api", inner)
    outer.mount("/", inner)
    return outer


app = build()
