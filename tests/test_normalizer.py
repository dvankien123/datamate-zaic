import pytest
from src.common.normalizer import (
    normalize_string,
    normalize_number,
    normalize_percent,
    normalize_date,
    normalize_boolean,
    normalize_list,
    normalize_table,
)


def test_normalize_string():
    assert normalize_string("Sting dâu 330ml") == "sting dâu 330ml"
    assert normalize_string("Xi măng Hà Tiên PCB40 bao 50kg!") == "xi măng hà tiên pcb40 bao 50kg"
    assert normalize_string("   cà   phê   sữa   ") == "cà phê sữa"
    assert normalize_string("SP_0042-A/B") == "sp 0042 a b"
    assert normalize_string("") == ""


def test_normalize_number():
    assert normalize_number(48250000) == 48250000
    assert normalize_number("48250000.0") == 48250000
    assert normalize_number(12.345) == 12.35
    assert normalize_number("12.341") == 12.34


def test_normalize_percent():
    assert normalize_percent(-12.456) == -12.46
    assert normalize_percent("2.08") == 2.08
    assert normalize_percent("+5.5") == 5.5


def test_normalize_date():
    assert normalize_date("2026-08-15") == "2026-08-15"
    assert normalize_date("2025/09/01") == "2025-09-01"
    assert normalize_date("2025-09") == "2025-09"
    assert normalize_date("2025/9") == "2025-09"


def test_normalize_boolean():
    assert normalize_boolean(True) is True
    assert normalize_boolean("true") is True
    assert normalize_boolean("false") is False
    assert normalize_boolean(False) is False


def test_normalize_list():
    raw = [" Cà phê sữa ", 12000.0, "Bạc xỉu!"]
    assert normalize_list(raw) == ["cà phê sữa", 12000, "bạc xỉu"]


def test_normalize_table():
    raw = {
        "columns": ["Khách Hàng", "Số Tiền Nợ"],
        "rows": [["Chị Lan", 3200000.0], ["Anh Tú", 1500000]]
    }
    expected = {
        "columns": ["khách hàng", "số tiền nợ"],
        "rows": [["chị lan", 3200000], ["anh tú", 1500000]]
    }
    assert normalize_table(raw) == expected
