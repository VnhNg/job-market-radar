BASES_DOCS = {
    "jobs": {
        "grain": (
            "posting-level view (v_jobs). Each row is one observed job posting/listing. "
            "Use this when counts or details should be about postings themselves."
        ),
        "good_for": [
            "counting job postings by channel, bundesland, company, source, or time",
            "answering 'most active companies' when active means number of job postings",
            "finding geographic hotspots when hotspot means where postings are concentrated",
            "showing concrete posting details such as title, company, location, url, created_at, description",
            "drill-through from an aggregate posting slice to the actual postings in that slice",
            "not suitable for measuring whether the same role is reposted across multiple locations",
        ],
        "fields": ["job_id", "title", "company", "location", "url", "created_at", "channel", "bundesland"],
    },
    "replication": {
        "grain": (
            "role-replication group view (v_replication_groups). Each row is one grouped role identity, "
            "defined by channel + company + role_signature. A row summarizes multiple postings that appear "
            "to be the same role reposted or repeated across locations."
        ),
        "good_for": [
            "measuring reposting or replication behavior of the same role across locations",
            "answering questions about replicated postings, repeated roles, role_signature groups, repost_ratio, or distinct_locations",
            "finding companies whose same roles appear in many locations",
            "comparing reposting footprint or location spread across companies/channels",
            "showing group-level examples such as sample_title, sample_location, postings, distinct_locations, repost_ratio",
            "not suitable for ordinary posting-volume questions like 'most active companies' unless the user explicitly means reposting/replication activity",
            "not suitable for listing many individual job postings with full URLs/descriptions",
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
