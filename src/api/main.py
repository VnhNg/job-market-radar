from pathlib import Path
from fastapi import FastAPI

from src.api.analytics.breakdown_builder import build_breakdown_sql
from src.api.analytics.detail_builder import build_detail_sql
from src.api.analytics.sample_builder import build_sample_sql
from src.api.analytics.spec import BASES_DOCS, BREAKDOWN_BASES, DETAIL_BASES
from src.api.analytics.op_docs import OP_DOCS
from src.api.analytics.query_docs import (
    BaseParam,
    MetricParam,
    DimensionsParam,
    SelectParam,
    LimitParam,
    DryRunParam,
    SeedParam,
    CommonFilters,
)

from src.api.analytics.filter_values import get_filter_values
from src.api.duckdb_client import query as duckdb_query


app = FastAPI(title="Job Market Radar API", version="0.1.0")

# Project root = .../job-market-radar
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "warehouse" / "job_market.duckdb"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get(
    "/definitions",
    summary=OP_DOCS["definitions"]["summary"],
    description=OP_DOCS["definitions"]["user"],
    openapi_extra={
        "x-job-market-llm-description": OP_DOCS["definitions"]["llm"],
        "x-job-market-llm-returns": OP_DOCS["definitions"]["returns"],
    },
)
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

@app.get(
    "/analytics/breakdown",
    summary=OP_DOCS["analytics_breakdown"]["summary"],
    description=OP_DOCS["analytics_breakdown"]["user"],
    openapi_extra={
        "x-job-market-llm-description": OP_DOCS["analytics_breakdown"]["llm"],
        "x-job-market-llm-returns": OP_DOCS["analytics_breakdown"]["returns"],
    },
)
def analytics_breakdown(
    base: BaseParam,
    metric: MetricParam,
    dimensions: DimensionsParam,
    all_filters: CommonFilters,
    limit: LimitParam = 20,
    dry_run: DryRunParam = False,
):
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

@app.get(
    "/analytics/detail",
    summary=OP_DOCS["analytics_detail"]["summary"],
    description=OP_DOCS["analytics_detail"]["user"],
    openapi_extra={
        "x-job-market-llm-description": OP_DOCS["analytics_detail"]["llm"],
        "x-job-market-llm-returns": OP_DOCS["analytics_detail"]["returns"],
    },
)
def analytics_detail(
    base: BaseParam,
    select: SelectParam,
    all_filters: CommonFilters,
    limit: LimitParam = 20,
    dry_run: DryRunParam = False,
):
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

@app.get(
    "/analytics/sample",
    summary=OP_DOCS["analytics_sample"]["summary"],
    description=OP_DOCS["analytics_sample"]["user"],
    openapi_extra={
        "x-job-market-llm-description": OP_DOCS["analytics_sample"]["llm"],
        "x-job-market-llm-returns": OP_DOCS["analytics_sample"]["returns"],
    },
)
def analytics_sample(
    base: BaseParam,
    select: SelectParam,
    all_filters: CommonFilters,
    seed: SeedParam = 42,
    limit: LimitParam = 20,
    dry_run: DryRunParam = False,
):
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

@app.get(
    "/analytics/semantic_spec",
    summary=OP_DOCS["analytics_semantic_spec"]["summary"],
    description=OP_DOCS["analytics_semantic_spec"]["user"],
    openapi_extra={
        "x-job-market-llm-description": OP_DOCS["analytics_semantic_spec"]["llm"],
        "x-job-market-llm-returns": OP_DOCS["analytics_semantic_spec"]["returns"],
    },
)
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

    return {"bases": BASES_DOCS, "breakdown": breakdown, "detail": detail}

@app.get(
    "/analytics/filter_values",
    summary=OP_DOCS["analytics_filter_values"]["summary"],
    description=OP_DOCS["analytics_filter_values"]["user"],
    openapi_extra={
        "x-job-market-llm-description": OP_DOCS["analytics_filter_values"]["llm"],
        "x-job-market-llm-returns": OP_DOCS["analytics_filter_values"]["returns"],
    },
)
def analytics_filter_values(base: str, field: str, limit: int = 200):
    return get_filter_values(base=base, field=field, limit=limit)

