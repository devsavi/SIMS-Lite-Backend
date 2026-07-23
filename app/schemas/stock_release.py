"""
Stock Release Pydantic v2 schemas — Phase 5.

Covers Stock Release documents, items, dashboard, and report filters.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, model_validator

from app.models.stock_release import StockReleasePurpose, StockReleaseStatus
from app.schemas.base import AppBaseModel


# ---------------------------------------------------------------------------
# Shared reference schemas
# ---------------------------------------------------------------------------


class ProductReleaseRef(AppBaseModel):
    id: uuid.UUID
    sku: str
    name: str
    barcode: str
    reorder_level: int
    cost_price: float | None
    selling_price: float | None


class UserReleaseRef(AppBaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str


# ---------------------------------------------------------------------------
# Stock Release Item schemas
# ---------------------------------------------------------------------------


class StockReleaseItemCreate(AppBaseModel):
    product_id: uuid.UUID
    quantity_requested: float = Field(gt=0, description="Quantity to release (must be > 0)")
    notes: str | None = None


class StockReleaseItemRead(AppBaseModel):
    id: uuid.UUID
    stock_release_id: uuid.UUID
    product: ProductReleaseRef | None
    quantity_requested: float
    unit_cost: float
    line_total: float
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Stock Release schemas
# ---------------------------------------------------------------------------


class StockReleaseCreate(AppBaseModel):
    purpose: StockReleasePurpose = StockReleasePurpose.INTERNAL_USE
    release_date: datetime
    notes: str | None = None
    reference_document: str | None = Field(default=None, max_length=100)
    items: list[StockReleaseItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_products(self) -> "StockReleaseCreate":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Duplicate products in stock release items.")
        return self


class StockReleaseUpdate(AppBaseModel):
    purpose: StockReleasePurpose | None = None
    release_date: datetime | None = None
    notes: str | None = None
    reference_document: str | None = Field(default=None, max_length=100)
    items: list[StockReleaseItemCreate] | None = None


class StockReleaseRead(AppBaseModel):
    id: uuid.UUID
    release_number: str
    purpose: str
    status: str
    release_date: datetime
    notes: str | None
    reference_document: str | None
    total_quantity: float
    total_cost: float
    created_by: UserReleaseRef | None
    submitted_by: UserReleaseRef | None
    submitted_at: datetime | None
    approved_by: UserReleaseRef | None
    approved_at: datetime | None
    cancelled_by: UserReleaseRef | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    items: list[StockReleaseItemRead]
    created_at: datetime
    updated_at: datetime


class StockReleaseSummary(AppBaseModel):
    """Lightweight summary for list views."""

    id: uuid.UUID
    release_number: str
    purpose: str
    status: str
    release_date: datetime
    total_quantity: float
    total_cost: float
    item_count: int
    created_by: UserReleaseRef | None
    created_at: datetime


class CancelReleaseRequest(AppBaseModel):
    reason: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Dashboard widget schemas
# ---------------------------------------------------------------------------


class StockReleaseDashboard(AppBaseModel):
    """Stock release KPIs appended to the inventory dashboard."""

    todays_releases: int
    todays_released_quantity: float
    monthly_released_quantity: float
    pending_releases: int
    recent_releases: list[dict]
    top_released_products: list[dict]


class InventoryDashboardExtended(AppBaseModel):
    """Extended inventory dashboard including stock release widgets."""

    # Core inventory KPIs (from Phase 4)
    total_products: int
    total_products_in_stock: int
    total_out_of_stock: int
    total_low_stock: int
    total_quantity_on_hand: float
    total_stock_value: float
    pending_adjustments: int
    recent_movements: list[dict]

    # Stock Release widgets (Phase 5)
    todays_releases: int
    todays_released_quantity: float
    monthly_released_quantity: float
    pending_releases: int
    recent_releases: list[dict]
    top_released_products: list[dict]


# ---------------------------------------------------------------------------
# Report filter schemas
# ---------------------------------------------------------------------------


class StockReleaseReportFilter(AppBaseModel):
    purpose: StockReleasePurpose | None = None
    status: StockReleaseStatus | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None


class ProductConsumptionReportFilter(AppBaseModel):
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
