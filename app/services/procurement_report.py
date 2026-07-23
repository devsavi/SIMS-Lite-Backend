"""
Procurement report generation service — Phase 3.

Generates Excel workbooks for PO, GRN, and Supplier Purchase reports.
"""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.models.procurement import GRN, PurchaseOrder
from app.services.report import (
    _auto_fit_columns,
    _make_workbook,
    _style_data_rows,
    _style_header_row,
)


class ProcurementReportService:
    """Generates Excel reports for procurement data."""

    def generate_po_report(self, pos: list[PurchaseOrder]) -> bytes:
        """Build an Excel Purchase Order report and return the bytes."""
        wb = _make_workbook()
        ws = wb.active
        ws.title = "Purchase Orders"

        headers = [
            "PO Number",
            "Supplier",
            "Status",
            "Order Date",
            "Expected Delivery",
            "Items Count",
            "Subtotal",
            "Discount",
            "Tax",
            "Total Amount",
            "Submitted By",
            "Submitted At",
            "Approved By",
            "Approved At",
            "Email Sent To",
            "Created At",
        ]
        ws.append(headers)
        _style_header_row(ws, len(headers))

        for po in pos:
            submitted_by = ""
            if po.submitted_by:
                submitted_by = f"{po.submitted_by.first_name} {po.submitted_by.last_name}"
            approved_by = ""
            if po.approved_by:
                approved_by = f"{po.approved_by.first_name} {po.approved_by.last_name}"

            ws.append(
                [
                    po.po_number,
                    po.supplier.name if po.supplier else "",
                    po.status,
                    po.order_date.strftime("%Y-%m-%d") if po.order_date else "",
                    (
                        po.expected_delivery_date.strftime("%Y-%m-%d")
                        if po.expected_delivery_date
                        else ""
                    ),
                    len(po.items),
                    float(po.subtotal),
                    float(po.discount_amount),
                    float(po.tax_amount),
                    float(po.total_amount),
                    submitted_by,
                    po.submitted_at.strftime("%Y-%m-%d %H:%M") if po.submitted_at else "",
                    approved_by,
                    po.approved_at.strftime("%Y-%m-%d %H:%M") if po.approved_at else "",
                    po.email_sent_to or "",
                    po.created_at.strftime("%Y-%m-%d %H:%M") if po.created_at else "",
                ]
            )

        _style_data_rows(ws, len(pos), len(headers))
        _auto_fit_columns(ws)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def generate_grn_report(self, grns: list[GRN]) -> bytes:
        """Build an Excel GRN report and return the bytes."""
        wb = _make_workbook()

        # Sheet 1: GRN Summary
        ws_summary = wb.active
        ws_summary.title = "GRN Summary"

        summary_headers = [
            "GRN Number",
            "PO Number",
            "Supplier",
            "Status",
            "Received Date",
            "Delivery Note No.",
            "Items Count",
            "Created By",
            "Approved By",
            "Approved At",
        ]
        ws_summary.append(summary_headers)
        _style_header_row(ws_summary, len(summary_headers))

        for grn in grns:
            po_number = grn.purchase_order.po_number if grn.purchase_order else ""
            supplier_name = (
                grn.purchase_order.supplier.name
                if grn.purchase_order and grn.purchase_order.supplier
                else ""
            )
            created_by = ""
            if grn.created_by:
                created_by = f"{grn.created_by.first_name} {grn.created_by.last_name}"
            approved_by = ""
            if grn.approved_by:
                approved_by = f"{grn.approved_by.first_name} {grn.approved_by.last_name}"

            ws_summary.append(
                [
                    grn.grn_number,
                    po_number,
                    supplier_name,
                    grn.status,
                    (
                        grn.received_date.strftime("%Y-%m-%d")
                        if grn.received_date
                        else ""
                    ),
                    grn.delivery_note_number or "",
                    len(grn.items),
                    created_by,
                    approved_by,
                    grn.approved_at.strftime("%Y-%m-%d %H:%M") if grn.approved_at else "",
                ]
            )

        _style_data_rows(ws_summary, len(grns), len(summary_headers))
        _auto_fit_columns(ws_summary)

        # Sheet 2: GRN Line Items
        ws_items = wb.create_sheet(title="GRN Items")
        items_headers = [
            "GRN Number",
            "PO Number",
            "Product SKU",
            "Product Name",
            "Quantity Received",
            "Unit Cost",
            "Line Total",
            "Received Date",
        ]
        ws_items.append(items_headers)
        _style_header_row(ws_items, len(items_headers))

        all_items = []
        for grn in grns:
            po_number = grn.purchase_order.po_number if grn.purchase_order else ""
            for item in grn.items:
                all_items.append(
                    [
                        grn.grn_number,
                        po_number,
                        item.product.sku if item.product else "",
                        item.product.name if item.product else "",
                        float(item.quantity_received),
                        float(item.unit_cost),
                        round(float(item.quantity_received) * float(item.unit_cost), 4),
                        (
                            grn.received_date.strftime("%Y-%m-%d")
                            if grn.received_date
                            else ""
                        ),
                    ]
                )
                ws_items.append(all_items[-1])

        _style_data_rows(ws_items, len(all_items), len(items_headers))
        _auto_fit_columns(ws_items)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def generate_supplier_purchase_report(self, pos: list[PurchaseOrder]) -> bytes:
        """Build a supplier-grouped purchase report."""
        wb = _make_workbook()
        ws = wb.active
        ws.title = "Supplier Purchases"

        # Group by supplier
        by_supplier: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"name": "", "code": "", "orders": 0, "total": 0.0, "items": []}
        )

        for po in pos:
            key = str(po.supplier_id)
            if po.supplier:
                by_supplier[key]["name"] = po.supplier.name
                by_supplier[key]["code"] = po.supplier.supplier_code
            by_supplier[key]["orders"] += 1
            by_supplier[key]["total"] += float(po.total_amount)
            by_supplier[key]["items"].append(po)

        headers = [
            "Supplier Code",
            "Supplier Name",
            "Total Orders",
            "Total Purchase Value",
            "Average Order Value",
            "Last Order Date",
        ]
        ws.append(headers)
        _style_header_row(ws, len(headers))

        for supplier_data in sorted(
            by_supplier.values(), key=lambda x: x["total"], reverse=True
        ):
            orders = supplier_data["items"]
            last_order_date = (
                max(po.order_date for po in orders if po.order_date).strftime(
                    "%Y-%m-%d"
                )
                if orders
                else ""
            )
            total = supplier_data["total"]
            count = supplier_data["orders"]
            ws.append(
                [
                    supplier_data["code"],
                    supplier_data["name"],
                    count,
                    round(total, 2),
                    round(total / count, 2) if count > 0 else 0,
                    last_order_date,
                ]
            )

        _style_data_rows(ws, len(by_supplier), len(headers))
        _auto_fit_columns(ws)

        # Sheet 2: Detail
        ws_detail = wb.create_sheet(title="PO Detail")
        detail_headers = [
            "PO Number",
            "Supplier",
            "Order Date",
            "Status",
            "Total Amount",
            "Items",
        ]
        ws_detail.append(detail_headers)
        _style_header_row(ws_detail, len(detail_headers))

        for po in pos:
            ws_detail.append(
                [
                    po.po_number,
                    po.supplier.name if po.supplier else "",
                    po.order_date.strftime("%Y-%m-%d") if po.order_date else "",
                    po.status,
                    float(po.total_amount),
                    len(po.items),
                ]
            )

        _style_data_rows(ws_detail, len(pos), len(detail_headers))
        _auto_fit_columns(ws_detail)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
