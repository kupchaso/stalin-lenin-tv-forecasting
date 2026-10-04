"""Export audited broadcast-level candidates and channel/day coverage as JSONL for BigQuery."""
import datetime as dt, gzip, json, sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    db=sqlite3.connect(ROOT/'data'/'tv.sqlite'); db.row_factory=sqlite3.Row
    destination=ROOT/'data'/'bigquery_upload'; destination.mkdir(exist_ok=True)
    coverage={}
    with gzip.open(destination/'tv_broadcasts.jsonl.gz','wt',encoding='utf-8',compresslevel=6) as out, gzip.open(destination/'tv_mention_contexts.jsonl.gz','wt',encoding='utf-8',compresslevel=6) as ctxout:
        for row in db.execute('SELECT * FROM broadcast ORDER BY id'):
            m=json.loads(row['metadata']); start=m.get('start_localtime')
            day=start[:10] if start else dt.datetime.strptime(row['day'],'%Y%m%d').date().isoformat()
            if not '2023-01-01'<=day<'2026-10-03': continue
            parts=m.get('runtime','').split(':'); seconds=sum(int(x)*n for x,n in zip(parts,[3600,60,1])) if len(parts)==3 else None
            status=row['status'] or 'pending'; counts=json.loads(row['counts']) if row['counts'] else None
            item={'broadcast_id':row['id'],'channel':row['channel'],'day':day,'start_utc':m.get('start_time','').replace(' ','T')+'Z' if m.get('start_time') else None,'program':m.get('program') or None,'title':m.get('title') or None,'runtime_seconds':seconds,'transcript_status':status,'word_count':row['word_count'] if status=='200' else None,'stalin_candidates':counts.get('stalin') if counts else None,'lenin_candidates':counts.get('lenin') if counts else None,'trump_candidates':counts.get('trump') if counts else None,'transcript_sha256':row['sha256'],'transcript_url':row['url'],'retrieved_at':row['retrieved_at'],'news_filter_status':'unreviewed','person_filter_status':'surname_candidates'}
            item['source_format']=row['source_format'] or ('txt' if status=='200' else None)
            item['source_sha256']=row['source_sha256'] or row['sha256']
            out.write(json.dumps(item,ensure_ascii=False)+'\n')
            c=coverage.setdefault((row['channel'],day),{'channel':row['channel'],'day':day,'listed_broadcasts':0,'available_transcripts':0,'missing_transcripts':0,'pending_or_error_transcripts':0,'observed_runtime_seconds':0,'observed_word_count':0,'stalin_candidates':0,'lenin_candidates':0,'trump_candidates':0})
            c['listed_broadcasts']+=1
            if status=='200':
                c['available_transcripts']+=1; c['observed_runtime_seconds']+=seconds or 0; c['observed_word_count']+=row['word_count'] or 0
                for p in ('stalin','lenin','trump'): c[p+'_candidates']+=counts[p]
                for ctx in json.loads(row['contexts'] or '[]'):
                    ctxout.write(json.dumps({'broadcast_id':row['id'],'channel':row['channel'],'day':day,**ctx},ensure_ascii=False)+'\n')
            elif status=='404': c['missing_transcripts']+=1
            else: c['pending_or_error_transcripts']+=1
    start=dt.date(2023,1,1); end=dt.date(2026,10,2)
    inventories={(r['channel'],dt.datetime.strptime(r['day'],'%Y%m%d').date().isoformat()):dict(r) for r in db.execute('SELECT * FROM inventory')}
    with gzip.open(destination/'tv_daily_coverage.jsonl.gz','wt',encoding='utf-8',compresslevel=6) as out:
        for i in range((end-start).days+1):
            day=(start+dt.timedelta(days=i)).isoformat()
            for channel in ('1TV','NTV','RUSSIA1','RUSSIA24'):
                item=coverage.get((channel,day),{'channel':channel,'day':day,'listed_broadcasts':0,'available_transcripts':0,'missing_transcripts':0,'pending_or_error_transcripts':0,'observed_runtime_seconds':0,'observed_word_count':0})
                item['inventory_status']=inventories.get((channel,day),{}).get('status','pending')
                item['coverage_status']='observed_listed_broadcasts' if item['listed_broadcasts'] and item['available_transcripts']==item['listed_broadcasts'] else 'incomplete_or_missing'
                if not item['available_transcripts']:
                    for p in ('stalin','lenin','trump'): item[p+'_candidates']=None
                out.write(json.dumps(item,ensure_ascii=False)+'\n')
    audit={'broadcasts_by_status':{str(r[0]):r[1] for r in db.execute('SELECT status,COUNT(*) FROM broadcast GROUP BY status')},'inventories_by_status':{str(r[0]):r[1] for r in db.execute('SELECT status,COUNT(*) FROM inventory GROUP BY status')},'raw_texts_saved_as_gzip':True,'count_definition':'Surname-token candidates in ASR transcripts; not disambiguated person mentions','news_program_filter':'Pending; all archived broadcasts retained','day_timezone':'Europe/Moscow','exported_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    (ROOT/'audit'/'tv_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False)); db.close()

if __name__=='__main__': main()
