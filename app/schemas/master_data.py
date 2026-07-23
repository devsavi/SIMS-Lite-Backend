"""
Master data Pydantic v2 schemas -- Phase 2.

Separate Create / Update / Read schemas for:
  - Category
  - Brand
  - UnitOfMeasure (UoM)
  - Supplier
  - Product
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from app.schemas.base import AppBaseModel


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


class CategoryRead(AppBaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    slug: str
    parent_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryCreate(AppBaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    slug: str | None = Field(default=None, max_length=120)
    parent_id: uuid.UUID | None = None
    is_active: bool = True


class CategoryUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    slug: str | None = Field(default=None, max_length=120)
    parent_id: uuid.UUID | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------


class BrandRead(AppBaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    logo_url: str | None
    website: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BrandCreate(AppBaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class BrandUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Unit of Measure
# ---------------------------------------------------------------------------


class UoMRead(AppBaseModel):
    id: uuid.UUID
    name: str
    symbol: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UoMCreate(AppBaseModel):
    name: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=20)
    description: str | None = None
    is_active: bool = True


class UoMUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    symbol: str | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------


class SupplierRead(AppBaseModel):
    id: uuid.UUID
    supplier_code: str
    name: str
    contact_person: str | None
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    state: str | None
    country: str | None
    postal_code: str | None
    tax_id: str | None
    payment_terms: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierCreate(AppBaseModel):
    supplier_code: str | None = Field(default=None, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    contact_person: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    tax_id: str | None = Field(default=None, max_length=50)
    payment_terms: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_active: bool = True


class SupplierUpdate(AppBaseModel):
    supplier_code: str | None = Field(default=None, max_length=30)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_person: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    tax_id: str | None = Field(default=None, max_length=50)
    payment_terms: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class ProductCategoryRef(AppBaseModel):
    id: uuid.UUID
    name: str
    slug: str


class ProductBrandRef(AppBaseModel):
    id: uuid.UUID
    name: str


class ProductUoMRef(AppBaseModel):
    id: uuid.UUID
    name: str
    symbol: str


class ProductSupplierRef(AppBaseModel):
    id: uuid.UUID
    supplier_code: str
    name: str


class ProductRead(AppBaseModel):
    id: uuid.UUID
    sku: str
    barcode: str
    name: str
    description: str | None
    short_description: str | None
    category: ProductCategoryRef | None
    brand: ProductBrandRef | None
    uom: ProductUoMRef | None
    supplier: ProductSupplierRef | None
    cost_price: float | None
    selling_price: float | None
    reorder_level: int
    reorder_quantity: int
    image_path: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductCreate(AppBaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    short_description: str | None = Field(default=None, max_length=500)
    category_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    uom_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    cost_price: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    reorder_level: int = Field(default=0, ge=0)
    reorder_quantity: int = Field(default=0, ge=0)
    is_active: bool = True


class ProductUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    short_description: str | None = Field(default=None, max_length=500)
    category_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    uom_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    cost_price: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    reorder_level: int | None = Field(default=None, ge=0)
    reorder_quantity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Product import row schema
# ---------------------------------------------------------------------------


class ProductImportRow(AppBaseModel):
    """Schema for a single row in the bulk import CSV/Excel."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category_name: str | None = None
    brand_name: str | None = None
    uom_symbol: str | None = None
    supplier_code: str | None = None
    cost_price: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    reorder_level: int = Field(default=0, ge=0)
    reorder_quantity: int = Field(default=0, ge=0)
