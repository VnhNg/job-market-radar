-- Q5: Where is entry-level demand concentrated by channel (Werkstudent/Praktikum/Junior)?
-- Uses extra_json.queries (list) and extra_json.location_area (list).

WITH base AS (
  SELECT
    source,
    job_id,
    location,
    extra_json::JSON AS ex
  FROM jobs_entry_level_v1
),
expanded AS (
  SELECT
    source,
    job_id,
    location,
    -- queries: explode into rows
    UNNEST(CAST(json_extract(ex, '$.queries') AS VARCHAR[])) AS query,
    -- location_area: list like ["Deutschland","Nordrhein-Westfalen","Dortmund"]
    CAST(json_extract(ex, '$.location_area') AS VARCHAR[]) AS area
  FROM base
)
SELECT
  query,
  area[2] AS bundesland,
  COUNT(*) AS jobs
FROM expanded
WHERE area IS NOT NULL
  AND array_length(area) >= 2
GROUP BY query, bundesland
ORDER BY query, jobs DESC;
