"""encrypt existing plaintext provider api keys at rest

Revision ID: a2b3c4d5e6f7
Revises: f8b9c0d1e2a3
Create Date: 2026-06-24

Background: `provider_configs.api_key_encrypted` historically held PLAINTEXT
despite its name. The write/read paths now Fernet-encrypt keys (see
app.core.encryption). This data migration encrypts any pre-existing plaintext
rows so the column is uniformly ciphertext. Rows that are already encrypted
(``gAAAAA`` prefix) and empty/null rows are left untouched, making the
migration idempotent. At time of writing only the keyless ``ollama`` provider
is typically configured, so in practice this is a no-op — but it closes the
gap for any instance that did store a real key as plaintext.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

from app.core.encryption import decrypt_credential, encrypt_credential, is_encrypted


# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f8b9c0d1e2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SELECT = sa.text(
    "SELECT id, api_key_encrypted FROM provider_configs "
    "WHERE api_key_encrypted IS NOT NULL AND api_key_encrypted != ''"
)
_UPDATE = sa.text(
    "UPDATE provider_configs SET api_key_encrypted = :value WHERE id = :id"
)


def upgrade() -> None:
    # Data migration needs a live connection; SQL-script (offline) mode can't
    # transform per-row values, so there is nothing to emit.
    if context.is_offline_mode():
        return

    conn = op.get_bind()
    for row_id, value in conn.execute(_SELECT).fetchall():
        if is_encrypted(value):
            continue  # already encrypted — idempotent
        conn.execute(_UPDATE, {"value": encrypt_credential(value), "id": row_id})


def downgrade() -> None:
    # Inverse: return encrypted rows to plaintext at rest.
    if context.is_offline_mode():
        return

    conn = op.get_bind()
    for row_id, value in conn.execute(_SELECT).fetchall():
        if not is_encrypted(value):
            continue
        conn.execute(_UPDATE, {"value": decrypt_credential(value), "id": row_id})
