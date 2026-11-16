import pytest
import duckdb
from types import SimpleNamespace
from src.agent.generator import DataMateAgent
from src.evaluation.metric import score_single_answer
from src.ingestion.schema_indexer import SchemaIndexer


class StubLLM:
    def generate(self, prompt, **kwargs):
        return "```sql\nSELECT SUM(amount) AS total FROM sales\n```"


def test_agent_executes_llm_sql_instead_of_abstaining():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE sales (amount INTEGER)")
    con.execute("INSERT INTO sales VALUES (20), (22)")
    indexer = SchemaIndexer(
        con,
        {"sales": {"row_count": 2, "source_file": "sales.csv"}},
    )

    agent = DataMateAgent(data_dir=".", llm_client=StubLLM())
    loader = SimpleNamespace(get_connection=lambda: con)
    agent.get_business_context = lambda business_id: (loader, indexer)

    try:
        result = agent.answer_question(
            {
                "id": "q_sql_smoke",
                "business_id": "biz_test",
                "question": "Doanh thu là bao nhiêu?",
                "as_of_date": "2026-11-16",
            }
        )
    finally:
        con.close()

    assert result == {"id": "q_sql_smoke", "type": "number", "answer": 42}


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
    assert res["type"] == "unanswerable"

    agent.close()
