import uuid
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.token import TokenTransaction
    from app.models.deck import Deck
    from app.models.game import GameSessionPlayer


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    device_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=True,
        doc="Mobile device identifier for instant anonymous onboarding",
    )
    device_secret_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 du secret aléatoire généré par l'appareil (jamais stocké en clair)",
    )
    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=True,
    )
    hashed_password: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    token_balance: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
        doc="Current IA token balance (e.g. ⚡ 3 initial)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    token_transactions: Mapped[list["TokenTransaction"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="TokenTransaction.created_at.desc()",
    )
    decks: Mapped[list["Deck"]] = relationship(
        back_populates="creator",
        foreign_keys="[Deck.creator_id]",
    )
    player_sessions: Mapped[list["GameSessionPlayer"]] = relationship(
        back_populates="user",
    )
