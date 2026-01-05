-- Q4: Which employers post the same job (same description) in multiple locations?

SELECT
  company,
  COUNT(*) AS postings,
  COUNT(DISTINCT location) AS distinct_locations,
  MIN(title) AS sample_title,
  MIN(url) AS sample_url,
  SUBSTR(MIN(description), 1, 220) AS description_preview
FROM jobs_entry_level_v1
GROUP BY company, description
HAVING COUNT(DISTINCT location) > 1
ORDER BY distinct_locations DESC, postings DESC;
