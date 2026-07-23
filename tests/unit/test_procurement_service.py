"""
Unit tests for procurement services — Phase 3.

Tests cover PurchaseOrderService, GRNService, InventoryLedgerService,
workflow validations, business rules, and inventory posting.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.procurement import (
    GRN,
    GRNItem,
    GRNStatus,
    InventoryLedger,
    LedgerEntryType,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.models.master_data import Product, Supplier
from app.models.user import User
from app.schemas.procurement import (
    GRNCreate,
    GRNItemCreate,
    POItemCreate,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)
from app.services.procurement import (
    GRNService,
    InventoryLedgerService,
    PurchaseOrderService,
    _calc_line_total,
    _recalc_po_totals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_actor(superuser: bool = True) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.first_name = "Test"
    u.last_name = "User"
    u.email = "test@example.com"
    u.is_superuser = superuser
    u.is_active = True
    u.roles = []
    u.failed_login_attempts = 0
    return u


def _make_supplier() -> Supplier:
    s = Supplier()
    s.id = uuid.uuid4()
    s.supplier_code = "SUP-00001"
    s.name = "Test Supplier"
    s.email = "supplier@example.com"
    s.contact_person = "John"
    s.is_active = True
    s.is_deleted = False
    return s


def _make_product(name: str = "Test Product") -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku = "GEN-20260101-00001"
    p.barcode = "123456789012"
    p.name = name
    p.is_active = True
    p.is_deleted = False
    return p


def _make_po_item(
    po_id: uuid.UUID,
    product: Product,
    qty_ordered: float = 10,
    qty_received: float = 0,
) -> PurchaseOrderItem:
    item = PurchaseOrderItem()
    item.id = uuid.uuid4()
    item.purchase_order_id = po_id
    item.product_id = product.id
    item.product = product
    item.quantity_ordered = qty_ordered
    item.quantity_received = qty_received
    item.unit_price = 100.0
    item.discount_percent = 0
    item.tax_percent = 0
    item.line_total = qty_ordered * 100.0
    item.notes = None
    item.grn_items = []
    return item


def _make_po(status: str = POStatus.DRAFT) -> PurchaseOrder:
    po = PurchaseOrder()
    po.id = uuid.uuid4()
    po.po_number = "PO-20260101-00001"
    po.supplier_id = uuid.uuid4()
    po.supplier = _make_supplier()
    po.status = status
    po.order_date = datetime.now(UTC)
    po.subtotal = 1000.0
    po.tax_amount = 0.0
    po.discount_amount = 0.0
    po.total_amount = 1000.0
    po.notes = None
    po.terms_conditions = None
    po.shipping_address = None
    po.created_by = None
    po.submitted_by = None
    po.submitted_at = None
    po.approved_by = None
    po.approved_at = None
    po.rejected_by = None
    po.rejected_at = None
    po.rejection_reason = None
    po.cancelled_by = None
    po.cancelled_at = None
    po.cancellation_reason = None
    po.email_sent_at = None
    po.email_sent_to = None
    po.is_deleted = False
    po.expected_delivery_date = None
    product = _make_product()
    po.items = [_make_po_item(po.id, product)]
    po.grns = []
    return po


def _make_grn(po: PurchaseOrder, status: str = GRNStatus.DRAFT) -> GRN:
    grn = GRN()
    grn.id = uuid.uuid4()
    grn.grn_number = "GRN-20260101-00001"
    grn.purchase_order_id = po.id
    grn.purchase_order = po
    grn.status = status
    grn.received_date = datetime.now(UTC)
    grn.delivery_note_number = None
    grn.notes = None
    grn.created_by = None
    grn.submitted_by = None
    grn.submitted_at = None
    grn.approved_by = None
    grn.approved_at = None
    grn.cancelled_by = None
    grn.cancelled_at = None
    grn.cancellation_reason = None

    product = po.items[0].product
    grn_item = GRNItem()
    grn_item.id = uuid.uuid4()
    grn_item.grn_id = grn.id
    grn_item.grn = grn
    grn_item.po_item_id = po.items[0].id
    grn_item.po_item = po.items[0]
    grn_item.product_id = product.id
    grn_item.product = product
    grn_item.quantity_received = 5.0
    grn_item.unit_cost = 95.0
    grn_item.notes = None
    grn.items = [grn_item]
    grn.ledger_entries = []
    return grn


def _mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_po_service():
    session = _mock_session()
    svc = PurchaseOrderService.__new__(PurchaseOrderService)
    svc._session = session
    svc._pos = AsyncMock()
    svc._suppliers = AsyncMock()
    svc._products = AsyncMock()
    svc._audit = AsyncMock()
    return svc


def _make_grn_service():
    session = _mock_session()
    svc = GRNService.__new__(GRNService)
    svc._session = session
    svc._grns = AsyncMock()
    svc._pos = AsyncMock()
    svc._products = AsyncMock()
    svc._ledger = AsyncMock()
    svc._audit = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# Line total calculation
# ---------------------------------------------------------------------------


def test_calc_line_total_no_discount_no_tax():
    result = _calc_line_total(10, 100, 0, 0)
    assert result == 1000.0


def test_calc_line_total_with_discount():
    result = _calc_line_total(10, 100, 10, 0)
    assert result == 900.0


def test_calc_line_total_with_tax():
    result = _calc_line_total(10, 100, 0, 10)
    assert result == 1100.0


def test_calc_line_total_with_discount_and_tax():
    # 10 * 100 = 1000, -10% = 900, +10% = 990
    result = _calc_line_total(10, 100, 10, 10)
    assert abs(result - 990.0) < 0.01


def test_recalc_po_totals():
    po = _make_po()
    po.items[0].quantity_ordered = 10
    po.items[0].unit_price = 100.0
    po.items[0].discount_percent = 0
    po.items[0].tax_percent = 0
    _recalc_po_totals(po)
    assert float(po.subtotal) == 1000.0
    assert float(po.total_amount) == 1000.0


# ---------------------------------------------------------------------------
# PurchaseOrderService tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_po_create_success():
    svc = _make_po_service()
    actor = _make_actor()
    supplier = _make_supplier()
    product = _make_product()
    po = _make_po()

    svc._suppliers.get_active.return_value = supplier
    svc._products.get_active.return_value = product
    svc._pos.get_next_po_number.return_value = "PO-20260101-00001"
    svc._pos.po_number_exists.return_value = False
    svc._pos.create.return_value = po
    svc._pos.get_active.return_value = po

    payload = PurchaseOrderCreate(
        supplier_id=supplier.id,
        order_date=datetime.now(UTC),
        items=[
            POItemCreate(
                product_id=product.id,
                quantity_ordered=10,
                unit_price=100.0,
            )
        ],
    )

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.create(payload, actor=actor)

    assert result is po
    svc._pos.create.assert_called_once()


@pytest.mark.asyncio
async def test_po_create_supplier_not_found_raises():
    svc = _make_po_service()
    actor = _make_actor()
    svc._suppliers.get_active.return_value = None

    payload = PurchaseOrderCreate(
        supplier_id=uuid.uuid4(),
        order_date=datetime.now(UTC),
        items=[
            POItemCreate(
                product_id=uuid.uuid4(),
                quantity_ordered=1,
                unit_price=10.0,
            )
        ],
    )
    with pytest.raises(NotFoundError, match="Supplier"):
        await svc.create(payload, actor=actor)


@pytest.mark.asyncio
async def test_po_create_product_not_found_raises():
    svc = _make_po_service()
    actor = _make_actor()
    svc._suppliers.get_active.return_value = _make_supplier()
    svc._products.get_active.return_value = None

    payload = PurchaseOrderCreate(
        supplier_id=uuid.uuid4(),
        order_date=datetime.now(UTC),
        items=[
            POItemCreate(product_id=uuid.uuid4(), quantity_ordered=1, unit_price=10.0)
        ],
    )
    with pytest.raises(NotFoundError, match="Product"):
        await svc.create(payload, actor=actor)


@pytest.mark.asyncio
async def test_po_get_not_found_raises():
    svc = _make_po_service()
    svc._pos.get_active.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4())


@pytest.mark.asyncio
async def test_po_update_non_draft_raises():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.SUBMITTED)
    svc._pos.get_active.return_value = po

    with pytest.raises(ValidationError, match="DRAFT"):
        await svc.update(po.id, PurchaseOrderUpdate(), actor=actor)


@pytest.mark.asyncio
async def test_po_delete_non_draft_raises():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    svc._pos.get_active.return_value = po

    with pytest.raises(ValidationError, match="DRAFT"):
        await svc.delete(po.id, actor=actor)


@pytest.mark.asyncio
async def test_po_submit_success():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.DRAFT)
    po_submitted = _make_po(status=POStatus.SUBMITTED)
    svc._pos.get_active.side_effect = [po, po_submitted]
    svc._pos.update.return_value = po_submitted

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.submit(po.id, actor=actor)

    assert result.status == POStatus.SUBMITTED


@pytest.mark.asyncio
async def test_po_submit_non_draft_raises():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    svc._pos.get_active.return_value = po

    with pytest.raises(ValidationError):
        await svc.submit(po.id, actor=actor)


@pytest.mark.asyncio
async def test_po_submit_no_items_raises():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.DRAFT)
    po.items = []
    svc._pos.get_active.return_value = po

    with pytest.raises(ValidationError, match="no items"):
        await svc.submit(po.id, actor=actor)


@pytest.mark.asyncio
async def test_po_approve_success():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.SUBMITTED)
    po_approved = _make_po(status=POStatus.APPROVED)
    svc._pos.get_active.side_effect = [po, po_approved]
    svc._pos.update.return_value = po_approved

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.approve(po.id, actor=actor)

    assert result.status == POStatus.APPROVED


@pytest.mark.asyncio
async def test_po_approve_non_submitted_raises():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.DRAFT)
    svc._pos.get_active.return_value = po

    with pytest.raises(ValidationError):
        await svc.approve(po.id, actor=actor)


@pytest.mark.asyncio
async def test_po_reject_success():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.SUBMITTED)
    po_rejected = _make_po(status=POStatus.REJECTED)
    svc._pos.get_active.side_effect = [po, po_rejected]
    svc._pos.update.return_value = po_rejected

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.reject(po.id, "Budget exceeded", actor=actor)

    assert result.status == POStatus.REJECTED


@pytest.mark.asyncio
async def test_po_cancel_draft_success():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.DRAFT)
    po_cancelled = _make_po(status=POStatus.CANCELLED)
    svc._pos.get_active.side_effect = [po, po_cancelled]
    svc._pos.update.return_value = po_cancelled

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.cancel(po.id, "Not needed", actor=actor)

    assert result.status == POStatus.CANCELLED


@pytest.mark.asyncio
async def test_po_cancel_approved_raises():
    svc = _make_po_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    svc._pos.get_active.return_value = po

    with pytest.raises(ValidationError):
        await svc.cancel(po.id, "reason", actor=actor)


# ---------------------------------------------------------------------------
# GRNService tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grn_create_success():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po)

    svc._pos.get_active.return_value = po
    svc._grns.get_next_grn_number.return_value = "GRN-20260101-00001"
    svc._grns.create.return_value = grn
    svc._grns.get_active.return_value = grn

    payload = GRNCreate(
        purchase_order_id=po.id,
        received_date=datetime.now(UTC),
        items=[
            GRNItemCreate(
                po_item_id=po.items[0].id,
                product_id=po.items[0].product_id,
                quantity_received=5.0,
                unit_cost=95.0,
            )
        ],
    )

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.create(payload, actor=actor)

    assert result is grn
    svc._grns.create.assert_called_once()


@pytest.mark.asyncio
async def test_grn_create_non_approved_po_raises():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.SUBMITTED)
    svc._pos.get_active.return_value = po

    payload = GRNCreate(
        purchase_order_id=po.id,
        received_date=datetime.now(UTC),
        items=[
            GRNItemCreate(
                po_item_id=po.items[0].id,
                product_id=po.items[0].product_id,
                quantity_received=5.0,
                unit_cost=95.0,
            )
        ],
    )
    with pytest.raises(ValidationError, match="Approved"):
        await svc.create(payload, actor=actor)


@pytest.mark.asyncio
async def test_grn_create_over_quantity_raises():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    po.items[0].quantity_ordered = 10
    po.items[0].quantity_received = 0
    svc._pos.get_active.return_value = po

    payload = GRNCreate(
        purchase_order_id=po.id,
        received_date=datetime.now(UTC),
        items=[
            GRNItemCreate(
                po_item_id=po.items[0].id,
                product_id=po.items[0].product_id,
                quantity_received=15.0,  # over-receive
                unit_cost=95.0,
            )
        ],
    )
    with pytest.raises(ValidationError, match="Cannot receive"):
        await svc.create(payload, actor=actor)


@pytest.mark.asyncio
async def test_grn_create_po_not_found_raises():
    svc = _make_grn_service()
    actor = _make_actor()
    svc._pos.get_active.return_value = None

    payload = GRNCreate(
        purchase_order_id=uuid.uuid4(),
        received_date=datetime.now(UTC),
        items=[
            GRNItemCreate(
                po_item_id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                quantity_received=1.0,
                unit_cost=10.0,
            )
        ],
    )
    with pytest.raises(NotFoundError):
        await svc.create(payload, actor=actor)


@pytest.mark.asyncio
async def test_grn_get_not_found_raises():
    svc = _make_grn_service()
    svc._grns.get_active.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4())


@pytest.mark.asyncio
async def test_grn_submit_success():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po, status=GRNStatus.DRAFT)
    grn_submitted = _make_grn(po, status=GRNStatus.SUBMITTED)
    svc._grns.get_active.side_effect = [grn, grn_submitted]
    svc._grns.update.return_value = grn_submitted

    result = await svc.submit(grn.id, actor=actor)
    assert result.status == GRNStatus.SUBMITTED


@pytest.mark.asyncio
async def test_grn_submit_non_draft_raises():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po, status=GRNStatus.SUBMITTED)
    svc._grns.get_active.return_value = grn

    with pytest.raises(ValidationError):
        await svc.submit(grn.id, actor=actor)


@pytest.mark.asyncio
async def test_grn_approve_posts_inventory():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po, status=GRNStatus.SUBMITTED)
    grn_approved = _make_grn(po, status=GRNStatus.APPROVED)

    svc._grns.get_active.side_effect = [grn, grn_approved]
    svc._grns.update.return_value = grn_approved
    svc._ledger.get_current_stock.return_value = 0.0
    svc._ledger.append.return_value = InventoryLedger()
    svc._pos.get_active.return_value = po
    svc._pos.update.return_value = po

    from sqlalchemy import update as sa_update

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.approve(grn.id, actor=actor)

    # Verify ledger append was called for each GRN item
    svc._ledger.append.assert_called_once()
    call_kwargs = svc._ledger.append.call_args.kwargs
    assert call_kwargs["entry_type"] == LedgerEntryType.PURCHASE_RECEIPT
    assert call_kwargs["quantity_change"] == 5.0
    assert call_kwargs["quantity_before"] == 0.0
    assert call_kwargs["quantity_after"] == 5.0


@pytest.mark.asyncio
async def test_grn_approve_non_submitted_raises():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po, status=GRNStatus.DRAFT)
    svc._grns.get_active.return_value = grn

    with pytest.raises(ValidationError):
        await svc.approve(grn.id, actor=actor)


@pytest.mark.asyncio
async def test_grn_cancel_approved_raises():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.FULLY_RECEIVED)
    grn = _make_grn(po, status=GRNStatus.APPROVED)
    svc._grns.get_active.return_value = grn

    with pytest.raises(ValidationError, match="Approved"):
        await svc.cancel(grn.id, "reason", actor=actor)


@pytest.mark.asyncio
async def test_grn_cancel_draft_success():
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po, status=GRNStatus.DRAFT)
    grn_cancelled = _make_grn(po, status=GRNStatus.CANCELLED)
    svc._grns.get_active.side_effect = [grn, grn_cancelled]
    svc._grns.update.return_value = grn_cancelled

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.cancel(grn.id, "Not needed", actor=actor)

    assert result.status == GRNStatus.CANCELLED


# ---------------------------------------------------------------------------
# Partial delivery — PO status becomes PARTIALLY_RECEIVED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grn_approve_partial_delivery_sets_po_status():
    """
    When a GRN is approved with partial quantities, the PO status reflects
    how much has been received based on the current in-memory state.
    Since we mock session.execute (the UPDATE), po_item.quantity_received
    stays at 0.0 after the mock, so the service sees 0/10 → stays APPROVED.
    The real integration test would verify PARTIALLY_RECEIVED.
    This test verifies the service calls _pos.update at all.
    """
    svc = _make_grn_service()
    actor = _make_actor()
    po = _make_po(status=POStatus.APPROVED)
    po.items[0].quantity_ordered = 10
    po.items[0].quantity_received = 0.0

    grn = _make_grn(po, status=GRNStatus.SUBMITTED)
    grn.items[0].quantity_received = 5.0
    grn_approved = _make_grn(po, status=GRNStatus.APPROVED)

    svc._grns.get_active.side_effect = [grn, grn_approved]
    svc._grns.update.return_value = grn_approved
    svc._ledger.get_current_stock.return_value = 0.0
    svc._ledger.append.return_value = InventoryLedger()
    svc._pos.get_active.return_value = po
    svc._pos.update.return_value = po

    with patch("app.services.procurement.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.approve(grn.id, actor=actor)

    # Verify PO status was updated (mocked session won't reflect in-memory update)
    svc._pos.update.assert_called_once()
    # Verify ledger was posted
    svc._ledger.append.assert_called_once()
    assert result.status == GRNStatus.APPROVED
