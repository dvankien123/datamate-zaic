"""Loader to ingest heterogeneous business files (.csv, .xlsx, .sqlite) into DuckDB."""
import re
from pathlib import Path
from typing import Dict, Any, List
import duckdb
import pandas as pd


def clean_table_name(name: str) -> str:
    """Normalize table and column names to valid SQL identifiers."""
    name = re.sub(r"[^\w]+", "_", str(name).strip().lower())
    name = re.sub(r"^_+|_+$", "", name)
    if name and name[0].isdigit():
        name = "tbl_" + name
    return name or "col"


def find_excel_header_row(raw_df: pd.DataFrame, max_search: int = 8) -> int:
    """Find the best header row index in a raw DataFrame."""
    best_row = 0
    max_score = -1
    
    keywords = [
        "mã", "tên", "ngày", "thời gian", "sl", "số lượng", "đơn giá", 
        "thành tiền", "trạng thái", "ghi chú", "khách", "nv", "tiền", 
        "hóa đơn", "phiếu", "giá", "loại", "nhóm", "kênh"
    ]
    
    for r_idx in range(min(max_search, len(raw_df))):
        row_vals = raw_df.iloc[r_idx].dropna().tolist()
        if not row_vals:
            continue
            
        str_cells = [
            str(v).strip() for v in row_vals 
            if isinstance(v, str) and not v.strip().replace(".", "", 1).isdigit()
        ]
        
        bonus = sum(1 for s in str_cells if any(k in s.lower() for k in keywords))
        score = len(str_cells) + bonus * 3
        
        if score > max_score and len(str_cells) >= 2:
            max_score = score
            best_row = r_idx
            
    return best_row


class BusinessDataLoader:
    """Loads all data files of a business into an in-memory DuckDB instance."""

    def __init__(self, biz_dir: str):
        self.biz_dir = Path(biz_dir)
        self.biz_id = self.biz_dir.name
        self.con = duckdb.connect(":memory:")
        self.tables: Dict[str, Dict[str, Any]] = {}
        self.readme_content: str = ""
        self._load_all()

    def _load_all(self):
        # 1. Read README.md if present
        readme_path = self.biz_dir / "README.md"
        if readme_path.exists():
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    self.readme_content = f.read()
            except Exception as e:
                self.readme_content = f"Error reading README.md: {e}"

        # 2. Iterate through files
        for file_path in sorted(self.biz_dir.iterdir()):
            if file_path.name == "README.md":
                continue
            
            suffix = file_path.suffix.lower()
            stem = file_path.stem
            
            if suffix == ".csv":
                self._load_csv(file_path, stem)
            elif suffix in [".xlsx", ".xls"]:
                self._load_excel(file_path, stem)
            elif suffix == ".sqlite":
                self._load_sqlite(file_path, stem)

    def _load_csv(self, file_path: Path, stem: str):
        tbl_name = clean_table_name(stem)
        try:
            self.con.execute(
                f"CREATE TABLE \"{tbl_name}\" AS SELECT * FROM read_csv_auto('{file_path.as_posix()}', normalize_names=True)"
            )
            count = self.con.execute(f"SELECT COUNT(*) FROM \"{tbl_name}\"").fetchone()[0]
            self.tables[tbl_name] = {
                "source_file": file_path.name,
                "type": "csv",
                "row_count": count
            }
        except Exception:
            try:
                df = pd.read_csv(file_path, low_memory=False)
                df.columns = [clean_table_name(c) for c in df.columns]
                self.con.register("temp_df", df)
                self.con.execute(f"CREATE TABLE \"{tbl_name}\" AS SELECT * FROM temp_df")
                self.con.unregister("temp_df")
                self.tables[tbl_name] = {
                    "source_file": file_path.name,
                    "type": "csv",
                    "row_count": len(df)
                }
            except Exception as e:
                print(f"Failed to load CSV {file_path.name}: {e}")

    def _load_excel(self, file_path: Path, stem: str):
        try:
            excel_file = pd.ExcelFile(file_path)
            for sheet_name in excel_file.sheet_names:
                raw_df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
                if raw_df.empty:
                    continue
                
                # Detect header row
                header_idx = find_excel_header_row(raw_df)
                df = raw_df.iloc[header_idx + 1:].copy().reset_index(drop=True)
                header_row = raw_df.iloc[header_idx].tolist()
                
                # Clean column names
                clean_cols = []
                seen = set()
                for idx, c in enumerate(header_row):
                    col_str = str(c).strip() if pd.notna(c) else f"col_{idx}"
                    c_clean = clean_table_name(col_str)
                    if not c_clean or c_clean in seen:
                        c_clean = f"{c_clean}_{idx}"
                    seen.add(c_clean)
                    clean_cols.append(c_clean)
                df.columns = clean_cols
                
                # Table name
                if len(excel_file.sheet_names) == 1:
                    tbl_name = clean_table_name(stem)
                else:
                    tbl_name = clean_table_name(f"{stem}_{sheet_name}")
                
                # Safely register into DuckDB
                try:
                    self.con.register("temp_sheet", df)
                    self.con.execute(f"CREATE TABLE \"{tbl_name}\" AS SELECT * FROM temp_sheet")
                    self.con.unregister("temp_sheet")
                except Exception:
                    # If mixed data types cause DuckDB register error, cast columns to string/object
                    for col in df.columns:
                        df[col] = df[col].astype(str).replace({"nan": None, "None": None})
                    self.con.register("temp_sheet", df)
                    self.con.execute(f"CREATE TABLE \"{tbl_name}\" AS SELECT * FROM temp_sheet")
                    self.con.unregister("temp_sheet")
                
                self.tables[tbl_name] = {
                    "source_file": file_path.name,
                    "sheet_name": sheet_name,
                    "type": "xlsx",
                    "row_count": len(df)
                }
        except Exception as e:
            print(f"Failed to load Excel {file_path.name}: {e}")

    def _load_sqlite(self, file_path: Path, stem: str):
        try:
            import sqlite3
            sqlite_con = sqlite3.connect(file_path)
            cursor = sqlite_con.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            sqlite_tables = [row[0] for row in cursor.fetchall()]
            
            for t in sqlite_tables:
                df = pd.read_sql_query(f"SELECT * FROM \"{t}\"", sqlite_con)
                df.columns = [clean_table_name(c) for c in df.columns]
                tbl_name = clean_table_name(t)
                self.con.register("temp_sqlite", df)
                self.con.execute(f"CREATE TABLE \"{tbl_name}\" AS SELECT * FROM temp_sqlite")
                self.con.unregister("temp_sqlite")
                self.tables[tbl_name] = {
                    "source_file": file_path.name,
                    "type": "sqlite",
                    "row_count": len(df)
                }
            sqlite_con.close()
        except Exception as e:
            print(f"Failed to load SQLite {file_path.name}: {e}")

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        return self.con

    def close(self):
        try:
            self.con.close()
        except Exception:
            pass
