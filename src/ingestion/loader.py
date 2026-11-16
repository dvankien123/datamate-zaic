"""Loader to ingest heterogeneous business files (.csv, .xlsx, .sqlite) into DuckDB."""
import re
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import duckdb
import pandas as pd
from src.ingestion.value_normalizer import (
    drop_repeated_header_rows,
    normalize_dataframe_for_duckdb,
)


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
        self.load_errors: List[Dict[str, Any]] = []
        self.readme_content: str = ""
        self._load_all()

    def _record_load_error(
        self, file_path: Path, error: Exception, sheet_name: Optional[str] = None
    ):
        """Keep ingestion failures visible to the agent instead of only printing them."""
        item = {
            "source_file": file_path.name,
            "error": f"{type(error).__name__}: {error}",
        }
        if sheet_name is not None:
            item["sheet_name"] = str(sheet_name)
        self.load_errors.append(item)
        location = f" sheet {sheet_name!r}" if sheet_name is not None else ""
        print(f"Failed to load {file_path.name}{location}: {error}")

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
        except Exception:
            try:
                df = pd.read_csv(file_path, low_memory=False)
                df.columns = [clean_table_name(c) for c in df.columns]
                normalizations, dropped_headers = self._create_table_from_dataframe(tbl_name, df)
                self.tables[tbl_name] = {
                    "source_file": file_path.name,
                    "type": "csv",
                    "row_count": len(df) - dropped_headers,
                    "normalizations": normalizations,
                    "dropped_repeated_header_rows": dropped_headers,
                }
            except Exception as e:
                self._record_load_error(file_path, e)
            return

        try:
            normalizations, dropped_headers = self._normalize_existing_table(tbl_name)
        except Exception as e:
            # Keep the successfully loaded raw table if normalization cannot be applied.
            self._record_load_error(file_path, e)
            normalizations = {}
            dropped_headers = 0
        count = self.con.execute(f"SELECT COUNT(*) FROM \"{tbl_name}\"").fetchone()[0]
        self.tables[tbl_name] = {
            "source_file": file_path.name,
            "type": "csv",
            "row_count": count,
            "normalizations": normalizations,
            "dropped_repeated_header_rows": dropped_headers,
        }

    def _create_table_from_dataframe(
        self, tbl_name: str, df: pd.DataFrame
    ) -> Tuple[Dict[str, Dict[str, Any]], int]:
        df, dropped_headers = drop_repeated_header_rows(df)
        normalized_df, report = normalize_dataframe_for_duckdb(df)
        self._register_dataframe(tbl_name, normalized_df, replace=False, report=report)
        return report, dropped_headers

    def _register_dataframe(
        self,
        tbl_name: str,
        df: pd.DataFrame,
        replace: bool,
        report: Dict[str, Dict[str, Any]],
    ) -> None:
        temp_name = "_datamate_normalized_df"
        normalized_numeric_columns = {
            detail["normalized_column"]
            for detail in report.values()
            if detail.get("normalized_column")
            and detail.get("kind") in {"amount", "quantity"}
        }

        # DuckDB can infer an overly narrow DECIMAL from pandas Decimal objects
        # (for example DECIMAL(7,0) from an early small value). Register these
        # normalized fields as text, then cast them explicitly below.
        staging_df = df.copy()
        for column in normalized_numeric_columns:
            if column not in staging_df.columns:
                continue

            def decimal_text(value):
                if pd.isna(value):
                    return None
                if isinstance(value, Decimal):
                    return format(value, "f")
                return str(value)

            staging_df[column] = staging_df[column].map(decimal_text)

        self.con.register(temp_name, staging_df)
        create_clause = "CREATE OR REPLACE TABLE" if replace else "CREATE TABLE"

        def select_clause():
            expressions = []
            for column in staging_df.columns:
                quoted = '"' + str(column).replace('"', '""') + '"'
                if column in normalized_numeric_columns:
                    expressions.append(f"TRY_CAST({quoted} AS DECIMAL(38,9)) AS {quoted}")
                else:
                    expressions.append(quoted)
            return ", ".join(expressions)

        def ensure_numeric_values_fit():
            for column in normalized_numeric_columns:
                if column not in staging_df.columns:
                    continue
                quoted = '"' + str(column).replace('"', '""') + '"'
                invalid_count = self.con.execute(
                    f"SELECT COUNT(*) FROM {temp_name} "
                    f"WHERE {quoted} IS NOT NULL AND TRY_CAST({quoted} AS DECIMAL(38,9)) IS NULL"
                ).fetchone()[0]
                if invalid_count:
                    raise ValueError(
                        f"{invalid_count} normalized values in {column!r} do not fit DECIMAL(38,9)"
                    )

        try:
            ensure_numeric_values_fit()
            self.con.execute(
                f'{create_clause} "{tbl_name}" AS SELECT {select_clause()} FROM {temp_name}'
            )
        except Exception:
            # Preserve original fields as text if mixed source types prevent registration;
            # typed companion columns remain typed.
            # Do not hide numeric range errors behind this fallback.
            try:
                ensure_numeric_values_fit()
            except ValueError:
                raise
            fallback_df = df.copy()
            for column in fallback_df.columns:
                if column in normalized_numeric_columns:
                    continue
                fallback_df[column] = fallback_df[column].map(
                    lambda value: None if pd.isna(value) else str(value)
                )
            self.con.unregister(temp_name)
            for column in normalized_numeric_columns:
                if column in fallback_df.columns:
                    fallback_df[column] = fallback_df[column].map(
                        lambda value: None if pd.isna(value) else (
                            format(value, "f") if isinstance(value, Decimal) else str(value)
                        )
                    )
            self.con.register(temp_name, fallback_df)
            ensure_numeric_values_fit()
            self.con.execute(
                f'{create_clause} "{tbl_name}" AS SELECT {select_clause()} FROM {temp_name}'
            )
        finally:
            try:
                self.con.unregister(temp_name)
            except Exception:
                pass

    def _normalize_existing_table(
        self, tbl_name: str
    ) -> Tuple[Dict[str, Dict[str, Any]], int]:
        df = self.con.execute(f'SELECT * FROM "{tbl_name}"').df()
        df, dropped_headers = drop_repeated_header_rows(df)
        normalized_df, report = normalize_dataframe_for_duckdb(df)
        if dropped_headers or any(item.get("normalized_column") for item in report.values()):
            self._register_dataframe(tbl_name, normalized_df, replace=True, report=report)
        return report, dropped_headers

    def _load_excel(self, file_path: Path, stem: str):
        try:
            excel_file = pd.ExcelFile(file_path)
        except Exception as e:
            self._record_load_error(file_path, e)
            return

        for sheet_name in excel_file.sheet_names:
            try:
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
                df, dropped_headers = drop_repeated_header_rows(df)
                normalized_df, normalization_report = normalize_dataframe_for_duckdb(df)
                
                # Table name
                if len(excel_file.sheet_names) == 1:
                    tbl_name = clean_table_name(stem)
                else:
                    tbl_name = clean_table_name(f"{stem}_{sheet_name}")
                
                # Safely register into DuckDB
                self._register_dataframe(tbl_name, normalized_df, replace=False, report=normalization_report)
                
                self.tables[tbl_name] = {
                    "source_file": file_path.name,
                    "sheet_name": sheet_name,
                    "type": "xlsx",
                    "row_count": len(df),
                    "normalizations": normalization_report,
                    "dropped_repeated_header_rows": dropped_headers,
                }
            except Exception as e:
                self._record_load_error(file_path, e, sheet_name)

    def _load_sqlite(self, file_path: Path, stem: str):
        sqlite_con = None
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
                normalizations, dropped_headers = self._create_table_from_dataframe(tbl_name, df)
                self.tables[tbl_name] = {
                    "source_file": file_path.name,
                    "type": "sqlite",
                    "row_count": len(df) - dropped_headers,
                    "normalizations": normalizations,
                    "dropped_repeated_header_rows": dropped_headers,
                }
        except Exception as e:
            self._record_load_error(file_path, e)
        finally:
            if sqlite_con is not None:
                sqlite_con.close()

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        return self.con

    def close(self):
        try:
            self.con.close()
        except Exception:
            pass
