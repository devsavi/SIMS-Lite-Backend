"""
API endpoint tests for Stock Release — Phase 5.

Covers all CRUD + workflow endpoints and dashboard.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.exceptions import NotFoundError, ValidationError
from app.models.master_data import Product
from app.models.stock_release import (
    StockRelease,
    StockReleaseItem,
    StockReleasePurpose,
    StockReleaseStatus,
)
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
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
    p.sku = "TST-20260101-00001"
    p.barcode = "123456789012"
    p.name = "Test Product"
    p.reorder_level = 5
    p.cost_price = 10.0
    p.selling_price = 15.0
    p.is_active = True
    p.is_deleted = False
    return p


def _make_release(status: str = StockReleaseStatus.DRAFT) -> StockRelease:
    sr = StockRelease()
    sr.id = uuid.uuid4()
    sr.release_number = "SR-20260101-00001"
    sr.purpose = StockReleasePurpose.INTERNAL_USE
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


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_stock_releases(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    sr = _make_release()
    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.get_all = AsyncMock(return_value=([sr], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/stock-releases/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["pagination"]["total"] == 1
    assert data["data"][0]["release_number"] == "SR-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_stock_release_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    sr = _make_release()
    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.create = AsyncMock(return_value=sr)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post(
        "/api/v1/stock-releases/",
        json={
            "purpose": "INTERNAL_USE",
            "release_date": _now().isoformat(),
            "items": [
                {
                    "product_id": str(uuid.uuid4()),
                    "quantity_requested": 10.0,
                }
            ],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["data"]["release_number"] == "SR-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_stock_release_duplicate_products_422(
    client: AsyncClient, app_instance
):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: MagicMock(
        spec=StockReleaseService
    )

    product_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/v1/stock-releases/",
        json={
            "purpose": "INTERNAL_USE",
            "release_date": _now().isoformat(),
            "items": [
                {"product_id": product_id, "quantity_requested": 5.0},
                {"product_id": product_id, "quantity_requested": 3.0},
            ],
        },
    )
    assert resp.status_code == 422

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stock_release_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    sr = _make_release()
    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.get = AsyncMock(return_value=sr)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/stock-releases/{sr.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["release_number"] == "SR-20260101-00001"
    assert data["data"]["status"] == StockReleaseStatus.DRAFT

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_get_stock_release_not_found(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.get = AsyncMock(side_effect=NotFoundError("Not found"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/stock-releases/{uuid.uuid4()}")
    assert resp.status_code == 404

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_stock_release_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    sr = _make_release()
    sr.notes = "Updated notes"
    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.update = AsyncMock(return_value=sr)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.put(
        f"/api/v1/stock-releases/{sr.id}",
        json={"notes": "Updated notes"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["notes"] == "Updated notes"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_update_non_draft_returns_422(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.update = AsyncMock(
        side_effect=ValidationError("Cannot edit non-DRAFT release")
    )

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.put(
        f"/api/v1/stock-releases/{uuid.uuid4()}",
        json={"notes": "test"},
    )
    assert resp.status_code == 422

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_stock_release_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    sr_id = uuid.uuid4()
    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.delete = AsyncMock(return_value=None)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.delete(f"/api/v1/stock-releases/{sr_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["deleted"] is True

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_stock_release_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    sr = _make_release(status=StockReleaseStatus.SUBMITTED)
    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.submit = AsyncMock(return_value=sr)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/stock-releases/{sr.id}/submit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["status"] == StockReleaseStatus.SUBMITTED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_submit_invalid_raises_422(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.submit = AsyncMock(side_effect=ValidationError("Cannot submit"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/stock-releases/{uuid.uuid4()}/submit")
    assert resp.status_code == 422

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_stock_release_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    sr = _make_release(status=StockReleaseStatus.APPROVED)
    sr.total_quantity = 10.0
    sr.total_cost = 100.0
    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.approve = AsyncMock(return_value=sr)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/stock-releases/{sr.id}/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["status"] == StockReleaseStatus.APPROVED
    assert data["data"]["total_quantity"] == 10.0

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_approve_insufficient_stock_returns_422(
    client: AsyncClient, app_instance
):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.approve = AsyncMock(
        side_effect=ValidationError("Insufficient stock for product")
    )

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/stock-releases/{uuid.uuid4()}/approve")
    assert resp.status_code == 422

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_stock_release_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    sr = _make_release(status=StockReleaseStatus.CANCELLED)
    sr.cancellation_reason = "No longer needed"
    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.cancel = AsyncMock(return_value=sr)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(
        f"/api/v1/stock-releases/{sr.id}/cancel",
        json={"reason": "No longer needed"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["status"] == StockReleaseStatus.CANCELLED
    assert data["data"]["cancellation_reason"] == "No longer needed"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_cancel_approved_returns_422(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.stock_releases import _svc
    from app.services.stock_release import StockReleaseService

    mock_svc = MagicMock(spec=StockReleaseService)
    mock_svc.cancel = AsyncMock(
        side_effect=ValidationError("Cannot cancel an APPROVED release")
    )

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(
        f"/api/v1/stock-releases/{uuid.uuid4()}/cancel",
        json={"reason": "trying to cancel approved"},
    )
    assert resp.status_code == 422

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_release_dashboard(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.services.stock_release import StockReleaseDashboardService

    dashboard_data = {
        "todays_releases": 3,
        "todays_released_quantity": 45.0,
        "monthly_released_quantity": 320.0,
        "pending_releases": 2,
        "recent_releases": [],
        "top_released_products": [],
    }

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()

    with patch.object(
        StockReleaseDashboardService,
        "get_summary",
        new=AsyncMock(return_value=dashboard_data),
    ):
        resp = await client.get("/api/v1/dashboard/stock-releases")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["todays_releases"] == 3
    assert data["data"]["monthly_released_quantity"] == 320.0

    app_instance.dependency_overrides.pop(get_current_user)


@pytest.mark.asyncio
async def test_extended_inventory_dashboard(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.services.inventory import InventoryDashboardService
    from app.services.stock_release import StockReleaseDashboardService

    inv_data = {
        "total_products": 10,
        "total_products_in_stock": 8,
        "total_out_of_stock": 2,
        "total_low_stock": 3,
        "total_quantity_on_hand": 500.0,
        "total_stock_value": 12000.0,
        "pending_adjustments": 1,
        "recent_movements": [],
    }
    sr_data = {
        "todays_releases": 2,
        "todays_released_quantity": 20.0,
        "monthly_released_quantity": 150.0,
        "pending_releases": 1,
        "recent_releases": [],
        "top_released_products": [],
    }

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()

    with patch.object(
        InventoryDashboardService, "get_summary", new=AsyncMock(return_value=inv_data)
    ):
        with patch.object(
            StockReleaseDashboardService,
            "get_summary",
            new=AsyncMock(return_value=sr_data),
        ):
            resp = await client.get("/api/v1/dashboard/inventory/extended")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["total_products"] == 10
    assert data["data"]["todays_releases"] == 2
    assert "top_released_products" in data["data"]

    app_instance.dependency_overrides.pop(get_current_user)
