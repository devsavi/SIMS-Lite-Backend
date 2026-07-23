"""
API endpoint tests for procurement — Phase 3.

Tests cover Purchase Order and GRN endpoints using mocked service layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.core.exceptions import NotFoundError, ValidationError
from app.models.procurement import (
    GRN,
    GRNItem,
    GRNStatus,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.models.master_data import Product, Supplier
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixture helpers
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


def _make_supplier() -> Supplier:
    s = Supplier()
    s.id = uuid.uuid4()
    s.supplier_code = "SUP-00001"
    s.name = "Test Supplier"
    s.email = "sup@example.com"
    s.contact_person = "Bob"
    s.is_active = True
    s.is_deleted = False
    return s


def _make_product() -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku = "GEN-20260101-00001"
    p.barcode = "123456789012"
    p.name = "Test Product"
    p.is_active = True
    p.is_deleted = False
    return p


def _make_po_item(po_id: uuid.UUID, product: Product) -> PurchaseOrderItem:
    item = PurchaseOrderItem()
    item.id = uuid.uuid4()
    item.purchase_order_id = po_id
    item.product_id = product.id
    item.product = product
    item.quantity_ordered = 10.0
    item.quantity_received = 0.0
    item.unit_price = 100.0
    item.discount_percent = 0.0
    item.tax_percent = 0.0
    item.line_total = 1000.0
    item.notes = None
    item.created_at = _now()
    item.updated_at = _now()
    return item


def _make_po(status: str = POStatus.DRAFT) -> PurchaseOrder:
    po = PurchaseOrder()
    po.id = uuid.uuid4()
    po.po_number = "PO-20260101-00001"
    po.supplier_id = uuid.uuid4()
    po.supplier = _make_supplier()
    po.status = status
    po.order_date = _now()
    po.expected_delivery_date = None
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
    po.created_at = _now()
    po.updated_at = _now()
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
    grn.received_date = _now()
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
    grn.created_at = _now()
    grn.updated_at = _now()

    grn_item = GRNItem()
    grn_item.id = uuid.uuid4()
    grn_item.grn_id = grn.id
    grn_item.po_item_id = po.items[0].id
    grn_item.product_id = po.items[0].product_id
    grn_item.product = po.items[0].product
    grn_item.quantity_received = 5.0
    grn_item.unit_cost = 95.0
    grn_item.notes = None
    grn_item.created_at = _now()
    grn_item.updated_at = _now()
    grn.items = [grn_item]
    return grn


# ---------------------------------------------------------------------------
# Purchase Order endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_purchase_orders(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.list = AsyncMock(return_value=([_make_po()], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/purchase-orders/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["pagination"]["total"] == 1
    assert data["data"][0]["po_number"] == "PO-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_purchase_order_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    po = _make_po()
    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.create = AsyncMock(return_value=po)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post(
        "/api/v1/purchase-orders/",
        json={
            "supplier_id": str(uuid.uuid4()),
            "order_date": datetime.now(UTC).isoformat(),
            "items": [
                {
                    "product_id": str(uuid.uuid4()),
                    "quantity_ordered": 10,
                    "unit_price": 100.0,
                }
            ],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["po_number"] == "PO-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_get_purchase_order_not_found(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.get = AsyncMock(side_effect=NotFoundError("Not found"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/purchase-orders/{uuid.uuid4()}")
    assert resp.status_code == 404

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_submit_purchase_order(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    po = _make_po(status=POStatus.SUBMITTED)
    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.submit = AsyncMock(return_value=po)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/purchase-orders/{uuid.uuid4()}/submit")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == POStatus.SUBMITTED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_approve_purchase_order(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    po = _make_po(status=POStatus.APPROVED)
    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.approve = AsyncMock(return_value=po)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/purchase-orders/{uuid.uuid4()}/approve")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == POStatus.APPROVED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_reject_purchase_order(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    po = _make_po(status=POStatus.REJECTED)
    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.reject = AsyncMock(return_value=po)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(
        f"/api/v1/purchase-orders/{uuid.uuid4()}/reject",
        json={"reason": "Budget exceeded"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == POStatus.REJECTED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_cancel_purchase_order(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    po = _make_po(status=POStatus.CANCELLED)
    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.cancel = AsyncMock(return_value=po)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(
        f"/api/v1/purchase-orders/{uuid.uuid4()}/cancel",
        json={"reason": "Not needed"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == POStatus.CANCELLED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_duplicate_purchase_order(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    new_po = _make_po()
    new_po.po_number = "PO-20260101-00002"
    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.duplicate = AsyncMock(return_value=new_po)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post(f"/api/v1/purchase-orders/{uuid.uuid4()}/duplicate")
    assert resp.status_code == 201

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_print_purchase_order(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.get_for_print = AsyncMock(return_value={"po_number": "PO-20260101-00001"})

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/purchase-orders/{uuid.uuid4()}/print")
    assert resp.status_code == 200
    assert resp.json()["data"]["po_number"] == "PO-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_submit_invalid_po_returns_422_validation(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.purchase_orders import _svc
    from app.services.procurement import PurchaseOrderService

    mock_svc = MagicMock(spec=PurchaseOrderService)
    mock_svc.submit = AsyncMock(side_effect=ValidationError("Cannot submit"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/purchase-orders/{uuid.uuid4()}/submit")
    assert resp.status_code == 422

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# GRN endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_grns(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.grns import _svc
    from app.services.procurement import GRNService

    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po)
    mock_svc = MagicMock(spec=GRNService)
    mock_svc.list = AsyncMock(return_value=([grn], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/grns/")
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_grn_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.grns import _svc
    from app.services.procurement import GRNService

    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po)
    mock_svc = MagicMock(spec=GRNService)
    mock_svc.create = AsyncMock(return_value=grn)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post(
        "/api/v1/grns/",
        json={
            "purchase_order_id": str(uuid.uuid4()),
            "received_date": datetime.now(UTC).isoformat(),
            "items": [
                {
                    "po_item_id": str(uuid.uuid4()),
                    "product_id": str(uuid.uuid4()),
                    "quantity_received": 5.0,
                    "unit_cost": 95.0,
                }
            ],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["grn_number"] == "GRN-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_get_grn_not_found(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.grns import _svc
    from app.services.procurement import GRNService

    mock_svc = MagicMock(spec=GRNService)
    mock_svc.get = AsyncMock(side_effect=NotFoundError("Not found"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/grns/{uuid.uuid4()}")
    assert resp.status_code == 404

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_approve_grn_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.grns import _svc
    from app.services.procurement import GRNService

    po = _make_po(status=POStatus.FULLY_RECEIVED)
    grn = _make_grn(po, status=GRNStatus.APPROVED)
    mock_svc = MagicMock(spec=GRNService)
    mock_svc.approve = AsyncMock(return_value=grn)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(f"/api/v1/grns/{uuid.uuid4()}/approve")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == GRNStatus.APPROVED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_cancel_grn_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.grns import _svc
    from app.services.procurement import GRNService

    po = _make_po(status=POStatus.APPROVED)
    grn = _make_grn(po, status=GRNStatus.CANCELLED)
    mock_svc = MagicMock(spec=GRNService)
    mock_svc.cancel = AsyncMock(return_value=grn)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.patch(
        f"/api/v1/grns/{uuid.uuid4()}/cancel",
        json={"reason": "Wrong delivery"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == GRNStatus.CANCELLED

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)
