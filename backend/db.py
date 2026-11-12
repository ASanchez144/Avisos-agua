"""Persistencia en SQLite: estaciones, histórico de lecturas y ejecuciones por fuente.

SQL deliberadamente simple (sin extensiones de SQLite) para poder migrar a
PostgreSQL. Se abre una conexión por operación: seguro entre hilos (API +
planificador).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from connectors.base import Reading, iso_utc, parse_iso_utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    station_id TEXT PRIMARY KEY,
    source     TEXT NOT NULL,
    name       TEXT NOT NULL,
    lat        REAL,
    lon        REAL,
    river      TEXT
);
CREATE TABLE IF NOT EXISTS readings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id     TEXT NOT NULL REFERENCES stations(station_id),
    timestamp_utc  TEXT,
    fetched_at_utc TEXT NOT NULL,
    flow_m3s       REAL,
    level_m        REAL,
    rain_1h_mm     REAL,
    rain_24h_mm    REAL,
    reservoir_pct  REAL,
    reservoir_hm3  REAL,
    thresholds     TEXT,
    quality        TEXT NOT NULL,
    UNIQUE (station_id, timestamp_utc)
);
CREATE INDEX IF NOT EXISTS idx_readings_station ON readings (station_id, fetched_at_utc);
CREATE TABLE IF NOT EXISTS source_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    started_at_utc  TEXT NOT NULL,
    finished_at_utc TEXT NOT NULL,
    ok              INTEGER NOT NULL,
    n_readings      INTEGER NOT NULL DEFAULT 0,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_source ON source_runs (source, id);
CREATE TABLE IF NOT EXISTS warnings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    payload        TEXT NOT NULL
);
"""

_LATEST_ORDER = "fetched_at_utc DESC, COALESCE(timestamp_utc, fetched_at_utc) DESC, id DESC"
_HISTORY_ORDER = "COALESCE(timestamp_utc, fetched_at_utc) DESC, id DESC"


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --------------------------------------------------------------- escritura
    def record_success(
        self, source: str, readings: list[Reading], started_at: datetime, finished_at: datetime
    ) -> None:
        with self._connect() as conn:
            for r in readings:
                conn.execute(
                    "INSERT INTO stations (station_id, source, name, lat, lon, river) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT (station_id) DO UPDATE SET source=excluded.source, name=excluded.name, "
                    "lat=excluded.lat, lon=excluded.lon, river=excluded.river",
                    (r.station_id, r.source, r.name, r.lat, r.lon, r.river),
                )
                conn.execute(
                    "INSERT INTO readings (station_id, timestamp_utc, fetched_at_utc, flow_m3s, level_m, "
                    "rain_1h_mm, rain_24h_mm, reservoir_pct, reservoir_hm3, thresholds, quality) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                    # misma lectura vista otra vez: no se duplica, solo se anota que sigue vigente
                    "ON CONFLICT (station_id, timestamp_utc) DO UPDATE SET fetched_at_utc=excluded.fetched_at_utc",
                    (
                        r.station_id, iso_utc(r.timestamp_utc), iso_utc(r.fetched_at_utc), r.flow_m3s,
                        r.level_m, r.rain_1h_mm, r.rain_24h_mm, r.reservoir_pct, r.reservoir_hm3,
                        json.dumps(r.thresholds) if r.thresholds else None, r.quality,
                    ),
                )
            conn.execute(
                "INSERT INTO source_runs (source, started_at_utc, finished_at_utc, ok, n_readings, error) "
                "VALUES (?,?,?,1,?,NULL)",
                (source, iso_utc(started_at), iso_utc(finished_at), len(readings)),
            )

    def record_failure(self, source: str, error: str, started_at: datetime, finished_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO source_runs (source, started_at_utc, finished_at_utc, ok, n_readings, error) "
                "VALUES (?,?,?,0,0,?)",
                (source, iso_utc(started_at), iso_utc(finished_at), error),
            )

    # ----------------------------------------------------------------- lectura
    def _to_reading(self, row: sqlite3.Row) -> Reading:
        return Reading(
            station_id=row["station_id"], source=row["source"], name=row["name"], lat=row["lat"],
            lon=row["lon"], river=row["river"], flow_m3s=row["flow_m3s"], level_m=row["level_m"],
            rain_1h_mm=row["rain_1h_mm"], rain_24h_mm=row["rain_24h_mm"],
            reservoir_pct=row["reservoir_pct"], reservoir_hm3=row["reservoir_hm3"],
            thresholds=json.loads(row["thresholds"]) if row["thresholds"] else None,
            timestamp_utc=parse_iso_utc(row["timestamp_utc"]),
            fetched_at_utc=parse_iso_utc(row["fetched_at_utc"]),
            quality=row["quality"],
        )

    def _readings(self, station_id: str, order: str, limit: int) -> list[Reading]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT r.*, s.source, s.name, s.lat, s.lon, s.river FROM readings r "
                f"JOIN stations s USING (station_id) WHERE r.station_id = ? ORDER BY {order} LIMIT ?",
                (station_id, limit),
            ).fetchall()
        return [self._to_reading(row) for row in rows]

    def latest(self, station_id: str) -> Optional[Reading]:
        rows = self._readings(station_id, _LATEST_ORDER, 1)
        return rows[0] if rows else None

    def history(self, station_id: str, limit: int = 100) -> list[Reading]:
        return self._readings(station_id, _HISTORY_ORDER, limit)

    def stations(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM stations ORDER BY station_id").fetchall()
        return [dict(row) for row in rows]

    def station(self, station_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM stations WHERE station_id = ?", (station_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _run(row: sqlite3.Row) -> dict[str, Any]:
        run = dict(row)
        run["ok"] = bool(run["ok"])
        return run

    def last_run(self, source: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_runs WHERE source = ? ORDER BY id DESC LIMIT 1", (source,)
            ).fetchone()
        return self._run(row) if row else None

    def failures(self, source: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM source_runs WHERE ok = 0"
        params: list[Any] = []
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        with self._connect() as conn:
            rows = conn.execute(query + " ORDER BY id DESC LIMIT ?", (*params, limit)).fetchall()
        return [self._run(row) for row in rows]

    # ------------------------------------------------------------------ avisos
    def replace_warnings(self, source: str, warnings: list[dict[str, Any]], fetched_at: datetime) -> None:
        """Sustituye los avisos de una fuente por la última descarga completa."""
        with self._connect() as conn:
            conn.execute("DELETE FROM warnings WHERE source = ?", (source,))
            conn.executemany(
                "INSERT INTO warnings (source, fetched_at_utc, payload) VALUES (?,?,?)",
                [(source, iso_utc(fetched_at), json.dumps(w)) for w in warnings],
            )

    def warnings(self, source: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM warnings WHERE source = ? ORDER BY id", (source,)).fetchall()
        return [json.loads(row["payload"]) for row in rows]
