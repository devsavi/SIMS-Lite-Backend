"""API endpoint tests for inventory — Phase 4."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(UTC)


def _make_superuser() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.email = "admin@test.com"
    u.first_name = "Admin"
    u.last_name = "User"
    u.is_superuser = True
    u.is_active = True
    u.is_verified = True
    u.roles = []
    u.failed_login_attempts = 0
    return u


def _make_product() -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku = "GEN-20260101-00001"
    p.barcode = "123456789012"
    p.name = "Test Product"
    p.reorder_level = 5
    p.cost_price = 10.0
    p.selling_price = 15.0
    p.is_active = True
    p.is_deleted = False
    return p


def _make_inventory(product: Product) -> Inventory:
    inv = Inventory()
    inv.id = uuid.uuid4()
    inv.product_id = product.id
    inv.product = product
    inv.quantity_on_hand = 50.0
    inv.average_cost = 10.0
    inv.last_updated_at = _now()
    inv.last_transaction_type = "PURCHASE_RECEIPT"
    inv.created_at = _now()
    inv.updated_at = _now()
    return inv


def _make_adjustment(status: str = StockAdjustmentStatus.DRAFT) -> StockAdjustment:
    adj = StockAdjustment()
    adj.id = uuid.uuid4()
    adj.adjustment_number = "ADJ-20260101-00001"
    adj.adjustment_type = StockAdjustmentType.INCREASE
    adj.status = status
    adj.reason = "Test"
    adj.notes = None
    adj.created_by = None
    adj.submitted_by = None
    adj.submitted_at = None
    adj.approved_by = None
    adj.approved_at = None
    adj.cancelled_by = None
    adj.cancelled_at = None
    adj.cancellation_reason = None
    adj.items = []
    adj.created_at = _now()
    adj.updated_at = _now()
    return adj


def _make_ledger_entry() -> InventoryLedgerEntry:
    product = _make_product()
    entry = InventoryLedgerEntry()
    entry.id = uuid.uuid4()
    entry.product_id = product.id
    entry.product = product
    entry.entry_type = LedgerEntryType.PURCHASE_RECEIPT
    entry.quantity_before = 0.0
    entry.quantity_change = 10.0
    entry.quantity_after = 10.0
    entry.unit_cost = 10.0
    entry.reference_type = "GRN"
    entry.reference_id = uuid.uuid4()
    entry.reference_number = "GRN-20260101-00001"
    entry.notes = None
    entry.created_by = None
    entry.created_at = _now()
    return entry


# ---------------------------------------------------------------------------
# Inventory endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_inventory(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory import _svc as inv_svc
    from app.services.inventory import InventoryService

    product = _make_product()
    inv = _make_inventory(product)
    mock_svc = MagicMock(spec=InventoryService)
    mock_svc.get_all = AsyncMock(return_value=([inv], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[inv_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/inventory/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(inv_svc)


@pytest.mark.asyncio
async def test_get_inventory_by_product(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory import _svc as inv_svc
    from app.services.inventory import InventoryService

    product = _make_product()
    inv = _make_inventory(product)
    mock_svc = MagicMock(spec=InventoryService)
    mock_svc.get_by_product = AsyncMock(return_value=inv)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[inv_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/inventory/{product.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["quantity_on_hand"] == 50.0

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(inv_svc)


@pytest.mark.asyncio
async def test_get_inventory_summary(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory import _svc as inv_svc
    from app.services.inventory import InventoryService

    summary = {
        "total_products": 5,
        "total_products_in_stock": 4,
        "total_out_of_stock": 1,
        "total_low_stock": 2,
        "total_quantity_on_hand": 100.0,
        "total_stock_value": 1500.0,
    }
    mock_svc = MagicMock(spec=InventoryService)
    mock_svc.get_summary = AsyncMock(return_value=summary)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[inv_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/inventory/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["total_products"] == 5

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(inv_svc)


@pytest.mark.asyncio
async def test_get_inventory_valuation(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory import _svc as inv_svc
    from app.services.inventory import InventoryService

    product = _make_product()
    inv = _make_inventory(product)
    mock_svc = MagicMock(spec=InventoryService)
    mock_svc.get_valuation = AsyncMock(return_value=[inv])

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[inv_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/inventory/value")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "total_products" in data["data"]

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(inv_svc)


@pytest.mark.asyncio
async def test_get_low_stock(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory import _svc as inv_svc
    from app.services.inventory import InventoryService

    product = _make_product()
    inv = _make_inventory(product)
    inv.quantity_on_hand = 3.0
    mock_svc = MagicMock(spec=InventoryService)
    mock_svc.get_low_stock = AsyncMock(return_value=([inv], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[inv_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/inventory/low-stock")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(inv_svc)


@pytest.mark.asyncio
async def test_get_out_of_stock(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory import _svc as inv_svc
    from app.services.inventory import InventoryService

    product = _make_product()
    inv = _make_inventory(product)
    inv.quantity_on_hand = 0.0
    mock_svc = MagicMock(spec=InventoryService)
    mock_svc.get_out_of_stock = AsyncMock(return_value=([inv], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[inv_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/inventory/out-of-stock")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(inv_svc)


@pytest.mark.asyncio
async def test_get_inventory_by_product_not_found(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory import _svc as inv_svc
    from app.services.inventory import InventoryService

    mock_svc = MagicMock(spec=InventoryService)
    mock_svc.get_by_product = AsyncMock(side_effect=NotFoundError("Product not found"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[inv_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/inventory/{uuid.uuid4()}")
    assert resp.status_code == 404

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(inv_svc)


# ---------------------------------------------------------------------------
# Stock Adjustment endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_adjustments(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    adj = _make_adjustment()
    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.get_all = AsyncMock(return_value=([adj], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/stock-adjustments/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_create_adjustment_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    adj = _make_adjustment()
    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.create = AsyncMock(return_value=adj)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.post(
        "/api/v1/stock-adjustments/",
        json={
            "adjustment_type": "INCREASE",
            "reason": "Found extra stock",
            "items": [
                {
                    "product_id": str(uuid.uuid4()),
                    "quantity_adjusted": 10.0,
                    "unit_cost": 5.0,
                }
            ],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["data"]["adjustment_number"] == "ADJ-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_get_adjustment_by_id(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    adj = _make_adjustment()
    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.get = AsyncMock(return_value=adj)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/stock-adjustments/{adj.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["adjustment_number"] == "ADJ-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_get_adjustment_not_found(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.get = AsyncMock(side_effect=NotFoundError("Not found"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/stock-adjustments/{uuid.uuid4()}")
    assert resp.status_code == 404

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_update_adjustment_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    adj = _make_adjustment()
    adj.reason = "Updated reason"
    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.update = AsyncMock(return_value=adj)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.put(
        f"/api/v1/stock-adjustments/{adj.id}",
        json={"reason": "Updated reason"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["reason"] == "Updated reason"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_delete_adjustment_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    adj_id = uuid.uuid4()
    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.delete = AsyncMock(return_value=None)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.delete(f"/api/v1/stock-adjustments/{adj_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["deleted"] is True

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_submit_adjustment_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    adj = _make_adjustment(status=StockAdjustmentStatus.SUBMITTED)
    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.submit = AsyncMock(return_value=adj)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/stock-adjustments/{adj.id}/submit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["status"] == StockAdjustmentStatus.SUBMITTED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_approve_adjustment_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    adj = _make_adjustment(status=StockAdjustmentStatus.APPROVED)
    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.approve = AsyncMock(return_value=adj)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/stock-adjustments/{adj.id}/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["status"] == StockAdjustmentStatus.APPROVED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_cancel_adjustment_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    adj = _make_adjustment(status=StockAdjustmentStatus.CANCELLED)
    adj.cancellation_reason = "No longer needed"
    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.cancel = AsyncMock(return_value=adj)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.patch(
        f"/api/v1/stock-adjustments/{adj.id}/cancel",
        json={"reason": "No longer needed"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["status"] == StockAdjustmentStatus.CANCELLED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


@pytest.mark.asyncio
async def test_submit_invalid_raises_422(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_adjustments import _svc as adj_svc
    from app.services.inventory import StockAdjustmentService

    mock_svc = MagicMock(spec=StockAdjustmentService)
    mock_svc.submit = AsyncMock(side_effect=ValidationError("Cannot submit"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[adj_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/stock-adjustments/{uuid.uuid4()}/submit")
    assert resp.status_code == 422

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(adj_svc)


# ---------------------------------------------------------------------------
# Inventory Ledger endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_ledger_entries(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory_ledger import _svc as ledger_svc
    from app.services.inventory import InventoryLedgerService

    entry = _make_ledger_entry()
    mock_svc = MagicMock(spec=InventoryLedgerService)
    mock_svc.get_all = AsyncMock(return_value=([entry], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[ledger_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/inventory-ledger/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(ledger_svc)


@pytest.mark.asyncio
async def test_get_ledger_entry_by_id(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory_ledger import _svc as ledger_svc
    from app.services.inventory import InventoryLedgerService

    entry = _make_ledger_entry()
    mock_svc = MagicMock(spec=InventoryLedgerService)
    mock_svc.get_by_id = AsyncMock(return_value=entry)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[ledger_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/inventory-ledger/{entry.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["entry_type"] == LedgerEntryType.PURCHASE_RECEIPT

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(ledger_svc)


@pytest.mark.asyncio
async def test_get_ledger_by_product(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory_ledger import _svc as ledger_svc
    from app.services.inventory import InventoryLedgerService

    entry = _make_ledger_entry()
    mock_svc = MagicMock(spec=InventoryLedgerService)
    mock_svc.get_for_product = AsyncMock(return_value=([entry], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[ledger_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/inventory-ledger/product/{entry.product_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(ledger_svc)


@pytest.mark.asyncio
async def test_get_ledger_by_reference(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.inventory_ledger import _svc as ledger_svc
    from app.services.inventory import InventoryLedgerService

    entry = _make_ledger_entry()
    ref_id = uuid.uuid4()
    mock_svc = MagicMock(spec=InventoryLedgerService)
    mock_svc.get_by_reference = AsyncMock(return_value=[entry])

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[ledger_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/inventory-ledger/reference/GRN/{ref_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["data"]) == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(ledger_svc)


# ---------------------------------------------------------------------------
# Dashboard test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inventory_dashboard(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.services.inventory import InventoryDashboardService

    dashboard_data = {
        "total_products": 10,
        "total_products_in_stock": 8,
        "total_out_of_stock": 2,
        "total_low_stock": 3,
        "total_quantity_on_hand": 500.0,
        "total_stock_value": 12000.0,
        "pending_adjustments": 2,
        "recent_movements": [],
    }

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()

    with patch.object(
        InventoryDashboardService, "get_summary", new=AsyncMock(return_value=dashboard_data)
    ):
        resp = await client.get("/api/v1/dashboard/inventory")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "total_products" in data["data"]
    assert data["data"]["total_products"] == 10
    assert "pending_adjustments" in data["data"]

    app_instance.dependency_overrides.pop(get_current_user)
