# src/api/analytics/op_docs.py

OP_DOCS = {
    "analytics_filter_values": {
        "summary": "Distinct values for one valid analytics filter field",
        "user": "Return exact distinct values for a valid string-like filter field in a governed analytics base.",
        "llm": "Use this to fetch exact candidate values for a valid filter field before matching question text to backend-backed values.",
        "returns": "JSON object with base, field, and exact distinct values.",
    },
    "analytics_semantic_spec": {
        "summary": "Semantic spec (capabilities + allowlists)",
        "user": (
            "Returns the governed semantic specification for the analytics API: "
            "available bases, allowed metrics/dimensions/columns/filters per base."
        ),
        "llm": (
            "Use this to learn what the API supports (bases, metrics, dimensions, columns, filters) "
            "before planning analytics calls. This is the source of truth for allowed parameter values."
        ),
        "returns": "metadata",
    },
    "analytics_breakdown": {
        "summary": "Breakdown (aggregate metric by dimensions)",
        "user": (
            "Aggregates one metric grouped by up to 2 dimensions with optional filters. "
            "Use this for rankings, distributions, and comparisons."
        ),
        "llm": (
            "Use for top-K and distributions. Prefer this first to find where something is high/low. "
            "Then optionally use drill-through (detail) for evidence rows."
        ),
        "returns": "aggregate_rows",
    },
    "analytics_detail": {
        "summary": "Detail (drill-through rows for a slice)",
        "user": (
            "Returns row-level records for a filtered slice. "
            "Use this after a breakdown to show concrete examples."
        ),
        "llm": (
            "Use to provide evidence rows after a breakdown. Keep select small (only needed columns)."
        ),
        "returns": "entity_rows",
    },
    "analytics_sample": {
        "summary": "Sample (deterministic row sample)",
        "user": (
            "Returns a deterministic sample of rows for inspection (seeded). "
            "Use this for qualitative checks and examples without biasing to top-K."
        ),
        "llm": (
            "Use when user asks for examples or inspection without wanting the top results. "
            "Seed makes results repeatable."
        ),
        "returns": "entity_rows",
    },
    "definitions": {
        "summary": "Definitions (glossary)",
        "user": "Glossary of terms and metric definitions used by the project.",
        "llm": "Use when user asks what a metric/term means or needs interpretation guidance.",
        "returns": "glossary",
    },
}
