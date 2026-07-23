"""
Unit tests for barcode generation and report service -- Phase 2.
"""

from __future__ import annotations

import pytest

from app.services.master_data import _generate_barcode_value, _generate_sku


# ---------------------------------------------------------------------------
# Barcode generation
# ---------------------------------------------------------------------------


def test_barcode_is_12_digits():
    barcode = _generate_barcode_value("ELE-20260101-00001")
    assert len(barcode) == 12
    assert barcode.isdigit()


def test_barcode_different_inputs_produce_different_values():
    b1 = _generate_barcode_value("SKU-001")
    b2 = _generate_barcode_value("SKU-002")
    # Different SKU seeds should produce different barcodes (by hash)
    assert b1 != b2


def test_barcode_png_generation():
    """Test that barcode PNG bytes are generated without error."""
    import io
    import barcode as python_barcode
    from barcode.writer import ImageWriter

    barcode_value = "123456789012"
    code128 = python_barcode.get_barcode_class("code128")
    buf = io.BytesIO()
    code128(barcode_value, writer=ImageWriter()).write(buf)
    data = buf.getvalue()
    assert len(data) > 0
    # PNG magic bytes
    assert data[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# SKU generation
# ---------------------------------------------------------------------------


def test_sku_format():
    sku = _generate_sku("Electronics", 0)
    parts = sku.split("-")
    assert len(parts) == 3
    assert parts[0] == "ELE"
    assert len(parts[1]) == 8   # YYYYMMDD
    assert parts[2] == "00001"  # sequence 0 => 1


def test_sku_sequence_increments():
    sku0 = _generate_sku("Electronics", 0)
    sku1 = _generate_sku("Electronics", 1)
    assert sku0.endswith("00001")
    assert sku1.endswith("00002")


def test_sku_none_category_uses_gen():
    sku = _generate_sku(None, 0)
    assert sku.startswith("GEN-")


def test_sku_short_category_name():
    # "AB" -> prefix is "AB" (only 2 chars)
    sku = _generate_sku("AB", 0)
    assert sku.startswith("AB-")


# ---------------------------------------------------------------------------
# Report service
# ---------------------------------------------------------------------------


def test_product_report_returns_xlsx_bytes():
    from app.services.report import ReportService

    svc = ReportService()
    data = svc.generate_product_report([])
    # XLSX files start with PK (zip)
    assert data[:2] == b"PK"


def test_supplier_report_returns_xlsx_bytes():
    from app.services.report import ReportService

    svc = ReportService()
    data = svc.generate_supplier_report([])
    assert data[:2] == b"PK"


def test_category_report_returns_xlsx_bytes():
    from app.services.report import ReportService

    svc = ReportService()
    data = svc.generate_category_report([])
    assert data[:2] == b"PK"


def test_import_template_returns_xlsx_bytes():
    from app.services.report import ReportService

    svc = ReportService()
    data = svc.generate_product_import_template()
    assert data[:2] == b"PK"
