BASES_DOCS = {
    "jobs": {
        "grain": "row-level job postings (v_jobs)",
        "good_for": [
            "counts/distribution by channel/bundesland/company/source",
            "drill-through to example postings",
        ],
        "fields": ["job_id", "title", "company", "location", "url", "created_at", "channel", "bundesland"],
    },
    "replication": {
        "grain": "role_signature groups (v_replication_groups)",
        "good_for": [
            "reposting intensity by company/channel",
            "multi-location repost patterns",
        ],
        "fields": ["channel", "company", "role_signature", "postings", "distinct_locations", "repost_ratio"],
    },
}

BREAKDOWN_BASES = {
    "jobs": {
        "table": "v_jobs",
        "dimensions": frozenset({"channel", "bundesland", "company", "source"}),
        "metrics": {
            "job_count": "COUNT(*)",
            "unique_companies": "COUNT(DISTINCT company)",
        },
        "filters": {
            "channel": {"clause": "channel = ?", "type": "str"},
            "bundesland": {"clause": "bundesland = ?", "type": "str"},
            "company": {"clause": "company = ?", "type": "str"},
            "source": {"clause": "source = ?", "type": "str"},
        },
    },
    "replication": {
        "table": "v_replication_groups",
        "dimensions": frozenset({"channel", "company"}),
        "metrics": {
            "replication_groups": "COUNT(*)",
            "replicated_postings": "SUM(postings)",
            "max_distinct_locations": "MAX(distinct_locations)",
        },
        "filters": {
            "channel": {"clause": "channel = ?", "type": "str"},
            "company": {"clause": "company = ?", "type": "str"},
            "min_locations": {"clause": "distinct_locations >= ?", "type": "int"},
        },
    },
}


DETAIL_BASES = {
    "jobs": {
        "table": "v_jobs",
        "columns": frozenset({
            "source", "job_id", "created_at", "title", "company",
            "location", "url", "description", "desc_sig",
            "channel", "bundesland",
        }),
        "filters": {
            "channel": {"clause": "channel = ?", "type": "str"},
            "bundesland": {"clause": "bundesland = ?", "type": "str"},
            "company": {"clause": "company = ?", "type": "str"},
            "source": {"clause": "source = ?", "type": "str"},
        },
    },
    "replication": {
        "table": "v_replication_groups",
        "columns": frozenset({
            "channel", "company", "role_signature",
            "postings", "distinct_locations", "repost_ratio",
            "sample_title", "sample_location", "sample_job_id",
        }),
        "filters": {
            "channel": {"clause": "channel = ?", "type": "str"},
            "company": {"clause": "company = ?", "type": "str"},
            "min_locations": {"clause": "distinct_locations >= ?", "type": "int"},
        },
    },
}
