"""Alignement ORM/Alembic : type enum token_transaction_type_enum et index manquants

Revision ID: 0005_align_orm_indexes_and_enums
Revises: 0004_vector_and_bid_indexes
Create Date: 2026-10-19 16:40:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005_align_orm_indexes_and_enums"
down_revision: Union[str, None] = "0004_vector_and_bid_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Créer le type enum PostgreSQL pour token_transactions.transaction_type et convertir la colonne
    tx_enum = sa.Enum(
        "INITIAL_GIFT",
        "IAP_PURCHASE",
        "REWARDED_AD",
        "AI_DECK_CREATION",
        "REFUND",
        "ADMIN_ADJUSTMENT",
        name="token_transaction_type_enum",
    )
    tx_enum.create(op.get_bind(), checkfirst=True)
    op.execute(
        "ALTER TABLE token_transactions "
        "ALTER COLUMN transaction_type TYPE token_transaction_type_enum "
        "USING transaction_type::token_transaction_type_enum"
    )

    # 2. Index déclarés dans les modèles ORM mais absents de 0001_initial_schema
    op.execute("CREATE INDEX IF NOT EXISTS ix_token_transactions_reference_id ON token_transactions (reference_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decks_creator_id ON decks (creator_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decks_title ON decks (title)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decks_is_public ON decks (is_public)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decks_is_official ON decks (is_official)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decks_public_play_count ON decks (is_public, play_count DESC, likes_count DESC)")

    op.execute("CREATE INDEX IF NOT EXISTS ix_game_sessions_deck_id ON game_sessions (deck_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_game_session_players_user_id ON game_session_players (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_game_session_players_session_user ON game_session_players (session_id, user_id)")

    op.execute("CREATE INDEX IF NOT EXISTS ix_bids_player_id ON bids (player_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bids_item_id ON bids (item_id)")

    op.execute("CREATE INDEX IF NOT EXISTS ix_drafted_items_player_id ON drafted_items (player_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_drafted_items_item_id ON drafted_items (item_id)")

    # 3. Retirer l'index HNSW inutilisé (le calcul de synergie cosinus est effectué en mémoire sur <= 10 items) (F-06)
    op.execute("DROP INDEX IF EXISTS ix_deck_items_embedding_hnsw")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deck_items_embedding_hnsw "
        "ON deck_items USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("DROP INDEX IF EXISTS ix_drafted_items_item_id")
    op.execute("DROP INDEX IF EXISTS ix_drafted_items_player_id")
    op.execute("DROP INDEX IF EXISTS ix_bids_item_id")
    op.execute("DROP INDEX IF EXISTS ix_bids_player_id")
    op.execute("DROP INDEX IF EXISTS ix_game_session_players_session_user")
    op.execute("DROP INDEX IF EXISTS ix_game_session_players_user_id")
    op.execute("DROP INDEX IF EXISTS ix_game_sessions_deck_id")
    op.execute("DROP INDEX IF EXISTS ix_decks_public_play_count")
    op.execute("DROP INDEX IF EXISTS ix_decks_is_official")
    op.execute("DROP INDEX IF EXISTS ix_decks_is_public")
    op.execute("DROP INDEX IF EXISTS ix_decks_title")
    op.execute("DROP INDEX IF EXISTS ix_decks_creator_id")
    op.execute("DROP INDEX IF EXISTS ix_token_transactions_reference_id")

    op.execute(
        "ALTER TABLE token_transactions "
        "ALTER COLUMN transaction_type TYPE VARCHAR(32) "
        "USING transaction_type::text"
    )
    sa.Enum(name="token_transaction_type_enum").drop(op.get_bind(), checkfirst=True)
