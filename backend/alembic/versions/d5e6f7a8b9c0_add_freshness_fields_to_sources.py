"""Add freshness lifecycle fields to sources.

Supports WS2 knowledge acquisition: freshness_policy, stale_after_days,
refresh_interval_days, and next_refresh_at for source lifecycle management.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("freshness_policy", sa.String(20), nullable=True, server_default="none"))
    op.add_column("sources", sa.Column("stale_after_days", sa.Integer(), nullable=True))
    op.add_column("sources", sa.Column("refresh_interval_days", sa.Integer(), nullable=True))
    op.add_column("sources", sa.Column("next_refresh_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "next_refresh_at")
    op.drop_column("sources", "refresh_interval_days")
    op.drop_column("sources", "stale_after_days")
    op.drop_column("sources", "freshness_policy")
