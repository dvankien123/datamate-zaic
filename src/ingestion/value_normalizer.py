"""Conservative normalization of date, money, and quantity fields."""
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any, Dict, Optional, Tuple

import pandas as pd


def fold_diacritics(value: Any) -> str:
    """Return a lowercase diacritic-folded form for matching Vietnamese column names."""
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(char for char in text if not unicodedata.combining(char)).replace("đ", "d")


def _column_kind(column_name: Any) -> Optional[str]:
    name = fold_diacritics(column_name).replace(" ", "_")
    if name.endswith("_normalized"):
        return None
    tokens = set(re.split(r"[^a-z0-9]+", name))

    quantity_compounds = {
        "so_ngay", "so_khach", "so_don", "so_phieu", "so_lan", "so_nguoi",
        "ton_kho", "ton_cuoi", "ton_dau", "so_luong", "so_luong_le",
    }
    quantity_markers = {"quantity", "qty", "sl", "sluong", "soluong", "count"}
    if any(compound in name for compound in quantity_compounds) or tokens.intersection(quantity_markers):
        return "quantity"

    if (
        tokens.intersection({"ngay", "date", "time", "gio", "timestamp"})
        or "created_at" in name
        or "updated_at" in name
        or "thoi_gian" in name
        or "gio_ban" in name
    ):
        is_timestamp = (
            bool(tokens.intersection({"gio", "time", "timestamp"}))
            or "thoi_gian" in name
            or "created_at" in name
            or "updated_at" in name
        )
        return "datetime" if is_timestamp else "date"

    currency_compounds = {
        "thanh_tien", "tong_tien", "don_gia", "gia_san_pham", "gia_ban",
        "gia_von", "tien_von", "so_tien", "doanh_thu", "con_no", "tien_mat",
        "hoa_hong", "gia_nhap", "tong_tien_hang", "khach_tra", "tong_thu",
        "so_thu", "tien_thu", "tong_chi", "so_chi", "tien_chi",
    }
    currency_tokens = {"tien", "gia", "amount", "price", "revenue", "cost", "phi", "debt", "no"}
    if any(compound in name for compound in currency_compounds) or tokens.intersection(currency_tokens):
        return "amount"
    return None


