"""phase4_inventory

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-07-23 22:00:00.000000

Creates:
  - inventory
  - inventory_ledger_entries
  - stock_adjustments
  - stock_adjustment_items
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- inventory ---
    op.create_table(
        "inventory",
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column(
            "quantity_on_hand",
            sa.Numeric(12, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "average_cost",
            sa.Numeric(12, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_transaction_type", sa.String(30), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", name="uq_inventory_product_id"),
    )
    op.create_index("ix_inventory_product_id", "inventory", ["product_id"], unique=True)

    # --- inventory_ledger_entries ---
    op.create_table(
        "inventory_ledger_entries",
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("quantity_before", sa.Numeric(12, 4), nullable=False),
        sa.Column("quantity_change", sa.Numeric(12, 4), nullable=False),
        sa.Column("quantity_after", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "unit_cost",
            sa.Numeric(12, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("reference_type", sa.String(30), nullable=True),
        sa.Column("reference_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_ledger_entries_product_id",
        "inventory_ledger_entries",
        ["product_id"],
    )
    op.create_index(
        "ix_inventory_ledger_entries_entry_type",
        "inventory_ledger_entries",
        ["entry_type"],
    )
    op.create_index(
        "ix_inventory_ledger_entries_reference_type",
        "inventory_ledger_entries",
        ["reference_type"],
    )
    op.create_index(
        "ix_inventory_ledger_entries_reference_id",
        "inventory_ledger_entries",
        ["reference_id"],
    )

    # --- stock_adjustments ---
    op.create_table(
        "stock_adjustments",
        sa.Column("adjustment_number", sa.String(30), nullable=False),
        sa.Column("adjustment_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("submitted_by_id", sa.UUID(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", sa.UUID(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adjustment_number"),
    )
    op.create_index(
        "ix_stock_adjustments_adjustment_number",
        "stock_adjustments",
        ["adjustment_number"],
        unique=True,
    )
    op.create_index(
        "ix_stock_adjustments_status", "stock_adjustments", ["status"]
    )
    op.create_index(
        "ix_stock_adjustments_adjustment_type",
        "stock_adjustments",
        ["adjustment_type"],
    )
    op.create_index(
        "ix_stock_adjustments_is_deleted", "stock_adjustments", ["is_deleted"]
    )
    op.create_index(
        "ix_stock_adjustments_created_by_id",
        "stock_adjustments",
        ["created_by_id"],
    )

    # --- stock_adjustment_items ---
    op.create_table(
        "stock_adjustment_items",
        sa.Column("stock_adjustment_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("quantity_adjusted", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "unit_cost",
            sa.Numeric(12, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
            ["stock_adjustment_id"],
            ["stock_adjustments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stock_adjustment_items_stock_adjustment_id",
        "stock_adjustment_items",
        ["stock_adjustment_id"],
    )
    op.create_index(
        "ix_stock_adjustment_items_product_id",
        "stock_adjustment_items",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_table("stock_adjustment_items")
    op.drop_table("stock_adjustments")
    op.drop_table("inventory_ledger_entries")
    op.drop_table("inventory")
