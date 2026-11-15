"""Date utilities and solar-lunar calendar resolver conforming to DataMate rules."""
import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict
import pandas as pd


class CalendarHelper:
    """Helper to query solar-lunar calendar and holidays."""

    def __init__(self, calendar_path: Optional[str] = None):
        self.df_cal: Optional[pd.DataFrame] = None
        if calendar_path and Path(calendar_path).exists():
            self.load_calendar(calendar_path)

    def load_calendar(self, calendar_path: str):
        df = pd.read_csv(calendar_path)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        self.df_cal = df

    def get_tet_range(self, year: int) -> Tuple[str, str]:
        """
        Khoảng Tết năm Y:
        Từ ngày dương của 23 tháng Chạp (năm âm Y - 1) đến hết ngày dương của mùng 10 tháng Giêng (năm âm Y).
        Tra trong calendar.csv:
        - 23 tháng Chạp (năm Y - 1): lunar_month == 12 & lunar_day == 23 (xảy ra vào cuối năm dương Y-1 hoặc đầu năm dương Y)
        - mùng 10 tháng Giêng (năm Y): lunar_month == 1 & lunar_day == 10
        """
        if self.df_cal is None:
            # Fallback approximate if calendar not loaded
            return (f"{year}-01-20", f"{year}-02-15")
        
        # Tìm ngày mùng 10 tháng Giêng năm Y
        # Mùng 10 Tết thường rơi vào tháng 1 hoặc tháng 2 năm dương Y
        mung_10 = self.df_cal[
            (self.df_cal["date"].str.startswith(str(year))) &
            (self.df_cal["lunar_month"] == 1) &
            (self.df_cal["lunar_day"] == 10)
        ]
        if mung_10.empty:
            # Có thể rơi vào đầu năm Y+1 hoặc năm Y
            mung_10 = self.df_cal[
                (self.df_cal["lunar_month"] == 1) &
                (self.df_cal["lunar_day"] == 10)
            ]
        
        end_date = mung_10.iloc[0]["date"] if not mung_10.empty else f"{year}-02-15"
        
        # 23 tháng Chạp năm âm Y-1 là ngày trước Tết
        # Tìm ngày 23/12 âm lịch ngay trước ngày mùng 10 đó
        prev_dates = self.df_cal[self.df_cal["date"] < end_date]
        chap_23 = prev_dates[
            (prev_dates["lunar_month"] == 12) &
            (prev_dates["lunar_day"] == 23)
        ]
        start_date = chap_23.iloc[-1]["date"] if not chap_23.empty else f"{year}-01-20"
        
        return (start_date, end_date)


def parse_date(date_str: str) -> datetime.date:
    """Parse string yyyy-mm-dd to datetime.date."""
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()


def get_week_range(as_of_date_str: str, which: str = "this_week") -> Tuple[str, str]:
    """
    Theo Rulebook §2:
    - Tuần bắt đầu thứ Hai (Monday = 0).
    - 'tuần này': từ thứ Hai của tuần chứa hôm nay đến hết hôm nay.
    - 'tuần trước', 'tuần rồi': CẢ tuần liền trước, từ thứ Hai đến Chủ nhật.
    """
    today = parse_date(as_of_date_str)
    weekday = today.weekday() # Monday=0, Sunday=6
    monday_this_week = today - datetime.timedelta(days=weekday)
    
    if which == "this_week":
        return (monday_this_week.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    elif which in ["last_week", "previous_week"]:
        monday_last_week = monday_this_week - datetime.timedelta(days=7)
        sunday_last_week = monday_this_week - datetime.timedelta(days=1)
        return (monday_last_week.strftime("%Y-%m-%d"), sunday_last_week.strftime("%Y-%m-%d"))
    else:
        raise ValueError(f"Unknown week type: {which}")


def get_month_range(as_of_date_str: str, which: str = "this_month") -> Tuple[str, str]:
    """
    Theo Rulebook §2:
    - 'Tháng M/Y': cả tháng từ ngày 1 đến hết ngày cuối tháng.
    - 'Tháng này': từ ngày 1 đến hết hôm nay.
    - So với tháng trước: cùng số ngày của tháng trước (từ ngày 1 đến ngày trùng số với hôm nay;
      nếu tháng trước ít ngày hơn thì đến hết tháng trước).
    """
    today = parse_date(as_of_date_str)
    year = today.year
    month = today.month
    day = today.day
    
    if which == "this_month":
        start_date = datetime.date(year, month, 1)
        return (start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    elif which == "this_month_full":
        # Cả tháng này
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        return (f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}")
    elif which == "last_month_same_days":
        # Cùng số ngày của tháng trước
        import calendar
        prev_month = 12 if month == 1 else month - 1
        prev_year = year - 1 if month == 1 else year
        max_days = calendar.monthrange(prev_year, prev_month)[1]
        target_day = min(day, max_days)
        start_date = datetime.date(prev_year, prev_month, 1)
        end_date = datetime.date(prev_year, prev_month, target_day)
        return (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    elif which == "last_month_full":
        # Cả tháng trước
        import calendar
        prev_month = 12 if month == 1 else month - 1
        prev_year = year - 1 if month == 1 else year
        last_day = calendar.monthrange(prev_year, prev_month)[1]
        return (f"{prev_year}-{prev_month:02d}-01", f"{prev_year}-{prev_month:02d}-{last_day:02d}")
    else:
        raise ValueError(f"Unknown month type: {which}")


def get_year_to_date_range(as_of_date_str: str) -> Tuple[str, str]:
    """
    Rulebook §2:
    'Từ đầu năm', 'từ đầu năm tới nay': từ 01/01 năm nay đến hết hôm nay.
    """
    today = parse_date(as_of_date_str)
    return (f"{today.year}-01-01", as_of_date_str)


def get_n_days_recent_range(as_of_date_str: str, n: int) -> Tuple[str, str]:
    """
    Rulebook §2:
    'N ngày gần nhất': N ngày liền nhau kể cả hôm nay, ngày cuối là hôm nay.
    """
    today = parse_date(as_of_date_str)
    start_date = today - datetime.timedelta(days=n - 1)
    return (start_date.strftime("%Y-%m-%d"), as_of_date_str)
