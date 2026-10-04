import json, sqlite3, gzip, hashlib
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'sources'
OUT.mkdir(parents=True, exist_ok=True)
attachments = Path(r'C:\Users\user\.codex\attachments')
names = ['Forecasting Project Instructions (1).pdf','Forecasting Project Instructions.pdf',
         'L1 Forecast Evaluation A (1).pdf','L1 Forecast Evaluation B (1).pdf',
         'L2 Bayesian Mechanics B.pdf','L3 Bayesian Computation.pdf',
         'L4 Hierarchical Modeling.pdf','L5 Sequential Forecasting.pdf']
for name in names:
    matches = list(attachments.glob('*/'+name))
    if not matches: continue
    p = matches[0]
    reader = PdfReader(p)
    txt = '\n\n'.join(f'=== PAGE {i+1} ===\n'+(page.extract_text() or '') for i,page in enumerate(reader.pages))
    (OUT/(p.stem+'.txt')).write_text(txt, encoding='utf-8')
    print(name, 'pages',len(reader.pages),'sha256',hashlib.sha256(p.read_bytes()).hexdigest())
for name in ['HA4_Hierarchical_Models.ipynb','S4_Hierarchical_Models.ipynb','ha15491_6191_3.ipynb']:
    p = next(attachments.glob('*/'+name))
    nb=json.loads(p.read_text(encoding='utf-8'))
    text='\n\n'.join(f'=== CELL {i} {c["cell_type"]} ===\n'+''.join(c['source']) for i,c in enumerate(nb['cells']))
    (OUT/(p.stem+'.txt')).write_text(text,encoding='utf-8')
db=ROOT/'data_collection/data/tv.sqlite'
con=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)
for name,sql in con.execute("select name,sql from sqlite_master where type='table'"):
    print(name,sql)
p=ROOT/'data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz'
with gzip.open(p,'rt',encoding='utf-8') as f:
    for line in f:
        row=json.loads(line)
        if row.get('channel')=='RUSSIA1':
            print('coverage sample',json.dumps(row,ensure_ascii=False));break
