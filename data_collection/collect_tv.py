"""Download public GDELT Russian TV inventories/transcripts; resumable, TLS verified."""
import argparse, concurrent.futures as cf, datetime as dt, gzip, hashlib, http.client, json, re, sqlite3, threading, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = 'https://storage.googleapis.com/data.gdeltproject.org/gdeltv3/iatv/visualexplorer/'
CHANNELS = ('1TV', 'NTV', 'RUSSIA1', 'RUSSIA24')
LOCAL = threading.local()
PATTERNS = {p: re.compile(r'(?<![а-яё])' + s + r'(?![а-яё])', re.I) for p,s in {
    'stalin': r'сталин(?:а|у|ым|е)?', 'lenin': r'ленин(?:а|у|ым|е)?', 'trump': r'трамп(?:а|у|ом|е)?'}.items()}

def fetch(url):
    for attempt in range(3):
        try:
            if not hasattr(LOCAL,'connection'):
                LOCAL.connection=http.client.HTTPSConnection('storage.googleapis.com',timeout=25)
            LOCAL.connection.request('GET',url.removeprefix('https://storage.googleapis.com'),headers={'User-Agent':'ResearchMentions/1.0'})
            response=LOCAL.connection.getresponse(); body=response.read(); status=response.status
            if status==200: return status,body
            if status==404: return status,b''
        except Exception as e:
            status = str(e)
            if hasattr(LOCAL,'connection'): LOCAL.connection.close(); del LOCAL.connection
        if attempt < 2: time.sleep(1 + attempt)
    return status, b''

def inventory(task):
    channel, day = task
    path = ROOT/'data'/'tv_inventories'/f'{channel}.{day}.json.gz'
    url = BASE+f'{channel}.{day}.inventory.json'
    if path.exists():
        body = gzip.decompress(path.read_bytes()); status = 200
    else:
        status, body = fetch(url)
        if status == 200:
            json.loads(body)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(body, mtime=0))
    return channel, day, status, body, url

def transcript(show):
    sid = show['id']; path = ROOT/'data'/'tv_transcripts'/sid[:4]/(sid+'.txt.gz')
    url = BASE+sid+'.transcript.txt'
    srt_path=ROOT/'data'/'tv_subtitles'/sid[:4]/(sid+'.srt.gz')
    source_format='txt'; source_sha=None
    body=None
    if path.exists():
        try: body = gzip.decompress(path.read_bytes()); status = 200
        except (OSError,EOFError): pass
        if body is not None and srt_path.exists():
            source_format='srt'; url=BASE+sid+'.transcript.srt'
            source_sha=hashlib.sha256(gzip.decompress(srt_path.read_bytes())).hexdigest()
    if body is None and srt_path.exists():
        raw_srt=gzip.decompress(srt_path.read_bytes())
        body=srt_to_text(raw_srt).encode('utf-8'); status=200
        source_format='srt'; url=BASE+sid+'.transcript.srt'
        source_sha=hashlib.sha256(raw_srt).hexdigest()
    if body is None:
        status, body = fetch(url)
        if status==404:
            url=BASE+sid+'.transcript.srt'
            status, raw_srt=fetch(url)
            if status==200:
                body=srt_to_text(raw_srt).encode('utf-8')
                source_format='srt'; source_sha=hashlib.sha256(raw_srt).hexdigest()
                srt_path.parent.mkdir(parents=True,exist_ok=True)
                tmp=srt_path.with_suffix('.partial'); tmp.write_bytes(gzip.compress(raw_srt,mtime=0)); tmp.replace(srt_path)
        if status == 200 and source_format=='txt':
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp=path.with_suffix('.partial'); tmp.write_bytes(gzip.compress(body, mtime=0)); tmp.replace(path)
    text = body.decode('utf-8-sig', errors='replace')
    matches={p:list(pattern.finditer(text)) for p,pattern in PATTERNS.items()} if status==200 else {}
    counts = {p:len(m) for p,m in matches.items()} if status == 200 else None
    contexts = []
    if status == 200:
        for p, found in matches.items():
            for m in found:
                contexts.append({'person':p,'offset':m.start(),'matched':m.group(),'context':text[max(0,m.start()-100):m.end()+100]})
    text_sha=hashlib.sha256(body).hexdigest() if status==200 else None
    return sid, status, len(re.findall(r'\w+',text)), counts, contexts, text_sha, url, source_format, source_sha or text_sha

