"""Index HNSW pgvector sur deck_items.embedding + index composites des enchères

Revision ID: 0004_vector_and_bid_indexes
Revises: 0003_user_device_secret_hash
Create Date: 2026-10-09 16:10:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = '0004_vector_and_bid_indexes'
down_revision: Union[str, None] = '0003_user_device_secret_hash'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Recherche de similarité cosinus (synergies / clustering de thèmes) sans balayage séquentiel
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deck_items_embedding_hnsw "
        "ON deck_items USING hnsw (embedding vector_cosine_ops)"
    )
    # Requêtes de manche : MAX(amount) / résolution du gagnant / contrôle « a déjà passé »
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_bids_session_round "
        "ON bids (session_id, round_number)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bids_session_round")
    op.execute("DROP INDEX IF EXISTS ix_deck_items_embedding_hnsw")
