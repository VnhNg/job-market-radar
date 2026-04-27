import argparse
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    p = argparse.ArgumentParser(description="Run a SQL file against DuckDB and export results to CSV.")
    p.add_argument("--db", default="data/warehouse/job_market.duckdb")
    p.add_argument("--sql", required=True, help="Path to .sql file relative to project root")
    p.add_argument("--out", required=True, help="Output CSV path relative to project root")
    args = p.parse_args()

    db_path = PROJECT_ROOT / args.db
    sql_path = PROJECT_ROOT / args.sql
    out_path = PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise SystemExit(f"Missing DuckDB file: {db_path}. Load the warehouse before exporting SQL results.")
    if not sql_path.exists():
        raise SystemExit(f"Missing SQL file: {sql_path}")

    query = sql_path.read_text(encoding="utf-8")
    con = duckdb.connect(str(db_path))
    df = con.execute(query).fetchdf()
    con.close()

    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Rows: {len(df)}")
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
