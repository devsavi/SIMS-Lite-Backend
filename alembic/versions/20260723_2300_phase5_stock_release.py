"""phase5_stock_release

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-23 23:00:00.000000

Creates:
  - stock_releases
  - stock_release_items
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- stock_releases ---
    op.create_table(
        "stock_releases",
        sa.Column("release_number", sa.String(30), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("release_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reference_document", sa.String(100), nullable=True),
        sa.Column(
            "total_quantity",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_cost",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        # Workflow metadata
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("submitted_by_id", sa.UUID(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", sa.UUID(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        # Soft delete
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Base columns
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
        # Constraints
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_number"),
    )
    op.create_index(
        "ix_stock_releases_release_number",
        "stock_releases",
        ["release_number"],
        unique=True,
    )
    op.create_index("ix_stock_releases_status", "stock_releases", ["status"])
    op.create_index("ix_stock_releases_purpose", "stock_releases", ["purpose"])
    op.create_index("ix_stock_releases_is_deleted", "stock_releases", ["is_deleted"])
    op.create_index(
        "ix_stock_releases_created_by_id", "stock_releases", ["created_by_id"]
    )
    op.create_index(
        "ix_stock_releases_approved_at", "stock_releases", ["approved_at"]
    )

    # --- stock_release_items ---
    op.create_table(
        "stock_release_items",
        sa.Column("stock_release_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("quantity_requested", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "unit_cost",
            sa.Numeric(12, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "line_total",
            sa.Numeric(14, 4),
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
            ["stock_release_id"],
            ["stock_releases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stock_release_items_stock_release_id",
        "stock_release_items",
        ["stock_release_id"],
    )
    op.create_index(
        "ix_stock_release_items_product_id",
        "stock_release_items",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_table("stock_release_items")
    op.drop_table("stock_releases")
