from datetime import date
from decimal import Decimal

import pandas as pd

from src.ingestion.value_normalizer import (
    drop_repeated_header_rows,
    normalize_dataframe_for_duckdb,
)


def test_normalize_dataframe_adds_typed_companions_without_changing_raw_values():
    source = pd.DataFrame({
        "Ngày đặt hàng": ["01/11/2025", "2025-11-02", None],
        "Thành tiền": ["24,000.0000", "29k", "50.000đ"],
        "Số lượng sản phẩm": ["1 ly", 1, "1 thùng"],
        "Số lượng quy đổi": [1, 6, 24],
        "Đơn vị tính": ["ly", "lon", "thùng"],
        "Mã đơn hàng": ["ORD1", "ORD2", "ORD3"],
    })

    normalized, report = normalize_dataframe_for_duckdb(source)

    assert normalized["Ngày đặt hàng"].equals(source["Ngày đặt hàng"])
    assert normalized["Thành tiền"].equals(source["Thành tiền"])
    assert "Mã đơn hàng_normalized" not in normalized.columns
    assert normalized["Ngày đặt hàng_normalized"].tolist() == [date(2025, 11, 1), date(2025, 11, 2), None]
    assert normalized["Thành tiền_normalized"].tolist() == [
        Decimal("24000.0000"), Decimal("29000"), Decimal("50000")
    ]
    assert normalized["Số lượng sản phẩm_normalized"].tolist() == [
        Decimal("1"), Decimal("1"), Decimal("1")
    ]
    assert normalized["Số lượng quy đổi_normalized"].tolist() == [
        Decimal("1"), Decimal("6"), Decimal("24")
    ]
    assert normalized["Đơn vị tính"].tolist() == ["ly", "lon", "thùng"]
    assert report["Thành tiền"]["normalized_column"] == "Thành tiền_normalized"
    assert report["Số lượng sản phẩm"]["parse_failures"] == 0


def test_normalization_reports_unparseable_values_without_coercing_to_zero():
    source = pd.DataFrame({"Tổng tiền": ["không rõ"], "Ngày": ["không rõ"]})

    normalized, report = normalize_dataframe_for_duckdb(source)

    assert "Tổng tiền_normalized" not in normalized.columns
    assert "Ngày_normalized" not in normalized.columns
    assert report["Tổng tiền"]["parse_failures"] == 1
    assert report["Ngày"]["parse_failures"] == 1


def test_drop_repeated_header_rows_removes_page_headers_only():
    source = pd.DataFrame(
        {
            "ngày_đặt_hàng": ["01/11/2025", "Ngày đặt hàng"],
            "tổng_tiền": [31000, "Tổng tiền"],
            "tên_sản_phẩm": ["Trà chanh", "Tên sản phẩm"],
        }
    )

    cleaned, removed = drop_repeated_header_rows(source)

    assert removed == 1
    assert cleaned.shape[0] == 1
    assert cleaned.iloc[0]["tên_sản_phẩm"] == "Trà chanh"


def test_quantity_headers_cover_short_labels_and_day_counts():
    source = pd.DataFrame({"Số ngày": [3], "SL nhập": ["1,000"]})

    normalized, _ = normalize_dataframe_for_duckdb(source)

    assert normalized["Số ngày_normalized"].tolist() == [Decimal("3")]
    assert normalized["SL nhập_normalized"].tolist() == [Decimal("1000")]
