# src/api/analytics/query_docs.py
from __future__ import annotations

from typing import Optional, Annotated
from fastapi import Query, Depends


PARAM_TEXT: dict[str, dict[str, str]] = {
    "base": {
        "user": "Data base. Allowed: jobs | replication.",
        "llm":  "Base name. Must be exactly one of: jobs | replication.",
    },
    "metric": {
        "user": "Metric id. Allowed values depend on base.",
        "llm":  "Metric id. Must be one of the allowed metric ids for the chosen base.",
    },
    "dimensions": {
        "user": "1–2 dimension ids, comma-separated.",
        "llm":  "Dimensions (1–2). Use allowed dimension ids; do not invent new ids.",
    },
    "select": {
        "user": "One or more column ids, comma-separated.",
        "llm":  "Columns (>=1). Use allowed column ids; do not invent new ids.",
    },
    "channel": {"user": "Exact match filter for channel.", "llm": "Filter. Exact channel string."},
    "bundesland": {"user": "Exact match filter for bundesland.", "llm": "Filter. Exact bundesland string."},
    "company": {"user": "Exact match filter for company.", "llm": "Filter. Exact company name; if unsure, get candidates via breakdown first."},
    "source": {"user": "Exact match filter for source system.", "llm": "Filter. Exact source string."},
    "min_locations": {"user": "Replication-only: distinct_locations >= min_locations.", "llm": "Replication-only integer threshold."},
    "limit": {"user": "Max rows returned.", "llm": "Max rows to return (small integer)."},
    "dry_run": {"user": "If true: return SQL+params only.", "llm": "Boolean. true returns SQL only; false executes."},
    "seed": {"user": "Deterministic sampling seed.", "llm": "Deterministic seed integer."},
}

def user_desc(name: str) -> str:
    return PARAM_TEXT.get(name, {}).get("user", "")

def llm_extra(name: str) -> dict:
    llm = PARAM_TEXT.get(name, {}).get("llm", "")
    return {"x-llm-description": llm} if llm else {}


# --- shared descriptions (LLM-friendly, short, strict) ---
DESC_BASE = user_desc("base")
DESC_METRIC = user_desc("metric")
DESC_DIMENSIONS = user_desc("dimensions")
DESC_SELECT = user_desc("select")

DESC_CHANNEL = user_desc("channel")
DESC_BUNDESLAND = user_desc("bundesland")
DESC_COMPANY = user_desc("company")
DESC_SOURCE = user_desc("source")
DESC_MIN_LOCATIONS = user_desc("min_locations")

DESC_LIMIT = user_desc("limit")
DESC_DRY_RUN = user_desc("dry_run")
DESC_SEED = user_desc("seed")


# --- Annotated aliases (centralized Query docs) ---
BaseParam = Annotated[str, Query(..., description=DESC_BASE, json_schema_extra=llm_extra("base"))]
MetricParam = Annotated[str, Query(..., description=DESC_METRIC, json_schema_extra=llm_extra("metric"))]
DimensionsParam = Annotated[str, Query(..., description=DESC_DIMENSIONS, json_schema_extra=llm_extra("dimensions"))]
SelectParam = Annotated[str, Query(..., description=DESC_SELECT, json_schema_extra=llm_extra("select"))]

LimitParam = Annotated[int, Query(ge=1, le=200, description=DESC_LIMIT, json_schema_extra=llm_extra("limit"))]
DryRunParam = Annotated[bool, Query(description=DESC_DRY_RUN, json_schema_extra=llm_extra("dry_run"))]
SeedParam = Annotated[int, Query(ge=0, le=10_000_000, description=DESC_SEED, json_schema_extra=llm_extra("seed"))]


def common_filters(
    channel: Optional[str] = Query(None, description=DESC_CHANNEL, json_schema_extra=llm_extra("channel")),
    bundesland: Optional[str] = Query(None, description=DESC_BUNDESLAND, json_schema_extra=llm_extra("bundesland")),
    company: Optional[str] = Query(None, description=DESC_COMPANY, json_schema_extra=llm_extra("company")),
    source: Optional[str] = Query(None, description=DESC_SOURCE, json_schema_extra=llm_extra("source")),
    min_locations: Optional[int] = Query(None, ge=1, description=DESC_MIN_LOCATIONS, json_schema_extra=llm_extra("min_locations")),
) -> dict:
    # Keep it as a plain dict so endpoints can pass it directly into builders.
    return {
        "channel": channel,
        "bundesland": bundesland,
        "company": company,
        "source": source,
        "min_locations": min_locations,
    }


CommonFilters = Annotated[dict, Depends(common_filters)]
