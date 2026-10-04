"""Reconcile files saved before interruption; never downloads anything."""
import datetime as dt, gzip, hashlib, json, sqlite3
from pathlib import Path
from collect_tv import ROOT, BASE, PATTERNS, srt_to_text
import re

def main():
    db=sqlite3.connect(ROOT/'data'/'tv.sqlite')
    recovered=0; corrupt=[]
    files={p.name.removesuffix('.txt.gz'):p for p in (ROOT/'data'/'tv_transcripts').rglob('*.txt.gz')}
    files.update({p.name.removesuffix('.srt.gz'):p for p in (ROOT/'data'/'tv_subtitles').rglob('*.srt.gz')})
    for sid,path in files.items():
        row=db.execute('SELECT status FROM broadcast WHERE id=?',(sid,)).fetchone()
        if row and row[0]=='200': continue
        try:
            raw=gzip.decompress(path.read_bytes())
            body=srt_to_text(raw).encode('utf-8') if path.name.endswith('.srt.gz') else raw
        except (OSError,EOFError): corrupt.append(str(path.relative_to(ROOT))); continue
        text=body.decode('utf-8-sig',errors='replace'); matches={p:list(rx.finditer(text)) for p,rx in PATTERNS.items()}
        counts={p:len(ms) for p,ms in matches.items()}
        contexts=[{'person':p,'offset':m.start(),'matched':m.group(),'context':text[max(0,m.start()-100):m.end()+100]} for p,ms in matches.items() for m in ms]
        when=dt.datetime.fromtimestamp(path.stat().st_mtime,dt.timezone.utc).isoformat()
        db.execute('UPDATE broadcast SET status=?,word_count=?,counts=?,contexts=?,sha256=?,url=?,retrieved_at=? WHERE id=?',('200',len(re.findall(r'\w+',text)),json.dumps(counts),json.dumps(contexts,ensure_ascii=False),hashlib.sha256(body).hexdigest(),BASE+sid+'.transcript.txt',when,sid)); recovered+=1
        srt_path=ROOT/'data'/'tv_subtitles'/sid[:4]/(sid+'.srt.gz')
        if srt_path.exists():
            raw=gzip.decompress(srt_path.read_bytes())
            db.execute('UPDATE broadcast SET source_format=?,source_sha256=?,url=? WHERE id=?',('srt',hashlib.sha256(raw).hexdigest(),BASE+sid+'.transcript.srt',sid))
    db.commit(); db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    summary={'state':'stopped_at_user_request','cached_transcripts_recovered':recovered,'corrupt_cache_files':corrupt,'broadcasts_by_status':{str(r[0]):r[1] for r in db.execute('SELECT status,COUNT(*) FROM broadcast GROUP BY status')},'stopped_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    (ROOT/'audit'/'checkpoint.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(summary)); db.close()
    import export_tv
    export_tv.main()

if __name__=='__main__': main()
