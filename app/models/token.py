import enum
import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class TokenTransactionType(str, enum.Enum):
    INITIAL_GIFT = "INITIAL_GIFT"
    IAP_PURCHASE = "IAP_PURCHASE"
    REWARDED_AD = "REWARDED_AD"
    AI_DECK_CREATION = "AI_DECK_CREATION"
    REFUND = "REFUND"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"


class TokenTransaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "token_transactions"
    __table_args__ = (
        # Idempotence : un même reçu IAP / reward de pub ne peut être crédité qu'une seule fois
        # par type de transaction. Index partiel : les débits (reference_id NULL) sont exclus.
        Index(
            "uq_token_tx_type_reference",
            "transaction_type",
            "reference_id",
            unique=True,
            postgresql_where=text("reference_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Token change: positive for credits, negative for debits (e.g. -1 for AI generation)",
    )
    balance_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="User balance after this transaction for auditing and reconciliation",
    )
    transaction_type: Mapped[TokenTransactionType] = mapped_column(
        Enum(TokenTransactionType, name="token_transaction_type_enum"),
        index=True,
        nullable=False,
    )
    reference_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
        doc="App Store / Google Play transaction receipt ID or Ad network reward ID",
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        default=dict,
        nullable=True,
        doc="Extra metadata (e.g. pack SKU, ad provider, device info)",
    )

    # Relationship
    user: Mapped["User"] = relationship(back_populates="token_transactions")


class TokenPack(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "token_packs"

    sku: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        doc="Store product identifier (e.g. pack_starter_5, pack_value_15, pack_pro_50)",
    )
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    tokens_amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    price_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Price in cents (e.g. 99 for $0.99, 249 for $2.49)",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    is_best_value: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Flag for UI highlighting with badge",
    )
    badge_text: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Badge text on card (e.g. 'Meilleure Valeur', 'Populaire')",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
