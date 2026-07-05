"""widen api_keys.key_hash for Argon2

Argon2id hashes are ~97 characters long (e.g. '$argon2id$v=19$m=65536,t=2,p=2$...').
The original column was String(64) sized for SHA-256 hex digests only.
Widening to String(255) accommodates both legacy SHA-256 and new Argon2 hashes
during the transparent migration window.

Revision ID: a1b2c3d4e5f6
Revises: 909d4f0919fd
Create Date: 2026-04-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '909d4f0919fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'api_keys',
        'key_hash',
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    # NOTE: downgrade will fail if any Argon2 hashes (>64 chars) are present.
    # Truncation is intentionally not performed — manually revert hashes before
    # running this downgrade.
    op.alter_column(
        'api_keys',
        'key_hash',
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
