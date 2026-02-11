# src/api/analytics/op_docs.py

OP_DOCS = {
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
    },
    "definitions": {
        "summary": "Definitions (glossary)",
        "user": "Glossary of terms and metric definitions used by the project.",
        "llm": "Use when user asks what a metric/term means or needs interpretation guidance.",
    },
}
