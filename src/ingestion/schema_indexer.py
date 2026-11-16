"""Schema profiling and compact markdown generator for LLM prompt context."""
from typing import Dict, Any, Optional
import duckdb
from src.ingestion.value_normalizer import fold_diacritics


class SchemaIndexer:
    """Profiles DuckDB tables and builds concise context for LLM prompts."""

    def __init__(self, con: duckdb.DuckDBPyConnection, tables_meta: Dict[str, Any], readme_content: str = ""):
        self.con = con
        self.tables_meta = tables_meta
        self.readme_content = readme_content
        self.profile: Dict[str, Any] = {}
        self._profile_tables()

    def _profile_tables(self):
        for tbl_name, meta in self.tables_meta.items():
            try:
                # Column names and types from DESCRIBE
                col_info = self.con.execute(f"DESCRIBE \"{tbl_name}\"").fetchall()
                col_types = {row[0]: row[1] for row in col_info}
                
                # Fetch first 5 rows to extract samples quickly without multiple table scans
                df_sample = self.con.execute(f"SELECT * FROM \"{tbl_name}\" LIMIT 5").df()
                
                cols = []
                for c_name, c_type in col_types.items():
                    samples_str = ""
                    if c_name in df_sample.columns:
                        non_null = df_sample[c_name].dropna().unique()
                        samples = [str(s) for s in non_null[:3]]
                        samples_str = ", ".join([s[:25] + "..." if len(s) > 25 else s for s in samples])
                    
                    cols.append({
                        "name": c_name,
                        "type": c_type,
                        "samples": samples_str
                    })
                
                # Find date min/max
                date_range = self._find_date_range(tbl_name, col_types)
                
                self.profile[tbl_name] = {
                    "row_count": meta.get("row_count", 0),
                    "source_file": meta.get("source_file", ""),
                    "columns": cols,
                    "date_range": date_range,
                    "normalizations": meta.get("normalizations", {}),
                    "dropped_repeated_header_rows": meta.get("dropped_repeated_header_rows", 0),
                }
            except Exception as e:
                print(f"Error profiling table {tbl_name}: {e}")

    def _find_date_range(self, tbl_name: str, col_types: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Find a reliable date range, preferring normalized DATE/TIMESTAMP fields."""
        date_keywords = {"ngay", "date", "time", "gio", "thoi_gian", "created_at", "updated_at", "timestamp", "ky"}
        candidates = []
        for name, col_type in col_types.items():
            folded_name = fold_diacritics(name)
            if not any(keyword in folded_name for keyword in date_keywords):
                continue
            type_name = str(col_type).upper()
            if any(kind in type_name for kind in ("DATE", "TIMESTAMP")):
                candidates.append(name)

        # Never use lexical MIN/MAX over raw DD/MM/YYYY text; that produces a
        # plausible-looking but incorrect interval.
        for column in candidates:
            try:
                res = self.con.execute(f"""
                    SELECT MIN(CAST(\"{column}\" AS VARCHAR)), MAX(CAST(\"{column}\" AS VARCHAR))
                    FROM \"{tbl_name}\"
                    WHERE \"{column}\" IS NOT NULL
                """).fetchone()
                if res and res[0] and res[1]:
                    return {"col": column, "min": str(res[0]), "max": str(res[1])}
            except Exception:
                continue
        return None

    def to_prompt_context(self, max_readme_chars: int = 1000) -> str:
        """Render a markdown summary tailored for LLM prompt."""
        lines = ["### THÔNG TIN CƠ SỞ DỮ LIỆU CỦA DOANH NGHIỆP:\n"]
        
        # README summary
        if self.readme_content:
            clean_readme = self.readme_content.strip()
            if len(clean_readme) > max_readme_chars:
                clean_readme = clean_readme[:max_readme_chars] + "\n...(tóm tắt)"
            lines.append(f"#### Ghi chú từ doanh nghiệp (README):\n{clean_readme}\n")
        
        # Table schemas
        lines.append("#### Danh sách các bảng dữ liệu:")
        for tbl_name, info in self.profile.items():
            date_info = ""
            if info.get("date_range"):
                dr = info["date_range"]
                date_info = f" | Dải ngày ({dr['col']}): từ {dr['min']} đến {dr['max']}"
            
            lines.append(f"\n- **Bảng `{tbl_name}`** ({info['row_count']} dòng{date_info}):")
            dropped_headers = info.get("dropped_repeated_header_rows", 0)
            if dropped_headers:
                lines[-1] += f" (đã bỏ {dropped_headers} dòng header lặp)"
            for c in info["columns"]:
                sample_hint = f" (ví dụ: {c['samples']})" if c['samples'] else ""
                if c["name"].endswith("_normalized"):
                    source_column = c["name"][:-len("_normalized")]
                    sample_hint += f" (đã chuẩn hóa từ `{source_column}`)"
                lines.append(f"  * `{c['name']}` ({c['type']}){sample_hint}")
            for source, detail in info.get("normalizations", {}).items():
                if detail.get("parse_failures"):
                    lines.append(
                        f"  * Cảnh báo chuẩn hóa `{source}`: {detail['parse_failures']} giá trị không parse được."
                    )
        
        return "\n".join(lines)
