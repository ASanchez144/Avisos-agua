"""API: GET /stations, /stations/{id}, /stations/{id}/history, /alerts, /propagation."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Query

from backend.cameras import CameraChecker
from backend.db import Database
from connectors.base import iso_utc, parse_iso_utc
from engine.cameras import CameraConfig, load_cameras
from engine.geo import haversine_km
from engine.propagation import LABEL, LinkTable, describe_links, evaluate, load_links
from engine.status import ALERTA, PREALERTA, VIGILANCIA, station_status

DEFAULT_LINKS = Path(__file__).resolve().parent.parent / "engine" / "river_links.yaml"
DEFAULT_CAMERAS = Path(__file__).resolve().parent.parent / "engine" / "cameras.yaml"
CAMERA_REFRESH_SECONDS = 120
SEVERITY = {ALERTA: 0, PREALERTA: 1, VIGILANCIA: 2}
WARNING_LEVELS = {"rojo": 0, "naranja": 1, "amarillo": 2}
HISTORY_FOR_TRIGGERS = 60  # lecturas por estación que mira el motor de propagación

DEMO_NOTICE = "DATOS DE DEMOSTRACIÓN"
DISCLAIMER = "Información no oficial. En emergencia llama al 112 y sigue a AEMET y Protección Civil."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_app(
    db: Any, now: Callable[[], datetime] = _utcnow, lifespan: Any = None, links: Optional[LinkTable] = None,
    demo: bool = False, cameras: Optional[CameraConfig] = None, camera_checker: Optional[CameraChecker] = None,
    sai_cameras: Any = None, collector: Optional[Callable[[], dict[str, Any]]] = None,
    collector_sources: tuple[str, ...] | list[str] = (), collect_every_minutes: int = 14,
) -> FastAPI:
    app = FastAPI(title="HidroRed España", description=DISCLAIMER, lifespan=lifespan)
    table = links or load_links(DEFAULT_LINKS)
    camera_cfg = cameras or (CameraConfig(3.0, 20, ()) if demo else load_cameras(DEFAULT_CAMERAS))
    checker = camera_checker or CameraChecker(stale_after_minutes=camera_cfg.stale_after_minutes)
    sai = sai_cameras  # se activa explícitamente en backend/main.py y api/index.py (los tests no tocan la red)

    def propagation_now() -> list[dict[str, Any]]:
        return evaluate(table, lambda station_id: db.history(station_id, limit=HISTORY_FOR_TRIGGERS), now())

    def weather_warnings() -> dict[str, Any]:
        """Avisos AEMET vigentes (amarillo o superior). Sin descarga válida: SIN_DATOS, nunca "0 avisos"."""
        run = db.last_run("aemet:avisos")
        if run is None and not db.warnings("aemet"):
            return {"status": "SIN_DATOS", "source": "AEMET", "items": []}
        if run is not None and not run["ok"]:
            return {"status": "SIN_DATOS", "source": "AEMET", "items": []}
        current = iso_utc(now())
        items = [
            w for w in db.warnings("aemet")
            if w.get("level") in WARNING_LEVELS and (w.get("expires") or "") > current
        ]
        items.sort(key=lambda w: (WARNING_LEVELS[w["level"]], w.get("onset") or ""))
        return {"status": "OK", "source": "AEMET", "items": items}

    def source_ok(source: str, cache: dict[str, bool]) -> bool:
        if source not in cache:
            run = db.last_run(source)
            cache[source] = run is None or run["ok"]
        return cache[source]

    def camera_ids() -> set[str]:
        try:
            return sai.station_ids() if sai is not None else set()
        except Exception:  # sin lista de cámaras la API sigue funcionando
            return set()

    def view(station: dict[str, Any], cache: dict[str, bool], latest_map: Optional[dict[str, Any]] = None,
             cams: Optional[set[str]] = None) -> dict[str, Any]:
        latest = latest_map.get(station["station_id"]) if latest_map is not None else db.latest(station["station_id"])
        ok = source_ok(station["source"], cache)
        return {
            **station,
            **station_status(latest, now(), source_ok=ok),
            "source_ok": ok,
            "has_camera": station["station_id"] in (cams or set()),
            "latest": latest.to_dict() if latest else None,
        }

    def envelope(**payload: Any) -> dict[str, Any]:
        marks: dict[str, Any] = {"demo": demo}
        if demo:
            marks["demo_notice"] = DEMO_NOTICE
        return {"disclaimer": DISCLAIMER, "generated_at_utc": iso_utc(now()), **marks, **payload}

    def find(station_id: str) -> dict[str, Any]:
        station = db.station(station_id)
        if station is None:
            raise HTTPException(status_code=404, detail="estación no encontrada")
        return station

    @app.get("/stations")
    def stations() -> dict[str, Any]:
        cache: dict[str, bool] = {}
        latest = db.latest_all() if hasattr(db, "latest_all") else None
        cams = camera_ids()
        return envelope(stations=[view(s, cache, latest, cams) for s in db.stations()])

    @app.get("/stations/{station_id}/history")
    def history(station_id: str, limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        find(station_id)
        readings = db.history(station_id, limit=limit)
        return envelope(station_id=station_id, readings=[r.to_dict() for r in readings])

    @app.get("/stations/{station_id}")
    def station(station_id: str) -> dict[str, Any]:
        return envelope(station=view(find(station_id), {}, None, camera_ids()))

    @app.get("/stations/{station_id}/camera")
    def station_camera(station_id: str) -> dict[str, Any]:
        """Cámara verificada más cercana (<3 km) para VER el cauce. Sin análisis: solo hotlink y estado de la imagen."""
        station = find(station_id)
        cam = camera_cfg.for_station(station_id)
        if cam is not None and station.get("lat") is not None:
            distance = haversine_km(station["lat"], station["lon"], cam.lat, cam.lon)
            if distance > camera_cfg.max_distance_km:
                cam = None
        else:
            distance = None
        if cam is None and sai is not None:
            official = sai.camera(station_id)  # cámara oficial en la propia estación de aforo
            if official is not None:
                return envelope(camera=official)
        if cam is None:
            return envelope(camera=None, reason="No hay ninguna cámara verificada a menos de "
                            f"{camera_cfg.max_distance_km:g} km que enfoque el cauce o el puente.")
        return envelope(camera={
            "id": cam.id, "image_url": cam.image_url, "origin_url": cam.origin_url, "distance_km": round(distance, 2),
            "focus_verified": True, "verified_by": cam.verified_by, "refresh_seconds": CAMERA_REFRESH_SECONDS,
            "kind": "trafico", "source_label": "Cámara de tráfico de la DGT",
            "status": checker.status(cam.image_url),
        })

    @app.get("/cameras/{camera_id}/status")
    def camera_status(camera_id: str) -> dict[str, Any]:
        cam = camera_cfg.get(camera_id)  # solo ids de la lista curada: no es un proxy abierto
        if cam is None:
            raise HTTPException(status_code=404, detail="cámara no encontrada")
        return envelope(camera_id=camera_id, **checker.status(cam.image_url))

    @app.api_route("/collect", methods=["GET", "POST"])
    def collect() -> dict[str, Any]:
        """Lanza un ciclo de recogida si los datos tienen más de ~15 min. Respaldo del cron: la propia web lo
        pide al abrirse. Seguro ante abusos: el límite de 1 petición/15 min por recurso está en la base de datos."""
        if collector is None:
            return envelope(ran=False, reason="recogida no disponible en este despliegue")
        current = now()
        ages = []
        for source in collector_sources:
            run = db.last_run(source)
            finished = parse_iso_utc(run["finished_at_utc"]) if run else None
            ages.append(None if finished is None else int((current - finished).total_seconds() // 60))
        if ages and all(a is not None and a < collect_every_minutes for a in ages):
            return envelope(ran=False, reason="datos recientes", oldest_minutes=max(ages))
        try:
            summary = collector()
        except Exception as exc:  # la API sigue respondiendo aunque falle la recogida
            return envelope(ran=False, reason=f"{type(exc).__name__}: la recogida falló")
        return envelope(ran=True, summary=summary)

    @app.get("/alerts")
    def alerts() -> dict[str, Any]:
        cache: dict[str, bool] = {}
        latest = db.latest_all() if hasattr(db, "latest_all") else None
        views = [view(s, cache, latest) for s in db.stations()]
        over = sorted((v for v in views if v["status"] in SEVERITY), key=lambda v: (SEVERITY[v["status"]], v["station_id"]))
        return envelope(station_alerts=over, weather_warnings=weather_warnings(), propagation=propagation_now())

    @app.get("/propagation")
    def propagation() -> dict[str, Any]:
        return envelope(
            label=LABEL, triggers=asdict(table.triggers), links=describe_links(table), active=propagation_now()
        )

    return app
