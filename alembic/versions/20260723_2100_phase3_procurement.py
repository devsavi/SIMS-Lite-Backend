"""phase3_procurement

Revision ID: c1d2e3f4a5b6
Revises: 86e34ca838b4
Create Date: 2026-07-23 21:00:00.000000

Creates:
  - purchase_orders
  - purchase_order_items
  - grns
  - grn_items
  - inventory_ledger
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "86e34ca838b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- purchase_orders ---
    op.create_table(
        "purchase_orders",
        sa.Column("po_number", sa.String(30), nullable=False),
        sa.Column("supplier_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_delivery_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subtotal", sa.Numeric(14, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("discount_amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("terms_conditions", sa.Text(), nullable=True),
        sa.Column("shipping_address", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("submitted_by_id", sa.UUID(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_id", sa.UUID(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_by_id", sa.UUID(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_to", sa.String(255), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("po_number"),
    )
    op.create_index("ix_purchase_orders_po_number", "purchase_orders", ["po_number"], unique=True)
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])
    op.create_index("ix_purchase_orders_is_deleted", "purchase_orders", ["is_deleted"])
    op.create_index("ix_purchase_orders_created_by_id", "purchase_orders", ["created_by_id"])

    # --- purchase_order_items ---
    op.create_table(
        "purchase_order_items",
        sa.Column("purchase_order_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("quantity_ordered", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 4), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_percent", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("line_total", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("quantity_received", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purchase_order_items_purchase_order_id",
        "purchase_order_items",
        ["purchase_order_id"],
    )
    op.create_index("ix_purchase_order_items_product_id", "purchase_order_items", ["product_id"])

    # --- grns ---
    op.create_table(
        "grns",
        sa.Column("grn_number", sa.String(30), nullable=False),
        sa.Column("purchase_order_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("received_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_note_number", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("submitted_by_id", sa.UUID(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", sa.UUID(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grn_number"),
    )
    op.create_index("ix_grns_grn_number", "grns", ["grn_number"], unique=True)
    op.create_index("ix_grns_purchase_order_id", "grns", ["purchase_order_id"])
    op.create_index("ix_grns_status", "grns", ["status"])
    op.create_index("ix_grns_created_by_id", "grns", ["created_by_id"])

    # --- grn_items ---
    op.create_table(
        "grn_items",
        sa.Column("grn_id", sa.UUID(), nullable=False),
        sa.Column("po_item_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("quantity_received", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["grn_id"], ["grns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["po_item_id"], ["purchase_order_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grn_items_grn_id", "grn_items", ["grn_id"])
    op.create_index("ix_grn_items_po_item_id", "grn_items", ["po_item_id"])
    op.create_index("ix_grn_items_product_id", "grn_items", ["product_id"])

    # --- inventory_ledger ---
    op.create_table(
        "inventory_ledger",
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("quantity_before", sa.Numeric(12, 4), nullable=False),
        sa.Column("quantity_change", sa.Numeric(12, 4), nullable=False),
        sa.Column("quantity_after", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("grn_id", sa.UUID(), nullable=True),
        sa.Column("reference_number", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["grn_id"], ["grns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_ledger_product_id", "inventory_ledger", ["product_id"])
    op.create_index("ix_inventory_ledger_entry_type", "inventory_ledger", ["entry_type"])
    op.create_index("ix_inventory_ledger_grn_id", "inventory_ledger", ["grn_id"])


def downgrade() -> None:
    op.drop_table("inventory_ledger")
    op.drop_table("grn_items")
    op.drop_table("grns")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
