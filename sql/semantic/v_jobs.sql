CREATE OR REPLACE VIEW v_jobs AS
WITH channelized AS (
  SELECT
    j.source,
    j.job_id,
    j.created_at,
    j.title,
    j.company,
    j.location,
    j.url,
    j.description,
    json_extract_string(j.extra_json, '$.desc_sig') AS desc_sig,
    json_extract_string(q.value, '$') AS channel,
    json_extract_string(j.extra_json, '$.location_area[1]') AS bundesland,

    ROW_NUMBER() OVER (
      PARTITION BY j.source, j.job_id
      ORDER BY md5(
        CAST(j.source AS VARCHAR)
        || '|'
        || CAST(j.job_id AS VARCHAR)
        || '|'
        || json_extract_string(q.value, '$')
      )
    ) AS channel_rank

  FROM jobs_active j,
       json_each(j.extra_json, '$.queries') q
)
SELECT
  source,
  job_id,
  created_at,
  title,
  company,
  location,
  url,
  description,
  desc_sig,
  channel,
  bundesland
FROM channelized
WHERE channel_rank = 1;