def drop_repeated_header_rows(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Remove page-break header rows repeated inside spreadsheet/CSV data."""
    if df.empty or len(df.columns) < 2:
        return df, 0

    def comparable(value: Any) -> str:
        text = fold_diacritics(value)
        return re.sub(r"[^a-z0-9]+", "_", text).strip("_")

    expected = [comparable(column) for column in df.columns]
    active_columns = [index for index, value in enumerate(expected) if value]
    if len(active_columns) < 2:
        return df, 0

    threshold = max(2, ceil(len(active_columns) * 0.75))
    matches = pd.DataFrame(
        {
            index: df.iloc[:, index].map(comparable).eq(expected[index])
            for index in active_columns
        },
        index=df.index,
    )
    repeated = matches.sum(axis=1) >= threshold
    dropped = int(repeated.sum())
    if not dropped:
        return df, 0
    return df.loc[~repeated].reset_index(drop=True), dropped


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _is_source_value(value: Any) -> bool:
    if _is_missing(value):
        return False
    return str(value).strip().lower() not in {"", "nan", "none", "null", "nat", "-", "—"}


def _parse_numeric(value: Any, kind: str) -> Optional[Decimal]:
    if _is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    if not text or text in {"nan", "none", "null", "-", "—"}:
        return None
    text = text.replace("\u00a0", "").replace(" ", "")

    negative_by_parentheses = text.startswith("(") and text.endswith(")")
    if negative_by_parentheses:
        text = text[1:-1]

    multiplier = Decimal("1")
    if kind == "amount":
        suffix = re.search(r"(?i)(tr|k|m)$", text)
        if suffix:
            multiplier = Decimal("1000000") if suffix.group(1).lower() in {"tr", "m"} else Decimal("1000")
            text = text[:suffix.start()]
        text = re.sub(r"(?i)(?:vnd|vnđ|đồng|đ|₫)$", "", text).strip()

    # Quantities may carry a unit (for example, "1 ly"). Keep only the numeric
    # amount here; the original unit column remains available to the query.
    number_match = re.match(r"^[+-]?(?:\d[\d.,]*|[.,]\d+)", text)
    if not number_match:
        return None
    number_text = number_match.group(0)
    tail = text[number_match.end():]
    if kind == "amount" and tail:
        return None
    if kind == "quantity" and tail and not re.fullmatch(r"[\w\-./]+", tail, flags=re.UNICODE):
        return None

    normalized = _normalize_separators(number_text)
    if normalized is None:
        return None
    try:
        result = Decimal(normalized) * multiplier
    except InvalidOperation:
        return None
    if not result.is_finite():
        return None
    return -result if negative_by_parentheses else result


def _normalize_separators(value: str) -> Optional[str]:
    """Normalize common Vietnamese and international thousands/decimal marks."""
    comma = value.rfind(",")
    dot = value.rfind(".")

    if comma >= 0 and dot >= 0:
        decimal_mark = "." if dot > comma else ","
        grouping_mark = "," if decimal_mark == "." else "."
        value = value.replace(grouping_mark, "")
        if decimal_mark == ",":
            value = value.replace(",", ".")
        return value

    mark = "," if comma >= 0 else "." if dot >= 0 else None
    if mark is None:
        return value

    pieces = value.split(mark)
    if len(pieces) > 2:
        if all(len(part) == 3 for part in pieces[1:]):
            return "".join(pieces)
        return None

    left, right = pieces
    # A single three-digit tail is treated as a thousands group in these
    # Vietnamese exports (e.g. 31,000 or 50.000); other tails are decimals.
    if len(right) == 3 and left.lstrip("+-").isdigit():
        return left + right
    return left + "." + right


def _parse_datetime_series(series: pd.Series, kind: str) -> pd.Series:
    values = []
    for value in series:
        if _is_missing(value):
            values.append(None)
            continue
        if not _is_source_value(value):
            values.append(None)
            continue
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, datetime.min.time())
        else:
            text = str(value).strip()
            if not text or text.isdigit():
                parsed = None
            else:
                iso_order = bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", text))
                parsed_value = pd.to_datetime(
                    text,
                    errors="coerce",
                    dayfirst=not iso_order,
                    format="mixed",
                )
                parsed = None if pd.isna(parsed_value) else parsed_value.to_pydatetime()

        if parsed is None:
            values.append(None)
        elif kind == "date":
            values.append(parsed.date())
        else:
            values.append(parsed)
    return pd.Series(values, index=series.index, dtype=object)


def normalize_dataframe_for_duckdb(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Add typed companion columns while leaving every source column untouched."""
    result = df.copy()
    report: Dict[str, Dict[str, Any]] = {}

    for source_column in df.columns:
        kind = _column_kind(source_column)
        if kind is None:
            continue

        normalized_column = f"{source_column}_normalized"
        while normalized_column in result.columns:
            normalized_column += "_parsed"

        source = df[source_column]
        if kind in {"date", "datetime"}:
            parsed = _parse_datetime_series(source, kind)
        else:
            parsed = pd.Series(
                [_parse_numeric(value, kind) for value in source],
                index=source.index,
                dtype=object,
            )

        nonempty = source.map(_is_source_value)
        parsed_count = int(parsed.notna().sum())
        if parsed_count == 0:
            report[str(source_column)] = {
                "normalized_column": None,
                "kind": kind,
                "parse_failures": int(nonempty.sum()),
            }
            continue

        result[normalized_column] = parsed
        report[str(source_column)] = {
            "normalized_column": normalized_column,
            "kind": kind,
            "parse_failures": int((nonempty & parsed.isna()).sum()),
        }

    return result, report
