"""
Inventory report generation service — Phase 4.

Generates Excel workbooks for:
- Current Stock Report
- Inventory Ledger Report
- Stock Adjustment Report
- Low Stock Report
"""

from __future__ import annotations

import io

from app.models.inventory import Inventory, InventoryLedgerEntry, StockAdjustment
from app.services.report import (
    _auto_fit_columns,
    _make_workbook,
    _style_data_rows,
    _style_header_row,
)


class InventoryReportService:
    """Generates Excel reports for inventory data."""

    def generate_current_stock_report(self, inventory_items: list[Inventory]) -> bytes:
        """Build an Excel current stock report."""
        wb = _make_workbook()
        ws = wb.active
        ws.title = "Current Stock"

        headers = [
            "SKU",
            "Barcode",
            "Product Name",
            "Category",
            "Brand",
            "UoM",
            "Qty On Hand",
            "Average Cost",
            "Stock Value",
            "Reorder Level",
            "Status",
            "Last Updated",
        ]
        ws.append(headers)
        _style_header_row(ws, len(headers))

        for inv in inventory_items:
            product = inv.product
            if not product:
                continue

            qty = float(inv.quantity_on_hand)
            avg_cost = float(inv.average_cost)
            stock_value = round(qty * avg_cost, 4)

            if qty <= 0:
                stock_status = "Out of Stock"
            elif product.reorder_level and qty <= product.reorder_level:
                stock_status = "Low Stock"
            else:
                stock_status = "In Stock"

            ws.append(
                [
                    product.sku,
                    product.barcode,
                    product.name,
                    product.category.name if product.category else "",
                    product.brand.name if product.brand else "",
                    product.uom.symbol if product.uom else "",
                    qty,
                    avg_cost,
                    stock_value,
                    product.reorder_level,
                    stock_status,
                    (
                        inv.last_updated_at.strftime("%Y-%m-%d %H:%M")
                        if inv.last_updated_at
                        else ""
                    ),
                ]
            )

        _style_data_rows(ws, len(inventory_items), len(headers))
        _auto_fit_columns(ws)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def generate_inventory_ledger_report(
        self, entries: list[InventoryLedgerEntry]
    ) -> bytes:
        """Build an Excel inventory ledger report."""
        wb = _make_workbook()
        ws = wb.active
        ws.title = "Inventory Ledger"

        headers = [
            "Date",
            "Product SKU",
            "Product Name",
            "Entry Type",
            "Qty Before",
            "Qty Change",
            "Qty After",
            "Unit Cost",
            "Total Value Change",
            "Reference Type",
            "Reference Number",
            "Notes",
            "Created By",
        ]
        ws.append(headers)
        _style_header_row(ws, len(headers))

        for entry in entries:
            product = entry.product
            created_by = ""
            if entry.created_by:
                created_by = (
                    f"{entry.created_by.first_name} {entry.created_by.last_name}"
                )

            ws.append(
                [
                    (
                        entry.created_at.strftime("%Y-%m-%d %H:%M")
                        if entry.created_at
                        else ""
                    ),
                    product.sku if product else "",
                    product.name if product else "",
                    entry.entry_type,
                    float(entry.quantity_before),
                    float(entry.quantity_change),
                    float(entry.quantity_after),
                    float(entry.unit_cost),
                    round(float(entry.quantity_change) * float(entry.unit_cost), 4),
                    entry.reference_type or "",
                    entry.reference_number or "",
                    entry.notes or "",
                    created_by,
                ]
            )

        _style_data_rows(ws, len(entries), len(headers))
        _auto_fit_columns(ws)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def generate_stock_adjustment_report(
        self, adjustments: list[StockAdjustment]
    ) -> bytes:
        """Build an Excel stock adjustment report (summary + line items)."""
        wb = _make_workbook()

        # Sheet 1: Adjustment Summary
        ws_summary = wb.active
        ws_summary.title = "Adjustments"

        summary_headers = [
            "Adjustment No.",
            "Type",
            "Status",
            "Reason",
            "Items Count",
            "Created By",
            "Submitted By",
            "Submitted At",
            "Approved By",
            "Approved At",
            "Created At",
        ]
        ws_summary.append(summary_headers)
        _style_header_row(ws_summary, len(summary_headers))

        for adj in adjustments:
            created_by = ""
            if adj.created_by:
                created_by = f"{adj.created_by.first_name} {adj.created_by.last_name}"
            submitted_by = ""
            if adj.submitted_by:
                submitted_by = (
                    f"{adj.submitted_by.first_name} {adj.submitted_by.last_name}"
                )
            approved_by = ""
            if adj.approved_by:
                approved_by = (
                    f"{adj.approved_by.first_name} {adj.approved_by.last_name}"
                )

            ws_summary.append(
                [
                    adj.adjustment_number,
                    adj.adjustment_type,
                    adj.status,
                    adj.reason,
                    len(adj.items),
                    created_by,
                    submitted_by,
                    (
                        adj.submitted_at.strftime("%Y-%m-%d %H:%M")
                        if adj.submitted_at
                        else ""
                    ),
                    approved_by,
                    (
                        adj.approved_at.strftime("%Y-%m-%d %H:%M")
                        if adj.approved_at
                        else ""
                    ),
                    (
                        adj.created_at.strftime("%Y-%m-%d %H:%M")
                        if adj.created_at
                        else ""
                    ),
                ]
            )

        _style_data_rows(ws_summary, len(adjustments), len(summary_headers))
        _auto_fit_columns(ws_summary)

        # Sheet 2: Line Items
        ws_items = wb.create_sheet(title="Adjustment Items")
        items_headers = [
            "Adjustment No.",
            "Type",
            "Status",
            "Product SKU",
            "Product Name",
            "Qty Adjusted",
            "Unit Cost",
            "Line Value",
            "Notes",
        ]
        ws_items.append(items_headers)
        _style_header_row(ws_items, len(items_headers))

        all_items = []
        for adj in adjustments:
            for item in adj.items:
                all_items.append(
                    [
                        adj.adjustment_number,
                        adj.adjustment_type,
                        adj.status,
                        item.product.sku if item.product else "",
                        item.product.name if item.product else "",
                        float(item.quantity_adjusted),
                        float(item.unit_cost),
                        round(
                            float(item.quantity_adjusted) * float(item.unit_cost), 4
                        ),
                        item.notes or "",
                    ]
                )
                ws_items.append(all_items[-1])

        _style_data_rows(ws_items, len(all_items), len(items_headers))
        _auto_fit_columns(ws_items)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def generate_low_stock_report(self, inventory_items: list[Inventory]) -> bytes:
        """Build an Excel low stock / reorder report."""
        wb = _make_workbook()
        ws = wb.active
        ws.title = "Low Stock"

        headers = [
            "SKU",
            "Barcode",
            "Product Name",
            "Category",
            "Supplier",
            "Qty On Hand",
            "Reorder Level",
            "Reorder Qty",
            "Units Below Reorder",
            "Average Cost",
            "Reorder Value",
            "Status",
        ]
        ws.append(headers)
        _style_header_row(ws, len(headers))

        for inv in inventory_items:
            product = inv.product
            if not product:
                continue

            qty = float(inv.quantity_on_hand)
            reorder_level = int(product.reorder_level or 0)
            reorder_qty = int(product.reorder_quantity or 0)
            avg_cost = float(inv.average_cost)
            units_below = max(0, reorder_level - qty)
            reorder_value = round(reorder_qty * avg_cost, 4)

            status = "Out of Stock" if qty <= 0 else "Low Stock"

            ws.append(
                [
                    product.sku,
                    product.barcode,
                    product.name,
                    product.category.name if product.category else "",
                    product.supplier.name if product.supplier else "",
                    qty,
                    reorder_level,
                    reorder_qty,
                    units_below,
                    avg_cost,
                    reorder_value,
                    status,
                ]
            )

        _style_data_rows(ws, len(inventory_items), len(headers))
        _auto_fit_columns(ws)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
