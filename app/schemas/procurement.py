"""
Procurement Pydantic v2 schemas — Phase 3.

Covers Purchase Orders, GRNs, Inventory Ledger, and Procurement Dashboard.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.models.procurement import GRNStatus, LedgerEntryType, POStatus
from app.schemas.base import AppBaseModel


# ---------------------------------------------------------------------------
# Shared reference schemas
# ---------------------------------------------------------------------------


class SupplierRef(AppBaseModel):
    id: uuid.UUID
    supplier_code: str
    name: str
    email: str | None
    contact_person: str | None


class ProductRef(AppBaseModel):
    id: uuid.UUID
    sku: str
    name: str
    barcode: str


class UserRef(AppBaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str


# ---------------------------------------------------------------------------
# Purchase Order Item schemas
# ---------------------------------------------------------------------------


class POItemCreate(AppBaseModel):
    product_id: uuid.UUID
    quantity_ordered: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    discount_percent: float = Field(default=0, ge=0, le=100)
    tax_percent: float = Field(default=0, ge=0, le=100)
    notes: str | None = None


class POItemUpdate(AppBaseModel):
    quantity_ordered: float | None = Field(default=None, gt=0)
    unit_price: float | None = Field(default=None, ge=0)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    tax_percent: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = None


class POItemRead(AppBaseModel):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    product: ProductRef | None
    quantity_ordered: float
    unit_price: float
    discount_percent: float
    tax_percent: float
    line_total: float
    quantity_received: float
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Purchase Order schemas
# ---------------------------------------------------------------------------


class PurchaseOrderCreate(AppBaseModel):
    supplier_id: uuid.UUID
    order_date: datetime
    expected_delivery_date: datetime | None = None
    notes: str | None = None
    terms_conditions: str | None = None
    shipping_address: str | None = None
    items: list[POItemCreate] = Field(min_length=1)


class PurchaseOrderUpdate(AppBaseModel):
    supplier_id: uuid.UUID | None = None
    order_date: datetime | None = None
    expected_delivery_date: datetime | None = None
    notes: str | None = None
    terms_conditions: str | None = None
    shipping_address: str | None = None
    items: list[POItemCreate] | None = None


class PurchaseOrderRead(AppBaseModel):
    id: uuid.UUID
    po_number: str
    supplier: SupplierRef | None
    status: str
    order_date: datetime
    expected_delivery_date: datetime | None
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    notes: str | None
    terms_conditions: str | None
    shipping_address: str | None
    created_by: UserRef | None
    submitted_by: UserRef | None
    submitted_at: datetime | None
    approved_by: UserRef | None
    approved_at: datetime | None
    rejected_by: UserRef | None
    rejected_at: datetime | None
    rejection_reason: str | None
    cancelled_by: UserRef | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    email_sent_at: datetime | None
    email_sent_to: str | None
    items: list[POItemRead]
    created_at: datetime
    updated_at: datetime


class PurchaseOrderSummary(AppBaseModel):
    """Lightweight PO summary for list views."""

    id: uuid.UUID
    po_number: str
    supplier: SupplierRef | None
    status: str
    order_date: datetime
    expected_delivery_date: datetime | None
    total_amount: float
    item_count: int
    created_at: datetime


class RejectPORequest(AppBaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class CancelRequest(AppBaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class EmailPORequest(AppBaseModel):
    """Optional override for the email recipient."""

    to_email: str | None = Field(default=None)
    message: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# GRN Item schemas
# ---------------------------------------------------------------------------


class GRNItemCreate(AppBaseModel):
    po_item_id: uuid.UUID
    product_id: uuid.UUID
    quantity_received: float = Field(gt=0)
    unit_cost: float = Field(ge=0)
    notes: str | None = None


class GRNItemRead(AppBaseModel):
    id: uuid.UUID
    grn_id: uuid.UUID
    po_item_id: uuid.UUID
    product: ProductRef | None
    quantity_received: float
    unit_cost: float
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# GRN schemas
# ---------------------------------------------------------------------------


class GRNCreate(AppBaseModel):
    purchase_order_id: uuid.UUID
    received_date: datetime
    delivery_note_number: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    items: list[GRNItemCreate] = Field(min_length=1)


class GRNUpdate(AppBaseModel):
    received_date: datetime | None = None
    delivery_note_number: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    items: list[GRNItemCreate] | None = None


class GRNRead(AppBaseModel):
    id: uuid.UUID
    grn_number: str
    purchase_order_id: uuid.UUID
    po_number: str | None = None
    supplier: SupplierRef | None = None
    status: str
    received_date: datetime
    delivery_note_number: str | None
    notes: str | None
    created_by: UserRef | None
    submitted_by: UserRef | None
    submitted_at: datetime | None
    approved_by: UserRef | None
    approved_at: datetime | None
    cancelled_by: UserRef | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    items: list[GRNItemRead]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Inventory Ledger schemas
# ---------------------------------------------------------------------------


class InventoryLedgerRead(AppBaseModel):
    id: uuid.UUID
    product: ProductRef | None
    entry_type: str
    quantity_before: float
    quantity_change: float
    quantity_after: float
    unit_cost: float
    grn_id: uuid.UUID | None
    reference_number: str | None
    notes: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Report filter schemas
# ---------------------------------------------------------------------------


class POReportFilter(AppBaseModel):
    supplier_id: uuid.UUID | None = None
    status: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None


class GRNReportFilter(AppBaseModel):
    supplier_id: uuid.UUID | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    status: str | None = None


# ---------------------------------------------------------------------------
# Dashboard summary schema
# ---------------------------------------------------------------------------


class ProcurementDashboard(AppBaseModel):
    pending_purchase_orders: int
    pending_grns: int
    total_po_this_month: float
    total_po_all_time: float
    approved_pos_this_month: int
    approved_grns_this_month: int
    recent_activities: list[dict]
