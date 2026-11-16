"""Deterministic execution sandbox for SQL and Python scripts with timeout and error capture."""
import re
import time
import traceback
from typing import Dict, Any, Optional, Tuple
import duckdb
import pandas as pd


_SQL_FENCE_RE = re.compile(
    r"```(?:sql)?[ \t]*(?:\r?\n|[ \t]+)([\s\S]*?)```",
    re.IGNORECASE,
)
_SQL_START_RE = re.compile(
    r"^\s*(?:(?:--[^\r\n]*|/\*[\s\S]*?\*/)\s*)*(?:SELECT|WITH)\b",
    re.IGNORECASE,
)


class ExecutionSandbox:
    """Safely executes DuckDB SQL and Python data scripts against a business connection."""

    def __init__(self, con: duckdb.DuckDBPyConnection, timeout_seconds: int = 10):
        self.con = con
        self.timeout = timeout_seconds

    def execute_sql(self, sql_query: str) -> Dict[str, Any]:
        """Execute a DuckDB SQL query and return rows/dataframe."""
        t0 = time.time()
        clean_sql, extraction_error = self._extract_sql(sql_query)
        if extraction_error:
            return {
                "success": False,
                "data": None,
                "error": f"SQLExtractionError: {extraction_error}",
                "traceback": None,
                "elapsed_time": time.time() - t0,
                "query": clean_sql,
            }

        try:
            rel = self.con.execute(clean_sql)
            df = rel.df()
            elapsed = time.time() - t0
            return {
                "success": True,
                "data": df,
                "error": None,
                "elapsed_time": elapsed,
                "query": clean_sql
            }
        except Exception as e:
            elapsed = time.time() - t0
            return {
                "success": False,
                "data": None,
                "error": f"{type(e).__name__}: {str(e)}",
                "traceback": traceback.format_exc(),
                "elapsed_time": elapsed,
                "query": clean_sql
            }

    @staticmethod
    def _extract_sql(sql_response: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract exactly one SELECT/WITH query from an LLM response."""
        raw = str(sql_response or "").strip()
        if not raw:
            return None, "LLM response is empty."

        # Remove complete reasoning blocks before looking for a query.
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()

        if "```" in raw:
            blocks = [block.strip() for block in _SQL_FENCE_RE.findall(raw)]
            candidates = [block for block in blocks if _SQL_START_RE.match(block)]
            if len(candidates) != 1:
                if not candidates:
                    return None, "No fenced SELECT/WITH query found."
                return None, "Multiple fenced SELECT/WITH queries found; expected one."
            clean_sql = candidates[0]
        else:
            clean_sql = raw
            if not _SQL_START_RE.match(clean_sql):
                return None, "Response must contain one SELECT/WITH query."

        clean_sql = re.sub(r";\s*$", "", clean_sql).strip().rstrip("`").strip()
        if not clean_sql:
            return None, "Extracted SQL is empty."
        return clean_sql, None

    def execute_python(self, py_code: str) -> Dict[str, Any]:
        """
        Execute python script that calculates and sets `final_result`.
        Script has access to `con` (duckdb) and `pd` (pandas).
        """
        t0 = time.time()
        clean_py = py_code.strip()
        if clean_py.startswith("```python"):
            clean_py = clean_py[9:]
        elif clean_py.startswith("```"):
            clean_py = clean_py[3:]
        if clean_py.endswith("```"):
            clean_py = clean_py[:-3]
        clean_py = clean_py.strip()

        # Local scope environment
        local_env = {
            "con": self.con,
            "pd": pd,
            "final_result": None
        }

        try:
            exec(clean_py, {}, local_env)
            res = local_env.get("final_result")
            elapsed = time.time() - t0
            return {
                "success": True,
                "result": res,
                "error": None,
                "elapsed_time": elapsed
            }
        except Exception as e:
            elapsed = time.time() - t0
            return {
                "success": False,
                "result": None,
                "error": f"{type(e).__name__}: {str(e)}",
                "traceback": traceback.format_exc(),
                "elapsed_time": elapsed
            }
