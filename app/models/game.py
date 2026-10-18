import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.deck import Deck, DeckItem
    from app.models.bid import Bid, DraftedItem


class GameMode(str, enum.Enum):
    LOCAL_PASS_AND_PLAY = "LOCAL_PASS_AND_PLAY"
    ONLINE_MULTIPLAYER = "ONLINE_MULTIPLAYER"
    SOLO_VS_AI = "SOLO_VS_AI"


class GameStatus(str, enum.Enum):
    LOBBY = "LOBBY"
    IN_PROGRESS = "IN_PROGRESS"
    ROUND_BIDDING = "ROUND_BIDDING"
    ROUND_REVEAL = "ROUND_REVEAL"
    CALCULATING_RESULTS = "CALCULATING_RESULTS"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class GameSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "game_sessions"

    code: Mapped[str] = mapped_column(
        String(8),
        unique=True,
        index=True,
        nullable=False,
        doc="Short room join code (e.g. 'DRAFT8')",
    )
    host_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deck_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decks.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    mode: Mapped[GameMode] = mapped_column(
        Enum(GameMode, name="game_mode_enum"),
        default=GameMode.LOCAL_PASS_AND_PLAY,
        nullable=False,
    )
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus, name="game_status_enum"),
        default=GameStatus.LOBBY,
        index=True,
        nullable=False,
    )
    starting_budget: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        nullable=False,
        doc="Virtual currency given to each player at the start of the draft",
    )
    total_rounds: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
        doc="Total number of items to auction",
    )
    current_round: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    current_clue_level: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        doc="Current clue step revealed: 1, 2, or 3",
    )
    current_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deck_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    timer_seconds: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )
    round_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    host: Mapped["User | None"] = relationship(foreign_keys=[host_id])
    deck: Mapped["Deck"] = relationship(back_populates="game_sessions", lazy="selectin")
    current_item: Mapped["DeckItem | None"] = relationship(foreign_keys=[current_item_id])
    players: Mapped[list["GameSessionPlayer"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="GameSessionPlayer.final_score.desc()",
    )
    bids: Mapped[list["Bid"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    drafted_items: Mapped[list["DraftedItem"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class GameSessionPlayer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "game_session_players"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        doc="Linked user ID or null for pass-and-play guests/AI",
    )
    display_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    remaining_budget: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        nullable=False,
    )
    base_score_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Sum of base scores (1-100) of all drafted items",
    )
    synergy_bonus: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Bonus points earned through AI & vector synergies",
    )
    final_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="base_score_total + synergy_bonus",
    )
    roi_percentage: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Return On Investment: (Final Score / Spent Budget) ratio",
    )
    rank: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Final leaderboard position (1st, 2nd, 3rd...)",
    )
    is_host: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_bot: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_ready: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    session: Mapped["GameSession"] = relationship(back_populates="players")
    user: Mapped["User | None"] = relationship(back_populates="player_sessions")
    bids: Mapped[list["Bid"]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
    )
    drafted_items: Mapped[list["DraftedItem"]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
    )
