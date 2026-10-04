SELECT 'tv_broadcasts' AS table_name,COUNT(*) AS rows_loaded,MIN(day) AS first_day,MAX(day) AS last_day,
COUNTIF(transcript_status='200') AS available_transcripts,COUNTIF(transcript_status='404') AS missing_transcripts,
SUM(stalin_candidates) AS stalin_candidates,SUM(lenin_candidates) AS lenin_candidates,SUM(trump_candidates) AS trump_candidates
FROM `forecasting-mentions-second.forecasting_mentions.tv_broadcasts`
UNION ALL
SELECT 'tv_daily_coverage',COUNT(*),MIN(day),MAX(day),SUM(available_transcripts),SUM(missing_transcripts),
SUM(stalin_candidates),SUM(lenin_candidates),SUM(trump_candidates)
FROM `forecasting-mentions-second.forecasting_mentions.tv_daily_coverage`
UNION ALL
SELECT 'tv_mention_contexts',COUNT(*),MIN(day),MAX(day),CAST(NULL AS INT64),CAST(NULL AS INT64),
COUNTIF(person='stalin'),COUNTIF(person='lenin'),COUNTIF(person='trump')
FROM `forecasting-mentions-second.forecasting_mentions.tv_mention_contexts`;
