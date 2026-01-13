from pathlib import Path
import duckdb
from fastapi import FastAPI, Query 
from typing import Optional


app = FastAPI(title="Job Market Radar API", version="0.1.0")

# Project root = .../job-market-radar
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "warehouse" / "job_market.duckdb"

def get_con():
    """
    Open a read-only connection to DuckDB.
    """
    if not DB_PATH.exists():
        raise RuntimeError(f"DuckDB not found at {DB_PATH}. Run: python src/load_to_duckdb.py")
    return duckdb.connect(str(DB_PATH), read_only=True)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-info")
def db_info():
    """
    Simple proof endpoint: return how many rows are in the jobs table.
    """
    con = get_con()
    n = con.execute("SELECT COUNT(*) FROM jobs_entry_level_v1").fetchone()[0]
    con.close()
    return {"jobs_entry_level_v1_rows": int(n)}

@app.get("/insights/replication-across-cities")
def replication_across_cities(min_locations: int = Query(2, ge=2)):
    """
    Companies posting the same description in multiple locations.
    """
    sql = """
    SELECT
      company,
      COUNT(*) AS postings,
      COUNT(DISTINCT location) AS distinct_locations,
      MIN(title) AS sample_title,
      MIN(url) AS sample_url,
      SUBSTR(MIN(description), 1, 220) AS description_preview
    FROM jobs_entry_level_v1
    GROUP BY company, description
    HAVING COUNT(DISTINCT location) >= ?
    ORDER BY distinct_locations DESC, postings DESC;
    """
    con = get_con()
    df = con.execute(sql, [min_locations]).fetchdf()
    con.close()
    return {"rows": df.to_dict(orient="records")}

@app.get("/insights/geo-by-channel")
def geo_by_channel(channel: Optional[str] = None):
    """
    Jobs by Bundesland and entry channel (Werkstudent/Praktikum/Junior).
    """
    sql = """
    WITH base AS (
      SELECT extra_json::JSON AS ex
      FROM jobs_entry_level_v1
    ),
    expanded AS (
      SELECT
        UNNEST(CAST(json_extract(ex, '$.queries') AS VARCHAR[])) AS ch,
        CAST(json_extract(ex, '$.location_area') AS VARCHAR[]) AS area
      FROM base
    )
    SELECT
      ch AS channel,
      area[2] AS bundesland,
      COUNT(*) AS jobs
    FROM expanded
    WHERE area IS NOT NULL AND array_length(area) >= 2
    GROUP BY ch, area[2]
    ORDER BY jobs DESC, bundesland;
    """
    con = get_con()
    df = con.execute(sql).fetchdf()
    con.close()

    if channel:
        df = df[df["channel"] == channel]

    return {"rows": df.to_dict(orient="records")}

@app.get("/definitions")
def definitions():
    """
    Metric/field glossary for users and the assistant.
    """
    return {
        "channel": "The query channel used to collect postings (e.g., 'werkstudent data', 'praktikum data', 'junior data'). A posting may appear in multiple channels.",
        "bundesland": "German federal state derived from location_area (2nd element in the Adzuna area list).",
        "distinct_locations": "Number of distinct locations for the same (company, description) pair; proxy for reposting the same role across cities.",
        "postings": "How many postings share the same (company, description) in the dataset.",
        "min_locations": "Threshold used to filter replication results (e.g., min_locations=3 shows only roles posted in 3+ locations).",
        "data_limits": [
            "Data is a snapshot from job boards and depends on the collection queries.",
            "Role mix classification (if used) is rule-based unless otherwise stated."
        ]
    }
