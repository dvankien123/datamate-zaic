"""Normalization utilities conforming to DataMate Evaluation rules."""
import unicodedata
import re
from typing import Any, Union, List, Dict


def normalize_string(text: Any) -> str:
    """
    Chuẩn hóa chuỗi theo đúng quy định của ban tổ chức (EVALUATION rule):
    (1) Unicode NFC
    (2) lowercase
    (3) Ký tự không phải chữ cái, chữ số hoặc khoảng trắng được thay bằng dấu cách
    (4) Bỏ khoảng trắng đầu/cuối và thu gọn các khoảng trắng liền nhau thành 1 dấu cách đơn
    * Lưu ý: Không bỏ dấu tiếng Việt (diacritics are not removed).
    """
    if text is None:
        return ""
    text = str(text)
    
    # (1) Unicode NFC
    text = unicodedata.normalize("NFC", text)
    
    # (2) Lowercase
    text = text.lower()
    
    # (3) Replace any char not a letter, digit or whitespace with a space
    # \w in Python regex with re.UNICODE matches Unicode letters and digits and underscore.
    # Note: Underscore is considered non-letter/digit, so replace underscore with space too.
    # In regex: replace anything not (\d or letter or \s)
    text = re.sub(r"[^\w\s]|_", " ", text)
    
    # (4) Strip leading/trailing and collapse multiple whitespace runs
    text = re.sub(r"\s+", " ", text).strip()
    
    return text


def normalize_number(val: Any) -> Union[int, float]:
    """
    Chuẩn hóa số (VND amounts, counts, quantities):
    Số nguyên hoặc số thực làm tròn 2 chữ số thập phân.
    """
    if val is None or val == "":
        return 0
    try:
        f = float(val)
        if f.is_integer():
            return int(f)
        return round(f, 2)
    except (ValueError, TypeError):
        return 0


def normalize_percent(val: Any) -> float:
    """
    Chuẩn hóa tỷ lệ phần trăm: làm tròn 2 chữ số thập phân, giữ đúng dấu (+/-).
    """
    if val is None or val == "":
        return 0.0
    try:
        f = float(val)
        return round(f, 2)
    except (ValueError, TypeError):
        return 0.0


def normalize_date(val: Any) -> str:
    """
    Chuẩn hóa định dạng ngày: ISO 'yyyy-mm-dd' hoặc tháng 'yyyy-mm'.
    """
    if not val:
        return ""
    s = str(val).strip()
    # Match yyyy-mm-dd or yyyy-mm
    m_full = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m_full:
        y, m, d = m_full.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    
    m_month = re.search(r"(\d{4})[/-](\d{1,2})", s)
    if m_month:
        y, m = m_month.groups()
        return f"{y}-{int(m):02d}"
    
    return s


def normalize_boolean(val: Any) -> bool:
    """
    Chuẩn hóa giá trị boolean: true / false.
    """
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ["true", "1", "yes", "đúng", "t"]


def normalize_list(val: Any) -> List[Any]:
    """
    Chuẩn hóa danh sách thứ tự:
    Nếu phần tử là chuỗi thì normalize_string, nếu là số thì normalize_number.
    """
    if not isinstance(val, (list, tuple)):
        return [val]
    res = []
    for item in val:
        if isinstance(item, (int, float)):
            res.append(normalize_number(item))
        else:
            res.append(normalize_string(item))
    return res


def normalize_table(val: Any) -> Dict[str, Any]:
    """
    Chuẩn hóa bảng: {"columns": [...], "rows": [[...], ...]}
    - Columns được chuẩn hóa theo normalize_string.
    - Từng ô trong row được chuẩn hóa theo số hoặc chuỗi.
    """
    if not isinstance(val, dict):
        return {"columns": [], "rows": []}
    cols = [normalize_string(c) for c in val.get("columns", [])]
    rows = []
    for row in val.get("rows", []):
        norm_row = []
        for cell in row:
            if isinstance(cell, (int, float)):
                norm_row.append(normalize_number(cell))
            else:
                norm_row.append(normalize_string(cell))
        rows.append(norm_row)
    return {"columns": cols, "rows": rows}
