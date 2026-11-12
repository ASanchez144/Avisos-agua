"""esquema inicial

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("stations",
        sa.Column("station_id", sa.Text, primary_key=True), sa.Column("source", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False), sa.Column("lat", sa.Float), sa.Column("lon", sa.Float),
        sa.Column("river", sa.Text))
    op.create_table("readings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("station_id", sa.Text, sa.ForeignKey("stations.station_id"), nullable=False),
        sa.Column("timestamp_utc", sa.Text), sa.Column("fetched_at_utc", sa.Text, nullable=False),
        sa.Column("flow_m3s", sa.Float), sa.Column("level_m", sa.Float), sa.Column("rain_1h_mm", sa.Float),
        sa.Column("rain_24h_mm", sa.Float), sa.Column("reservoir_pct", sa.Float), sa.Column("reservoir_hm3", sa.Float),
        sa.Column("thresholds", sa.Text), sa.Column("quality", sa.Text, nullable=False),
        sa.UniqueConstraint("station_id", "timestamp_utc", name="uq_readings_station_ts"))
    op.create_index("idx_readings_station", "readings", ["station_id", "fetched_at_utc"])
    op.create_index("idx_readings_ts", "readings", ["timestamp_utc"])
    op.create_table("source_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True), sa.Column("source", sa.Text, nullable=False),
        sa.Column("started_at_utc", sa.Text, nullable=False), sa.Column("finished_at_utc", sa.Text, nullable=False),
        sa.Column("ok", sa.Integer, nullable=False), sa.Column("n_readings", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text))
    op.create_index("idx_runs_source", "source_runs", ["source", "id"])
    op.create_table("warnings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True), sa.Column("source", sa.Text, nullable=False),
        sa.Column("fetched_at_utc", sa.Text, nullable=False), sa.Column("payload", sa.Text, nullable=False))
    op.create_table("request_log",
        sa.Column("key", sa.Text, primary_key=True), sa.Column("last_request_utc", sa.Text, nullable=False))


def downgrade() -> None:
    for table in ("request_log", "warnings", "source_runs", "readings", "stations"):
        op.drop_table(table)
