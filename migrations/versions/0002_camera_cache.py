"""caché de cámaras

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("camera_cache",
        sa.Column("code", sa.Text, primary_key=True), sa.Column("payload", sa.Text, nullable=False),
        sa.Column("fetched_at_utc", sa.Text, nullable=False))


def downgrade() -> None:
    op.drop_table("camera_cache")
