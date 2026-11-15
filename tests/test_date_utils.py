import pytest
from src.common.date_utils import (
    get_week_range,
    get_month_range,
    get_year_to_date_range,
    get_n_days_recent_range,
    CalendarHelper
)


def test_week_range():
    # 2026-03-04 là thứ Tư (Wednesday)
    # Tuần này: thứ Hai 2026-03-02 đến hết 2026-03-04
    start, end = get_week_range("2026-03-04", which="this_week")
    assert start == "2026-03-02"
    assert end == "2026-03-04"

    # Tuần trước: thứ Hai 2026-02-23 đến Chủ nhật 2026-03-01
    start_prev, end_prev = get_week_range("2026-03-04", which="last_week")
    assert start_prev == "2026-02-23"
    assert end_prev == "2026-03-01"


def test_month_range():
    # 2026-03-15: tháng này từ 2026-03-01 đến 2026-03-15
    start, end = get_month_range("2026-03-15", which="this_month")
    assert start == "2026-03-01"
    assert end == "2026-03-15"

    # Cùng số ngày tháng trước: 2026-02-01 đến 2026-02-15
    start_prev, end_prev = get_month_range("2026-03-15", which="last_month_same_days")
    assert start_prev == "2026-02-01"
    assert end_prev == "2026-02-15"


def test_year_to_date_range():
    start, end = get_year_to_date_range("2026-08-27")
    assert start == "2026-01-01"
    assert end == "2026-08-27"


def test_n_days_recent_range():
    # 7 ngày gần nhất tính đến 2026-08-27
    start, end = get_n_days_recent_range("2026-08-27", 7)
    assert start == "2026-08-21"
    assert end == "2026-08-27"


def test_calendar_tet():
    helper = CalendarHelper("data/train/calendar.csv")
    # Tết 2025: kiểm tra khoảng Tết
    start, end = helper.get_tet_range(2025)
    assert start.startswith("2025") or start.startswith("2024")
    assert end.startswith("2025")
