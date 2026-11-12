"""Esquema de la base de datos (SQLAlchemy Core). Las migraciones de Alembic lo reflejan."""
import sqlalchemy as sa

metadata = sa.MetaData()

stations = sa.Table(
    "stations", metadata,
    sa.Column("station_id", sa.Text, primary_key=True),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("lat", sa.Float), sa.Column("lon", sa.Float), sa.Column("river", sa.Text),
)
readings = sa.Table(
    "readings", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("station_id", sa.Text, sa.ForeignKey("stations.station_id"), nullable=False),
    sa.Column("timestamp_utc", sa.Text), sa.Column("fetched_at_utc", sa.Text, nullable=False),
    sa.Column("flow_m3s", sa.Float), sa.Column("level_m", sa.Float),
    sa.Column("rain_1h_mm", sa.Float), sa.Column("rain_24h_mm", sa.Float),
    sa.Column("reservoir_pct", sa.Float), sa.Column("reservoir_hm3", sa.Float),
    sa.Column("thresholds", sa.Text), sa.Column("quality", sa.Text, nullable=False),
    sa.UniqueConstraint("station_id", "timestamp_utc", name="uq_readings_station_ts"),
)
sa.Index("idx_readings_station", readings.c.station_id, readings.c.fetched_at_utc)
sa.Index("idx_readings_ts", readings.c.timestamp_utc)
source_runs = sa.Table(
    "source_runs", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("started_at_utc", sa.Text, nullable=False), sa.Column("finished_at_utc", sa.Text, nullable=False),
    sa.Column("ok", sa.Integer, nullable=False), sa.Column("n_readings", sa.Integer, nullable=False, server_default="0"),
    sa.Column("error", sa.Text),
)
sa.Index("idx_runs_source", source_runs.c.source, source_runs.c.id)
warnings = sa.Table(
    "warnings", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("source", sa.Text, nullable=False), sa.Column("fetched_at_utc", sa.Text, nullable=False),
    sa.Column("payload", sa.Text, nullable=False),
)
request_log = sa.Table(  # límite de 1 petición/15 min por recurso, persistente
    "request_log", metadata,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("last_request_utc", sa.Text, nullable=False),
)
