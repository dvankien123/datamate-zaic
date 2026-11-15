import pytest
from src.agent.generator import DataMateAgent
from src.evaluation.metric import score_single_answer


def test_agent_unanswerable_pipeline():
    agent = DataMateAgent(
        data_dir="data/train",
        calendar_path="data/train/calendar.csv"
    )
    
    # Test a question asking about cost for a business without cost
    q_unans = {
        "id": "q_test_1",
        "business_id": "biz_101",
        "question": "Lợi nhuận và tiền vốn của shop trong tháng này là bao nhiêu?",
        "as_of_date": "2026-03-04"
    }
    
    res = agent.answer_question(q_unans)
    assert res["id"] == "q_test_1"
    # biz_101 only has ban_hang.csv without cost, so router should detect unanswerable
    assert res["type"] in ["unanswerable", "abstain"]

    agent.close()
