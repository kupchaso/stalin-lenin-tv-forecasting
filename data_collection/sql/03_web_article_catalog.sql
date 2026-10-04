CREATE TABLE IF NOT EXISTS `forecasting-mentions-project.forecasting_mentions.web_articles`
CLUSTER BY source_domain
OPTIONS(description='GAL metadata for a provisional fixed panel of 18 Russian outlets, Russian language. date is publication-or-first-seen; raw versions retained.') AS
SELECT date AS article_date,DATE(date,'Europe/Moscow') AS day,url,domain,NET.REG_DOMAIN(url) AS source_domain,outletName AS outlet_name,title,`desc` AS description
FROM `gdelt-bq.gdeltv2.gal`
WHERE date >= TIMESTAMP('2023-01-01','Europe/Moscow') AND date < TIMESTAMP('2026-10-03','Europe/Moscow') AND lang='ru'
AND NET.REG_DOMAIN(url) IN ("ria.ru","tass.ru","rg.ru","rbc.ru","kommersant.ru","interfax.ru","iz.ru","lenta.ru","gazeta.ru","vedomosti.ru","aif.ru","mk.ru","fontanka.ru","1tv.ru","ntv.ru","vesti.ru","ren.tv","tvc.ru");
