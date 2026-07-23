"""
Procurement ORM models — Phase 3.

Tables:
  purchase_orders       — PO header with supplier, totals, status, workflow
  purchase_order_items  — line items on a PO (product, qty, price)
  grns                  — Goods Received Note header
  grn_items             — GRN line items linked to PO items
  inventory_ledger      — immutable record of every inventory movement

All tables use UUID primary keys, TimestampMixin, and soft-delete where
appropriate.  Inventory ledger entries are intentionally immutable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
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


class POStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    FULLY_RECEIVED = "FULLY_RECEIVED"


class GRNStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class LedgerEntryType(StrEnum):
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    ADJUSTMENT_IN = "ADJUSTMENT_IN"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT"
    RETURN = "RETURN"


# ---------------------------------------------------------------------------
# PurchaseOrder
# ---------------------------------------------------------------------------


class PurchaseOrder(Base, UUIDMixin, TimestampMixin):
    """
    Purchase Order header.

    Lifecycle: DRAFT → SUBMITTED → APPROVED → (PARTIALLY_RECEIVED | FULLY_RECEIVED)
               SUBMITTED → REJECTED
               DRAFT | SUBMITTED → CANCELLED
    """

    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=POStatus.DRAFT, index=True
    )

    # Dates
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expected_delivery_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Financial totals (derived / cached)
    subtotal: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    rejected_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Email tracking
    email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_sent_to: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    supplier: Mapped["app.models.master_data.Supplier"] = relationship(  # type: ignore[name-defined]
        "Supplier", foreign_keys=[supplier_id], lazy="selectin"
    )
    created_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[created_by_id], lazy="select"
    )
    submitted_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[submitted_by_id], lazy="select"
    )
    approved_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[approved_by_id], lazy="select"
    )
    rejected_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[rejected_by_id], lazy="select"
    )
    cancelled_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[cancelled_by_id], lazy="select"
    )
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    grns: Mapped[list["GRN"]] = relationship(
        "GRN", back_populates="purchase_order", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder {self.po_number} status={self.status}>"


# ---------------------------------------------------------------------------
# PurchaseOrderItem
# ---------------------------------------------------------------------------


class PurchaseOrderItem(Base, UUIDMixin, TimestampMixin):
    """Single line item on a Purchase Order."""

    __tablename__ = "purchase_order_items"

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity_ordered: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    discount_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0
    )
    tax_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0
    )
    line_total: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    quantity_received: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    purchase_order: Mapped[PurchaseOrder] = relationship(
        "PurchaseOrder", back_populates="items"
    )
    product: Mapped["app.models.master_data.Product"] = relationship(  # type: ignore[name-defined]
        "Product", foreign_keys=[product_id], lazy="selectin"
    )
    grn_items: Mapped[list["GRNItem"]] = relationship(
        "GRNItem", back_populates="po_item", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<POItem po={self.purchase_order_id} product={self.product_id} "
            f"qty={self.quantity_ordered}>"
        )


# ---------------------------------------------------------------------------
# GRN (Goods Received Note)
# ---------------------------------------------------------------------------


class GRN(Base, UUIDMixin, TimestampMixin):
    """
    Goods Received Note.

    Links to an Approved Purchase Order.  Multiple GRNs can exist for
    a single PO to support partial deliveries.
    """

    __tablename__ = "grns"

    grn_number: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=GRNStatus.DRAFT, index=True
    )
    received_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    delivery_note_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
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

    # Relationships
    purchase_order: Mapped[PurchaseOrder] = relationship(
        "PurchaseOrder", back_populates="grns", lazy="selectin"
    )
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
    items: Mapped[list["GRNItem"]] = relationship(
        "GRNItem",
        back_populates="grn",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    ledger_entries: Mapped[list["InventoryLedger"]] = relationship(
        "InventoryLedger", back_populates="grn", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<GRN {self.grn_number} status={self.status}>"


# ---------------------------------------------------------------------------
# GRNItem
# ---------------------------------------------------------------------------


class GRNItem(Base, UUIDMixin, TimestampMixin):
    """Single line item on a Goods Received Note."""

    __tablename__ = "grn_items"

    grn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("grns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    po_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity_received: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    grn: Mapped[GRN] = relationship("GRN", back_populates="items")
    po_item: Mapped[PurchaseOrderItem] = relationship(
        "PurchaseOrderItem", back_populates="grn_items", lazy="selectin"
    )
    product: Mapped["app.models.master_data.Product"] = relationship(  # type: ignore[name-defined]
        "Product", foreign_keys=[product_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<GRNItem grn={self.grn_id} product={self.product_id} "
            f"qty={self.quantity_received}>"
        )


# ---------------------------------------------------------------------------
# InventoryLedger
# ---------------------------------------------------------------------------


class InventoryLedger(Base, UUIDMixin, TimestampMixin):
    """
    Immutable ledger of all inventory movements.

    Never update or delete rows.  Every stock change appends a new entry.
    quantity_before + quantity_change = quantity_after (always).
    """

    __tablename__ = "inventory_ledger"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # LedgerEntryType values

    # Quantities
    quantity_before: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_change: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_after: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)

    # References
    grn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("grns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reference_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    grn: Mapped[GRN | None] = relationship(
        "GRN", back_populates="ledger_entries", lazy="select"
    )
    created_by: Mapped["app.models.user.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[created_by_id], lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryLedger product={self.product_id} type={self.entry_type} "
            f"change={self.quantity_change}>"
        )
