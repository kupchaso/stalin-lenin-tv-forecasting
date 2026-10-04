"""Save the exact, reviewable SQL used by the browser workflow."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STEMS=['Сталин','сталин','Ленин','ленин','Трамп','трамп']
PREFIXES=['','«','"','(','[','“']
RANGES=' OR '.join(f"(ngram >= '{p+s}' AND ngram < '{p+s}я')" for p in PREFIXES for s in STEMS)
NORMALIZED=r"^[^а-яё]*(сталин(а|у|ым|е)?|ленин(а|у|ым|е)?|трамп(а|у|ом|е)?)[^а-яё]*$"
SQL=f'''CREATE TABLE IF NOT EXISTS `forecasting-mentions-project.forecasting_mentions.web_mentions_candidates`
CLUSTER BY domain,person
OPTIONS(description='GDELT Russian-language surname candidate tokens. Raw repeated occurrences retained. Requires source/person and duplicate audit. Common leading punctuation ranges only.') AS
SELECT date AS seen_at,DATE(date,'Europe/Moscow') AS day,NET.HOST(url) AS domain,url,ngram,pos,pre,post,
CASE WHEN REGEXP_CONTAINS(LOWER(ngram),'сталин') THEN 'stalin' WHEN REGEXP_CONTAINS(LOWER(ngram),'ленин') THEN 'lenin' ELSE 'trump' END AS person
FROM `gdelt-bq.gdeltv2.webngrams`
WHERE date >= TIMESTAMP('2023-01-01') AND date < TIMESTAMP('2026-10-03') AND lang='ru'
AND ({RANGES})
AND REGEXP_CONTAINS(LOWER(ngram),r'{NORMALIZED}');
'''
(ROOT/'sql'/'01_web_mentions.sql').write_text(SQL,encoding='utf-8')
(ROOT/'sql'/'00_create_dataset.sql').write_text("CREATE SCHEMA IF NOT EXISTS `forecasting-mentions-project.forecasting_mentions` OPTIONS(location='US', description='Russian news mention forecasting: Stalin, Lenin, Trump; data from 2023');\n",encoding='utf-8')
CORE=' OR '.join(f"(ngram >= '{p+s}' AND ngram < '{p+s}я')" for p in PREFIXES[:3] for s in STEMS)
chunk=f'''CREATE TABLE IF NOT EXISTS `forecasting-mentions-project.forecasting_mentions_staging.web_%s`
OPTIONS(description='Weekly surname candidates; leading punctuation: bare, guillemet, double quote') AS
SELECT date AS seen_at,DATE(date,'Europe/Moscow') AS day,NET.HOST(url) AS domain,url,ngram,pos,
CASE WHEN REGEXP_CONTAINS(LOWER(ngram),'сталин') THEN 'stalin' WHEN REGEXP_CONTAINS(LOWER(ngram),'ленин') THEN 'lenin' ELSE 'trump' END AS person
FROM `gdelt-bq.gdeltv2.webngrams` WHERE DATE(date) >= %T AND DATE(date) < %T AND lang='ru'
AND ({CORE}) AND REGEXP_CONTAINS(LOWER(ngram),r'{NORMALIZED}')'''
batch=f'''FOR batch IN (SELECT start_day,LEAST(DATE_ADD(start_day,INTERVAL 7 DAY),DATE('2026-10-03')) AS end_day
FROM UNNEST(GENERATE_DATE_ARRAY(DATE('2023-01-08'),DATE('2026-10-02'),INTERVAL 7 DAY)) AS start_day) DO
EXECUTE IMMEDIATE FORMAT("""{chunk}""",FORMAT_DATE('%Y%m%d',batch.start_day),batch.start_day,batch.end_day);
END FOR;
'''
(ROOT/'sql'/'02_web_weekly_batches.sql').write_text(batch,encoding='utf-8')
panel=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))['provisional_russian_outlet_panel']
gal=f'''CREATE TABLE IF NOT EXISTS `forecasting-mentions-project.forecasting_mentions.web_articles`
CLUSTER BY source_domain
OPTIONS(description='GAL metadata for a provisional fixed panel of 18 Russian outlets, Russian language. date is publication-or-first-seen; raw versions retained.') AS
SELECT date AS article_date,DATE(date,'Europe/Moscow') AS day,url,domain,NET.REG_DOMAIN(url) AS source_domain,outletName AS outlet_name,title,`desc` AS description
FROM `gdelt-bq.gdeltv2.gal`
WHERE date >= TIMESTAMP('2023-01-01','Europe/Moscow') AND date < TIMESTAMP('2026-10-03','Europe/Moscow') AND lang='ru'
AND NET.REG_DOMAIN(url) IN ({','.join(json.dumps(x) for x in panel)});
'''
(ROOT/'sql'/'03_web_article_catalog.sql').write_text(gal,encoding='utf-8')
