import argparse
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ACTIVE_JOBS_TABLE = "jobs_active"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load one processed dataset as the active warehouse dataset."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Processed dataset name without extension, e.g. entry_level_v1",
    )
    parser.add_argument(
        "--db",
        default="data/warehouse/job_market.duckdb",
        help="DuckDB file path relative to project root",
    )
    args = parser.parse_args()

    db_path = PROJECT_ROOT / args.db
    db_path.parent.mkdir(parents=True, exist_ok=True)

    jobs_csv = PROJECT_ROOT / "data" / "processed" / f"{args.dataset}.csv"

    if not jobs_csv.exists():
        raise SystemExit(f"Missing processed dataset CSV: {jobs_csv}")

    con = duckdb.connect(str(db_path))

    # Load chosen dataset into the single active jobs table
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {ACTIVE_JOBS_TABLE} AS
        FROM read_csv_auto('{jobs_csv.as_posix()}', header=true);
        """
    )

    # Metadata table for debugging / API info
    con.execute(
        """
        CREATE OR REPLACE TABLE warehouse_metadata AS
        SELECT
            ? AS active_dataset,
            current_timestamp AS loaded_at
        """,
        [args.dataset],
    )

    jobs_n = con.execute(f"SELECT COUNT(*) FROM {ACTIVE_JOBS_TABLE}").fetchone()[0]
    print(f"DB: {db_path}")
    print(f"Loaded active jobs table: {ACTIVE_JOBS_TABLE} from dataset '{args.dataset}' ({jobs_n} rows)")

    # Apply semantic views
    semantic_dir = PROJECT_ROOT / "sql" / "semantic"
    if semantic_dir.exists():
        sql_files = sorted(semantic_dir.glob("*.sql"))
        for p in sql_files:
            con.execute(p.read_text(encoding="utf-8"))
        print(f"Applied semantic SQL: {len(sql_files)} file(s) from {semantic_dir}")
    else:
        print(f"Semantic dir not found; skipped: {semantic_dir}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())