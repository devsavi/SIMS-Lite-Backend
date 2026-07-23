"""
API endpoint tests for master data -- Phase 2.

Tests cover categories, brands, UoMs, suppliers, and products endpoints
using a mocked service layer to avoid database dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.core.exceptions import ConflictError, NotFoundError
from app.models.master_data import Brand, Category, Product, Supplier, UnitOfMeasure
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers: build minimal ORM-like objects for schema serialisation
# ---------------------------------------------------------------------------


def _now():
    return datetime.utcnow()


def _cat(name: str = "Electronics") -> Category:
    c = Category()
    c.id = uuid.uuid4()
    c.name = name
    c.slug = name.lower()
    c.description = None
    c.parent_id = None
    c.is_active = True
    c.is_deleted = False
    c.created_at = _now()
    c.updated_at = _now()
    return c


def _brand(name: str = "Acme") -> Brand:
    b = Brand()
    b.id = uuid.uuid4()
    b.name = name
    b.description = None
    b.logo_url = None
    b.website = None
    b.is_active = True
    b.is_deleted = False
    b.created_at = _now()
    b.updated_at = _now()
    return b


def _uom() -> UnitOfMeasure:
    u = UnitOfMeasure()
    u.id = uuid.uuid4()
    u.name = "Kilogram"
    u.symbol = "kg"
    u.description = None
    u.is_active = True
    u.is_deleted = False
    u.created_at = _now()
    u.updated_at = _now()
    return u


def _supplier() -> Supplier:
    s = Supplier()
    s.id = uuid.uuid4()
    s.supplier_code = "SUP-00001"
    s.name = "Test Supplier"
    s.contact_person = None
    s.email = None
    s.phone = None
    s.address = None
    s.city = None
    s.state = None
    s.country = None
    s.postal_code = None
    s.tax_id = None
    s.payment_terms = None
    s.notes = None
    s.is_active = True
    s.is_deleted = False
    s.created_at = _now()
    s.updated_at = _now()
    return s


def _product() -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku = "ELE-20260101-00001"
    p.barcode = "123456789012"
    p.name = "Test Product"
    p.description = None
    p.short_description = None
    p.category = None
    p.brand = None
    p.uom = None
    p.supplier = None
    p.cost_price = None
    p.selling_price = None
    p.reorder_level = 0
    p.reorder_quantity = 0
    p.image_path = None
    p.is_active = True
    p.is_deleted = False
    p.created_at = _now()
    p.updated_at = _now()
    return p


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


# ---------------------------------------------------------------------------
# Category endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_categories_returns_paginated(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.categories import _svc
    from app.services.master_data import CategoryService

    cat = _cat()
    mock_svc = MagicMock(spec=CategoryService)
    mock_svc.list = AsyncMock(return_value=([cat], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/categories/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["data"]) == 1
    assert data["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_category_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.categories import _svc
    from app.services.master_data import CategoryService

    cat = _cat()
    mock_svc = MagicMock(spec=CategoryService)
    mock_svc.create = AsyncMock(return_value=cat)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post("/api/v1/categories/", json={"name": "Electronics"})
    assert resp.status_code == 201
    assert resp.json()["data"]["name"] == "Electronics"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_category_conflict_returns_409(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.categories import _svc
    from app.services.master_data import CategoryService

    mock_svc = MagicMock(spec=CategoryService)
    mock_svc.create = AsyncMock(side_effect=ConflictError("Duplicate"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post("/api/v1/categories/", json={"name": "Dup"})
    assert resp.status_code == 409

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_get_category_not_found_returns_404(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.categories import _svc
    from app.services.master_data import CategoryService

    mock_svc = MagicMock(spec=CategoryService)
    mock_svc.get = AsyncMock(side_effect=NotFoundError("Not found"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/categories/{uuid.uuid4()}")
    assert resp.status_code == 404

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_delete_category_returns_204(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.categories import _svc
    from app.services.master_data import CategoryService

    mock_svc = MagicMock(spec=CategoryService)
    mock_svc.delete = AsyncMock(return_value=None)

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.delete(f"/api/v1/categories/{uuid.uuid4()}")
    assert resp.status_code == 204

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Brand endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_brands(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.brands import _svc
    from app.services.master_data import BrandService

    mock_svc = MagicMock(spec=BrandService)
    mock_svc.list = AsyncMock(return_value=([_brand()], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/brands/")
    assert resp.status_code == 200

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_brand_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.brands import _svc
    from app.services.master_data import BrandService

    mock_svc = MagicMock(spec=BrandService)
    mock_svc.create = AsyncMock(return_value=_brand("NewBrand"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post("/api/v1/brands/", json={"name": "NewBrand"})
    assert resp.status_code == 201

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# UoM endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_uoms(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.uoms import _svc
    from app.services.master_data import UoMService

    mock_svc = MagicMock(spec=UoMService)
    mock_svc.list = AsyncMock(return_value=([_uom()], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/uoms/")
    assert resp.status_code == 200

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_uom_duplicate_symbol_returns_409(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.uoms import _svc
    from app.services.master_data import UoMService

    mock_svc = MagicMock(spec=UoMService)
    mock_svc.create = AsyncMock(side_effect=ConflictError("Symbol exists"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post("/api/v1/uoms/", json={"name": "Kilogram", "symbol": "kg"})
    assert resp.status_code == 409

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Supplier endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_suppliers(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.suppliers import _svc
    from app.services.master_data import SupplierService

    mock_svc = MagicMock(spec=SupplierService)
    mock_svc.list = AsyncMock(return_value=([_supplier()], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/suppliers/")
    assert resp.status_code == 200

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_supplier_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.suppliers import _svc
    from app.services.master_data import SupplierService

    mock_svc = MagicMock(spec=SupplierService)
    mock_svc.create = AsyncMock(return_value=_supplier())

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post("/api/v1/suppliers/", json={"name": "Acme Corp"})
    assert resp.status_code == 201

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


# ---------------------------------------------------------------------------
# Product endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_products(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.products import _svc
    from app.services.master_data import ProductService

    mock_svc = MagicMock(spec=ProductService)
    mock_svc.list = AsyncMock(return_value=([_product()], 1))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/products/")
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 1

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_create_product_success(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.products import _svc
    from app.services.master_data import ProductService

    mock_svc = MagicMock(spec=ProductService)
    mock_svc.create = AsyncMock(return_value=_product())

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.post("/api/v1/products/", json={"name": "Test Product"})
    assert resp.status_code == 201
    assert resp.json()["data"]["sku"] == "ELE-20260101-00001"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_get_product_not_found(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.products import _svc
    from app.services.master_data import ProductService

    mock_svc = MagicMock(spec=ProductService)
    mock_svc.get = AsyncMock(side_effect=NotFoundError("Not found"))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/products/{uuid.uuid4()}")
    assert resp.status_code == 404

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_get_barcode_returns_png(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.products import _svc
    from app.services.master_data import ProductService

    product = _product()
    mock_svc = MagicMock(spec=ProductService)
    mock_svc.get = AsyncMock(return_value=product)
    # Return real PNG bytes
    import io
    import barcode as python_barcode
    from barcode.writer import ImageWriter
    buf = io.BytesIO()
    python_barcode.get_barcode_class("code128")(product.barcode, writer=ImageWriter()).write(buf)
    mock_svc.generate_barcode_png = MagicMock(return_value=buf.getvalue())

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get(f"/api/v1/products/{product.id}/barcode")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)


@pytest.mark.asyncio
async def test_download_import_template(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()

    resp = await client.get("/api/v1/products/import-template")
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "")
    assert "spreadsheetml" in ct

    app_instance.dependency_overrides.pop(get_current_user)


@pytest.mark.asyncio
async def test_product_search_filter(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.api.v1.endpoints.products import _svc
    from app.services.master_data import ProductService

    mock_svc = MagicMock(spec=ProductService)
    mock_svc.list = AsyncMock(return_value=([], 0))

    app_instance.dependency_overrides[get_current_user] = lambda: _make_superuser()
    app_instance.dependency_overrides[_svc] = lambda: mock_svc

    resp = await client.get("/api/v1/products/?search=laptop&active_only=true")
    assert resp.status_code == 200
    # Verify service was called with the right filters
    call_kwargs = mock_svc.list.call_args.kwargs
    assert call_kwargs.get("search") == "laptop"
    assert call_kwargs.get("active_only") is True

    app_instance.dependency_overrides.pop(get_current_user)
    app_instance.dependency_overrides.pop(_svc)
