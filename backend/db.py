"""Persistencia con SQLAlchemy Core: SQLite en local, PostgreSQL (Neon) en producción.

El mismo código y las mismas migraciones (Alembic) sirven para los dos. Se elige por
`Database(url_o_ruta)`; en producción la URL es DATABASE_URL (con pooler en Vercel).
Una conexión por operación: seguro entre hilos y en funciones serverless.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.models import readings as t_readings, request_log, source_runs, stations as t_stations, warnings as t_warnings
from connectors.base import Reading, iso_utc, parse_iso_utc

ROOT = Path(__file__).resolve().parent.parent
RETENTION_DAYS = 7


def normalize_url(value: str | Path) -> str:
    """Acepta una ruta de SQLite o una URL (postgres://, postgresql://, sqlite:///)."""
    text = str(value)
    if text.startswith("postgres://"):
        text = "postgresql://" + text[len("postgres://"):]
    if text.startswith("postgresql://"):
        return "postgresql+psycopg://" + text[len("postgresql://"):]
    if "://" in text:
        return text
    return "sqlite:///" + str(Path(text).resolve()) if not text.startswith("/") else "sqlite:///" + text


class Database:
    def __init__(self, url_or_path: str | Path, migrate: bool = True) -> None:
        self.url = normalize_url(url_or_path)
        if self.url.startswith("sqlite:///") and ":memory:" not in self.url:
            Path(self.url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        self.engine = sa.create_engine(self.url, pool_pre_ping=True)
        self.dialect = self.engine.dialect.name
        if migrate:
            self.migrate()

    def migrate(self) -> None:
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        with self.engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")

    def _insert(self, table):
        return (pg_insert if self.dialect == "postgresql" else sqlite_insert)(table)

    # --------------------------------------------------------------- escritura
    def record_success(self, source: str, readings: list[Reading], started_at: datetime, finished_at: datetime) -> None:
        with self.engine.begin() as conn:
            for r in readings:
                ins = self._insert(t_stations).values(
                    station_id=r.station_id, source=r.source, name=r.name, lat=r.lat, lon=r.lon, river=r.river)
                conn.execute(ins.on_conflict_do_update(
                    index_elements=["station_id"],
                    set_={c: ins.excluded[c] for c in ("source", "name", "lat", "lon", "river")}))
                ins = self._insert(t_readings).values(
                    station_id=r.station_id, timestamp_utc=iso_utc(r.timestamp_utc), fetched_at_utc=iso_utc(r.fetched_at_utc),
                    flow_m3s=r.flow_m3s, level_m=r.level_m, rain_1h_mm=r.rain_1h_mm, rain_24h_mm=r.rain_24h_mm,
                    reservoir_pct=r.reservoir_pct, reservoir_hm3=r.reservoir_hm3,
                    thresholds=json.dumps(r.thresholds) if r.thresholds else None, quality=r.quality)
                # misma lectura vista otra vez: no se duplica, solo se anota que sigue vigente
                conn.execute(ins.on_conflict_do_update(
                    index_elements=["station_id", "timestamp_utc"], set_={"fetched_at_utc": ins.excluded.fetched_at_utc}))
            conn.execute(source_runs.insert().values(
                source=source, started_at_utc=iso_utc(started_at), finished_at_utc=iso_utc(finished_at),
                ok=1, n_readings=len(readings), error=None))

    def record_failure(self, source: str, error: str, started_at: datetime, finished_at: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(source_runs.insert().values(
                source=source, started_at_utc=iso_utc(started_at), finished_at_utc=iso_utc(finished_at),
                ok=0, n_readings=0, error=error))

    # ----------------------------------------------------------------- lectura
    @staticmethod
    def _to_reading(row: Any) -> Reading:
        return Reading(
            station_id=row.station_id, source=row.source, name=row.name, lat=row.lat, lon=row.lon, river=row.river,
            flow_m3s=row.flow_m3s, level_m=row.level_m, rain_1h_mm=row.rain_1h_mm, rain_24h_mm=row.rain_24h_mm,
            reservoir_pct=row.reservoir_pct, reservoir_hm3=row.reservoir_hm3,
            thresholds=json.loads(row.thresholds) if row.thresholds else None,
            timestamp_utc=parse_iso_utc(row.timestamp_utc), fetched_at_utc=parse_iso_utc(row.fetched_at_utc), quality=row.quality)

    def _readings(self, station_id: str, order: list, limit: int) -> list[Reading]:
        q = (sa.select(t_readings, t_stations.c.source, t_stations.c.name, t_stations.c.lat, t_stations.c.lon, t_stations.c.river)
             .join(t_stations, t_stations.c.station_id == t_readings.c.station_id)
             .where(t_readings.c.station_id == station_id).order_by(*order).limit(limit))
        with self.engine.connect() as conn:
            return [self._to_reading(row) for row in conn.execute(q)]

    def latest(self, station_id: str) -> Optional[Reading]:
        rows = self._readings(station_id, [
            t_readings.c.fetched_at_utc.desc(),
            sa.func.coalesce(t_readings.c.timestamp_utc, t_readings.c.fetched_at_utc).desc(), t_readings.c.id.desc()], 1)
        return rows[0] if rows else None

    def latest_all(self) -> dict[str, Reading]:
        """Última lectura de TODAS las estaciones en UNA consulta (sin una consulta por estación)."""
        rn = sa.func.row_number().over(
            partition_by=t_readings.c.station_id,
            order_by=[t_readings.c.fetched_at_utc.desc(),
                      sa.func.coalesce(t_readings.c.timestamp_utc, t_readings.c.fetched_at_utc).desc(), t_readings.c.id.desc()],
        ).label("rn")
        ranked = sa.select(t_readings, rn).subquery()
        q = (sa.select(ranked, t_stations.c.source, t_stations.c.name, t_stations.c.lat, t_stations.c.lon, t_stations.c.river)
             .join(t_stations, t_stations.c.station_id == ranked.c.station_id).where(ranked.c.rn == 1))
        with self.engine.connect() as conn:
            return {row.station_id: self._to_reading(row) for row in conn.execute(q)}

    def history(self, station_id: str, limit: int = 100) -> list[Reading]:
        return self._readings(station_id, [
            sa.func.coalesce(t_readings.c.timestamp_utc, t_readings.c.fetched_at_utc).desc(), t_readings.c.id.desc()], limit)

    def stations(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(sa.select(t_stations).order_by(t_stations.c.station_id))]

    def station(self, station_id: str) -> Optional[dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(t_stations).where(t_stations.c.station_id == station_id)).first()
        return dict(row._mapping) if row else None

    @staticmethod
    def _run(row: Any) -> dict[str, Any]:
        run = dict(row._mapping)
        run["ok"] = bool(run["ok"])
        return run

    def last_run(self, source: str) -> Optional[dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(source_runs).where(source_runs.c.source == source)
                               .order_by(source_runs.c.id.desc()).limit(1)).first()
        return self._run(row) if row else None

    def failures(self, source: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        q = sa.select(source_runs).where(source_runs.c.ok == 0)
        if source is not None:
            q = q.where(source_runs.c.source == source)
        with self.engine.connect() as conn:
            return [self._run(r) for r in conn.execute(q.order_by(source_runs.c.id.desc()).limit(limit))]

    # ------------------------------------------------------------------ avisos
    def replace_warnings(self, source: str, items: list[dict[str, Any]], fetched_at: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(t_warnings.delete().where(t_warnings.c.source == source))
            if items:
                conn.execute(t_warnings.insert(), [
                    {"source": source, "fetched_at_utc": iso_utc(fetched_at), "payload": json.dumps(w)} for w in items])

    def warnings(self, source: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(sa.select(t_warnings.c.payload).where(t_warnings.c.source == source).order_by(t_warnings.c.id))
            return [json.loads(r.payload) for r in rows]

    # --------------------------------------------------------------- retención
    def purge_older_than(self, now: datetime, days: int = RETENTION_DAYS) -> dict[str, int]:
        """Borra lecturas y registros de ejecución de más de `days` días (plan gratuito: 0,5 GB)."""
        cutoff = iso_utc(now - timedelta(days=days))
        stamp = sa.func.coalesce(t_readings.c.timestamp_utc, t_readings.c.fetched_at_utc)
        with self.engine.begin() as conn:
            n_readings = conn.execute(t_readings.delete().where(stamp < cutoff)).rowcount
            n_runs = conn.execute(source_runs.delete().where(source_runs.c.finished_at_utc < cutoff)).rowcount
        return {"readings": n_readings, "source_runs": n_runs}

    # ------------------------------------------------- límite de peticiones (HTTP)
    def last_request(self, key: str) -> Optional[datetime]:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(request_log.c.last_request_utc).where(request_log.c.key == key)).first()
        return parse_iso_utc(row.last_request_utc) if row else None

    def mark_request(self, key: str, at: datetime) -> None:
        with self.engine.begin() as conn:
            ins = self._insert(request_log).values(key=key, last_request_utc=iso_utc(at))
            conn.execute(ins.on_conflict_do_update(index_elements=["key"], set_={"last_request_utc": ins.excluded.last_request_utc}))
