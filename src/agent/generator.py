"""Core DataMate Agent coordinator orchestrating ingestion, reasoning, sandbox execution and repair."""
import re
from typing import Dict, Any, Optional
from pathlib import Path
from src.ingestion.loader import BusinessDataLoader
from src.ingestion.schema_indexer import SchemaIndexer
from src.engine.sandbox import ExecutionSandbox
from src.common.date_utils import CalendarHelper
from src.llm.client import LocalLLMClient
from src.llm.prompt_builder import PromptBuilder, detect_type_hint
from src.agent.router import QuestionRouter
from src.agent.post_processor import infer_and_format_result


class DataMateAgent:
    """End-to-end agent answering tabular questions over Vietnamese business data."""

    def __init__(
        self,
        data_dir: str,
        calendar_path: Optional[str] = None,
        llm_client: Optional[LocalLLMClient] = None,
        max_repair_attempts: int = 1,
        verbose: bool = False
    ):
        self.data_dir = Path(data_dir)
        self.cal_helper = CalendarHelper(calendar_path) if calendar_path else None
        self.llm = llm_client or LocalLLMClient()
        self.prompt_builder = PromptBuilder(self.cal_helper)
        self.max_repair = max_repair_attempts
        self.verbose = verbose
        
        # Cache loaders and indexers per business_id
        self._cache_loaders: Dict[str, BusinessDataLoader] = {}
        self._cache_indexers: Dict[str, SchemaIndexer] = {}
        # Per-question diagnostics consumed by main.py; never included in answers.
        self.last_execution_trace = []
        self.last_data_diagnostics = {}

    @staticmethod
    def _response_preview(response: Optional[str], max_chars: int = 4000) -> Optional[str]:
        if response is None:
            return None
        preview = re.sub(r"<think>[\s\S]*?</think>", "", str(response), flags=re.IGNORECASE).strip()
        if len(preview) > max_chars:
            return preview[:max_chars] + "…[truncated]"
        return preview

    def _record_sql_attempt(
        self,
        stage: str,
        response: Optional[str],
        exec_result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        result = exec_result or {}
        self.last_execution_trace.append({
            "attempt": len(self.last_execution_trace) + 1,
            "stage": stage,
            "response_preview": self._response_preview(response),
            "clean_sql": result.get("query"),
            "success": bool(result.get("success", False)),
            "error": error or result.get("error"),
        })

    @staticmethod
    def _summarize_data_diagnostics(indexer: SchemaIndexer) -> Dict[str, Any]:
        normalized_column_count = 0
        parse_failures = 0
        dropped_header_rows = 0
        tables_with_warnings = {}

        for table_name, info in indexer.profile.items():
            normalized_column_count += sum(
                column["name"].endswith("_normalized") for column in info.get("columns", [])
            )
            table_failures = {
                source: detail["parse_failures"]
                for source, detail in info.get("normalizations", {}).items()
                if detail.get("parse_failures")
            }
            dropped = int(info.get("dropped_repeated_header_rows", 0))
            parse_failures += sum(table_failures.values())
            dropped_header_rows += dropped
            if table_failures or dropped:
                tables_with_warnings[table_name] = {
                    "parse_failures": table_failures,
                    "dropped_repeated_header_rows": dropped,
                }

        return {
            "table_count": len(indexer.profile),
            "normalized_column_count": normalized_column_count,
            "parse_failures": parse_failures,
            "dropped_repeated_header_rows": dropped_header_rows,
            "tables_with_warnings": tables_with_warnings,
        }

    def get_business_context(self, business_id: str):
        if business_id not in self._cache_loaders:
            biz_path = self.data_dir / "data" / business_id
            if not biz_path.exists():
                biz_path = self.data_dir / business_id
            
            loader = BusinessDataLoader(str(biz_path))
            indexer = SchemaIndexer(loader.get_connection(), loader.tables, loader.readme_content)
            self._cache_loaders[business_id] = loader
            self._cache_indexers[business_id] = indexer
            
        return self._cache_loaders[business_id], self._cache_indexers[business_id]

    def answer_question(self, question_item: Dict[str, Any]) -> Dict[str, Any]:
        self.last_execution_trace = []
        self.last_data_diagnostics = {}
        qid = question_item["id"]
        bid = question_item["business_id"]
        question = question_item["question"]
        as_of_date = question_item["as_of_date"]
        
        type_hint = detect_type_hint(question)
        
        try:
            loader, indexer = self.get_business_context(bid)
            self.last_data_diagnostics = self._summarize_data_diagnostics(indexer)
            con = loader.get_connection()
            sandbox = ExecutionSandbox(con)
            
            # 1. Unanswerable check
            router = QuestionRouter(indexer.profile)
            is_unans, reason = router.check_unanswerable(question, as_of_date)
            if is_unans:
                if self.verbose:
                    print(f"[{qid}] Detected UNANSWERABLE: {reason}")
                return {"id": qid, "type": "unanswerable", "reason": reason}
            
            # 2. Build prompt
            schema_context = indexer.to_prompt_context()
            prompt = self.prompt_builder.build_sql_prompt(question, as_of_date, schema_context)
            
            # 3. Call LLM
            sql_response = self.llm.generate(prompt)
            
            if not sql_response:
                self._record_sql_attempt("initial", sql_response, error="LLM returned an empty response or timed out.")
                if self.verbose:
                    print(f"[{qid}] LLM returned empty or timed out -> abstain")
                return {"id": qid, "type": "abstain"}
            
            # 4. Sandbox execution loop with self-repair
            exec_res = sandbox.execute_sql(sql_response)
            last_sql_response = sql_response
            self._record_sql_attempt("initial", sql_response, exec_res)
            if self.verbose:
                print(f"[{qid}] SQL attempt 1 (initial): {exec_res.get('query') or '<no SQL extracted>'}")
                if not exec_res["success"]:
                    print(f"[{qid}] SQL error: {exec_res['error']}")
            attempts = 0
            
            while not exec_res["success"] and attempts < self.max_repair:
                attempts += 1
                if self.verbose:
                    print(f"[{qid}] SQL Execution error (attempt {attempts}/{self.max_repair}): {exec_res['error']}")
                
                repair_prompt = f"""Câu truy vấn DuckDB SQL sau bị lỗi thực thi:
Lỗi: {exec_res['error']}

Câu SQL lỗi hoặc phản hồi cần sửa:
{exec_res.get('query') or self._response_preview(last_sql_response) or ''}

Schema và kiểu dữ liệu hiện có:
{schema_context[:6000]}

Hãy sửa lỗi dựa trên lỗi DuckDB và schema. Chỉ trả về đúng một câu SELECT hoặc WITH hợp lệ cho DuckDB, trong một khối ```sql ... ```. Không viết giải thích hay nội dung ngoài khối SQL.
"""
                fixed_sql = self.llm.generate(repair_prompt, max_tokens=256)
                if not fixed_sql:
                    self._record_sql_attempt(
                        "repair",
                        fixed_sql,
                        exec_res,
                        error=f"Repair attempt {attempts} returned an empty response or timed out.",
                    )
                    if self.verbose:
                        print(f"[{qid}] Repair attempt {attempts} timed out or failed.")
                    break
                last_sql_response = fixed_sql
                exec_res = sandbox.execute_sql(fixed_sql)
                self._record_sql_attempt("repair", fixed_sql, exec_res)
                if self.verbose:
                    print(f"[{qid}] SQL attempt {attempts + 1} (repair): {exec_res.get('query') or '<no SQL extracted>'}")
                    if not exec_res["success"]:
                        print(f"[{qid}] SQL error: {exec_res['error']}")
            
            # 5. Post-process result
            if exec_res["success"] and exec_res["data"] is not None:
                res = infer_and_format_result(qid, exec_res["data"], expected_type_hint=type_hint)
                if self.verbose:
                    print(f"[{qid}] SUCCESS -> type: {res.get('type')}, answer: {res.get('answer')}")
                return res
            else:
                if self.verbose:
                    print(f"[{qid}] SQL failed after repairs ({exec_res.get('error')}) -> abstain")
                # Failed execution after repair -> abstain to prevent -1 penalty
                return {"id": qid, "type": "abstain"}
                
        except Exception as e:
            self.last_execution_trace.append({
                "attempt": len(self.last_execution_trace) + 1,
                "stage": "agent",
                "response_preview": None,
                "clean_sql": None,
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            })
            if self.verbose:
                print(f"[{qid}] Unhandled Exception: {e}")
            # Any unhandled exception -> fallback to abstain
            return {"id": qid, "type": "abstain"}

    def close(self):
        for loader in self._cache_loaders.values():
            loader.close()
        self._cache_loaders.clear()
        self._cache_indexers.clear()
