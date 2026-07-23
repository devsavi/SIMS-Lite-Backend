"""
Master Data ORM models — Phase 2.

Tables:
  categories     — hierarchical product categories (self-referential parent)
  brands         — product brands / manufacturers
  units_of_measure — measurement units (kg, pcs, litre, …)
  suppliers      — vendor/supplier directory
  products       — product catalogue with SKU, barcode, and image URL

All tables use UUID primary keys, TimestampMixin (created_at / updated_at),
and a soft-delete column ``is_deleted`` so records can be archived rather than
permanently removed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


class Category(Base, UUIDMixin, TimestampMixin):
    """
    Product category — supports one level of parent hierarchy.

    A category can optionally reference a parent category, allowing
    a simple tree structure (e.g. Electronics → Computers).
    """

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    parent: Mapped[Category | None] = relationship(
        "Category", remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list[Category]] = relationship(
        "Category", back_populates="parent"
    )
    products: Mapped[list[Product]] = relationship(
        "Product", back_populates="category"
    )

    __table_args__ = (
        UniqueConstraint("name", "parent_id", name="uq_category_name_parent"),
    )

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------


class Brand(Base, UUIDMixin, TimestampMixin):
    """Product brand or manufacturer."""

    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    products: Mapped[list[Product]] = relationship("Product", back_populates="brand")

    def __repr__(self) -> str:
        return f"<Brand {self.name}>"


# ---------------------------------------------------------------------------
# Unit of Measure
# ---------------------------------------------------------------------------


class UnitOfMeasure(Base, UUIDMixin, TimestampMixin):
    """
    Unit of measurement for products (e.g. kg, pcs, litre, box).

    ``symbol`` is the short form used on documents (kg, pcs, etc.).
    ``base_unit`` optionally references the SI base unit (e.g. gram → kg).
    ``conversion_factor`` is the multiplier from this unit to the base unit.
    """

    __tablename__ = "units_of_measure"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    products: Mapped[list[Product]] = relationship("Product", back_populates="uom")

    def __repr__(self) -> str:
        return f"<UnitOfMeasure {self.symbol}>"


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------


class Supplier(Base, UUIDMixin, TimestampMixin):
    """
    Supplier / vendor record.

    ``supplier_code`` is a unique, system-generated or manually assigned
    short code used on purchase orders (e.g. SUP-00001).
    """

    __tablename__ = "suppliers"

    supplier_code: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    contact_person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    products: Mapped[list[Product]] = relationship(
        "Product", back_populates="supplier"
    )

    def __repr__(self) -> str:
        return f"<Supplier {self.supplier_code} {self.name}>"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class Product(Base, UUIDMixin, TimestampMixin):
    """
    Product catalogue entry.

    Each product has a system-generated SKU and barcode value.
    Product images are stored in MinIO; ``image_url`` holds the object
    path returned after upload.
    """

    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    barcode: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Foreign keys
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uom_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("units_of_measure.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Pricing & stock
    cost_price: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    selling_price: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    reorder_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Storage
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    category: Mapped[Category | None] = relationship(
        "Category", back_populates="products"
    )
    brand: Mapped[Brand | None] = relationship("Brand", back_populates="products")
    uom: Mapped[UnitOfMeasure | None] = relationship("UnitOfMeasure", back_populates="products")
    supplier: Mapped[Supplier | None] = relationship(
        "Supplier", back_populates="products"
    )

    def __repr__(self) -> str:
        return f"<Product {self.sku} {self.name}>"
