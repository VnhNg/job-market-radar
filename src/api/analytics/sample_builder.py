from __future__ import annotations

from .spec import DETAIL_BASES


def _coerce(value, t: str):
    if t == "int":
        return int(value)
    if t == "float":
        return float(value)
    return str(value)


def build_sample_sql(
    *,
    base: str,
    select_csv: str,
    filters: dict | None = None,
    seed: int = 42,
    limit: int = 20,
) -> tuple[str, list]:
    if base not in DETAIL_BASES:
        raise ValueError(f"Unknown base: {base}")

    spec = DETAIL_BASES[base]
    table = spec["table"]

    cols = [c.strip() for c in select_csv.split(",") if c.strip()]
    if not cols:
        raise ValueError("select must be non-empty")
    allowed_cols = spec["columns"]
    for c in cols:
        if c not in allowed_cols:
            raise ValueError(f"Select column not allowed for base={base}: {c}")

    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")

    where = []
    params: list = []

    filters = filters or {}
    filter_specs = spec["filters"]
    for name, value in filters.items():
        if value is None:
            continue
        if name not in filter_specs:
            raise ValueError(f"Filter not allowed for base={base}: {name}")
        clause = filter_specs[name]["clause"]
        ptype = filter_specs[name]["type"]
        where.append(clause)
        params.append(_coerce(value, ptype))

    select_cols = ", ".join(cols)

    # Deterministic ordering key (seed parameterized at the end)
    if base == "jobs":
        order_key = "hash(CAST(job_id AS VARCHAR) || CAST(? AS VARCHAR))"
    else:
        order_key = "hash(role_signature || CAST(? AS VARCHAR))"

    sql = f"SELECT {select_cols} FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order_key} LIMIT {int(limit)}"

    params.append(int(seed))
    return sql, params
