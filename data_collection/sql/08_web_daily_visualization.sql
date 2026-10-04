-- Read only the collected tables, never the original GDELT corpus.
-- One earliest observed candidate-containing snapshot per URL; retain every occurrence.
-- pos is an article decile, NOT a unique token position: never deduplicate by pos.
-- Keep the same leading punctuation filter for every week of the collection.
WITH base AS (
  SELECT seen_at, DATE(seen_at, 'Europe/Moscow') AS day,
    NET.REG_DOMAIN(url) AS source, url, person
  FROM `forecasting-mentions-second.forecasting_mentions.web_mentions_candidates_2023_2026`
  WHERE seen_at >= TIMESTAMP('2023-01-01', 'Europe/Moscow')
    AND seen_at < TIMESTAMP('2026-10-03', 'Europe/Moscow')
    AND NET.REG_DOMAIN(url) IN (
      'ria.ru','tass.ru','rg.ru','rbc.ru','kommersant.ru','interfax.ru',
      'iz.ru','lenta.ru','gazeta.ru','vedomosti.ru','aif.ru','mk.ru',
      'fontanka.ru','1tv.ru','ntv.ru','vesti.ru','ren.tv','tvc.ru')
    AND REGEXP_CONTAINS(ngram, r'^[«"]?[СсЛлТт]')
), snapshots AS (
  SELECT * FROM base
  QUALIFY seen_at = MIN(seen_at) OVER (PARTITION BY url)
), mentions AS (
  SELECT day, source,
    COUNTIF(person='stalin') AS stalin_candidates,
    COUNTIF(person='lenin') AS lenin_candidates,
    COUNTIF(person='trump') AS trump_candidates,
    COUNT(DISTINCT url) AS candidate_articles
  FROM snapshots GROUP BY day, source
), raw AS (
  SELECT day, source, COUNT(*) AS raw_candidate_rows
  FROM base GROUP BY day, source
), catalog AS (
  SELECT day, source_domain AS source, COUNT(DISTINCT url) AS catalog_articles
  FROM `forecasting-mentions-second.forecasting_mentions.web_articles`
  WHERE day >= '2023-01-01' AND day < '2026-10-03'
  GROUP BY day, source
), keys AS (
  SELECT day, source FROM mentions UNION DISTINCT
  SELECT day, source FROM raw UNION DISTINCT
  SELECT day, source FROM catalog
)
SELECT k.day, k.source,
  COALESCE(m.stalin_candidates,0) AS stalin_candidates,
  COALESCE(m.lenin_candidates,0) AS lenin_candidates,
  COALESCE(m.trump_candidates,0) AS trump_candidates,
  COALESCE(m.candidate_articles,0) AS candidate_articles,
  COALESCE(r.raw_candidate_rows,0) AS raw_candidate_rows,
  COALESCE(c.catalog_articles,0) AS catalog_articles
FROM keys k
LEFT JOIN mentions m USING(day,source)
LEFT JOIN raw r USING(day,source)
LEFT JOIN catalog c USING(day,source)
ORDER BY k.day,k.source;
