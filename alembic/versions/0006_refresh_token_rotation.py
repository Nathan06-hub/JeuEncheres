"""Persist the active refresh token ID for single-use token rotation.

Revision ID: 0006_refresh_token_rotation
Revises: 0005_align_orm_indexes_and_enums
Create Date: 2026-11-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_refresh_token_rotation"
down_revision: Union[str, None] = "0005_align_orm_indexes_and_enums"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("refresh_token_jti", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "refresh_token_jti")
