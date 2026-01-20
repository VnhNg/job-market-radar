CREATE OR REPLACE VIEW v_replication_groups AS
WITH base AS (
  SELECT
    channel,
    company,
    location,
    title,
    job_id,
    desc_sig AS role_signature
  FROM v_jobs
  WHERE desc_sig IS NOT NULL
)
SELECT
  channel,
  company,
  role_signature,
  COUNT(*) AS postings,
  COUNT(DISTINCT location) AS distinct_locations,
  CAST(COUNT(*) AS DOUBLE) / NULLIF(COUNT(DISTINCT location), 0) AS repost_ratio,
  MIN(title) AS sample_title,
  MIN(location) AS sample_location,
  MIN(job_id) AS sample_job_id
FROM base
GROUP BY
  channel, company, role_signature;
