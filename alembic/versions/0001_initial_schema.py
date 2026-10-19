"""Initial schema with pgvector

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-22 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector & uuid-ossp extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # 2. Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('device_id', sa.String(128), unique=True, nullable=True),
        sa.Column('username', sa.String(64), unique=True, nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=True),
        sa.Column('hashed_password', sa.String(255), nullable=True),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('token_balance', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_users_device_id', 'users', ['device_id'])
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])

    # 3. Token Transactions
    op.create_table(
        'token_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('transaction_type', sa.String(32), nullable=False),
        sa.Column('reference_id', sa.String(255), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_token_transactions_user_id', 'token_transactions', ['user_id'])
    op.create_index('ix_token_transactions_transaction_type', 'token_transactions', ['transaction_type'])

    # 4. Token Packs
    op.create_table(
        'token_packs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('sku', sa.String(64), unique=True, nullable=False),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('tokens_amount', sa.Integer(), nullable=False),
        sa.Column('price_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), server_default='USD', nullable=False),
        sa.Column('is_best_value', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('badge_text', sa.String(64), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_token_packs_sku', 'token_packs', ['sku'])

    # 5. Decks
    op.create_table(
        'decks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('creator_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.String(150), nullable=False),
        sa.Column('slug', sa.String(180), unique=True, nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('category', sa.Enum('Pop Culture', 'Cinéma', 'Séries', 'Sport', 'Histoire', 'Mangas', 'Musique', 'Géographie', 'Sciences', 'Autre', name='deck_category_enum', create_type=True), nullable=False),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_public', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_official', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('play_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('likes_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('ai_prompt', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_decks_slug', 'decks', ['slug'])
    op.create_index('ix_decks_category', 'decks', ['category'])

    # 6. Deck Items (with pgvector embedding)
    op.create_table(
        'deck_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('deck_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('decks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('clue_1', sa.Text(), nullable=False),
        sa.Column('clue_2', sa.Text(), nullable=False),
        sa.Column('clue_3', sa.Text(), nullable=False),
        sa.Column('base_score', sa.Integer(), nullable=False),
        sa.Column('rarity', sa.Enum('COMMON', 'UNCOMMON', 'RARE', 'EPIC', 'LEGENDARY', name='item_rarity_enum', create_type=True), nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('embedding', Vector(768), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_deck_items_deck_id', 'deck_items', ['deck_id'])
    op.create_index('ix_deck_items_name', 'deck_items', ['name'])

    # 7. Game Sessions
    op.create_table(
        'game_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(8), unique=True, nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('deck_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('decks.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('mode', sa.Enum('LOCAL_PASS_AND_PLAY', 'ONLINE_MULTIPLAYER', 'SOLO_VS_AI', name='game_mode_enum', create_type=True), server_default='LOCAL_PASS_AND_PLAY', nullable=False),
        sa.Column('status', sa.Enum('LOBBY', 'IN_PROGRESS', 'ROUND_BIDDING', 'ROUND_REVEAL', 'CALCULATING_RESULTS', 'FINISHED', 'CANCELLED', name='game_status_enum', create_type=True), server_default='LOBBY', nullable=False),
        sa.Column('starting_budget', sa.Integer(), server_default='1000', nullable=False),
        sa.Column('total_rounds', sa.Integer(), server_default='10', nullable=False),
        sa.Column('current_round', sa.Integer(), server_default='0', nullable=False),
        sa.Column('current_clue_level', sa.Integer(), server_default='1', nullable=False),
        sa.Column('current_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('deck_items.id', ondelete='SET NULL'), nullable=True),
        sa.Column('timer_seconds', sa.Integer(), server_default='15', nullable=False),
        sa.Column('round_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_game_sessions_code', 'game_sessions', ['code'])
    op.create_index('ix_game_sessions_status', 'game_sessions', ['status'])

    # 8. Game Session Players
    op.create_table(
        'game_session_players',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('display_name', sa.String(64), nullable=False),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('remaining_budget', sa.Integer(), server_default='1000', nullable=False),
        sa.Column('base_score_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('synergy_bonus', sa.Integer(), server_default='0', nullable=False),
        sa.Column('final_score', sa.Integer(), server_default='0', nullable=False),
        sa.Column('roi_percentage', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('is_host', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_bot', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_ready', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_game_session_players_session_id', 'game_session_players', ['session_id'])

    # 9. Bids
    op.create_table(
        'bids',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('game_session_players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('deck_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('clue_level', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('is_pass', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_winning_bid', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_bids_session_id', 'bids', ['session_id'])

    # 10. Drafted Items
    op.create_table(
        'drafted_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('game_session_players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('deck_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('winning_bid_amount', sa.Integer(), nullable=False),
        sa.Column('clue_level_won', sa.Integer(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('synergy_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_drafted_items_session_id', 'drafted_items', ['session_id'])


def downgrade() -> None:
    op.drop_table('drafted_items')
    op.drop_table('bids')
    op.drop_table('game_session_players')
    op.drop_table('game_sessions')
    op.drop_table('deck_items')
    op.drop_table('decks')
    op.drop_table('token_packs')
    op.drop_table('token_transactions')
    op.drop_table('users')
    sa.Enum(name='game_status_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='game_mode_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='item_rarity_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='deck_category_enum').drop(op.get_bind(), checkfirst=True)
