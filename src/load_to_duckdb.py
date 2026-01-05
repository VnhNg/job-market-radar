import argparse
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Load CSV datasets into a local DuckDB warehouse.")
    parser.add_argument(
        "--db",
        default="data/warehouse/job_market.duckdb",
        help="DuckDB file path relative to project root",
    )
    parser.add_argument(
        "--jobs-csv",
        default="data/processed/entry_level_v1.csv",
        help="Jobs CSV path relative to project root",
    )
    parser.add_argument(
        "--jobs-table",
        default="jobs_entry_level_v1",
        help="Target table name for jobs",
    )
    parser.add_argument(
        "--index-csv",
        default="data/raw/adzuna/de/jobs_search/_index.csv",
        help="Raw index CSV path relative to project root",
    )
    parser.add_argument(
        "--index-table",
        default="adzuna_raw_index",
        help="Target table name for raw index",
    )
    args = parser.parse_args()

    db_path = (PROJECT_ROOT / args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    jobs_csv = (PROJECT_ROOT / args.jobs_csv)
    index_csv = (PROJECT_ROOT / args.index_csv)

    if not jobs_csv.exists():
        raise SystemExit(f"Missing jobs CSV: {jobs_csv}")

    con = duckdb.connect(str(db_path))

    # Load jobs (CSV -> persistent table)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {args.jobs_table} AS
        FROM read_csv_auto('{jobs_csv.as_posix()}', header=true);
        """
    )

    # Load raw index if present (optional but recommended)
    if index_csv.exists():
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {args.index_table} AS
            FROM read_csv_auto('{index_csv.as_posix()}', header=true);
            """
        )

    # Quick sanity outputs
    jobs_n = con.execute(f"SELECT COUNT(*) FROM {args.jobs_table}").fetchone()[0]
    print(f"DB: {db_path}")
    print(f"Loaded jobs table: {args.jobs_table} ({jobs_n} rows)")

    if index_csv.exists():
        idx_n = con.execute(f"SELECT COUNT(*) FROM {args.index_table}").fetchone()[0]
        print(f"Loaded raw index table: {args.index_table} ({idx_n} rows)")
    else:
        print("Raw index CSV not found; skipped loading raw index.")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
