"""
Inventory ORM models — Phase 4.

Tables:
  inventory              — current stock record per product (one row per product)
  inventory_ledger       — immutable ledger of every inventory movement
  stock_adjustments      — stock adjustment header
  stock_adjustment_items — line items on a stock adjustment

Rules:
- inventory.quantity_on_hand is always derived from the ledger (latest quantity_after)
- Every change to inventory MUST create an inventory_ledger row
- Inventory ledger rows are immutable — never update or delete
- inventory increases only from approved GRNs
- inventory decreases only from approved Stock Releases
- inventory corrections via approved Stock Adjustments
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StockAdjustmentStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class StockAdjustmentType(StrEnum):
    INCREASE = "INCREASE"   # positive correction (found stock, damage reversal, etc.)
    DECREASE = "DECREASE"   # negative correction (damaged goods, theft, shrinkage)
    RECOUNT = "RECOUNT"     # physical stock count correction (can be + or -)


class LedgerReferenceType(StrEnum):
    GRN = "GRN"
    STOCK_ADJUSTMENT = "STOCK_ADJUSTMENT"
    STOCK_RELEASE = "STOCK_RELEASE"
    INITIAL = "INITIAL"


class LedgerEntryType(StrEnum):
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"    # from approved GRN
    ADJUSTMENT_IN = "ADJUSTMENT_IN"          # stock adjustment increase
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT"        # stock adjustment decrease
    STOCK_RELEASE = "STOCK_RELEASE"          # approved stock release / out
    INITIAL_STOCK = "INITIAL_STOCK"          # opening balance


# ---------------------------------------------------------------------------
# Inventory (current stock snapshot)
# ---------------------------------------------------------------------------


class Inventory(Base, UUIDMixin, TimestampMixin):
    """
    Current stock level for a single product.

    One row per active product.  Updated atomically whenever a ledger
    entry is appended.  quantity_on_hand mirrors the latest ledger
    quantity_after for the product.
    """

    __tablename__ = "inventory"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Stock quantity
    quantity_on_hand: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0
    )

    # Weighted average cost (updated on each receipt)
    average_cost: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0
    )

    # Dates for audit / freshness
    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_transaction_type: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    # Relationships
    product: Mapped["app.models.master_data.Product"] = relationship(  # type: ignore[name-defined]
        "Product", foreign_keys=[product_id], lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("product_id", name="uq_inventory_product_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Inventory product={self.product_id} "
            f"qty={self.quantity_on_hand}>"
        )


# ---------------------------------------------------------------------------
# Inventory Ledger (immutable movement log)
# ---------------------------------------------------------------------------


class InventoryLedgerEntry(Base, UUIDMixin, TimestampMixin):
    """
    Immutable audit ledger of every inventory movement.

    NEVER update or delete rows.  Each stock change appends a new entry.
    Invariant: quantity_before + quantity_change == quantity_after.

    This table is the single source of truth for stock history.
    """

    __tablename__ = "inventory_ledger_entries"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )

    # Quantities
    quantity_before: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_change: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_after: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)

    # Valuation
    unit_cost: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0
    )

    # References — what caused this movement?
    reference_type: Mapped[str | None] = mapped_column(
        String(30), nullable=True, index=True
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    reference_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who created the entry
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    product: Mapped["app.models.master_data.Product"] = relationship(  # type: ignore[name-defined]
        "Product", foreign_keys=[product_id], lazy="selectin"
    )
    created_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[created_by_id], lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryLedgerEntry product={self.product_id} "
            f"type={self.entry_type} change={self.quantity_change}>"
        )


# ---------------------------------------------------------------------------
# StockAdjustment
# ---------------------------------------------------------------------------


class StockAdjustment(Base, UUIDMixin, TimestampMixin):
    """
    Stock Adjustment header.

    Lifecycle: DRAFT → SUBMITTED → APPROVED (applies to inventory)
               DRAFT | SUBMITTED → CANCELLED
    """

    __tablename__ = "stock_adjustments"

    adjustment_number: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    adjustment_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # StockAdjustmentType values

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=StockAdjustmentStatus.DRAFT, index=True
    )

    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Workflow metadata
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    created_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[created_by_id], lazy="select"
    )
    submitted_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[submitted_by_id], lazy="select"
    )
    approved_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[approved_by_id], lazy="select"
    )
    cancelled_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[cancelled_by_id], lazy="select"
    )
    items: Mapped[list["StockAdjustmentItem"]] = relationship(
        "StockAdjustmentItem",
        back_populates="stock_adjustment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    ledger_entries: Mapped[list["InventoryLedgerEntry"]] = relationship(
        "InventoryLedgerEntry",
        primaryjoin=(
            "and_(StockAdjustment.id == foreign(InventoryLedgerEntry.reference_id), "
            "InventoryLedgerEntry.reference_type == 'STOCK_ADJUSTMENT')"
        ),
        lazy="select",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return (
            f"<StockAdjustment {self.adjustment_number} "
            f"type={self.adjustment_type} status={self.status}>"
        )


# ---------------------------------------------------------------------------
# StockAdjustmentItem
# ---------------------------------------------------------------------------


class StockAdjustmentItem(Base, UUIDMixin, TimestampMixin):
    """Single product line on a Stock Adjustment."""

    __tablename__ = "stock_adjustment_items"

    stock_adjustment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_adjustments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Quantity to adjust (always positive; direction determined by adjustment_type)
    quantity_adjusted: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False
    )

    # Unit cost at time of adjustment (for valuation)
    unit_cost: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0
    )

    # Optional per-item notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    stock_adjustment: Mapped[StockAdjustment] = relationship(
        "StockAdjustment", back_populates="items"
    )
    product: Mapped["app.models.master_data.Product"] = relationship(  # type: ignore[name-defined]
        "Product", foreign_keys=[product_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<StockAdjustmentItem adj={self.stock_adjustment_id} "
            f"product={self.product_id} qty={self.quantity_adjusted}>"
        )
