"""
Stock Release report generation service — Phase 5.

Generates Excel workbooks for:
- Stock Release Report   (summary + line items)
- Product Consumption Report (per-product released qty over a period)
"""

from __future__ import annotations

import io

from app.models.stock_release import StockRelease
from app.services.report import (
    _auto_fit_columns,
    _make_workbook,
    _style_data_rows,
    _style_header_row,
)


class StockReleaseReportService:
    """Generates Excel reports for stock release data."""

    def generate_stock_release_report(
        self, releases: list[StockRelease]
    ) -> bytes:
        """Build an Excel stock release report (summary + line items)."""
        wb = _make_workbook()

        # -- Sheet 1: Release Summary -----------------------------------------
        ws_summary = wb.active
        ws_summary.title = "Stock Releases"

        summary_headers = [
            "Release No.",
            "Purpose",
            "Status",
            "Release Date",
            "Reference Doc",
            "Total Qty",
            "Total Cost",
            "Items Count",
            "Created By",
            "Submitted By",
            "Submitted At",
            "Approved By",
            "Approved At",
            "Notes",
        ]
        ws_summary.append(summary_headers)
        _style_header_row(ws_summary, len(summary_headers))

        for sr in releases:
            created_by = (
                f"{sr.created_by.first_name} {sr.created_by.last_name}"
                if sr.created_by
                else ""
            )
            submitted_by = (
                f"{sr.submitted_by.first_name} {sr.submitted_by.last_name}"
                if sr.submitted_by
                else ""
            )
            approved_by = (
                f"{sr.approved_by.first_name} {sr.approved_by.last_name}"
                if sr.approved_by
                else ""
            )

            ws_summary.append(
                [
                    sr.release_number,
                    sr.purpose,
                    sr.status,
                    sr.release_date.strftime("%Y-%m-%d") if sr.release_date else "",
                    sr.reference_document or "",
                    float(sr.total_quantity),
                    float(sr.total_cost),
                    len(sr.items),
                    created_by,
                    submitted_by,
                    sr.submitted_at.strftime("%Y-%m-%d %H:%M") if sr.submitted_at else "",
                    approved_by,
                    sr.approved_at.strftime("%Y-%m-%d %H:%M") if sr.approved_at else "",
                    sr.notes or "",
                ]
            )

        _style_data_rows(ws_summary, len(releases), len(summary_headers))
        _auto_fit_columns(ws_summary)

        # -- Sheet 2: Line Items -----------------------------------------------
        ws_items = wb.create_sheet(title="Release Items")
        items_headers = [
            "Release No.",
            "Purpose",
            "Status",
            "Release Date",
            "Product SKU",
            "Product Name",
            "Category",
            "UoM",
            "Qty Released",
            "Unit Cost",
            "Line Total",
            "Notes",
        ]
        ws_items.append(items_headers)
        _style_header_row(ws_items, len(items_headers))

        all_item_rows: list[list] = []
        for sr in releases:
            for item in sr.items:
                p = item.product
                all_item_rows.append(
                    [
                        sr.release_number,
                        sr.purpose,
                        sr.status,
                        sr.release_date.strftime("%Y-%m-%d") if sr.release_date else "",
                        p.sku if p else "",
                        p.name if p else "",
                        p.category.name if (p and p.category) else "",
                        p.uom.symbol if (p and p.uom) else "",
                        float(item.quantity_requested),
                        float(item.unit_cost),
                        float(item.line_total),
                        item.notes or "",
                    ]
                )
                ws_items.append(all_item_rows[-1])

        _style_data_rows(ws_items, len(all_item_rows), len(items_headers))
        _auto_fit_columns(ws_items)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def generate_product_consumption_report(
        self, releases: list[StockRelease]
    ) -> bytes:
        """
        Build a product consumption report.

        Aggregates all APPROVED release items and shows per-product
        total released quantity and total cost value over the filter period.
        """
        wb = _make_workbook()

        # -- Sheet 1: Product Consumption Summary ------------------------------
        ws_summary = wb.active
        ws_summary.title = "Product Consumption"

        summary_headers = [
            "Product SKU",
            "Product Name",
            "Category",
            "UoM",
            "Total Qty Released",
            "Total Cost",
            "Avg Cost Per Unit",
            "# Releases",
        ]
        ws_summary.append(summary_headers)
        _style_header_row(ws_summary, len(summary_headers))

        # Aggregate per product
        product_agg: dict[str, dict] = {}
        for sr in releases:
            for item in sr.items:
                p = item.product
                key = str(item.product_id)
                if key not in product_agg:
                    product_agg[key] = {
                        "sku": p.sku if p else key,
                        "name": p.name if p else "",
                        "category": p.category.name if (p and p.category) else "",
                        "uom": p.uom.symbol if (p and p.uom) else "",
                        "total_qty": 0.0,
                        "total_cost": 0.0,
                        "release_count": 0,
                    }
                product_agg[key]["total_qty"] += float(item.quantity_requested)
                product_agg[key]["total_cost"] += float(item.line_total)
                product_agg[key]["release_count"] += 1

        rows = sorted(
            product_agg.values(), key=lambda x: x["total_qty"], reverse=True
        )
        for row in rows:
            total_qty = row["total_qty"]
            total_cost = row["total_cost"]
            avg_cost = round(total_cost / total_qty, 4) if total_qty > 0 else 0.0
            ws_summary.append(
                [
                    row["sku"],
                    row["name"],
                    row["category"],
                    row["uom"],
                    round(total_qty, 4),
                    round(total_cost, 4),
                    avg_cost,
                    row["release_count"],
                ]
            )

        _style_data_rows(ws_summary, len(rows), len(summary_headers))
        _auto_fit_columns(ws_summary)

        # -- Sheet 2: Detailed Release Lines -----------------------------------
        ws_detail = wb.create_sheet(title="Detail")
        detail_headers = [
            "Release No.",
            "Release Date",
            "Purpose",
            "Product SKU",
            "Product Name",
            "Qty Released",
            "Unit Cost",
            "Line Total",
            "Approved By",
            "Approved At",
        ]
        ws_detail.append(detail_headers)
        _style_header_row(ws_detail, len(detail_headers))

        detail_rows: list[list] = []
        for sr in releases:
            approved_by = (
                f"{sr.approved_by.first_name} {sr.approved_by.last_name}"
                if sr.approved_by
                else ""
            )
            for item in sr.items:
                p = item.product
                detail_rows.append(
                    [
                        sr.release_number,
                        sr.release_date.strftime("%Y-%m-%d") if sr.release_date else "",
                        sr.purpose,
                        p.sku if p else "",
                        p.name if p else "",
                        float(item.quantity_requested),
                        float(item.unit_cost),
                        float(item.line_total),
                        approved_by,
                        sr.approved_at.strftime("%Y-%m-%d %H:%M") if sr.approved_at else "",
                    ]
                )
                ws_detail.append(detail_rows[-1])

        _style_data_rows(ws_detail, len(detail_rows), len(detail_headers))
        _auto_fit_columns(ws_detail)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
