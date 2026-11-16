import shutil
from pathlib import Path

import pytest

from src.ingestion.loader import BusinessDataLoader
from src.ingestion.schema_indexer import SchemaIndexer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "business_id,filename,table,date_column,amount_column,date_value,raw_amount,normalized_amount,dropped_headers",
    [
        (
            "dev_002",
            "BanHang_T11_2025.xlsx",
            "banhang_t11_2025",
            "ngày_đặt_hàng",
            "tổng_tiền",
            "2025-11-01",
            "29k",
            29000,
            27,
        ),
        (
            "dev_001",
            "So_chi_tiet_ban_hang.xlsx",
            "so_chi_tiet_ban_hang",
            "ngày",
            "thành_tiền",
            "2025-01-01",
            "24,000.0000",
            24000,
            0,
        ),
    ],
)
def test_loader_adds_typed_columns_for_real_public_workbooks(
    tmp_path,
    business_id,
    filename,
    table,
    date_column,
    amount_column,
    date_value,
    raw_amount,
    normalized_amount,
    dropped_headers,
):
    source = PROJECT_ROOT / "data" / "public_test" / "data" / business_id / filename
    if not source.exists():
        pytest.skip(f"public test workbook not found: {source}")

    business_dir = tmp_path / business_id
    business_dir.mkdir()
    shutil.copy2(source, business_dir / filename)
    loader = BusinessDataLoader(str(business_dir))

    try:
        con = loader.get_connection()
        described = {
            row[0]: row[1]
            for row in con.execute(f'DESCRIBE "{table}"').fetchall()
        }
        date_normalized = f"{date_column}_normalized"
        amount_normalized = f"{amount_column}_normalized"

        assert "DATE" in described[date_normalized].upper()
        assert "DECIMAL" in described[amount_normalized].upper()
        assert loader.tables[table]["dropped_repeated_header_rows"] == dropped_headers
        assert con.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{date_normalized}" = DATE \'{date_value}\''
        ).fetchone()[0] > 0
        assert con.execute(
            f'SELECT COUNT(*) FROM "{table}" '
            f'WHERE CAST("{amount_column}" AS VARCHAR) = ? '
            f'AND "{amount_normalized}" = ?',
            [raw_amount, normalized_amount],
        ).fetchone()[0] > 0

        indexer = SchemaIndexer(con, loader.tables, loader.readme_content)
        assert indexer.profile[table]["date_range"]["col"] == date_normalized
    finally:
        loader.close()
