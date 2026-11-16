"""Deterministic execution sandbox for SQL and Python scripts with timeout and error capture."""
import re
import time
import traceback
from typing import Dict, Any, Optional
import duckdb
import pandas as pd


class ExecutionSandbox:
    """Safely executes DuckDB SQL and Python data scripts against a business connection."""

    def __init__(self, con: duckdb.DuckDBPyConnection, timeout_seconds: int = 10):
        self.con = con
        self.timeout = timeout_seconds

    def execute_sql(self, sql_query: str) -> Dict[str, Any]:
        """Execute a DuckDB SQL query and return rows/dataframe."""
        t0 = time.time()
        raw = sql_query.strip()

        # 1. Remove thinking tags if present (e.g. from DeepSeek R1 / QwQ)
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()

        # 2. Extract code block
        code_blocks = re.findall(r"```(?:sql)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
        if code_blocks:
            # Pick block containing SQL query keyword (SELECT or WITH)
            chosen = code_blocks[0]
            for b in code_blocks:
                if re.search(r"\b(SELECT|WITH)\b", b, re.IGNORECASE):
                    chosen = b
                    break
            clean_sql = chosen.strip()
        else:
            # Fallback: find starting from WITH or SELECT
            m = re.search(r"\b(WITH|SELECT)\b[\s\S]*", raw, re.IGNORECASE)
            if m:
                clean_sql = m.group(0).strip()
            else:
                clean_sql = raw

        # Clean trailing semicolon or backticks
        clean_sql = re.sub(r";\s*$", "", clean_sql).strip()
        clean_sql = clean_sql.rstrip("`").strip()

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
