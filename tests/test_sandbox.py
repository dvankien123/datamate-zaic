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
        "<think>reasoning</think>\n```sql\nSELECT 42 AS answer;\n```",
        "Query:\n```sql\nSELECT 42 AS answer;\n```",
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


def test_sandbox_rejects_non_sql_fence_with_clear_error():
    con = duckdb.connect(":memory:")
    try:
        result = ExecutionSandbox(con).execute_sql("```python\nprint('not SQL')\n```")

        assert result["success"] is False
        assert result["query"] is None
        assert result["error"].startswith("SQLExtractionError:")
    finally:
        con.close()


def test_sandbox_rejects_multiple_sql_blocks_as_ambiguous():
    con = duckdb.connect(":memory:")
    try:
        result = ExecutionSandbox(con).execute_sql(
            "```sql\nSELECT 1\n```\n```sql\nSELECT 2\n```"
        )

        assert result["success"] is False
        assert result["error"].startswith("SQLExtractionError:")
        assert "Multiple" in result["error"]
    finally:
        con.close()


def test_schema_indexer_uses_normalized_date_range():
    con = duckdb.connect(":memory:")
    try:
        con.execute('CREATE TABLE sales ("ngày" VARCHAR, "ngày_normalized" DATE)')
        con.execute("INSERT INTO sales VALUES ('01/11/2025', DATE '2025-11-01'), ('02/11/2025', DATE '2025-11-02')")
        indexer = SchemaIndexer(
            con,
            {
                "sales": {
                    "row_count": 2,
                    "source_file": "sales.xlsx",
                    "normalizations": {
                        "ngày": {
                            "normalized_column": "ngày_normalized",
                            "kind": "date",
                            "parse_failures": 0,
                        }
                    },
                }
            },
        )

        assert indexer.profile["sales"]["date_range"] == {
            "col": "ngày_normalized",
            "min": "2025-11-01",
            "max": "2025-11-02",
        }
        assert "đã chuẩn hóa từ `ngày`" in indexer.to_prompt_context()
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
