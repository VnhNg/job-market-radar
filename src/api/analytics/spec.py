BASES_DOCS = {
    "jobs": {
        "grain": "row-level job postings (v_jobs). One row = one posting instance.",
        "good_for": [
            "questions that need individual postings or posting attributes (e.g., title, company, location, url, created_at)",
            "volume/distribution questions where the unit is postings (counts grouped by channel/bundesland/company/source)",
            "drill-through to concrete postings after an aggregate slice is identified",
            "not suitable when the question is about behavior across multiple postings that requires linking postings into the same role identity",
        ],
        "fields": ["job_id", "title", "company", "location", "url", "created_at", "channel", "bundesland"],
    },
    "replication": {
        "grain": "group-level reposting aggregates (v_replication_groups). One row = (channel, company, role_signature) group.",
        "good_for": [
            "questions that require group-level reposting measures across locations (postings, distinct_locations, repost_ratio)",
            "comparing reposting intensity/footprint across companies or channels",
            "answers where the unit is a role_signature group rather than a single posting",
            "not suitable when the question requires URLs/full posting text for many individual postings",
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
