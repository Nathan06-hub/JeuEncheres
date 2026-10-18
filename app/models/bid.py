import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import Boolean, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.game import GameSession, GameSessionPlayer
    from app.models.deck import DeckItem


class Bid(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bids"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_session_players.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deck_items.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    clue_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Clue level active when bid was submitted (1, 2, or 3)",
    )
    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Virtual currency bid amount",
    )
    is_pass: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="True if the player chose to pass this round",
    )
    is_winning_bid: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    session: Mapped["GameSession"] = relationship(back_populates="bids")
    player: Mapped["GameSessionPlayer"] = relationship(back_populates="bids")
    item: Mapped["DeckItem"] = relationship(back_populates="bids")


class DraftedItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "drafted_items"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_session_players.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deck_items.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    winning_bid_amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    clue_level_won: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="At which clue revelation stage the item was won (1, 2, or 3)",
    )
    round_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    synergy_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        default=dict,
        nullable=True,
        doc="Synergies triggered with other items in the player's draft team",
    )

    # Relationships
    session: Mapped["GameSession"] = relationship(back_populates="drafted_items")
    player: Mapped["GameSessionPlayer"] = relationship(back_populates="drafted_items")
    item: Mapped["DeckItem"] = relationship(back_populates="drafted_instances")
