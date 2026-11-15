"""Output formatting and post-processing conforming to competition submission schema."""
import re
from typing import Any, Dict, Optional, Tuple, List
import pandas as pd
from src.common.normalizer import (
    normalize_string,
    normalize_number,
    normalize_percent,
    normalize_date,
    normalize_boolean,
    normalize_list,
    normalize_table,
)


def infer_and_format_result(
    qid: str,
    raw_data: Any,
    expected_type_hint: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format raw output from Sandbox into the exact schema required for submission:
    {"id": qid, "type": <type>, "answer": <answer>}
    """
    # 1. Handle abstain or error
    if raw_data is None:
        return {"id": qid, "type": "abstain"}
    
    # 2. Convert DataFrame if output is a DataFrame
    if isinstance(raw_data, pd.DataFrame):
        df = raw_data
        if df.empty:
            # Empty result
            if expected_type_hint == "number":
                return {"id": qid, "type": "number", "answer": 0}
            return {"id": qid, "type": "abstain"}
        
        # 1x1 cell -> scalar value
        if df.shape == (1, 1):
            val = df.iloc[0, 0]
            return _format_scalar(qid, val, expected_type_hint)
        
        # 1 row, multiple columns
        elif df.shape[0] == 1 and df.shape[1] > 1:
            if expected_type_hint == "table":
                return _format_table(qid, df)
            # If hinted as list (e.g. [old_month, middle_month, new_month])
            elif expected_type_hint == "list":
                return {"id": qid, "type": "list", "answer": normalize_list(df.iloc[0].tolist())}
            # Default to scalar of first column
            val = df.iloc[0, 0]
            return _format_scalar(qid, val, expected_type_hint)
        
        # Multiple rows, 1 column -> list or top-1 scalar
        elif df.shape[1] == 1 and df.shape[0] > 1:
            if expected_type_hint == "list":
                vals = df.iloc[:, 0].tolist()
                return {"id": qid, "type": "list", "answer": normalize_list(vals)}
            # If question asks for "... nhất" (top 1)
            val = df.iloc[0, 0]
            return _format_scalar(qid, val, expected_type_hint)
        
        # Multiple rows, multiple columns -> table
        else:
            return _format_table(qid, df)
            
    # 3. Handle Python list/tuple
    elif isinstance(raw_data, (list, tuple)):
        if expected_type_hint == "table":
            return {"id": qid, "type": "abstain"}
        return {"id": qid, "type": "list", "answer": normalize_list(raw_data)}
        
    # 4. Handle Python dictionary (e.g. table)
    elif isinstance(raw_data, dict):
        if "columns" in raw_data and "rows" in raw_data:
            return {"id": qid, "type": "table", "answer": normalize_table(raw_data)}
        return {"id": qid, "type": "abstain"}
        
    # 5. Handle scalar
    else:
        return _format_scalar(qid, raw_data, expected_type_hint)


def _format_scalar(qid: str, val: Any, hint: Optional[str]) -> Dict[str, Any]:
    if pd.isna(val) or val is None:
        return {"id": qid, "type": "abstain"}
        
    # If hint provided, cast accordingly
    if hint == "number":
        return {"id": qid, "type": "number", "answer": normalize_number(val)}
    elif hint == "percent":
        return {"id": qid, "type": "percent", "answer": normalize_percent(val)}
    elif hint == "date":
        return {"id": qid, "type": "date", "answer": normalize_date(val)}
    elif hint == "boolean":
        return {"id": qid, "type": "boolean", "answer": normalize_boolean(val)}
    elif hint == "string":
        return {"id": qid, "type": "string", "answer": normalize_string(val)}
    
    # Auto-infer if no hint:
    # Check boolean
    if isinstance(val, bool) or str(val).lower() in ["true", "false"]:
        return {"id": qid, "type": "boolean", "answer": normalize_boolean(val)}
    
    # Check date
    val_str = str(val).strip()
    if re.match(r"^\d{4}-\d{2}(-\d{2})?$", val_str):
        return {"id": qid, "type": "date", "answer": normalize_date(val_str)}
        
    # Check number
    try:
        f = float(val)
        return {"id": qid, "type": "number", "answer": normalize_number(f)}
    except (ValueError, TypeError):
        pass
        
    # Fallback to string
    return {"id": qid, "type": "string", "answer": normalize_string(val)}


def _format_table(qid: str, df: pd.DataFrame) -> Dict[str, Any]:
    cols = [normalize_string(c) for c in df.columns]
    rows = []
    for _, row in df.iterrows():
        r_vals = []
        for cell in row:
            if isinstance(cell, (int, float)) and not pd.isna(cell):
                r_vals.append(normalize_number(cell))
            else:
                r_vals.append(normalize_string(cell))
        rows.append(r_vals)
    return {
        "id": qid,
        "type": "table",
        "answer": {"columns": cols, "rows": rows}
    }
