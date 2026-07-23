"""
Unit tests for master data services -- Phase 2.

Tests cover CategoryService, BrandService, UoMService, SupplierService,
and ProductService CRUD operations, validation, and business rules.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.models.master_data import Brand, Category, Product, Supplier, UnitOfMeasure
from app.models.user import User
from app.schemas.master_data import (
    BrandCreate,
    BrandUpdate,
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductUpdate,
    SupplierCreate,
    SupplierUpdate,
    UoMCreate,
    UoMUpdate,
)
from app.services.master_data import (
    BrandService,
    CategoryService,
    ProductService,
    SupplierService,
    UoMService,
    _generate_barcode_value,
    _generate_sku,
    _slugify,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_actor() -> User:
    user = User()
    user.id = uuid.uuid4()
    user.is_superuser = True
    user.is_active = True
    return user


def _make_category(name: str = "Electronics", parent_id=None) -> Category:
    cat = Category()
    cat.id = uuid.uuid4()
    cat.name = name
    cat.slug = name.lower()
    cat.description = None
    cat.parent_id = parent_id
    cat.is_active = True
    cat.is_deleted = False
    return cat


def _make_brand(name: str = "Acme") -> Brand:
    b = Brand()
    b.id = uuid.uuid4()
    b.name = name
    b.is_active = True
    b.is_deleted = False
    return b


def _make_uom(name: str = "Kilogram", symbol: str = "kg") -> UnitOfMeasure:
    u = UnitOfMeasure()
    u.id = uuid.uuid4()
    u.name = name
    u.symbol = symbol
    u.is_active = True
    u.is_deleted = False
    return u


def _make_supplier(code: str = "SUP-00001") -> Supplier:
    s = Supplier()
    s.id = uuid.uuid4()
    s.supplier_code = code
    s.name = "Test Supplier"
    s.is_active = True
    s.is_deleted = False
    return s


def _make_product(sku: str = "ELE-20260101-00001") -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku = sku
    p.barcode = "123456789012"
    p.name = "Test Product"
    p.is_active = True
    p.is_deleted = False
    p.image_path = None
    p.category = None
    p.brand = None
    p.uom = None
    p.supplier = None
    return p


def _mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Slugify helper
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert _slugify("Hello World") == "hello-world"


def test_slugify_special_chars():
    assert _slugify("Phones & Tablets!") == "phones-tablets"


def test_slugify_extra_spaces():
    assert _slugify("  multiple   spaces  ") == "multiple-spaces"


# ---------------------------------------------------------------------------
# SKU and Barcode generation
# ---------------------------------------------------------------------------


def test_generate_sku_uses_prefix():
    sku = _generate_sku("Electronics", 0)
    assert sku.startswith("ELE-")
    assert len(sku.split("-")) == 3


def test_generate_sku_no_category_uses_gen():
    sku = _generate_sku(None, 0)
    assert sku.startswith("GEN-")


def test_generate_barcode_value_12_digits():
    barcode = _generate_barcode_value("ELE-20260101-00001")
    assert len(barcode) == 12
    assert barcode.isdigit()


def test_generate_barcode_unique():
    b1 = _generate_barcode_value("SKU-001")
    b2 = _generate_barcode_value("SKU-001-1")
    # Different inputs should generally produce different outputs
    assert b1 != b2


# ---------------------------------------------------------------------------
# CategoryService tests
# ---------------------------------------------------------------------------


def _make_category_service():
    session = _mock_session()
    svc = CategoryService.__new__(CategoryService)
    svc._session = session
    svc._cats = AsyncMock()
    svc._audit = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_category_create_success():
    svc = _make_category_service()
    actor = _make_actor()
    cat = _make_category()

    svc._cats.slug_exists.return_value = False
    svc._cats.name_exists_in_parent.return_value = False
    svc._cats.create.return_value = cat

    result = await svc.create(
        CategoryCreate(name="Electronics"), actor=actor
    )
    assert result is cat
    svc._cats.create.assert_called_once()


@pytest.mark.asyncio
async def test_category_create_duplicate_name_raises_conflict():
    svc = _make_category_service()
    actor = _make_actor()

    svc._cats.slug_exists.return_value = False
    svc._cats.name_exists_in_parent.return_value = True

    with pytest.raises(ConflictError):
        await svc.create(CategoryCreate(name="Electronics"), actor=actor)


@pytest.mark.asyncio
async def test_category_create_invalid_parent_raises_not_found():
    svc = _make_category_service()
    actor = _make_actor()

    svc._cats.slug_exists.return_value = False
    svc._cats.name_exists_in_parent.return_value = False
    svc._cats.get_active.return_value = None  # parent not found

    with pytest.raises(NotFoundError):
        await svc.create(
            CategoryCreate(name="Sub", parent_id=uuid.uuid4()), actor=actor
        )


@pytest.mark.asyncio
async def test_category_get_not_found_raises():
    svc = _make_category_service()
    svc._cats.get_active.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4())


@pytest.mark.asyncio
async def test_category_delete_soft_deletes():
    svc = _make_category_service()
    actor = _make_actor()
    cat = _make_category()

    svc._cats.get_active.return_value = cat
    svc._cats.update.return_value = cat

    await svc.delete(cat.id, actor=actor)
    svc._cats.update.assert_called_once()
    call_kwargs = svc._cats.update.call_args.kwargs
    assert call_kwargs["is_deleted"] is True


# ---------------------------------------------------------------------------
# BrandService tests
# ---------------------------------------------------------------------------


def _make_brand_service():
    session = _mock_session()
    svc = BrandService.__new__(BrandService)
    svc._session = session
    svc._brands = AsyncMock()
    svc._audit = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_brand_create_success():
    svc = _make_brand_service()
    actor = _make_actor()
    brand = _make_brand()

    svc._brands.name_exists.return_value = False
    svc._brands.create.return_value = brand

    result = await svc.create(BrandCreate(name="Acme"), actor=actor)
    assert result is brand


@pytest.mark.asyncio
async def test_brand_create_duplicate_raises_conflict():
    svc = _make_brand_service()
    actor = _make_actor()
    svc._brands.name_exists.return_value = True

    with pytest.raises(ConflictError):
        await svc.create(BrandCreate(name="Acme"), actor=actor)


@pytest.mark.asyncio
async def test_brand_update_name_conflict_raises():
    svc = _make_brand_service()
    actor = _make_actor()
    brand = _make_brand("OldName")

    svc._brands.get_active.return_value = brand
    svc._brands.name_exists.return_value = True

    with pytest.raises(ConflictError):
        await svc.update(brand.id, BrandUpdate(name="Acme"), actor=actor)


@pytest.mark.asyncio
async def test_brand_delete_soft_deletes():
    svc = _make_brand_service()
    actor = _make_actor()
    brand = _make_brand()

    svc._brands.get_active.return_value = brand
    svc._brands.update.return_value = brand

    await svc.delete(brand.id, actor=actor)
    call_kwargs = svc._brands.update.call_args.kwargs
    assert call_kwargs["is_deleted"] is True


# ---------------------------------------------------------------------------
# UoMService tests
# ---------------------------------------------------------------------------


def _make_uom_service():
    session = _mock_session()
    svc = UoMService.__new__(UoMService)
    svc._session = session
    svc._uoms = AsyncMock()
    svc._audit = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_uom_create_success():
    svc = _make_uom_service()
    actor = _make_actor()
    uom = _make_uom()

    svc._uoms.name_exists.return_value = False
    svc._uoms.symbol_exists.return_value = False
    svc._uoms.create.return_value = uom

    result = await svc.create(UoMCreate(name="Kilogram", symbol="kg"), actor=actor)
    assert result is uom


@pytest.mark.asyncio
async def test_uom_create_duplicate_name_raises():
    svc = _make_uom_service()
    actor = _make_actor()
    svc._uoms.name_exists.return_value = True

    with pytest.raises(ConflictError):
        await svc.create(UoMCreate(name="Kilogram", symbol="kg"), actor=actor)


@pytest.mark.asyncio
async def test_uom_create_duplicate_symbol_raises():
    svc = _make_uom_service()
    actor = _make_actor()
    svc._uoms.name_exists.return_value = False
    svc._uoms.symbol_exists.return_value = True

    with pytest.raises(ConflictError):
        await svc.create(UoMCreate(name="Kilogram", symbol="kg"), actor=actor)


# ---------------------------------------------------------------------------
# SupplierService tests
# ---------------------------------------------------------------------------


def _make_supplier_service():
    session = _mock_session()
    svc = SupplierService.__new__(SupplierService)
    svc._session = session
    svc._suppliers = AsyncMock()
    svc._audit = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_supplier_create_auto_code():
    svc = _make_supplier_service()
    actor = _make_actor()
    supplier = _make_supplier()

    svc._suppliers.get_next_code.return_value = "SUP-00001"
    svc._suppliers.code_exists.return_value = False
    svc._suppliers.create.return_value = supplier

    result = await svc.create(SupplierCreate(name="Acme Corp"), actor=actor)
    assert result is supplier


@pytest.mark.asyncio
async def test_supplier_create_manual_code_duplicate_raises():
    svc = _make_supplier_service()
    actor = _make_actor()
    svc._suppliers.code_exists.return_value = True

    with pytest.raises(ConflictError):
        await svc.create(
            SupplierCreate(name="Acme Corp", supplier_code="SUP-99999"),
            actor=actor,
        )


@pytest.mark.asyncio
async def test_supplier_get_not_found_raises():
    svc = _make_supplier_service()
    svc._suppliers.get_active.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4())


@pytest.mark.asyncio
async def test_supplier_delete_soft_deletes():
    svc = _make_supplier_service()
    actor = _make_actor()
    supplier = _make_supplier()

    svc._suppliers.get_active.return_value = supplier
    svc._suppliers.update.return_value = supplier

    await svc.delete(supplier.id, actor=actor)
    call_kwargs = svc._suppliers.update.call_args.kwargs
    assert call_kwargs["is_deleted"] is True


# ---------------------------------------------------------------------------
# ProductService tests
# ---------------------------------------------------------------------------


def _make_product_service():
    session = _mock_session()
    svc = ProductService.__new__(ProductService)
    svc._session = session
    svc._products = AsyncMock()
    svc._cats = AsyncMock()
    svc._brands = AsyncMock()
    svc._uoms = AsyncMock()
    svc._suppliers = AsyncMock()
    svc._audit = AsyncMock()
    svc._storage = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_product_create_generates_sku_and_barcode():
    svc = _make_product_service()
    actor = _make_actor()
    product = _make_product()

    svc._cats.get_active.return_value = _make_category()
    svc._products.get_next_sku_sequence.return_value = 0
    svc._products.sku_exists.return_value = False
    svc._products.barcode_exists.return_value = False
    svc._products.create.return_value = product
    svc._products.get_active.return_value = product

    result = await svc.create(
        ProductCreate(name="Test Product", category_id=uuid.uuid4()),
        actor=actor,
    )
    assert result is product
    # SKU and barcode were injected into create call
    create_kwargs = svc._products.create.call_args.kwargs
    assert "sku" in create_kwargs
    assert "barcode" in create_kwargs
    assert create_kwargs["sku"].startswith("ELE-")
    assert len(create_kwargs["barcode"]) == 12


@pytest.mark.asyncio
async def test_product_create_no_category_uses_gen_prefix():
    svc = _make_product_service()
    actor = _make_actor()
    product = _make_product("GEN-20260101-00001")

    svc._products.get_next_sku_sequence.return_value = 0
    svc._products.sku_exists.return_value = False
    svc._products.barcode_exists.return_value = False
    svc._products.create.return_value = product
    svc._products.get_active.return_value = product

    result = await svc.create(ProductCreate(name="No Category Product"), actor=actor)
    create_kwargs = svc._products.create.call_args.kwargs
    assert create_kwargs["sku"].startswith("GEN-")


@pytest.mark.asyncio
async def test_product_get_not_found_raises():
    svc = _make_product_service()
    svc._products.get_active.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4())


@pytest.mark.asyncio
async def test_product_delete_soft_deletes():
    svc = _make_product_service()
    actor = _make_actor()
    product = _make_product()
    product.image_path = None

    svc._products.get_active.return_value = product
    svc._products.update.return_value = product

    await svc.delete(product.id, actor=actor)
    call_kwargs = svc._products.update.call_args.kwargs
    assert call_kwargs["is_deleted"] is True


@pytest.mark.asyncio
async def test_product_delete_removes_image_from_minio():
    svc = _make_product_service()
    actor = _make_actor()
    product = _make_product()
    product.image_path = "products/abc/image.jpg"

    svc._products.get_active.return_value = product
    svc._products.update.return_value = product
    svc._storage.delete = AsyncMock()

    await svc.delete(product.id, actor=actor)
    svc._storage.delete.assert_called_once_with("products/abc/image.jpg")


@pytest.mark.asyncio
async def test_product_upload_image_success():
    svc = _make_product_service()
    actor = _make_actor()
    product = _make_product()
    product.image_path = None

    svc._products.get_active.return_value = product
    svc._products.update.return_value = product
    svc._storage.upload = AsyncMock(return_value="products/id/img.jpg")

    result = await svc.upload_image(
        product.id, b"imagedata", "image/jpeg", actor=actor
    )
    svc._storage.upload.assert_called_once()


@pytest.mark.asyncio
async def test_product_delete_image_no_image_raises():
    svc = _make_product_service()
    actor = _make_actor()
    product = _make_product()
    product.image_path = None

    svc._products.get_active.return_value = product

    with pytest.raises(NotFoundError):
        await svc.delete_image(product.id, actor=actor)


@pytest.mark.asyncio
async def test_product_fk_validation_invalid_category_raises():
    svc = _make_product_service()
    actor = _make_actor()

    svc._cats.get_active.return_value = None  # category not found

    with pytest.raises(NotFoundError):
        await svc.create(
            ProductCreate(name="Product", category_id=uuid.uuid4()),
            actor=actor,
        )
