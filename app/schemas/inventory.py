"""
Inventory Pydantic v2 schemas — Phase 4.

Covers:
- Inventory (current stock)
- InventoryLedgerEntry
- StockAdjustment
- Dashboard and Report filters
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, model_validator

from app.models.inventory import (
    LedgerEntryType,
    StockAdjustmentStatus,
    StockAdjustmentType,
)
from app.schemas.base import AppBaseModel


# ---------------------------------------------------------------------------
# Shared reference schemas
# ---------------------------------------------------------------------------


class ProductInventoryRef(AppBaseModel):
    id: uuid.UUID
    sku: str
    name: str
    barcode: str
    reorder_level: int
    cost_price: float | None
    selling_price: float | None


class UserRef(AppBaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str


# ---------------------------------------------------------------------------
# Inventory (current stock)
# ---------------------------------------------------------------------------


class InventoryRead(AppBaseModel):
    id: uuid.UUID
    product: ProductInventoryRef | None
    quantity_on_hand: float
    average_cost: float
    stock_value: float  # computed: quantity_on_hand * average_cost
    last_updated_at: datetime | None
    last_transaction_type: str | None
    created_at: datetime
    updated_at: datetime


class InventorySummary(AppBaseModel):
    """Aggregate inventory summary."""

    total_products: int
    total_products_in_stock: int
    total_out_of_stock: int
    total_low_stock: int
    total_quantity_on_hand: float
    total_stock_value: float


class InventoryValuation(AppBaseModel):
    """Per-product valuation record."""

    product_id: uuid.UUID
    sku: str
    product_name: str
    quantity_on_hand: float
    average_cost: float
    stock_value: float


class InventoryValuationSummary(AppBaseModel):
    """Inventory valuation summary."""

    total_products: int
    total_quantity: float
    total_value: float
    items: list[InventoryValuation]


# ---------------------------------------------------------------------------
# Inventory Ledger Entry
# ---------------------------------------------------------------------------


class InventoryLedgerEntryRead(AppBaseModel):
    id: uuid.UUID
    product: ProductInventoryRef | None
    entry_type: str
    quantity_before: float
    quantity_change: float
    quantity_after: float
    unit_cost: float
    reference_type: str | None
    reference_id: uuid.UUID | None
    reference_number: str | None
    notes: str | None
    created_by: UserRef | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Stock Adjustment Item schemas
# ---------------------------------------------------------------------------


class StockAdjustmentItemCreate(AppBaseModel):
    product_id: uuid.UUID
    quantity_adjusted: float = Field(gt=0)
    unit_cost: float = Field(default=0, ge=0)
    notes: str | None = None


class StockAdjustmentItemRead(AppBaseModel):
    id: uuid.UUID
    stock_adjustment_id: uuid.UUID
    product: ProductInventoryRef | None
    quantity_adjusted: float
    unit_cost: float
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Stock Adjustment schemas
# ---------------------------------------------------------------------------


class StockAdjustmentCreate(AppBaseModel):
    adjustment_type: StockAdjustmentType
    reason: str = Field(min_length=1, max_length=500)
    notes: str | None = None
    items: list[StockAdjustmentItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_products(self) -> "StockAdjustmentCreate":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Duplicate products in adjustment items.")
        return self


class StockAdjustmentUpdate(AppBaseModel):
    adjustment_type: StockAdjustmentType | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    notes: str | None = None
    items: list[StockAdjustmentItemCreate] | None = None


class StockAdjustmentRead(AppBaseModel):
    id: uuid.UUID
    adjustment_number: str
    adjustment_type: str
    status: str
    reason: str
    notes: str | None
    created_by: UserRef | None
    submitted_by: UserRef | None
    submitted_at: datetime | None
    approved_by: UserRef | None
    approved_at: datetime | None
    cancelled_by: UserRef | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    items: list[StockAdjustmentItemRead]
    created_at: datetime
    updated_at: datetime


class StockAdjustmentSummary(AppBaseModel):
    """Lightweight summary for list views."""

    id: uuid.UUID
    adjustment_number: str
    adjustment_type: str
    status: str
    reason: str
    item_count: int
    created_by: UserRef | None
    created_at: datetime


class CancelAdjustmentRequest(AppBaseModel):
    reason: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class InventoryDashboard(AppBaseModel):
    """Inventory KPI dashboard response."""

    total_products: int
    total_products_in_stock: int
    total_out_of_stock: int
    total_low_stock: int
    total_quantity_on_hand: float
    total_stock_value: float
    pending_adjustments: int
    recent_movements: list[dict]


# ---------------------------------------------------------------------------
# Report filter schemas
# ---------------------------------------------------------------------------


class InventoryReportFilter(AppBaseModel):
    category_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    low_stock_only: bool = False
    out_of_stock_only: bool = False


class LedgerReportFilter(AppBaseModel):
    product_id: uuid.UUID | None = None
    entry_type: str | None = None
    reference_type: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None


class StockAdjustmentReportFilter(AppBaseModel):
    adjustment_type: str | None = None
    status: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
