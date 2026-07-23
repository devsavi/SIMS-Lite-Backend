"""
Stock Release ORM models — Phase 5.

Tables:
  stock_releases       — Stock Release header (issue document)
  stock_release_items  — Line items on a stock release

Business rules (encoded as docstrings / comments):
- Only DRAFT documents can be edited or deleted.
- Only SUBMITTED documents can be approved.
- Inventory is deducted ONLY after approval.
- Approved documents are read-only.
- Cancelled documents do NOT affect inventory.
- Every approved release creates immutable InventoryLedgerEntry rows.
- Inventory must NEVER go below zero.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StockReleaseStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class StockReleasePurpose(StrEnum):
    """Why stock is being released / issued."""

    INTERNAL_USE = "INTERNAL_USE"
    PRODUCTION = "PRODUCTION"
    MAINTENANCE = "MAINTENANCE"
    SALES = "SALES"
    SAMPLE = "SAMPLE"
    DISPOSAL = "DISPOSAL"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# StockRelease (header)
# ---------------------------------------------------------------------------


class StockRelease(Base, UUIDMixin, TimestampMixin):
    """
    Stock Release document header.

    Lifecycle: DRAFT → SUBMITTED → APPROVED (inventory deducted)
               DRAFT | SUBMITTED → CANCELLED
    Approved documents are immutable.
    """

    __tablename__ = "stock_releases"

    release_number: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    purpose: Mapped[str] = mapped_column(
        String(30), nullable=False, default=StockReleasePurpose.INTERNAL_USE, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=StockReleaseStatus.DRAFT, index=True
    )

    release_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_document: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # external PO, work order, etc.

    # Totals (cached)
    total_quantity: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, default=0
    )
    total_cost: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, default=0
    )

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
    items: Mapped[list["StockReleaseItem"]] = relationship(
        "StockReleaseItem",
        back_populates="stock_release",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<StockRelease {self.release_number} "
            f"purpose={self.purpose} status={self.status}>"
        )


# ---------------------------------------------------------------------------
# StockReleaseItem (line item)
# ---------------------------------------------------------------------------


class StockReleaseItem(Base, UUIDMixin, TimestampMixin):
    """Single product line on a Stock Release document."""

    __tablename__ = "stock_release_items"

    stock_release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_releases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Quantity to release (always positive)
    quantity_requested: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False
    )

    # Unit cost captured at time of approval (for valuation / ledger)
    unit_cost: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, default=0
    )

    # Line total (quantity_requested * unit_cost) — computed on approval
    line_total: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, default=0
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    stock_release: Mapped[StockRelease] = relationship(
        "StockRelease", back_populates="items"
    )
    product: Mapped["app.models.master_data.Product"] = relationship(  # type: ignore[name-defined]
        "Product", foreign_keys=[product_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<StockReleaseItem release={self.stock_release_id} "
            f"product={self.product_id} qty={self.quantity_requested}>"
        )
