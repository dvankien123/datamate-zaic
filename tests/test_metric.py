import pytest
from src.evaluation.metric import score_single_answer, calculate_penalized_accuracy


def test_score_number():
    ref = {"id": "q1", "type": "number", "answer": 48250000}
    
    # Đúng
    assert score_single_answer({"type": "number", "answer": 48250000}, ref)[0] == 1
    assert score_single_answer({"type": "number", "answer": "48250000.0"}, ref)[0] == 1
    
    # Sai
    assert score_single_answer({"type": "number", "answer": 48250001}, ref)[0] == -1
    
    # Abstain
    assert score_single_answer({"type": "abstain"}, ref)[0] == 0
    assert score_single_answer(None, ref)[0] == 0


def test_score_string_with_alias():
    ref = {
        "id": "q2",
        "type": "string",
        "answer": "Xi măng Hà Tiên PCB40 bao 50kg",
        "alias": ["SP0001", "xi mang ha tien"]
    }
    
    # Đúng theo tên gốc
    assert score_single_answer({"type": "string", "answer": "Xi măng Hà Tiên PCB40 bao 50kg"}, ref)[0] == 1
    # Đúng theo alias mã
    assert score_single_answer({"type": "string", "answer": "sp0001"}, ref)[0] == 1
    # Sai
    assert score_single_answer({"type": "string", "answer": "Xi măng Nghi Sơn"}, ref)[0] == -1


def test_score_unanswerable():
    ref = {"id": "q3", "type": "unanswerable", "answer": None}
    
    # Đoán đúng unanswerable
    assert score_single_answer({"type": "unanswerable"}, ref)[0] == 1
    # Cố đoán một kết quả khác -> bị phạt -1
    assert score_single_answer({"type": "number", "answer": 0}, ref)[0] == -1
    # Abstain -> 0 điểm
    assert score_single_answer({"type": "abstain"}, ref)[0] == 0


def test_penalized_accuracy_calc():
    refs = [
        {"id": "q1", "type": "number", "answer": 100},
        {"id": "q2", "type": "number", "answer": 200},
        {"id": "q3", "type": "number", "answer": 300},
        {"id": "q4", "type": "unanswerable", "answer": None},
    ]
    preds = [
        {"id": "q1", "type": "number", "answer": 100}, # +1 (đúng)
        {"id": "q2", "type": "number", "answer": 999}, # -1 (sai)
        {"id": "q3", "type": "abstain"},               # 0 (abstain)
        {"id": "q4", "type": "unanswerable"},          # +1 (đúng)
    ]
    
    res = calculate_penalized_accuracy(preds, refs)
    # Tổng điểm: 1 - 1 + 0 + 1 = 1. PA = 1 / 4 = 0.25
    assert res["penalized_accuracy"] == 0.25
    assert res["correct"] == 2
    assert res["wrong"] == 1
    assert res["abstain"] == 1
