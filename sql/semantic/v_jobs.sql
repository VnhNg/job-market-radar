CREATE OR REPLACE VIEW v_jobs AS
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
  json_extract_string(j.extra_json, '$.location_area[1]') AS bundesland
FROM jobs_entry_level_v1 j,
     json_each(j.extra_json, '$.queries') q
WHERE j.extra_json IS NOT NULL;
