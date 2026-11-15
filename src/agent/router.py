"""Router to detect unanswerable questions based on schema and date coverage."""
import re
from typing import Tuple, Dict, Any, Optional


class QuestionRouter:
    """Detects unanswerable conditions or special intent before querying."""

    def __init__(self, schema_profile: Dict[str, Any]):
        self.profile = schema_profile

    def check_unanswerable(self, question: str, as_of_date: str) -> Tuple[bool, Optional[str]]:
        """
        Kiểm tra câu hỏi có thuộc trường hợp không thể trả lời theo Rulebook §7:
        1. Kỳ hỏi hoàn toàn ngoài khoảng ngày có dữ liệu.
        2. Dữ liệu không có thông tin cần thiết (ví dụ giá vốn/lợi nhuận, tỉ lệ huỷ...).
        """
        q = question.lower()
        
        # 1. Kiểm tra lợi nhuận / giá vốn
        if any(k in q for k in ["lợi nhuận", "lãi", "giá vốn", "tiền vốn"]):
            has_cost = False
            for tbl, info in self.profile.items():
                col_names = [c["name"].lower() for c in info.get("columns", [])]
                if any(c in col_names for c in ["gia_von", "tien_von", "von", "cost", "loi_nhuan"]):
                    has_cost = True
                    break
            if not has_cost:
                return True, "Dữ liệu không có giá vốn/chi phí nên không tính được lợi nhuận."

        # 2. Kiểm tra tỉ lệ huỷ đơn
        if any(k in q for k in ["huỷ", "tỉ lệ huỷ", "đơn huỷ"]):
            has_status = False
            for tbl, info in self.profile.items():
                col_names = [c["name"].lower() for c in info.get("columns", [])]
                if any(c in col_names for c in ["trang_thai", "status", "huy", "huy_don"]):
                    has_status = True
                    break
            if not has_status:
                return True, "Dữ liệu không có thông tin trạng thái huỷ đơn."

        # 3. Kiểm tra ngày ngoài dải dữ liệu
        # Trích xuất năm/tháng trong câu hỏi nếu có, ví dụ "thang 2/2024", "năm 2023"
        m_year = re.search(r"\b(202[0-9])\b", q)
        if m_year:
            target_year = m_year.group(1)
            # Kiểm tra min/max date của tất cả các bảng
            all_min = []
            all_max = []
            for tbl, info in self.profile.items():
                dr = info.get("date_range")
                if dr and dr.get("min") and dr.get("max"):
                    all_min.append(dr["min"])
                    all_max.append(dr["max"])
            if all_min and all_max:
                global_min = min(all_min)
                global_max = max(all_max)
                # Nếu năm hỏi nhỏ hơn năm bắt đầu dữ liệu hoặc lớn hơn năm kết thúc
                if target_year < global_min[:4] or target_year > global_max[:4]:
                    return True, f"Kỳ hỏi năm {target_year} nằm ngoài khoảng dữ liệu ({global_min} đến {global_max})."

        return False, None
