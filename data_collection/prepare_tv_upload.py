"""Prepare gzip JSONL and explicit schemas for the authorized BigQuery upload."""
import gzip, hashlib, json, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
schemas={
    'tv_broadcasts':{'day':'DATE','start_utc':'TIMESTAMP','retrieved_at':'TIMESTAMP',**{n:'INTEGER' for n in ('runtime_seconds','word_count','stalin_candidates','lenin_candidates','trump_candidates')}},
    'tv_daily_coverage':{'day':'DATE',**{n:'INTEGER' for n in ('listed_broadcasts','available_transcripts','missing_transcripts','pending_or_error_transcripts','observed_runtime_seconds','observed_word_count','stalin_candidates','lenin_candidates','trump_candidates')}},
    'tv_mention_contexts':{'day':'DATE','offset':'INTEGER'}
}
destination=ROOT/'data'/'bigquery_upload'; destination.mkdir(exist_ok=True)
manifest={}
for name,types in schemas.items():
    source=ROOT/'data'/(name+'.jsonl'); target=destination/(name+'.jsonl.gz')
    if source.exists():
        with source.open('rb') as src, target.open('wb') as dst, gzip.GzipFile(fileobj=dst,mode='wb',mtime=0,compresslevel=6) as compressed:
            shutil.copyfileobj(src,compressed)
    keys={}; rows=0; first=None; last=None
    with gzip.open(target,'rt',encoding='utf-8') as src:
        for line in src:
            record=json.loads(line); rows+=1
            keys.update({k:None for k in record})
            first=min(first or record['day'],record['day']); last=max(last or record['day'],record['day'])
    schema=[{'name':k,'type':types.get(k,'STRING'),'mode':'NULLABLE'} for k in keys]
    (destination/(name+'.schema.json')).write_text(json.dumps(schema,indent=2),encoding='utf-8')
    digest=hashlib.sha256()
    with gzip.open(target,'rb') as src:
        for block in iter(lambda:src.read(1024*1024),b''): digest.update(block)
    manifest[name]={'rows':rows,'first_day':first,'last_day':last,'compressed_bytes':target.stat().st_size,'source_sha256':digest.hexdigest()}
(ROOT/'audit'/'tv_upload_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest))
