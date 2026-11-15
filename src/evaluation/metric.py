"""Evaluation metric (Penalized Accuracy) conforming to DataMate official rules."""
from typing import Dict, Any, List, Tuple, Optional
from src.common.normalizer import (
    normalize_string,
    normalize_number,
    normalize_percent,
    normalize_date,
    normalize_boolean,
    normalize_list,
    normalize_table,
)


def match_number(pred: Any, ref: Any) -> bool:
    try:
        p = normalize_number(pred)
        r = normalize_number(ref)
        return p == r
    except Exception:
        return False


def match_percent(pred: Any, ref: Any) -> bool:
    try:
        p = normalize_percent(pred)
        r = normalize_percent(ref)
        return p == r
    except Exception:
        return False


def match_string(pred: Any, ref: Any, alias: Optional[List[str]] = None) -> bool:
    """
    Chuỗi chuẩn hóa: so sánh exact match với ref và danh sách alias (mã sản phẩm, tên khác).
    """
    p_norm = normalize_string(pred)
    accepted_forms = [normalize_string(ref)]
    if alias:
        for a in alias:
            accepted_forms.append(normalize_string(a))
    return p_norm in accepted_forms


def match_date(pred: Any, ref: Any) -> bool:
    return normalize_date(pred) == normalize_date(ref)


def match_boolean(pred: Any, ref: Any) -> bool:
    return normalize_boolean(pred) == normalize_boolean(ref)


def match_list(pred: Any, ref: Any) -> bool:
    if not isinstance(pred, (list, tuple)) or not isinstance(ref, (list, tuple)):
        return False
    if len(pred) != len(ref):
        return False
    for p, r in zip(pred, ref):
        if isinstance(r, (int, float)):
            if not match_number(p, r):
                return False
        else:
            if normalize_string(p) != normalize_string(r):
                return False
    return True


def match_table(pred: Any, ref: Any) -> bool:
    if not isinstance(pred, dict) or not isinstance(ref, dict):
        return False
    
    pred_t = normalize_table(pred)
    ref_t = normalize_table(ref)
    
    # Check rows as a set (converted to tuples of normalized values)
    pred_rows = pred_t.get("rows", [])
    ref_rows = ref_t.get("rows", [])
    
    if len(pred_rows) != len(ref_rows):
        return False
    
    def row_to_tuple(row):
        return tuple(row)
    
    try:
        return set(map(row_to_tuple, pred_rows)) == set(map(row_to_tuple, ref_rows))
    except Exception:
        return False


def score_single_answer(pred_dict: Optional[Dict[str, Any]], ref_dict: Dict[str, Any]) -> Tuple[int, str]:
    """
    Chấm điểm cho một câu hỏi:
    Trả về (score, status):
    score: +1 (correct), 0 (abstain), -1 (wrong)
    status: 'correct' | 'abstain' | 'wrong'
    """
    ref_type = ref_dict.get("type")
    ref_answer = ref_dict.get("answer")
    ref_alias = ref_dict.get("alias", [])
    
    # Missing answer hoặc type là abstain -> abstain (0 điểm)
    if not pred_dict or pred_dict.get("type") == "abstain":
        return 0, "abstain"
    
    pred_type = pred_dict.get("type")
    pred_answer = pred_dict.get("answer")
    
    # Câu hỏi unanswerable
    if ref_type == "unanswerable":
        if pred_type == "unanswerable":
            return 1, "correct"
        else:
            # Any answer given to an unanswerable question counts as wrong (-1 điểm)
            return -1, "wrong"
    
    # Nếu ref không phải unanswerable mà pred trả về unanswerable -> wrong
    if pred_type == "unanswerable":
        return -1, "wrong"
    
    # Sai type -> wrong
    if pred_type != ref_type:
        return -1, "wrong"
    
    # So khớp giá trị theo từng type
    is_correct = False
    if ref_type == "number":
        is_correct = match_number(pred_answer, ref_answer)
    elif ref_type == "percent":
        is_correct = match_percent(pred_answer, ref_answer)
    elif ref_type == "string":
        is_correct = match_string(pred_answer, ref_answer, ref_alias)
    elif ref_type == "date":
        is_correct = match_date(pred_answer, ref_answer)
    elif ref_type == "boolean":
        is_correct = match_boolean(pred_answer, ref_answer)
    elif ref_type == "list":
        is_correct = match_list(pred_answer, ref_answer)
    elif ref_type == "table":
        is_correct = match_table(pred_answer, ref_answer)
    
    if is_correct:
        return 1, "correct"
    return -1, "wrong"


def calculate_penalized_accuracy(predictions: List[Dict[str, Any]], references: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Tính chỉ số Penalized Accuracy (PA):
    PA = (1 / N) * sum(s_i)
    """
    ref_map = {r["id"]: r for r in references}
    pred_map = {p["id"]: p for p in predictions}
    
    total_questions = len(references)
    if total_questions == 0:
        return {"penalized_accuracy": 0.0, "total": 0, "correct": 0, "wrong": 0, "abstain": 0}
    
    total_score = 0
    counts = {"correct": 0, "wrong": 0, "abstain": 0}
    type_breakdown = {}
    
    for qid, ref in ref_map.items():
        ref_type = ref.get("type", "unknown")
        if ref_type not in type_breakdown:
            type_breakdown[ref_type] = {"total": 0, "correct": 0, "wrong": 0, "abstain": 0}
        type_breakdown[ref_type]["total"] += 1
        
        pred = pred_map.get(qid)
        score, status = score_single_answer(pred, ref)
        
        total_score += score
        counts[status] += 1
        type_breakdown[ref_type][status] += 1
    
    pa = total_score / total_questions
    
    return {
        "penalized_accuracy": round(pa, 4),
        "total": total_questions,
        "correct": counts["correct"],
        "wrong": counts["wrong"],
        "abstain": counts["abstain"],
        "score_sum": total_score,
        "type_breakdown": type_breakdown
    }
