from __future__ import annotations

from .spec import BREAKDOWN_BASES


def _coerce(value, t: str):
    if t == "int":
        return int(value)
    if t == "float":
        return float(value)
    return str(value)


def build_breakdown_sql(
    *,
    base: str,
    metric: str,
    dimensions_csv: str,
    filters: dict | None = None,
    limit: int = 20,
) -> tuple[str, list]:
    if base not in BREAKDOWN_BASES:
        raise ValueError(f"Unknown base: {base}")

    spec = BREAKDOWN_BASES[base]
    table = spec["table"]

    dims = [d.strip() for d in dimensions_csv.split(",") if d.strip()]
    if not dims:
        raise ValueError("dimensions must be non-empty (e.g. 'bundesland' or 'channel,bundesland')")
    if len(dims) > 2:
        raise ValueError("max 2 dimensions supported")
    for d in dims:
        if d not in spec["dimensions"]:
            raise ValueError(f"Dimension not allowed for base={base}: {d}")

    metrics = spec["metrics"]
    if metric not in metrics:
        raise ValueError(f"Metric not allowed for base={base}: {metric}")
    metric_expr = metrics[metric]

    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")

    where = []
    params: list = []

    filters = filters or {}
    filter_specs = spec["filters"]  # dict: name -> {clause, type}
    for name, value in filters.items():
        if value is None:
            continue
        if name not in filter_specs:
            raise ValueError(f"Filter not allowed for base={base}: {name}")
        clause = filter_specs[name]["clause"]
        ptype = filter_specs[name]["type"]
        where.append(clause)
        params.append(_coerce(value, ptype))

    select_dims = ", ".join(dims)
    group_by = ", ".join(dims)

    sql = f"SELECT {select_dims}, {metric_expr} AS value FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" GROUP BY {group_by} ORDER BY value DESC LIMIT {int(limit)}"

    return sql, params
