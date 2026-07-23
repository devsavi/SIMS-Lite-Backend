"""
Unit tests for Stock Release service — Phase 5.

Covers:
- StockReleaseService: create, get, update, delete, submit, approve, cancel
- Inventory validation (negative stock prevention)
- Ledger entry creation on approval
- Status transition guards
- WebSocket event broadcasting
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.inventory import Inventory, InventoryLedgerEntry, LedgerEntryType
from app.models.master_data import Product
from app.models.stock_release import (
    StockRelease,
    StockReleaseItem,
    StockReleasePurpose,
    StockReleaseStatus,
)
from app.models.user import User
from app.schemas.stock_release import (
    StockReleaseCreate,
    StockReleaseItemCreate,
    StockReleaseUpdate,
)
from app.services.stock_release import StockReleaseService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


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
    p.sku = "TST-20260101-00001"
    p.barcode = "123456789012"
    p.name = name
    p.reorder_level = 5
    p.cost_price = 10.0
    p.selling_price = 15.0
    p.is_active = True
    p.is_deleted = False
    p.category = None
    p.brand = None
    p.uom = None
    p.supplier = None
    return p


def _make_inventory(product: Product, qty: float = 100.0) -> Inventory:
    inv = Inventory()
    inv.id = uuid.uuid4()
    inv.product_id = product.id
    inv.product = product
    inv.quantity_on_hand = qty
    inv.average_cost = 10.0
    inv.last_updated_at = _now()
    inv.last_transaction_type = "PURCHASE_RECEIPT"
    return inv


def _make_release(
    status: str = StockReleaseStatus.DRAFT,
    purpose: str = StockReleasePurpose.INTERNAL_USE,
) -> StockRelease:
    sr = StockRelease()
    sr.id = uuid.uuid4()
    sr.release_number = "SR-20260101-00001"
    sr.purpose = purpose
    sr.status = status
    sr.release_date = _now()
    sr.notes = None
    sr.reference_document = None
    sr.total_quantity = 0.0
    sr.total_cost = 0.0
    sr.items = []
    sr.created_by = None
    sr.submitted_by = None
    sr.submitted_at = None
    sr.approved_by = None
    sr.approved_at = None
    sr.cancelled_by = None
    sr.cancelled_at = None
    sr.cancellation_reason = None
    sr.is_deleted = False
    sr.created_at = _now()
    sr.updated_at = _now()
    return sr


def _make_release_item(
    release: StockRelease,
    product: Product,
    qty: float = 10.0,
) -> StockReleaseItem:
    item = StockReleaseItem()
    item.id = uuid.uuid4()
    item.stock_release_id = release.id
    item.stock_release = release
    item.product_id = product.id
    item.product = product
    item.quantity_requested = qty
    item.unit_cost = 0.0
    item.line_total = 0.0
    item.notes = None
    item.created_at = _now()
    item.updated_at = _now()
    return item


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_service() -> StockReleaseService:
    session = _mock_session()
    svc = StockReleaseService.__new__(StockReleaseService)
    svc._session = session
    svc._sr = AsyncMock()
    svc._inv = AsyncMock()
    svc._ledger = AsyncMock()
    svc._products = AsyncMock()
    svc._audit = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_success():
    svc = _make_service()
    actor = _make_actor()
    product = _make_product()
    release = _make_release()

    svc._products.get_active.return_value = product
    svc._sr.get_next_release_number = AsyncMock(return_value="SR-20260101-00001")
    svc._sr.get_active = AsyncMock(return_value=release)

    payload = StockReleaseCreate(
        purpose=StockReleasePurpose.INTERNAL_USE,
        release_date=_now(),
        items=[StockReleaseItemCreate(product_id=product.id, quantity_requested=10.0)],
    )

    with patch("app.services.stock_release.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.create(payload, actor=actor)

    assert result is release
    svc._audit.log.assert_called_once()
    mock_ws.broadcast_json.assert_called_once()


@pytest.mark.asyncio
async def test_create_product_not_found_raises():
    svc = _make_service()
    actor = _make_actor()
    svc._products.get_active.return_value = None

    payload = StockReleaseCreate(
        purpose=StockReleasePurpose.INTERNAL_USE,
        release_date=_now(),
        items=[StockReleaseItemCreate(product_id=uuid.uuid4(), quantity_requested=5.0)],
    )

    with pytest.raises(NotFoundError):
        await svc.create(payload, actor=actor)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_not_found_raises():
    svc = _make_service()
    svc._sr.get_active.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_success():
    svc = _make_service()
    release = _make_release()
    svc._sr.get_active.return_value = release

    result = await svc.get(release.id)
    assert result is release


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_non_draft_raises():
    svc = _make_service()
    actor = _make_actor()
    release = _make_release(status=StockReleaseStatus.SUBMITTED)
    svc._sr.get_active.return_value = release

    with pytest.raises(ValidationError, match="DRAFT"):
        await svc.update(release.id, StockReleaseUpdate(), actor=actor)


@pytest.mark.asyncio
async def test_update_draft_success():
    svc = _make_service()
    actor = _make_actor()
    release = _make_release(status=StockReleaseStatus.DRAFT)
    updated_release = _make_release(status=StockReleaseStatus.DRAFT)
    updated_release.notes = "Updated notes"

    svc._sr.get_active.side_effect = [release, updated_release]

    result = await svc.update(
        release.id, StockReleaseUpdate(notes="Updated notes"), actor=actor
    )
    assert result.notes == "Updated notes"
    svc._audit.log.assert_called_once()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_non_draft_raises():
    svc = _make_service()
    actor = _make_actor()
    release = _make_release(status=StockReleaseStatus.APPROVED)
    svc._sr.get_active.return_value = release

    with pytest.raises(ValidationError, match="DRAFT"):
        await svc.delete(release.id, actor=actor)


@pytest.mark.asyncio
async def test_delete_draft_success():
    svc = _make_service()
    actor = _make_actor()
    release = _make_release(status=StockReleaseStatus.DRAFT)
    svc._sr.get_active.return_value = release

    await svc.delete(release.id, actor=actor)

    assert release.is_deleted is True
    svc._audit.log.assert_called_once()


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_success():
    svc = _make_service()
    actor = _make_actor()
    product = _make_product()

    draft = _make_release(status=StockReleaseStatus.DRAFT)
    item = _make_release_item(draft, product)
    draft.items.append(item)

    submitted = _make_release(status=StockReleaseStatus.SUBMITTED)
    submitted.items.append(item)

    svc._sr.get_active.side_effect = [draft, submitted]

    with patch("app.services.stock_release.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.submit(draft.id, actor=actor)

    assert result.status == StockReleaseStatus.SUBMITTED
    mock_ws.broadcast_json.assert_called_once()


@pytest.mark.asyncio
async def test_submit_non_draft_raises():
    svc = _make_service()
    actor = _make_actor()
    release = _make_release(status=StockReleaseStatus.SUBMITTED)
    svc._sr.get_active.return_value = release

    with pytest.raises(ValidationError):
        await svc.submit(release.id, actor=actor)


@pytest.mark.asyncio
async def test_submit_no_items_raises():
    svc = _make_service()
    actor = _make_actor()
    release = _make_release(status=StockReleaseStatus.DRAFT)
    release.items = []
    svc._sr.get_active.return_value = release

    with pytest.raises(ValidationError, match="no items"):
        await svc.submit(release.id, actor=actor)


# ---------------------------------------------------------------------------
# approve — inventory validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_insufficient_stock_raises():
    """Approval must fail if any item exceeds available inventory."""
    svc = _make_service()
    actor = _make_actor()
    product = _make_product()

    # Only 5 units available, but 20 requested
    inv = _make_inventory(product, qty=5.0)
    submitted = _make_release(status=StockReleaseStatus.SUBMITTED)
    item = _make_release_item(submitted, product, qty=20.0)
    submitted.items.append(item)

    svc._sr.get_active.return_value = submitted
    svc._inv.get_by_product.return_value = inv

    with pytest.raises(ValidationError, match="Insufficient stock"):
        await svc.approve(submitted.id, actor=actor)


@pytest.mark.asyncio
async def test_approve_zero_stock_raises():
    """Approval must fail if product has zero stock."""
    svc = _make_service()
    actor = _make_actor()
    product = _make_product()

    inv = _make_inventory(product, qty=0.0)
    submitted = _make_release(status=StockReleaseStatus.SUBMITTED)
    item = _make_release_item(submitted, product, qty=1.0)
    submitted.items.append(item)

    svc._sr.get_active.return_value = submitted
    svc._inv.get_by_product.return_value = inv

    with pytest.raises(ValidationError, match="Insufficient stock"):
        await svc.approve(submitted.id, actor=actor)


@pytest.mark.asyncio
async def test_approve_non_submitted_raises():
    svc = _make_service()
    actor = _make_actor()
    release = _make_release(status=StockReleaseStatus.DRAFT)
    svc._sr.get_active.return_value = release

    with pytest.raises(ValidationError):
        await svc.approve(release.id, actor=actor)


@pytest.mark.asyncio
async def test_approve_success_deducts_inventory():
    """
    On approval:
    - _apply_inventory_change is called with negative qty_change
    - item.unit_cost and item.line_total are updated
    - ledger entry is created
    - WebSocket events are broadcast
    """
    svc = _make_service()
    actor = _make_actor()
    product = _make_product()

    inv = _make_inventory(product, qty=50.0)
    inv.average_cost = 10.0

    submitted = _make_release(status=StockReleaseStatus.SUBMITTED)
    item = _make_release_item(submitted, product, qty=10.0)
    submitted.items.append(item)

    approved = _make_release(status=StockReleaseStatus.APPROVED)
    approved.total_quantity = 10.0
    approved.total_cost = 100.0

    svc._sr.get_active.side_effect = [submitted, approved]
    svc._inv.get_by_product.return_value = inv
    svc._inv.get_or_create = AsyncMock(return_value=inv)

    mock_entry = MagicMock(spec=InventoryLedgerEntry)

    with patch("app.services.stock_release.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        with patch(
            "app.services.stock_release._apply_inventory_change",
            new=AsyncMock(return_value=mock_entry),
        ) as mock_apply:
            with patch(
                "app.services.stock_release.InventoryService"
            ) as mock_inv_svc_cls:
                mock_inv_svc = MagicMock()
                mock_inv_svc._publish_stock_alerts = AsyncMock()
                mock_inv_svc_cls.return_value = mock_inv_svc

                result = await svc.approve(submitted.id, actor=actor)

    # Verify _apply_inventory_change was called with negative qty
    assert mock_apply.called, "_apply_inventory_change must be called on approval"
    call_kwargs = mock_apply.call_args_list[0]  # inspect first call
    qty_change = (
        call_kwargs.args[1]
        if len(call_kwargs.args) > 1
        else call_kwargs.kwargs.get("qty_change")
    )
    assert qty_change is not None
    assert qty_change < 0, "Approval must deduct (negative) qty from inventory"

    # Verify entry_type is STOCK_RELEASE
    entry_type = call_kwargs.kwargs.get("entry_type")
    assert entry_type == LedgerEntryType.STOCK_RELEASE

    # Broadcast called at least once (inventory + approval events)
    assert mock_ws.broadcast_json.call_count >= 1

    # Audit logged
    svc._audit.log.assert_called()


@pytest.mark.asyncio
async def test_approve_updates_item_cost_from_average():
    """Unit cost on items should be set from inventory.average_cost at approval time."""
    svc = _make_service()
    actor = _make_actor()
    product = _make_product()

    inv = _make_inventory(product, qty=100.0)
    inv.average_cost = 25.0  # current WAC

    submitted = _make_release(status=StockReleaseStatus.SUBMITTED)
    item = _make_release_item(submitted, product, qty=4.0)
    item.unit_cost = 0.0  # not yet set
    submitted.items.append(item)

    approved = _make_release(status=StockReleaseStatus.APPROVED)

    svc._sr.get_active.side_effect = [submitted, approved]
    svc._inv.get_by_product.return_value = inv
    svc._inv.get_or_create = AsyncMock(return_value=inv)

    mock_entry = MagicMock(spec=InventoryLedgerEntry)

    with patch("app.services.stock_release.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        with patch(
            "app.services.stock_release._apply_inventory_change",
            new=AsyncMock(return_value=mock_entry),
        ):
            with patch("app.services.stock_release.InventoryService") as mock_cls:
                mock_inv_svc = MagicMock()
                mock_inv_svc._publish_stock_alerts = AsyncMock()
                mock_cls.return_value = mock_inv_svc
                await svc.approve(submitted.id, actor=actor)

    # Item should be updated with WAC from inventory
    assert float(item.unit_cost) == 25.0
    assert float(item.line_total) == round(4.0 * 25.0, 4)


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_draft_success():
    svc = _make_service()
    actor = _make_actor()

    draft = _make_release(status=StockReleaseStatus.DRAFT)
    cancelled = _make_release(status=StockReleaseStatus.CANCELLED)
    cancelled.cancellation_reason = "Not needed"
    svc._sr.get_active.side_effect = [draft, cancelled]

    with patch("app.services.stock_release.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.cancel(draft.id, "Not needed", actor=actor)

    assert result.status == StockReleaseStatus.CANCELLED
    mock_ws.broadcast_json.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_submitted_success():
    svc = _make_service()
    actor = _make_actor()

    submitted = _make_release(status=StockReleaseStatus.SUBMITTED)
    cancelled = _make_release(status=StockReleaseStatus.CANCELLED)
    cancelled.cancellation_reason = "Rejected"
    svc._sr.get_active.side_effect = [submitted, cancelled]

    with patch("app.services.stock_release.ws_manager") as mock_ws:
        mock_ws.broadcast_json = AsyncMock()
        result = await svc.cancel(submitted.id, "Rejected", actor=actor)

    assert result.status == StockReleaseStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_approved_raises():
    svc = _make_service()
    actor = _make_actor()
    release = _make_release(status=StockReleaseStatus.APPROVED)
    svc._sr.get_active.return_value = release

    with pytest.raises(ValidationError):
        await svc.cancel(release.id, "reason", actor=actor)


# ---------------------------------------------------------------------------
# Duplicate products in items
# ---------------------------------------------------------------------------


def test_create_schema_rejects_duplicate_products():
    """StockReleaseCreate validator must reject duplicate product IDs."""
    product_id = uuid.uuid4()
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        StockReleaseCreate(
            purpose=StockReleasePurpose.INTERNAL_USE,
            release_date=datetime.now(UTC),
            items=[
                StockReleaseItemCreate(product_id=product_id, quantity_requested=5.0),
                StockReleaseItemCreate(product_id=product_id, quantity_requested=3.0),
            ],
        )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_service_returns_expected_keys():
    from app.services.stock_release import StockReleaseDashboardService

    session = _mock_session()
    svc = StockReleaseDashboardService.__new__(StockReleaseDashboardService)
    svc._session = session
    svc._sr = AsyncMock()

    svc._sr.count_approved_today = AsyncMock(return_value=3)
    svc._sr.sum_quantity_approved_today = AsyncMock(return_value=45.0)
    svc._sr.sum_quantity_approved_since = AsyncMock(return_value=320.0)
    svc._sr.count_by_status = AsyncMock(return_value=2)
    svc._sr.get_recent_approved = AsyncMock(return_value=[])
    svc._sr.get_top_released_products = AsyncMock(return_value=[])

    result = await svc.get_summary()

    assert result["todays_releases"] == 3
    assert result["todays_released_quantity"] == 45.0
    assert result["monthly_released_quantity"] == 320.0
    assert result["pending_releases"] == 2
    assert "recent_releases" in result
    assert "top_released_products" in result
