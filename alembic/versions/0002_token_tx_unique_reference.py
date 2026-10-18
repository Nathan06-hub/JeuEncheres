"""Unique partial index on token_transactions (transaction_type, reference_id)

Revision ID: 0002_token_tx_unique_reference
Revises: 0001_initial_schema
Create Date: 2026-10-08 18:20:00.000000

Rend idempotents les crédits IAP / publicités récompensées : un même `reference_id`
(reçu de store, reward token de pub) ne peut plus être crédité deux fois pour un même type.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_token_tx_unique_reference'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = 'uq_token_tx_type_reference'


def upgrade() -> None:
    # Si des doublons historiques existent, la création échouera : il faut alors les
    # dédoublonner manuellement (et auditer ces crédits) avant de relancer la migration.
    op.create_index(
        INDEX_NAME,
        'token_transactions',
        ['transaction_type', 'reference_id'],
        unique=True,
        postgresql_where=sa.text('reference_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        INDEX_NAME,
        table_name='token_transactions',
        postgresql_where=sa.text('reference_id IS NOT NULL'),
    )
