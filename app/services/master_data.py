"""
Master data service layer -- Phase 2.

Business logic for categories, brands, UoMs, suppliers, and products.
Handles SKU/barcode generation, image upload/delete, and audit logging.
"""

from __future__ import annotations

import io
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.master_data import Brand, Category, Product, Supplier, UnitOfMeasure
from app.models.user import User
from app.repositories.audit_log import AuditLogRepository
from app.repositories.master_data import (
    BrandRepository,
    CategoryRepository,
    ProductRepository,
    SupplierRepository,
    UnitOfMeasureRepository,
)
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
from app.storage.minio_client import StorageService

logger = get_logger(__name__)


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cats = CategoryRepository(session)
        self._audit = AuditLogRepository(session)

    async def create(
        self, payload: CategoryCreate, *, actor: User, ip_address: str | None = None
    ) -> Category:
        slug = payload.slug or _slugify(payload.name)
        # Ensure slug uniqueness
        base_slug = slug
        counter = 1
        while await self._cats.slug_exists(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1

        if await self._cats.name_exists_in_parent(payload.name, payload.parent_id):
            raise ConflictError(
                f"Category '{payload.name}' already exists under the same parent."
            )
        if payload.parent_id:
            parent = await self._cats.get_active(payload.parent_id)
            if not parent:
                raise NotFoundError("Parent category not found.")

        cat = await self._cats.create(
            name=payload.name,
            description=payload.description,
            slug=slug,
            parent_id=payload.parent_id,
            is_active=payload.is_active,
        )
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="category:create",
            resource_type="categories",
            resource_id=str(cat.id),
            ip_address=ip_address,
            status="success",
        )
        return cat

    async def get(self, pk: uuid.UUID) -> Category:
        cat = await self._cats.get_active(pk)
        if not cat:
            raise NotFoundError("Category not found.")
        return cat

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        active_only: bool = False,
        parent_id: uuid.UUID | None = None,
        include_parent_filter: bool = False,
    ) -> tuple[list[Category], int]:
        offset = (page - 1) * size
        return await self._cats.get_all_paginated(
            offset=offset,
            limit=size,
            search=search,
            active_only=active_only,
            parent_id=parent_id,
            include_parent_filter=include_parent_filter,
        )

    async def update(
        self,
        pk: uuid.UUID,
        payload: CategoryUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Category:
        cat = await self.get(pk)
        updates: dict[str, Any] = {}

        if payload.name is not None and payload.name != cat.name:
            parent_id = payload.parent_id if payload.parent_id is not None else cat.parent_id
            if await self._cats.name_exists_in_parent(payload.name, parent_id, exclude_id=pk):
                raise ConflictError(
                    f"Category '{payload.name}' already exists under the same parent."
                )
            updates["name"] = payload.name
            updates["slug"] = payload.slug or _slugify(payload.name)

        if payload.slug is not None:
            new_slug = payload.slug
            if await self._cats.slug_exists(new_slug, exclude_id=pk):
                raise ConflictError(f"Slug '{new_slug}' is already in use.")
            updates["slug"] = new_slug

        for field in ("description", "parent_id", "is_active"):
            val = getattr(payload, field, None)
            if val is not None:
                updates[field] = val

        cat = await self._cats.update(cat, **updates)
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="category:update",
            resource_type="categories",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return cat

    async def delete(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> None:
        cat = await self.get(pk)
        await self._cats.update(
            cat,
            is_deleted=True,
            is_active=False,
            deleted_at=datetime.now(UTC),
        )
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="category:delete",
            resource_type="categories",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )


class BrandService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._brands = BrandRepository(session)
        self._audit = AuditLogRepository(session)

    async def create(
        self, payload: BrandCreate, *, actor: User, ip_address: str | None = None
    ) -> Brand:
        if await self._brands.name_exists(payload.name):
            raise ConflictError(f"Brand '{payload.name}' already exists.")
        brand = await self._brands.create(**payload.model_dump())
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="brand:create",
            resource_type="brands",
            resource_id=str(brand.id),
            ip_address=ip_address,
            status="success",
        )
        return brand

    async def get(self, pk: uuid.UUID) -> Brand:
        brand = await self._brands.get_active(pk)
        if not brand:
            raise NotFoundError("Brand not found.")
        return brand

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        active_only: bool = False,
    ) -> tuple[list[Brand], int]:
        offset = (page - 1) * size
        return await self._brands.get_all_paginated(
            offset=offset, limit=size, search=search, active_only=active_only
        )

    async def update(
        self,
        pk: uuid.UUID,
        payload: BrandUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Brand:
        brand = await self.get(pk)
        updates: dict[str, Any] = {}
        if payload.name is not None and payload.name != brand.name:
            if await self._brands.name_exists(payload.name, exclude_id=pk):
                raise ConflictError(f"Brand '{payload.name}' already exists.")
            updates["name"] = payload.name
        for field in ("description", "logo_url", "website", "is_active"):
            val = getattr(payload, field, None)
            if val is not None:
                updates[field] = val
        brand = await self._brands.update(brand, **updates)
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="brand:update",
            resource_type="brands",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return brand

    async def delete(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> None:
        brand = await self.get(pk)
        await self._brands.update(
            brand,
            is_deleted=True,
            is_active=False,
            deleted_at=datetime.now(UTC),
        )
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="brand:delete",
            resource_type="brands",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )


class UoMService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._uoms = UnitOfMeasureRepository(session)
        self._audit = AuditLogRepository(session)

    async def create(
        self, payload: UoMCreate, *, actor: User, ip_address: str | None = None
    ) -> UnitOfMeasure:
        if await self._uoms.name_exists(payload.name):
            raise ConflictError(f"UoM '{payload.name}' already exists.")
        if await self._uoms.symbol_exists(payload.symbol):
            raise ConflictError(f"UoM symbol '{payload.symbol}' already exists.")
        uom = await self._uoms.create(**payload.model_dump())
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="uom:create",
            resource_type="units_of_measure",
            resource_id=str(uom.id),
            ip_address=ip_address,
            status="success",
        )
        return uom

    async def get(self, pk: uuid.UUID) -> UnitOfMeasure:
        uom = await self._uoms.get_active(pk)
        if not uom:
            raise NotFoundError("Unit of measure not found.")
        return uom

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        active_only: bool = False,
    ) -> tuple[list[UnitOfMeasure], int]:
        offset = (page - 1) * size
        return await self._uoms.get_all_paginated(
            offset=offset, limit=size, search=search, active_only=active_only
        )

    async def update(
        self,
        pk: uuid.UUID,
        payload: UoMUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> UnitOfMeasure:
        uom = await self.get(pk)
        updates: dict[str, Any] = {}
        if payload.name is not None and payload.name != uom.name:
            if await self._uoms.name_exists(payload.name, exclude_id=pk):
                raise ConflictError(f"UoM '{payload.name}' already exists.")
            updates["name"] = payload.name
        if payload.symbol is not None and payload.symbol != uom.symbol:
            if await self._uoms.symbol_exists(payload.symbol, exclude_id=pk):
                raise ConflictError(f"UoM symbol '{payload.symbol}' already exists.")
            updates["symbol"] = payload.symbol
        for field in ("description", "is_active"):
            val = getattr(payload, field, None)
            if val is not None:
                updates[field] = val
        uom = await self._uoms.update(uom, **updates)
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="uom:update",
            resource_type="units_of_measure",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return uom

    async def delete(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> None:
        uom = await self.get(pk)
        await self._uoms.update(
            uom,
            is_deleted=True,
            is_active=False,
            deleted_at=datetime.now(UTC),
        )
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="uom:delete",
            resource_type="units_of_measure",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )


class SupplierService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._suppliers = SupplierRepository(session)
        self._audit = AuditLogRepository(session)

    async def create(
        self, payload: SupplierCreate, *, actor: User, ip_address: str | None = None
    ) -> Supplier:
        # Auto-generate supplier code if not provided
        supplier_code = payload.supplier_code
        if not supplier_code:
            supplier_code = await self._suppliers.get_next_code()
            # Ensure uniqueness in case of race conditions
            while await self._suppliers.code_exists(supplier_code):
                supplier_code = await self._suppliers.get_next_code()
        else:
            if await self._suppliers.code_exists(supplier_code):
                raise ConflictError(
                    f"Supplier code '{supplier_code}' already exists."
                )

        data = payload.model_dump()
        data["supplier_code"] = supplier_code
        supplier = await self._suppliers.create(**data)
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="supplier:create",
            resource_type="suppliers",
            resource_id=str(supplier.id),
            ip_address=ip_address,
            status="success",
        )
        return supplier

    async def get(self, pk: uuid.UUID) -> Supplier:
        supplier = await self._suppliers.get_active(pk)
        if not supplier:
            raise NotFoundError("Supplier not found.")
        return supplier

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        active_only: bool = False,
    ) -> tuple[list[Supplier], int]:
        offset = (page - 1) * size
        return await self._suppliers.get_all_paginated(
            offset=offset, limit=size, search=search, active_only=active_only
        )

    async def update(
        self,
        pk: uuid.UUID,
        payload: SupplierUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Supplier:
        supplier = await self.get(pk)
        updates: dict[str, Any] = {}
        if payload.supplier_code is not None and payload.supplier_code != supplier.supplier_code:
            if await self._suppliers.code_exists(payload.supplier_code, exclude_id=pk):
                raise ConflictError(
                    f"Supplier code '{payload.supplier_code}' already exists."
                )
            updates["supplier_code"] = payload.supplier_code

        for field in (
            "name", "contact_person", "email", "phone", "address",
            "city", "state", "country", "postal_code", "tax_id",
            "payment_terms", "notes", "is_active",
        ):
            val = getattr(payload, field, None)
            if val is not None:
                updates[field] = val

        supplier = await self._suppliers.update(supplier, **updates)
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="supplier:update",
            resource_type="suppliers",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return supplier

    async def delete(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> None:
        supplier = await self.get(pk)
        await self._suppliers.update(
            supplier,
            is_deleted=True,
            is_active=False,
            deleted_at=datetime.now(UTC),
        )
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="supplier:delete",
            resource_type="suppliers",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )


# ---------------------------------------------------------------------------
# SKU & Barcode generation helpers
# ---------------------------------------------------------------------------

def _generate_sku(category_name: str | None, sequence: int) -> str:
    """
    Generate a SKU in the format: CAT-YYYYMMDD-XXXXX
      CAT  = first 3 uppercase letters of category name (or GEN)
      YYYY = year, MM = month, DD = day
      XXXXX = zero-padded 5-digit sequence
    """
    prefix = (category_name or "GEN")[:3].upper()
    today = datetime.now(UTC).strftime("%Y%m%d")
    return f"{prefix}-{today}-{sequence + 1:05d}"


def _generate_barcode_value(sku: str) -> str:
    """
    Generate a numeric barcode value suitable for Code128.
    Uses a 12-digit numeric code derived from the current timestamp
    and a hash of the SKU for uniqueness.
    """
    import hashlib
    import time
    ts = str(int(time.time() * 1000))[-6:]
    sku_hash = str(int(hashlib.md5(sku.encode()).hexdigest(), 16))[:6]
    return (ts + sku_hash)[:12].zfill(12)


class ProductService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._products = ProductRepository(session)
        self._cats = CategoryRepository(session)
        self._brands = BrandRepository(session)
        self._uoms = UnitOfMeasureRepository(session)
        self._suppliers = SupplierRepository(session)
        self._audit = AuditLogRepository(session)
        self._storage = StorageService()

    async def _resolve_fk(self, payload: ProductCreate | ProductUpdate) -> None:
        """Validate that referenced foreign keys exist."""
        if getattr(payload, "category_id", None):
            if not await self._cats.get_active(payload.category_id):
                raise NotFoundError("Category not found.")
        if getattr(payload, "brand_id", None):
            if not await self._brands.get_active(payload.brand_id):
                raise NotFoundError("Brand not found.")
        if getattr(payload, "uom_id", None):
            if not await self._uoms.get_active(payload.uom_id):
                raise NotFoundError("Unit of measure not found.")
        if getattr(payload, "supplier_id", None):
            if not await self._suppliers.get_active(payload.supplier_id):
                raise NotFoundError("Supplier not found.")

    async def create(
        self, payload: ProductCreate, *, actor: User, ip_address: str | None = None
    ) -> Product:
        await self._resolve_fk(payload)

        # SKU generation
        category_name: str | None = None
        if payload.category_id:
            cat = await self._cats.get_active(payload.category_id)
            if cat:
                category_name = cat.name
        prefix = (category_name or "GEN")[:3].upper()
        today = datetime.now(UTC).strftime("%Y%m%d")
        sku_prefix = f"{prefix}-{today}-"
        seq = await self._products.get_next_sku_sequence(sku_prefix)
        sku = _generate_sku(category_name, seq)

        # Guarantee SKU uniqueness
        while await self._products.sku_exists(sku):
            seq += 1
            sku = _generate_sku(category_name, seq)

        # Barcode generation
        barcode_value = _generate_barcode_value(sku)
        attempts = 0
        while await self._products.barcode_exists(barcode_value):
            if attempts > 10:
                raise ConflictError("Unable to generate unique barcode. Please try again.")
            barcode_value = _generate_barcode_value(sku + str(attempts))
            attempts += 1

        data = payload.model_dump()
        data["sku"] = sku
        data["barcode"] = barcode_value
        product = await self._products.create(**data)
        # Reload with relationships
        product = await self._products.get_active(product.id)

        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="product:create",
            resource_type="products",
            resource_id=str(product.id),
            ip_address=ip_address,
            status="success",
            detail={"sku": sku, "barcode": barcode_value},
        )
        return product

    async def get(self, pk: uuid.UUID) -> Product:
        product = await self._products.get_active(pk)
        if not product:
            raise NotFoundError("Product not found.")
        return product

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        active_only: bool = False,
        category_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> tuple[list[Product], int]:
        offset = (page - 1) * size
        return await self._products.get_all_paginated(
            offset=offset,
            limit=size,
            search=search,
            active_only=active_only,
            category_id=category_id,
            brand_id=brand_id,
            supplier_id=supplier_id,
        )

    async def update(
        self,
        pk: uuid.UUID,
        payload: ProductUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Product:
        product = await self.get(pk)
        await self._resolve_fk(payload)

        updates: dict[str, Any] = {}
        for field in (
            "name", "description", "short_description",
            "category_id", "brand_id", "uom_id", "supplier_id",
            "cost_price", "selling_price", "reorder_level",
            "reorder_quantity", "is_active",
        ):
            val = getattr(payload, field, None)
            if val is not None:
                updates[field] = val

        product = await self._products.update(product, **updates)
        product = await self._products.get_active(product.id)
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="product:update",
            resource_type="products",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return product

    async def delete(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> None:
        product = await self.get(pk)
        # Remove image from MinIO if present
        if product.image_path:
            try:
                await self._storage.delete(product.image_path)
            except Exception as exc:
                logger.warning("Failed to delete product image", error=str(exc))
        await self._products.update(
            product,
            is_deleted=True,
            is_active=False,
            deleted_at=datetime.now(UTC),
        )
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="product:delete",
            resource_type="products",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )

    async def upload_image(
        self,
        pk: uuid.UUID,
        file_data: bytes,
        content_type: str,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Product:
        product = await self.get(pk)
        # Delete old image
        if product.image_path:
            try:
                await self._storage.delete(product.image_path)
            except Exception as exc:
                logger.warning("Failed to delete old product image", error=str(exc))

        ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]
        object_name = f"products/{product.id}/{uuid.uuid4()}.{ext}"
        await self._storage.upload(object_name, file_data, content_type=content_type)
        product = await self._products.update(product, image_path=object_name)
        product = await self._products.get_active(product.id)
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="product:image_upload",
            resource_type="products",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return product

    async def delete_image(
        self,
        pk: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Product:
        product = await self.get(pk)
        if not product.image_path:
            raise NotFoundError("Product has no image.")
        await self._storage.delete(product.image_path)
        product = await self._products.update(product, image_path=None)
        product = await self._products.get_active(product.id)
        await self._audit.log(
            self._session,
            actor_id=actor.id,
            action="product:image_delete",
            resource_type="products",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return product

    async def get_image_url(self, pk: uuid.UUID) -> str:
        product = await self.get(pk)
        if not product.image_path:
            raise NotFoundError("Product has no image.")
        return await self._storage.get_presigned_url(product.image_path)

    def generate_barcode_png(self, barcode_value: str) -> bytes:
        """Render a Code128 barcode as PNG bytes."""
        import barcode as python_barcode
        from barcode.writer import ImageWriter

        code128 = python_barcode.get_barcode_class("code128")
        buf = io.BytesIO()
        code128(barcode_value, writer=ImageWriter()).write(buf)
        return buf.getvalue()

    async def get_for_report(
        self,
        *,
        active_only: bool = False,
        category_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> list[Product]:
        return await self._products.get_all_for_report(
            active_only=active_only,
            category_id=category_id,
            supplier_id=supplier_id,
        )
