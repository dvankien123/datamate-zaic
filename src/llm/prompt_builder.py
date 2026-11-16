"""Constructs rich, concise context prompts for the Code-LLM."""
import re
from typing import Optional, Tuple
from src.common.date_utils import (
    get_week_range,
    get_month_range,
    get_year_to_date_range,
    get_n_days_recent_range,
    CalendarHelper
)


def detect_type_hint(question: str) -> str:
    """Detect expected answer type hint from Vietnamese question keywords."""
    q = question.lower()
    
    # 1. Percent
    if any(k in q for k in ["tỉ lệ", "tỷ lệ", "bao nhiêu %", "mấy %", "phần trăm", "tăng trưởng"]):
        return "percent"
    
    # 2. Boolean
    if any(k in q for k in ["có phải không", "có không", "đúng không", "phải không", "hay không", "tăng liên tục không"]):
        return "boolean"
        
    # 3. Date
    if any(k in q for k in ["ngày nào", "thời gian nào", "hôm nào", "tháng nào trong năm"]):
        return "date"
        
    # 4. Table
    if any(k in q for k in ["cho xem bảng", "mỗi người còn nợ bao nhiu", "danh sách kèm", "và số tiền", "chi tiết từng"]):
        return "table"
        
    # 5. List
    if any(k in q for k in ["top 3", "top 5", "3 tháng", "5 khách", "những sản phẩm nào", "các mặt hàng", "danh sách"]):
        return "list"
        
    # 6. String
    if any(k in q for k in ["hàng nào", "sản phẩm nào", "ai", "khách nào", "nhân viên nào", "món gì", "thuốc nào", "gì"]):
        return "string"
        
    # 7. Default to number (majority 62.8%)
    return "number"


def extract_time_context(question: str, as_of_date: str, cal_helper: Optional[CalendarHelper] = None) -> str:
    """Analyze question for relative time expressions and compute exact date boundaries."""
    q = question.lower()
    hints = [f"- Hôm nay (as_of_date): `{as_of_date}`"]
    
    # Tuần
    if "tuần này" in q:
        start, end = get_week_range(as_of_date, "this_week")
        hints.append(f"- 'tuần này': từ ngày `{start}` đến hết ngày `{end}`")
    elif any(k in q for k in ["tuần trước", "tuần rồi"]):
        start, end = get_week_range(as_of_date, "last_week")
        hints.append(f"- 'tuần trước/tuần rồi': CẢ tuần liền trước từ ngày `{start}` đến hết ngày `{end}` (thứ Hai đến Chủ nhật)")
        
    # Tháng này
    if "tháng này" in q:
        start, end = get_month_range(as_of_date, "this_month")
        hints.append(f"- 'tháng này': từ ngày `{start}` đến hết ngày `{end}` (tính đến hôm nay)")
        if any(k in q for k in ["so với", "thay đổi", "tăng trưởng"]):
            p_start, p_end = get_month_range(as_of_date, "last_month_same_days")
            hints.append(f"- 'cùng số ngày tháng trước để so sánh': từ ngày `{p_start}` đến `{p_end}`")
            
    # Từ đầu năm
    if any(k in q for k in ["từ đầu năm", "từ đầu năm tới nay", "năm nay"]):
        start, end = get_year_to_date_range(as_of_date)
        hints.append(f"- 'từ đầu năm tới nay': từ `{start}` đến `{end}`")
        
    # N ngày gần nhất
    m_days = re.search(r"(\d+)\s*ngày gần nhất", q)
    if m_days:
        n = int(m_days.group(1))
        start, end = get_n_days_recent_range(as_of_date, n)
        hints.append(f"- '{n} ngày gần nhất': từ ngày `{start}` đến hết ngày `{end}`")
        
    # Tết
    if "tết" in q and cal_helper:
        year = int(as_of_date.split("-")[0])
        start_tet, end_tet = cal_helper.get_tet_range(year)
        hints.append(f"- Dịp Tết năm {year}: từ 23 tháng Chạp (`{start_tet}`) đến mùng 10 tháng Giêng (`{end_tet}`)")
        
    return "\n".join(hints)


class PromptBuilder:
    """Constructs prompts for SQL generation."""

    def __init__(self, calendar_helper: Optional[CalendarHelper] = None):
        self.cal_helper = calendar_helper

    def build_sql_prompt(self, question: str, as_of_date: str, schema_context: str) -> str:
        type_hint = detect_type_hint(question)
        time_context = extract_time_context(question, as_of_date, self.cal_helper)

        prompt = f"""Bạn là trợ lý phân tích dữ liệu DuckDB SQL chuyên nghiệp cho doanh nghiệp Việt Nam.
Hãy viết MỘT câu truy vấn DuckDB SQL DUY NHẤT để trả lời câu hỏi dưới đây.

### QUY TẮC NGHIỆP VỤ BẮT BUỘC:
1. **Doanh thu**: Tổng thành tiền sau chiết khấu dòng (không trừ voucher đơn, không cộng VAT/phí ship). BỎ các đơn có trạng thái Huỷ hoặc Trả hàng (kể cả trả 1 phần).
2. **Bán chạy / Hot nhất**: Xếp hạng theo SỐ LƯỢNG (quy về đơn vị cơ bản), BỎ đơn huỷ, trả.
3. **Mốc thời gian**: Dữ liệu phát sinh sau ngày mốc as_of_date coi như chưa xảy ra (loại bỏ).
4. **Cú pháp DuckDB SQL**:
   - Tên bảng và tên cột có dấu hoặc số hoặc khoảng trắng: luôn bọc trong dấu ngoặc kép `"tên_cột"`.
   - Tìm kiếm chuỗi tiếng Việt: dùng `ILIKE '%...%'`.
   - Tránh chia cho 0: dùng `NULLIF(..., 0)`. Tránh NULL: dùng `COALESCE(..., 0)`.
5. **Dữ liệu đã chuẩn hóa**: Khi cộng tiền, tính số lượng hoặc lọc ngày, ưu tiên cột có hậu tố `_normalized` nếu schema có cột đó. Cột số lượng đã chuẩn hóa vẫn theo đơn vị của dòng; nếu cần đơn vị cơ bản, dùng cột số lượng quy đổi hoặc bảng quy đổi trong schema/README, không coi `1 thùng` là `1` đơn vị cơ bản.
6. **Kiểu đáp án dự kiến**: `{type_hint}`.
{time_context}

{schema_context}

### CÂU HỎI:
"{question}"

### QUY TẮC ĐẦU RA BẮT BUỘC:
- CHỈ trả về DUY NHẤT một khối ```sql ... ```.
- TUYỆT ĐỐI KHÔNG viết bất kỳ lời giải thích, chào hỏi, suy nghĩ hay ghi chú nào bên ngoài khối ```sql ... ```.
"""
        return prompt
