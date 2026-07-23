"""Unit tests for inventory services — Phase 4."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.inventory import (
    Inventory,
    InventoryLedgerEntry,
    LedgerEntryType,
    StockAdjustment,
    StockAdjustmentItem,
    StockAdjustmentStatus,
    StockAdjustmentType,
)
from app.models.master_data import Product
from app.models.user import User
from app.schemas.inventory import (
    StockAdjustmentCreate,
    StockAdjustmentItemCreate,
    StockAdjustmentUpdate,
)
from app.services.inventory import (
    InventoryService,
    StockAdjustmentService,
    _apply_inventory_change,
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


def _make_product(name: str = "Test Product") -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku = "GEN-20260101-00001"
    p.barcode = "123456789012"
    p.name = name
    p.reorder_level = 5
    p.is_active = True
    p.is_deleted = False
    return p


def _make_inventory(product: Product) -> Inventory:
    inv = Inventory()
    inv.id = uuid.uuid4()
    inv.product_id = product.id
    inv.product = product
    inv.quantity_on_hand = 0.0
    inv.average_cost = 0.0
    inv.last_updated_at = None
    inv.last_transaction_type = None
    return inv


def _make_adjustment(
    adjustment_type: str = StockAdjustmentType.INCREASE,
    status: str = StockAdjustmentStatus.DRAFT,
) -> StockAdjustment:
    adj = StockAdjustment()
    adj.id = uuid.uuid4()
    adj.adjustment_number = "ADJ-20260101-00001"
    adj.adjustment_type = adjustment_type
    adj.status = status
    adj.reason = "Test reason"
    adj.notes = None
    adj.items = []
    adj.created_by = None
    adj.submitted_by = None
    adj.submitted_at = None
    adj.approved_by = None
    adj.approved_at = None
    adj.cancelled_by = None
    adj.cancelled_at = None
    adj.cancellation_reason = None
    adj.is_deleted = False
    return adj


def _mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_inventory_service() -> InventoryService:
    session = _mock_session()
    svc = InventoryService.__new__(InventoryService)
    svc._session = session
    svc._inv = AsyncMock()
    svc._ledger = AsyncMock()
    svc._products = AsyncMock()
    return svc


def _make_adjustment_service() -> StockAdjustmentService:
    session = _mock_session()
    svc = StockAdjustmentService.__new__(StockAdjustmentService)
    svc._session = session
    svc._adj = AsyncMock()
    svc._inv = AsyncMock()
    svc._ledger = AsyncMock()
    svc._products = AsyncMock()
    svc._audit = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# _apply_inventory_change tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_inventory_change_increase():
    product = _make_product()
    inv = _make_inventory(product)
    inv.quantity_on_hand = 0.0
    inv.average_cost = 0.0

    inventory_repo = AsyncMock()
    inventory_repo.session = _mock_session()
    ledger_repo = AsyncMock()
    mock_entry = MagicMock(spec=InventoryLedgerEntry)
    ledger_repo.append = AsyncMock(return_value=mock_entry)

    result = await _apply_inventory_change(
        inv,
        qty_change=10.0,
        unit_cost=5.0,
        inventory_repo=inventory_repo,
        ledger_repo=ledger_repo,
        entry_type=LedgerEntryType.ADJUSTMENT_IN,
        reference_type="STOCK_ADJUSTMENT",
        reference_id=uuid.uuid4(),
        reference_number="ADJ-20260101-00001",
        notes="Test increase",
        created_by_id=uuid.uuid4(),
    )

    assert float(inv.quantity_on_hand) == 10.0
    assert result is mock_entry


@pytest.mark.asyncio
async def test_apply_inventory_change_decrease_valid():
    product = _make_product()
    inv = _make_inventory(product)
    inv.quantity_on_hand = 20.0
    inv.average_cost = 10.0

    inventory_repo = AsyncMock()
    inventory_repo.session = _mock_session()
    ledger_repo = AsyncMock()
    mock_entry = MagicMock(spec=InventoryLedgerEntry)
    ledger_repo.append = AsyncMock(return_value=mock_entry)

    await _apply_inventory_change(
        inv,
        qty_change=-5.0,
        unit_cost=10.0,
        inventory_repo=inventory_repo,
        ledger_repo=ledger_repo,
        entry_type=LedgerEntryType.ADJUSTMENT_OUT,
        reference_type="STOCK_ADJUSTMENT",
        reference_id=uuid.uuid4(),
        reference_number="ADJ-20260101-00001",
        notes="Test decrease",
        created_by_id=uuid.uuid4(),
    )

    assert float(inv.quantity_on_hand) == 15.0


@pytest.mark.asyncio
async def test_apply_inventory_change_below_zero_raises():
    product = _make_product()
    inv = _make_inventory(product)
    inv.quantity_on_hand = 5.0
    inv.average_cost = 10.0

    inventory_repo = AsyncMock()
    inventory_repo.session = _mock_session()
    ledger_repo = AsyncMock()

    with pytest.raises(ValidationError, match="Insufficient"):
        await _apply_inventory_change(
            inv,
            qty_change=-10.0,
            unit_cost=10.0,
            inventory_repo=inventory_repo,
            ledger_repo=ledger_repo,
            entry_type=LedgerEntryType.ADJUSTMENT_OUT,
            reference_type="STOCK_ADJUSTMENT",
            reference_id=uuid.uuid4(),
            reference_number="ADJ-20260101-00001",
            notes="Test below zero",
            created_by_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_apply_inventory_change_updates_weighted_avg_cost():
    product = _make_product()
    inv = _make_inventory(product)
    inv.quantity_on_hand = 10.0
    inv.average_cost = 10.0

    inventory_repo = AsyncMock()
    inventory_repo.session = _mock_session()
    ledger_repo = AsyncMock()
    mock_entry = MagicMock(spec=InventoryLedgerEntry)
    ledger_repo.append = AsyncMock(return_value=mock_entry)

    await _apply_inventory_change(
        inv,
        qty_change=10.0,
        unit_cost=20.0,
        inventory_repo=inventory_repo,
        ledger_repo=ledger_repo,
        entry_type=LedgerEntryType.ADJUSTMENT_IN,
        reference_type="STOCK_ADJUSTMENT",
        reference_id=uuid.uuid4(),
        reference_number="ADJ-20260101-00001",
        notes="Weighted avg test",
        created_by_id=uuid.uuid4(),
    )

    # (10 * 10 + 10 * 20) / 20 = 300 / 20 = 15.0
    assert float(inv.average_cost) == 15.0


# ---------------------------------------------------------------------------
# InventoryService tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inventory_service_get_by_product_not_found_raises():
    svc = _make_inventory_service()
    svc._products.get_active.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get_by_product(uuid.uuid4())


@pytest.mark.asyncio
async def test_inventory_service_get_summary_returns_dict():
    svc = _make_inventory_service()
    expected = {
        "total_products": 10,
        "total_products_in_stock": 8,
        "total_out_of_stock": 2,
        "total_low_stock": 3,
        "total_quantity_on_hand": 200.0,
        "total_stock_value": 5000.0,
    }
    svc._inv.get_summary = AsyncMock(return_value=expected)

    result = await svc.get_summary()

    assert "total_products" in result
    assert result == expected


# ---------------------------------------------------------------------------
# StockAdjustmentService — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_adjustment_create_success():
    svc = _make_adjustment_service()
    actor = _make_actor()
    product = _make_product()
    adj = _make_adjustment()

    svc._products.get_active.return_value = product
    svc._adj.get_next_adjustment_number = AsyncMock(return_value="ADJ-20260101-00001")
    svc._adj.get_active = AsyncMock(return_value=adj)

    payload = StockAdjustmentCreate(
        adjustment_type=StockAdjustmentType.INCREASE,
        reason="Found extra stock",
        items=[
            StockAdjustmentItemCreate(
                product_id=product.id,
                quantity_adjusted=10.0,
                unit_cost=5.0,
            )
        ],
    )

    with patch("app.services.inventory.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.create(payload, actor=actor)

    assert result is adj
    assert result.status == StockAdjustmentStatus.DRAFT
    assert result.adjustment_number == "ADJ-20260101-00001"
    svc._audit.log.assert_called_once()


@pytest.mark.asyncio
async def test_stock_adjustment_create_product_not_found_raises():
    svc = _make_adjustment_service()
    actor = _make_actor()
    svc._products.get_active.return_value = None

    payload = StockAdjustmentCreate(
        adjustment_type=StockAdjustmentType.INCREASE,
        reason="Test",
        items=[
            StockAdjustmentItemCreate(
                product_id=uuid.uuid4(),
                quantity_adjusted=10.0,
            )
        ],
    )

    with pytest.raises(NotFoundError):
        await svc.create(payload, actor=actor)


# ---------------------------------------------------------------------------
# StockAdjustmentService — get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_adjustment_get_not_found_raises():
    svc = _make_adjustment_service()
    svc._adj.get_active.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4())


# ---------------------------------------------------------------------------
# StockAdjustmentService — update / delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_adjustment_update_non_draft_raises():
    svc = _make_adjustment_service()
    actor = _make_actor()
    adj = _make_adjustment(status=StockAdjustmentStatus.SUBMITTED)
    svc._adj.get_active.return_value = adj

    with pytest.raises(ValidationError, match="DRAFT"):
        await svc.update(adj.id, StockAdjustmentUpdate(), actor=actor)


@pytest.mark.asyncio
async def test_stock_adjustment_delete_non_draft_raises():
    svc = _make_adjustment_service()
    actor = _make_actor()
    adj = _make_adjustment(status=StockAdjustmentStatus.APPROVED)
    svc._adj.get_active.return_value = adj

    with pytest.raises(ValidationError, match="DRAFT"):
        await svc.delete(adj.id, actor=actor)


# ---------------------------------------------------------------------------
# StockAdjustmentService — submit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_adjustment_submit_success():
    svc = _make_adjustment_service()
    actor = _make_actor()
    product = _make_product()

    adj_draft = _make_adjustment(status=StockAdjustmentStatus.DRAFT)

    item = StockAdjustmentItem()
    item.id = uuid.uuid4()
    item.stock_adjustment_id = adj_draft.id
    item.stock_adjustment = adj_draft
    item.product_id = product.id
    item.product = product
    item.quantity_adjusted = 10.0
    item.unit_cost = 5.0
    item.notes = None
    # Assign via the instrumented list so SA back-references are set
    adj_draft.items.append(item)

    adj_submitted = _make_adjustment(status=StockAdjustmentStatus.SUBMITTED)
    adj_submitted.items.append(item)

    svc._adj.get_active.side_effect = [adj_draft, adj_submitted]

    with patch("app.services.inventory.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.submit(adj_draft.id, actor=actor)

    assert result.status == StockAdjustmentStatus.SUBMITTED


@pytest.mark.asyncio
async def test_stock_adjustment_submit_non_draft_raises():
    svc = _make_adjustment_service()
    actor = _make_actor()
    adj = _make_adjustment(status=StockAdjustmentStatus.SUBMITTED)
    svc._adj.get_active.return_value = adj

    with pytest.raises(ValidationError):
        await svc.submit(adj.id, actor=actor)


@pytest.mark.asyncio
async def test_stock_adjustment_submit_no_items_raises():
    svc = _make_adjustment_service()
    actor = _make_actor()
    adj = _make_adjustment(status=StockAdjustmentStatus.DRAFT)
    adj.items = []
    svc._adj.get_active.return_value = adj

    with pytest.raises(ValidationError, match="no items"):
        await svc.submit(adj.id, actor=actor)


# ---------------------------------------------------------------------------
# StockAdjustmentService — approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_adjustment_approve_increase_adds_stock():
    svc = _make_adjustment_service()
    actor = _make_actor()
    product = _make_product()

    adj = _make_adjustment(
        adjustment_type=StockAdjustmentType.INCREASE,
        status=StockAdjustmentStatus.SUBMITTED,
    )
    item = StockAdjustmentItem()
    item.id = uuid.uuid4()
    item.stock_adjustment_id = adj.id
    item.stock_adjustment = adj
    item.product_id = product.id
    item.product = product
    item.quantity_adjusted = 10.0
    item.unit_cost = 5.0
    item.notes = None
    adj.items.append(item)

    adj_approved = _make_adjustment(
        adjustment_type=StockAdjustmentType.INCREASE,
        status=StockAdjustmentStatus.APPROVED,
    )
    adj_approved.items.append(item)

    inv = _make_inventory(product)
    svc._inv.get_or_create = AsyncMock(return_value=inv)
    svc._adj.get_active.side_effect = [adj, adj_approved]

    mock_entry = MagicMock(spec=InventoryLedgerEntry)

    with patch("app.services.inventory.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        with patch(
            "app.services.inventory._apply_inventory_change",
            new=AsyncMock(return_value=mock_entry),
        ) as mock_apply:
            with patch.object(
                InventoryService, "_publish_stock_alerts", new=AsyncMock()
            ):
                result = await svc.approve(adj.id, actor=actor)

    # Verify _apply_inventory_change was called with a positive qty_change
    mock_apply.assert_called_once()
    call_kwargs = mock_apply.call_args
    # qty_change is passed as the second positional arg: _apply_inventory_change(inv, qty_change, ...)
    qty_change = call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("qty_change")
    assert qty_change is not None
    assert qty_change > 0


@pytest.mark.asyncio
async def test_stock_adjustment_approve_decrease_removes_stock():
    svc = _make_adjustment_service()
    actor = _make_actor()
    product = _make_product()

    adj = _make_adjustment(
        adjustment_type=StockAdjustmentType.DECREASE,
        status=StockAdjustmentStatus.SUBMITTED,
    )
    item = StockAdjustmentItem()
    item.id = uuid.uuid4()
    item.stock_adjustment_id = adj.id
    item.stock_adjustment = adj
    item.product_id = product.id
    item.product = product
    item.quantity_adjusted = 5.0
    item.unit_cost = 0.0
    item.notes = None
    adj.items.append(item)

    adj_approved = _make_adjustment(
        adjustment_type=StockAdjustmentType.DECREASE,
        status=StockAdjustmentStatus.APPROVED,
    )
    adj_approved.items.append(item)

    inv = _make_inventory(product)
    inv.quantity_on_hand = 20.0
    svc._inv.get_or_create = AsyncMock(return_value=inv)
    svc._adj.get_active.side_effect = [adj, adj_approved]

    mock_entry = MagicMock(spec=InventoryLedgerEntry)

    with patch("app.services.inventory.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        with patch(
            "app.services.inventory._apply_inventory_change",
            new=AsyncMock(return_value=mock_entry),
        ) as mock_apply:
            with patch.object(
                InventoryService, "_publish_stock_alerts", new=AsyncMock()
            ):
                result = await svc.approve(adj.id, actor=actor)

    mock_apply.assert_called_once()
    # qty_change should be negative for a DECREASE
    call_args = mock_apply.call_args
    qty_change = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("qty_change")
    assert qty_change < 0


@pytest.mark.asyncio
async def test_stock_adjustment_approve_non_submitted_raises():
    svc = _make_adjustment_service()
    actor = _make_actor()
    adj = _make_adjustment(status=StockAdjustmentStatus.DRAFT)
    svc._adj.get_active.return_value = adj

    with pytest.raises(ValidationError):
        await svc.approve(adj.id, actor=actor)


# ---------------------------------------------------------------------------
# StockAdjustmentService — cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_adjustment_cancel_success():
    svc = _make_adjustment_service()
    actor = _make_actor()

    adj_draft = _make_adjustment(status=StockAdjustmentStatus.DRAFT)
    adj_cancelled = _make_adjustment(status=StockAdjustmentStatus.CANCELLED)
    adj_cancelled.cancellation_reason = "Not needed"
    svc._adj.get_active.side_effect = [adj_draft, adj_cancelled]

    with patch("app.services.inventory.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.cancel(adj_draft.id, "Not needed", actor=actor)

    assert result.status == StockAdjustmentStatus.CANCELLED


@pytest.mark.asyncio
async def test_stock_adjustment_cancel_approved_raises():
    svc = _make_adjustment_service()
    actor = _make_actor()
    adj = _make_adjustment(status=StockAdjustmentStatus.APPROVED)
    svc._adj.get_active.return_value = adj

    with pytest.raises(ValidationError):
        await svc.cancel(adj.id, "reason", actor=actor)
