CREATE SCHEMA IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions_staging` OPTIONS(location='US',default_table_expiration_days=7);
CREATE TABLE IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions.web_articles`
CLUSTER BY source_domain
OPTIONS(description='GAL metadata for a provisional fixed panel of 18 Russian outlets, Russian language. date is publication-or-first-seen; raw versions retained.') AS
SELECT date AS article_date,DATE(date,'Europe/Moscow') AS day,url,domain,NET.REG_DOMAIN(url) AS source_domain,outletName AS outlet_name,title,`desc` AS description
FROM `gdelt-bq.gdeltv2.gal`
WHERE date >= TIMESTAMP('2023-01-01','Europe/Moscow') AND date < TIMESTAMP('2026-10-03','Europe/Moscow') AND lang='ru'
AND NET.REG_DOMAIN(url) IN ("ria.ru","tass.ru","rg.ru","rbc.ru","kommersant.ru","interfax.ru","iz.ru","lenta.ru","gazeta.ru","vedomosti.ru","aif.ru","mk.ru","fontanka.ru","1tv.ru","ntv.ru","vesti.ru","ren.tv","tvc.ru");

FOR batch IN (SELECT start_day,LEAST(DATE_ADD(start_day,INTERVAL 7 DAY),DATE('2026-10-03')) AS end_day
FROM UNNEST(GENERATE_DATE_ARRAY(DATE('2025-08-24'),DATE('2026-10-02'),INTERVAL 7 DAY)) AS start_day) DO
EXECUTE IMMEDIATE FORMAT("""CREATE TABLE IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions_staging.web_%s`
OPTIONS(description='Weekly surname candidates; leading punctuation: bare, guillemet, double quote') AS
SELECT date AS seen_at,DATE(date,'Europe/Moscow') AS day,NET.HOST(url) AS domain,url,ngram,pos,
CASE WHEN REGEXP_CONTAINS(LOWER(ngram),'сталин') THEN 'stalin' WHEN REGEXP_CONTAINS(LOWER(ngram),'ленин') THEN 'lenin' ELSE 'trump' END AS person
FROM `gdelt-bq.gdeltv2.webngrams` WHERE DATE(date) >= %T AND DATE(date) < %T AND lang='ru'
AND ((ngram >= 'Сталин' AND ngram < 'Сталиня') OR (ngram >= 'сталин' AND ngram < 'сталиня') OR (ngram >= 'Ленин' AND ngram < 'Лениня') OR (ngram >= 'ленин' AND ngram < 'лениня') OR (ngram >= 'Трамп' AND ngram < 'Трампя') OR (ngram >= 'трамп' AND ngram < 'трампя') OR (ngram >= '«Сталин' AND ngram < '«Сталиня') OR (ngram >= '«сталин' AND ngram < '«сталиня') OR (ngram >= '«Ленин' AND ngram < '«Лениня') OR (ngram >= '«ленин' AND ngram < '«лениня') OR (ngram >= '«Трамп' AND ngram < '«Трампя') OR (ngram >= '«трамп' AND ngram < '«трампя') OR (ngram >= '"Сталин' AND ngram < '"Сталиня') OR (ngram >= '"сталин' AND ngram < '"сталиня') OR (ngram >= '"Ленин' AND ngram < '"Лениня') OR (ngram >= '"ленин' AND ngram < '"лениня') OR (ngram >= '"Трамп' AND ngram < '"Трампя') OR (ngram >= '"трамп' AND ngram < '"трампя')) AND REGEXP_CONTAINS(LOWER(ngram),r'^[^а-яё]*(сталин(а|у|ым|е)?|ленин(а|у|ым|е)?|трамп(а|у|ом|е)?)[^а-яё]*$')""",FORMAT_DATE('%Y%m%d',batch.start_day),batch.start_day,batch.end_day);
END FOR;


CREATE TABLE IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions.web_mentions_candidates_2023_2026`
CLUSTER BY domain,person
OPTIONS(description='2023-2026 surname candidates, raw ingestion versions retained; common leading punctuation; not disambiguated person counts.') AS
SELECT * FROM `forecasting-mentions-second.forecasting_mentions.web_mentions_candidates`
UNION ALL SELECT *,_TABLE_SUFFIX AS load_week FROM `forecasting-mentions-second.forecasting_mentions_staging.web_*`;
CREATE TABLE IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions.web_load_manifest_2023_2026` AS
SELECT load_week,COUNT(*) AS rows_loaded,MIN(seen_at) AS first_seen_at,MAX(seen_at) AS last_seen_at
FROM `forecasting-mentions-second.forecasting_mentions.web_mentions_candidates_2023_2026` GROUP BY load_week;
CREATE TABLE IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions.web_batch_inventory_2023_2026` AS
SELECT * FROM `forecasting-mentions-second.forecasting_mentions.web_batch_inventory`
UNION ALL
SELECT t.table_name,PARSE_DATE('%Y%m%d',SUBSTR(t.table_name,5)) AS start_date,
LEAST(DATE_ADD(PARSE_DATE('%Y%m%d',SUBSTR(t.table_name,5)),INTERVAL 7 DAY),DATE('2026-10-03')) AS end_date_exclusive,
COALESCE(m.rows_loaded,0) AS rows_loaded
FROM `forecasting-mentions-second.forecasting_mentions_staging.INFORMATION_SCHEMA.TABLES` t
LEFT JOIN `forecasting-mentions-second.forecasting_mentions.web_load_manifest_2023_2026` m ON m.load_week=SUBSTR(t.table_name,5)
WHERE REGEXP_CONTAINS(t.table_name,r'^web_[0-9]{8}$');
SELECT COUNT(*) AS candidate_tokens,COUNT(DISTINCT url) AS unique_urls,MIN(seen_at) AS first_seen_at,
MAX(seen_at) AS last_seen_at FROM `forecasting-mentions-second.forecasting_mentions.web_mentions_candidates_2023_2026`;
