"""Ajout de users.device_secret_hash (authentification invité par secret d'appareil)

Revision ID: 0003_user_device_secret_hash
Revises: 0002_token_tx_unique_reference
Create Date: 2026-10-09 16:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003_user_device_secret_hash'
down_revision: Union[str, None] = '0002_token_tx_unique_reference'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('device_secret_hash', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'device_secret_hash')
