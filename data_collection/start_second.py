"""Prepare the continuation SQL and record which collection run was launched."""
import datetime as dt, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
first='forecasting-mentions-project'; second='forecasting-mentions-second'
resume=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))['web_resume_date']
batch=(ROOT/'sql'/'02_web_weekly_batches.sql').read_text(encoding='utf-8').replace(first,second).replace("DATE('2023-01-08')",f"DATE('{resume}')")
gal=(ROOT/'sql'/'03_web_article_catalog.sql').read_text(encoding='utf-8').replace(first,second)
finish=f'''
CREATE TABLE IF NOT EXISTS `{second}.forecasting_mentions.web_mentions_candidates_2023_2026`
CLUSTER BY domain,person
OPTIONS(description='2023-2026 surname candidates, raw ingestion versions retained; common leading punctuation; not disambiguated person counts.') AS
SELECT * FROM `{second}.forecasting_mentions.web_mentions_candidates`
UNION ALL SELECT *,_TABLE_SUFFIX AS load_week FROM `{second}.forecasting_mentions_staging.web_*`;
CREATE TABLE IF NOT EXISTS `{second}.forecasting_mentions.web_load_manifest_2023_2026` AS
SELECT load_week,COUNT(*) AS rows_loaded,MIN(seen_at) AS first_seen_at,MAX(seen_at) AS last_seen_at
FROM `{second}.forecasting_mentions.web_mentions_candidates_2023_2026` GROUP BY load_week;
CREATE TABLE IF NOT EXISTS `{second}.forecasting_mentions.web_batch_inventory_2023_2026` AS
SELECT * FROM `{second}.forecasting_mentions.web_batch_inventory`
UNION ALL
SELECT t.table_name,PARSE_DATE('%Y%m%d',SUBSTR(t.table_name,5)) AS start_date,
LEAST(DATE_ADD(PARSE_DATE('%Y%m%d',SUBSTR(t.table_name,5)),INTERVAL 7 DAY),DATE('2026-10-03')) AS end_date_exclusive,
COALESCE(m.rows_loaded,0) AS rows_loaded
FROM `{second}.forecasting_mentions_staging.INFORMATION_SCHEMA.TABLES` t
LEFT JOIN `{second}.forecasting_mentions.web_load_manifest_2023_2026` m ON m.load_week=SUBSTR(t.table_name,5)
WHERE REGEXP_CONTAINS(t.table_name,r'^web_[0-9]{{8}}$');
SELECT COUNT(*) AS candidate_tokens,COUNT(DISTINCT url) AS unique_urls,MIN(seen_at) AS first_seen_at,
MAX(seen_at) AS last_seen_at FROM `{second}.forecasting_mentions.web_mentions_candidates_2023_2026`;
'''
sql=f"CREATE SCHEMA IF NOT EXISTS `{second}.forecasting_mentions_staging` OPTIONS(location='US',default_table_expiration_days=7);\n"+gal+'\n'+batch+'\n'+finish
(ROOT/'sql'/'06_collect_second_project.sql').write_text(sql,encoding='utf-8')
state={'state':'starting','project':second,'web_resume_date':resume,'web_end_date_exclusive':'2026-10-03','tv_resume_pending':91341,'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'cloud_pipeline_sql':'sql/06_collect_second_project.sql','tv_collection_exec_session':90721,'billing_enabled_by_agent':False}
(ROOT/'audit'/'second_run.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
config=json.loads((ROOT/'config.json').read_text(encoding='utf-8')); config['active_project']=second; config['state']='collection_starting'; (ROOT/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'sql_bytes':len(sql.encode()),'project':second,'resume':resume}))

if __name__=='__main__': pass
