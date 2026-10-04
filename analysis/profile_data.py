import json, gzip, sqlite3
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data_collection'
with gzip.open(BASE/'data/bigquery_upload/tv_daily_coverage.jsonl.gz','rt',encoding='utf-8') as f:
    d=pd.DataFrame(json.loads(line) for line in f)
d=d[d.channel=='RUSSIA1'].copy()
print('coverage',d.coverage_status.value_counts().to_dict())
print('dates',d.day.min(),d.day.max(),'total',d.stalin_candidates.sum())
print(d[['stalin_candidates','observed_word_count','available_transcripts']].describe().to_string())
d['year']=d.day.str[:4]
print(d.groupby('year').agg(days=('day','size'),sum=('stalin_candidates','sum'),mean=('stalin_candidates','mean'),var=('stalin_candidates','var'),words=('observed_word_count','mean')).to_string())
print('incomplete',d[d.coverage_status!='observed_listed_broadcasts'][['day','available_transcripts','listed_broadcasts','inventory_status']].to_string(index=False))
print('monthly',d.assign(month=d.day.str[:7]).groupby('month').stalin_candidates.sum().to_string())
con=sqlite3.connect((BASE/'data/tv.sqlite').as_uri()+'?mode=ro',uri=True)
print('metadata',con.execute("select metadata from broadcast where channel='RUSSIA1' limit 1").fetchone())
contexts=[]
for sid,metadata,c in con.execute("select id,metadata,contexts from broadcast where channel='RUSSIA1' and counts is not null"):
    for x in json.loads(c or '[]'):
        if x.get('person')=='stalin': contexts.append({'broadcast_id':sid,**x})
print('contexts',len(contexts),'sample',contexts[:4])
(ROOT/'analysis'/'stalin_contexts.json').write_text(json.dumps(contexts,ensure_ascii=False),encoding='utf-8')
if contexts:
    print('last sample',contexts[-4:])
