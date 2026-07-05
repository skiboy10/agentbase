"""add agents.api_key_prefix and index key-prefix lookup columns

Revision ID: c5d6e7f8a9b0
Revises: a2b3c4d5e6f7
Create Date: 2026-07-04

Background (#184): Agent API key validation fetched every public agent with a
key set and ran Argon2 verification against each candidate — any invalid key
cost N Argon2 hashes. Storing an indexed prefix of the plaintext key (a tiny,
non-secret fraction of it) lets validation narrow to ~1 candidate before any
hashing. The column is nullable: keys issued before this migration have no
prefix and are backfilled opportunistically on their next successful
validation; until then validation falls back to the legacy scan.

Also indexes the pre-existing api_keys.key_prefix column, which the platform
key lookup already filters on but which had no index.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("api_key_prefix", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_agents_api_key_prefix", "agents", ["api_key_prefix"], unique=False
    )
    op.create_index(
        "ix_api_keys_key_prefix", "api_keys", ["key_prefix"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_agents_api_key_prefix", table_name="agents")
    op.drop_column("agents", "api_key_prefix")
