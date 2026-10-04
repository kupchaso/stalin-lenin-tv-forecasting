CREATE TABLE IF NOT EXISTS `forecasting-mentions-project.forecasting_mentions.web_mentions_candidates`
CLUSTER BY domain,person
OPTIONS(description='PARTIAL backfill stopped at sandbox quota. Surname candidate tokens, not disambiguated persons. First batch covers six leading prefixes; remaining batches cover bare, guillemet and double quote. Raw duplicate ingestion/versions retained.') AS
SELECT *,_TABLE_SUFFIX AS load_week FROM `forecasting-mentions-project.forecasting_mentions_staging.web_*`;

CREATE TABLE IF NOT EXISTS `forecasting-mentions-project.forecasting_mentions.web_load_manifest` AS
SELECT load_week,COUNT(*) AS rows_loaded,MIN(seen_at) AS first_seen_at,MAX(seen_at) AS last_seen_at
FROM `forecasting-mentions-project.forecasting_mentions.web_mentions_candidates` GROUP BY load_week;
