"""
CSV-to-SQLite ETL for FFIEC NIC bulk data.

Reads the 5 CSV files from the project root, loads them into a SQLite
database with proper indexes and normalized name columns.  Idempotent:
re-running recreates the database from scratch.
"""

import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "ffiec_rssd_agent" / "ffiec_nic.db"

CSV_TABLE_MAP = {
    "CSV_ATTRIBUTES_ACTIVE.CSV": "institutions_active",
    "CSV_ATTRIBUTES_CLOSED.CSV": "institutions_closed",
    "CSV_ATTRIBUTES_BRANCHES.CSV": "branches",
    "CSV_RELATIONSHIPS.CSV": "relationships",
    "CSV_TRANSFORMATIONS.CSV": "transformations",
}

ATTRIBUTE_INDEXES = [
    ("idx_{table}_rssd", "{table}", "ID_RSSD"),
    ("idx_{table}_nm_lgl_upper", "{table}", "NM_LGL_UPPER"),
    ("idx_{table}_nm_short", "{table}", "NM_SHORT"),
    ("idx_{table}_city", "{table}", "CITY"),
    ("idx_{table}_state", "{table}", "STATE_ABBR_NM"),
    ("idx_{table}_fdic", "{table}", "ID_FDIC_CERT"),
    ("idx_{table}_ncua", "{table}", "ID_NCUA"),
    ("idx_{table}_aba", "{table}", "ID_ABA_PRIM"),
    ("idx_{table}_lei", "{table}", "ID_LEI"),
    ("idx_{table}_entity_type", "{table}", "ENTITY_TYPE"),
]

RELATIONSHIP_INDEXES = [
    ("idx_rel_parent", "relationships", "ID_RSSD_PARENT"),
    ("idx_rel_offspring", "relationships", "ID_RSSD_OFFSPRING"),
    ("idx_rel_dt_end", "relationships", "DT_END"),
]

TRANSFORMATION_INDEXES = [
    ("idx_trans_pred", "transformations", "ID_RSSD_PREDECESSOR"),
    ("idx_trans_succ", "transformations", "ID_RSSD_SUCCESSOR"),
    ("idx_trans_code", "transformations", "TRNSFM_CD"),
]


def _strip_comment_prefix(df: pd.DataFrame) -> pd.DataFrame:
    """The CSV header row starts with '#' -- strip it from the first column name."""
    cols = list(df.columns)
    if cols[0].startswith("#"):
        cols[0] = cols[0].lstrip("#")
    df.columns = cols
    return df


def _normalize_names(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from name columns and add an uppercase search column."""
    if "NM_LGL" in df.columns:
        df["NM_LGL"] = df["NM_LGL"].astype(str).str.strip()
        df["NM_LGL_UPPER"] = df["NM_LGL"].str.upper()
    if "NM_SHORT" in df.columns:
        df["NM_SHORT"] = df["NM_SHORT"].astype(str).str.strip()
    return df


def load_csv(csv_path: Path) -> pd.DataFrame:
    print(f"  Reading {csv_path.name} ...")
    df = pd.read_csv(csv_path, dtype=str, low_memory=False)
    df = _strip_comment_prefix(df)
    df = _normalize_names(df)
    return df


def build_database() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing database at {DB_PATH}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    try:
        for csv_name, table_name in CSV_TABLE_MAP.items():
            csv_path = PROJECT_ROOT / csv_name
            if not csv_path.exists():
                print(f"  WARNING: {csv_path} not found, skipping.")
                continue

            df = load_csv(csv_path)
            df.to_sql(table_name, conn, if_exists="replace", index=False)
            row_count = len(df)
            print(f"  Loaded {row_count:,} rows into '{table_name}'")

        # Create a unified view across active + closed institutions
        print("  Creating 'institutions_all' view ...")
        conn.execute("DROP VIEW IF EXISTS institutions_all")
        conn.execute("""
            CREATE VIEW institutions_all AS
            SELECT *, 'active' AS status FROM institutions_active
            UNION ALL
            SELECT *, 'closed' AS status FROM institutions_closed
        """)

        print("  Creating indexes ...")
        attr_tables = ["institutions_active", "institutions_closed", "branches"]
        for tbl in attr_tables:
            for idx_name, _, col in ATTRIBUTE_INDEXES:
                sql = f'CREATE INDEX IF NOT EXISTS {idx_name.format(table=tbl)} ON {tbl} ("{col}")'
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # column may not exist in branches

        for idx_name, tbl, col in RELATIONSHIP_INDEXES:
            conn.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ("{col}")')

        for idx_name, tbl, col in TRANSFORMATION_INDEXES:
            conn.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ("{col}")')

        conn.commit()
        print(f"\nDatabase built successfully at {DB_PATH}")
        print(f"  Size: {DB_PATH.stat().st_size / (1024*1024):.1f} MB")

    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("FFIEC NIC Bulk Data -> SQLite Loader")
    print("=" * 60)
    build_database()
