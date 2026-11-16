import pytest
import duckdb
from pathlib import Path
from src.ingestion.loader import BusinessDataLoader
from src.ingestion.schema_indexer import SchemaIndexer
from src.engine.sandbox import ExecutionSandbox


@pytest.mark.parametrize(
    "query",
    [
        "SELECT 42 AS answer",
        "```sql\nSELECT 42 AS answer;\n```",
    ],
)
def test_sandbox_executes_plain_and_fenced_sql(query):
    con = duckdb.connect(":memory:")
    try:
        result = ExecutionSandbox(con).execute_sql(query)

        assert result["success"] is True
        assert result["data"].iloc[0]["answer"] == 42
    finally:
        con.close()


def test_sandbox_returns_structured_error_for_invalid_sql():
    con = duckdb.connect(":memory:")
    try:
        result = ExecutionSandbox(con).execute_sql("SELECT FROM")

        assert result["success"] is False
        assert result["data"] is None
        assert result["error"]
        assert "NameError" not in result["error"]
    finally:
        con.close()


def test_loader_and_sandbox_biz101():
    biz_dir = Path("data/train/data/biz_101")
    if not biz_dir.exists():
        pytest.skip("biz_101 data not found")

    loader = BusinessDataLoader(str(biz_dir))
    con = loader.get_connection()
    assert len(loader.tables) > 0

    # Index schema
    indexer = SchemaIndexer(con, loader.tables, loader.readme_content)
    context_str = indexer.to_prompt_context()
    assert "ban_hang" in context_str

    # Test Sandbox SQL
    sandbox = ExecutionSandbox(con)
    res = sandbox.execute_sql("SELECT COUNT(*) as total_rows FROM ban_hang")
    assert res["success"] is True
    assert res["data"].iloc[0]["total_rows"] > 0

    # Test Sandbox Python
    py_code = """
df = con.execute("SELECT COUNT(*) as cnt FROM ban_hang").df()
final_result = int(df.iloc[0]['cnt'])
"""
    res_py = sandbox.execute_python(py_code)
    assert res_py["success"] is True
    assert res_py["result"] > 0

    loader.close()
