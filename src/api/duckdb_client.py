from __future__ import annotations

from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "warehouse" / "job_market.duckdb"


def connect(db_path: Path = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """
    Create a new DuckDB connection.
    """
    return duckdb.connect(str(db_path), read_only=True)


def query(sql: str, params: list | None = None, *, db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """
    Execute a SELECT and return rows as list[dict].
    Uses parameterized execution (params) for safety.
    """
    con = connect(db_path=db_path)
    try:
        cur = con.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()
