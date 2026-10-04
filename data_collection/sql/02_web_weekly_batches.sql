FOR batch IN (SELECT start_day,LEAST(DATE_ADD(start_day,INTERVAL 7 DAY),DATE('2026-10-03')) AS end_day
FROM UNNEST(GENERATE_DATE_ARRAY(DATE('2023-01-08'),DATE('2026-10-02'),INTERVAL 7 DAY)) AS start_day) DO
EXECUTE IMMEDIATE FORMAT("""CREATE TABLE IF NOT EXISTS `forecasting-mentions-project.forecasting_mentions_staging.web_%s`
OPTIONS(description='Weekly surname candidates; leading punctuation: bare, guillemet, double quote') AS
SELECT date AS seen_at,DATE(date,'Europe/Moscow') AS day,NET.HOST(url) AS domain,url,ngram,pos,
CASE WHEN REGEXP_CONTAINS(LOWER(ngram),'сталин') THEN 'stalin' WHEN REGEXP_CONTAINS(LOWER(ngram),'ленин') THEN 'lenin' ELSE 'trump' END AS person
FROM `gdelt-bq.gdeltv2.webngrams` WHERE DATE(date) >= %T AND DATE(date) < %T AND lang='ru'
AND ((ngram >= 'Сталин' AND ngram < 'Сталиня') OR (ngram >= 'сталин' AND ngram < 'сталиня') OR (ngram >= 'Ленин' AND ngram < 'Лениня') OR (ngram >= 'ленин' AND ngram < 'лениня') OR (ngram >= 'Трамп' AND ngram < 'Трампя') OR (ngram >= 'трамп' AND ngram < 'трампя') OR (ngram >= '«Сталин' AND ngram < '«Сталиня') OR (ngram >= '«сталин' AND ngram < '«сталиня') OR (ngram >= '«Ленин' AND ngram < '«Лениня') OR (ngram >= '«ленин' AND ngram < '«лениня') OR (ngram >= '«Трамп' AND ngram < '«Трампя') OR (ngram >= '«трамп' AND ngram < '«трампя') OR (ngram >= '"Сталин' AND ngram < '"Сталиня') OR (ngram >= '"сталин' AND ngram < '"сталиня') OR (ngram >= '"Ленин' AND ngram < '"Лениня') OR (ngram >= '"ленин' AND ngram < '"лениня') OR (ngram >= '"Трамп' AND ngram < '"Трампя') OR (ngram >= '"трамп' AND ngram < '"трампя')) AND REGEXP_CONTAINS(LOWER(ngram),r'^[^а-яё]*(сталин(а|у|ым|е)?|ленин(а|у|ым|е)?|трамп(а|у|ом|е)?)[^а-яё]*$')""",FORMAT_DATE('%Y%m%d',batch.start_day),batch.start_day,batch.end_day);
END FOR;