def srt_to_text(body):
    """Keep each cue's speech once; exclude cue indexes and timing metadata."""
    text=body.decode('utf-8-sig')
    if not text.strip(): return ''
    cues=[]
    for block in re.split(r'\r?\n\s*\r?\n',text.strip()):
        lines=block.splitlines()
        timing=next((i for i,line in enumerate(lines) if re.match(r'^\d{2,}:\d{2}:\d{2}[,.]\d+\s*-->\s*\d{2,}:\d{2}:\d{2}[,.]\d+',line.strip())),None)
        if timing is None:
            raise ValueError('SRT block lacks a valid timecode')
        speech=' '.join(line.strip() for line in lines[timing+1:] if line.strip())
        if speech: cues.append(speech)
    return '\n'.join(cues)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--start',default='2023-01-01'); parser.add_argument('--end',default='2026-10-02'); parser.add_argument('--workers',type=int,default=96); parser.add_argument('--transcripts-only',action='store_true'); parser.add_argument('--retry-missing',action='store_true',help='Retry unavailable inventories and HTTP 404 transcripts; retain successful downloads')
    args=parser.parse_args(); (ROOT/'audit').mkdir(exist_ok=True)
    db=sqlite3.connect(ROOT/'data'/'tv.sqlite'); db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''CREATE TABLE IF NOT EXISTS inventory(channel TEXT,day TEXT,status TEXT,url TEXT,retrieved_at TEXT, PRIMARY KEY(channel,day));
    CREATE TABLE IF NOT EXISTS broadcast(id TEXT PRIMARY KEY,channel TEXT,day TEXT,metadata TEXT,status TEXT,word_count INTEGER,counts TEXT,contexts TEXT,sha256 TEXT,url TEXT,retrieved_at TEXT);''')
    columns={r[1] for r in db.execute('PRAGMA table_info(broadcast)')}
    for column in ('source_format','source_sha256'):
        if column not in columns: db.execute('ALTER TABLE broadcast ADD COLUMN '+column+' TEXT')
    start=dt.date.fromisoformat(args.start); end=dt.date.fromisoformat(args.end)
    tasks=[(c,(start+dt.timedelta(days=i)).strftime('%Y%m%d')) for i in range((end-start).days+1) for c in CHANNELS]
    if args.retry_missing:
        successful={(c,day) for c,day in db.execute("SELECT channel,day FROM inventory WHERE status='200'")}
        tasks=[t for t in tasks if t not in successful]
    def progress(stage,done,total,**extra):
        report={'stage':stage,'done':done,'total':total,'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),**extra}
        (ROOT/'audit'/'tv_progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(report),flush=True)
    if args.transcripts_only: tasks=[]
    done=0
    with cf.ThreadPoolExecutor(args.workers) as pool:
        futures={pool.submit(inventory,t):t for t in tasks}; done=0
        for f in cf.as_completed(futures):
            c,day,status,body,url=f.result(); now=dt.datetime.now(dt.timezone.utc).isoformat()
            db.execute('INSERT OR REPLACE INTO inventory VALUES(?,?,?,?,?)',(c,day,str(status),url,now))
            if status==200:
                for show in json.loads(body).get('shows',[]):
                    db.execute('INSERT OR IGNORE INTO broadcast(id,channel,day,metadata) VALUES(?,?,?,?)',(show['id'],c,day,json.dumps(show,ensure_ascii=False)))
            done+=1
            if done%100==0: db.commit(); progress('inventories',done,len(tasks))
    db.commit(); progress('inventories',done,len(tasks))
    condition="status IS NULL OR status!='200'" if args.retry_missing else "status IS NULL OR status NOT IN ('200','404')"
    shows=[json.loads(row[0]) for row in db.execute('SELECT metadata FROM broadcast WHERE ('+condition+') AND day BETWEEN ? AND ?', (start.strftime('%Y%m%d'),end.strftime('%Y%m%d')))]
    progress('transcripts',0,len(shows)); done=0; ok=0; missing=0
    with cf.ThreadPoolExecutor(args.workers) as pool:
        futures={pool.submit(transcript,s):s['id'] for s in shows}
        for f in cf.as_completed(futures):
            sid,status,words,counts,contexts,sha,url,source_format,source_sha=f.result(); now=dt.datetime.now(dt.timezone.utc).isoformat()
            db.execute('UPDATE broadcast SET status=?,word_count=?,counts=?,contexts=?,sha256=?,url=?,retrieved_at=?,source_format=?,source_sha256=? WHERE id=?',(str(status),words,json.dumps(counts),json.dumps(contexts,ensure_ascii=False),sha,url,now,source_format,source_sha,sid))
            done+=1; ok+=status==200; missing+=status==404
            if done%500==0: db.commit(); progress('transcripts',done,len(shows),downloaded=ok,not_found=missing)
    db.commit(); progress('complete',done,len(shows),downloaded=ok,not_found=missing)
    db.close()

if __name__=='__main__': main()
