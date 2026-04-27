-- Q3: Role mix by entry channel (Werkstudent/Praktikum/Junior)
-- Rule-based buckets from title (no advanced NLP).
-- Explodes extra_json.queries so jobs can count under multiple channels.

WITH base AS (
  SELECT
    title,
    extra_json::JSON AS ex
  FROM jobs_entry_level_v1
),
expanded AS (
  SELECT
    UNNEST(CAST(json_extract(ex, '$.queries') AS VARCHAR[])) AS query,
    title
  FROM base
),
bucketed AS (
  SELECT
    query,
    CASE
      WHEN title ILIKE '%data engineer%' OR title ILIKE '%dateningenieur%' OR title ILIKE '%data engineering%' THEN 'Data Engineering'
      WHEN title ILIKE '%data scientist%' OR title ILIKE '%datascientist%' THEN 'Data Science'
      WHEN title ILIKE '%machine learning%' OR title ILIKE '%ml engineer%' OR title ILIKE '%mlops%' THEN 'Machine Learning'
      WHEN title ILIKE '%data analyst%' OR title ILIKE '%datenanalyst%' OR title ILIKE '%business intelligence%' OR title ILIKE '%power bi%' OR title ILIKE '%bi analyst%' THEN 'BI / Analytics'
      ELSE 'Other'
    END AS role_bucket
  FROM expanded
)
SELECT
  query,
  role_bucket,
  COUNT(*) AS jobs
FROM bucketed
GROUP BY query, role_bucket
ORDER BY query, jobs DESC;
