from pathlib import Path
import duckdb
from fastapi import FastAPI, Query 
from typing import Optional

from src.api.analytics.breakdown_builder import build_breakdown_sql
from src.api.analytics.detail_builder import build_detail_sql
from src.api.analytics.sample_builder import build_sample_sql
from src.api.analytics.spec import BREAKDOWN_BASES, DETAIL_BASES

from src.api.duckdb_client import query as duckdb_query


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

@app.get("/analytics/breakdown")
def analytics_breakdown(
    base: str = Query(..., description="jobs | replication"),
    metric: str = Query(...),
    dimensions: str = Query(..., description="comma-separated, max 2, e.g. 'channel,bundesland'"),
    channel: Optional[str] = None,
    bundesland: Optional[str] = None,
    company: Optional[str] = None,
    source: Optional[str] = None,
    min_locations: Optional[int] = None,
    limit: int = 20,
    dry_run: bool = False,
):
    all_filters = {
        "channel": channel,
        "bundesland": bundesland,
        "company": company,
        "source": source,
        "min_locations": min_locations,
    }

    allowed = set(BREAKDOWN_BASES[base]["filters"].keys())
    filters = {k: v for k, v in all_filters.items() if (k in allowed and v is not None)}

    sql, params = build_breakdown_sql(
        base=base,
        metric=metric,
        dimensions_csv=dimensions,
        filters=filters,
        limit=limit,
    )

    if dry_run:
        return {"sql": sql, "params": params}

    rows = duckdb_query(sql, params)
    return {
        "base": base,
        "metric": metric,
        "dimensions": [d.strip() for d in dimensions.split(",") if d.strip()],
        "filters": filters,
        "rows": rows,
    }

@app.get("/analytics/detail")
def analytics_detail(
    base: str = Query(..., description="jobs | replication"),
    select: str = Query(..., description="comma-separated columns, allowlisted per base"),
    channel: Optional[str] = None,
    bundesland: Optional[str] = None,
    company: Optional[str] = None,
    source: Optional[str] = None,
    min_locations: Optional[int] = None,
    limit: int = 20,
    dry_run: bool = False,
):
    all_filters = {
        "channel": channel,
        "bundesland": bundesland,
        "company": company,
        "source": source,
        "min_locations": min_locations,
    }

    allowed = set(DETAIL_BASES[base]["filters"].keys())
    filters = {k: v for k, v in all_filters.items() if (k in allowed and v is not None)}

    sql, params = build_detail_sql(
        base=base,
        select_csv=select,
        filters=filters,
        limit=limit,
    )

    if dry_run:
        return {"sql": sql, "params": params}

    rows = duckdb_query(sql, params)
    return {
        "base": base,
        "select": [c.strip() for c in select.split(",") if c.strip()],
        "filters": filters,
        "rows": rows,
    }

@app.get("/analytics/sample")
def analytics_sample(
    base: str = Query(..., description="jobs | replication"),
    select: str = Query(..., description="comma-separated columns, allowlisted per base"),
    seed: int = 42,
    channel: Optional[str] = None,
    bundesland: Optional[str] = None,
    company: Optional[str] = None,
    source: Optional[str] = None,
    min_locations: Optional[int] = None,
    limit: int = 20,
    dry_run: bool = False,
):
    all_filters = {
        "channel": channel,
        "bundesland": bundesland,
        "company": company,
        "source": source,
        "min_locations": min_locations,
    }

    allowed = set(DETAIL_BASES[base]["filters"].keys())
    filters = {k: v for k, v in all_filters.items() if (k in allowed and v is not None)}

    sql, params = build_sample_sql(
        base=base,
        select_csv=select,
        filters=filters,
        seed=seed,
        limit=limit,
    )

    if dry_run:
        return {"sql": sql, "params": params}

    rows = duckdb_query(sql, params)
    return {
        "base": base,
        "select": [c.strip() for c in select.split(",") if c.strip()],
        "seed": seed,
        "filters": filters,
        "rows": rows,
    }

@app.get("/analytics/semantic_spec")
def analytics_semantic_spec():
    breakdown = {}
    for base, spec in BREAKDOWN_BASES.items():
        breakdown[base] = {
            "metrics": sorted(spec["metrics"].keys()),
            "dimensions": sorted(spec["dimensions"]),
            "filters": {k: v["type"] for k, v in spec["filters"].items()},
        }

    detail = {}
    for base, spec in DETAIL_BASES.items():
        detail[base] = {
            "columns": sorted(spec["columns"]),
            "filters": {k: v["type"] for k, v in spec["filters"].items()},
        }

    return {"breakdown": breakdown, "detail": detail}



