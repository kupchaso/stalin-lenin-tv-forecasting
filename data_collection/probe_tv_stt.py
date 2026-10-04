"""Check the documented raw STT JSON alternative for remaining unavailable shows."""
import concurrent.futures as cf, gzip, json, sqlite3
from collect_tv import ROOT, BASE, fetch

def probe(sid):
    url=BASE+sid+'.stt.latest_long.json'
    status,body=fetch(url)
    item={'id':sid,'url':url,'status':status,'bytes':len(body)}
    if status==200:
        parsed=json.loads(body)
        item['top_level_keys']=list(parsed) if isinstance(parsed,dict) else None
        path=ROOT/'data'/'tv_stt_json'/sid[:4]/(sid+'.json.gz'); path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(gzip.compress(body,mtime=0))
    return item

with sqlite3.connect(ROOT/'data'/'tv.sqlite') as db:
    ids=[r[0] for r in db.execute("SELECT id FROM broadcast WHERE status='404'")]
results=list(cf.ThreadPoolExecutor(16).map(probe,ids))
(ROOT/'audit'/'tv_stt_probe.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps({'checked':len(results),'statuses':{str(s):sum(r['status']==s for r in results) for s in set(r['status'] for r in results)},'available_examples':[r for r in results if r['status']==200][:2]}))
