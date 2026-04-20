from __future__ import annotations

from typing import Literal

from .spec import BREAKDOWN_BASES, DETAIL_BASES
from ..duckdb_client import query


BaseName = Literal["jobs", "replication"]


def _base_table(base: BaseName) -> str:
    """
    Resolve the authoritative table/view for a base.
    Prefer breakdown spec, fall back to detail spec.
    """
    if base in BREAKDOWN_BASES:
        return BREAKDOWN_BASES[base]["table"]
    if base in DETAIL_BASES:
        return DETAIL_BASES[base]["table"]
    raise ValueError(f"Unknown base: {base}")


def _allowed_filter_types(base: BaseName) -> dict[str, str]:
    """
    Union of filter fields for this base across breakdown/detail.
    Values are the backend-declared types, e.g. 'str', 'int'.
    """
    out: dict[str, str] = {}

    if base in BREAKDOWN_BASES:
        for name, spec in BREAKDOWN_BASES[base]["filters"].items():
            out[name] = spec["type"]

    if base in DETAIL_BASES:
        for name, spec in DETAIL_BASES[base]["filters"].items():
            out[name] = spec["type"]

    return out


def get_filter_values(
    *,
    base: BaseName,
    field: str,
    limit: int = 200,
) -> dict:
    """
    Return exact distinct values for one valid string-like filter field.

    Current scope:
    - supports only filter fields declared with type='str'
    - returns exact values from data unchanged
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if limit > 1000:
        raise ValueError("limit must be <= 1000")

    filter_types = _allowed_filter_types(base)
    if field not in filter_types:
        raise ValueError(f"Field '{field}' is not a valid filter for base '{base}'")

    field_type = filter_types[field]
    if field_type != "str":
        raise ValueError(
            f"Field '{field}' has type '{field_type}'. "
            "Only type='str' is supported by filter_values right now."
        )

    table = _base_table(base)

    # field and table are safe to interpolate because they come from validated backend specs
    sql = f'''
        SELECT DISTINCT "{field}" AS value
        FROM {table}
        WHERE "{field}" IS NOT NULL
          AND TRIM(CAST("{field}" AS VARCHAR)) <> ''
        ORDER BY 1
        LIMIT ?
    '''

    rows = query(sql, [limit])
    values = [r["value"] for r in rows]

    return {
        "base": base,
        "field": field,
        "values": values,
    }