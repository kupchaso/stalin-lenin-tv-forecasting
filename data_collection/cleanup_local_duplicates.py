"""Remove only hash-verified, reproducible local duplicates in this dataset folder."""
import datetime as dt, gzip, hashlib, json, sqlite3
from pathlib import Path
from collect_tv import ROOT, srt_to_text

workspace=ROOT.resolve()
report={'scope':str(workspace),'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'groups':{},'removed_bytes':0,'removed_files':0}

def remove_file(path,group):
    absolute=path.resolve(strict=True)
    if path.is_symlink() or not absolute.is_relative_to(workspace):
        raise ValueError('Deletion target is outside the intended folder or is a symlink')
    size=absolute.stat().st_size; absolute.unlink()
    entry=report['groups'].setdefault(group,{'files':0,'bytes':0})
    entry['files']+=1; entry['bytes']+=size; report['removed_bytes']+=size; report['removed_files']+=1

def digest_stream(stream):
    digest=hashlib.sha256()
    for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()

def save():
    (ROOT/'audit'/'local_cleanup.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

try:
    manifest=json.loads((ROOT/'audit'/'tv_upload_manifest.json').read_text())
    for name,item in manifest.items():
        raw=ROOT/'data'/(name+'.jsonl'); archive=ROOT/'data'/'bigquery_upload'/(name+'.jsonl.gz')
        if not raw.exists(): continue
        with raw.open('rb') as src: raw_sha=digest_stream(src)
        with gzip.open(archive,'rb') as src: archived_sha=digest_stream(src)
        if raw_sha!=archived_sha or raw_sha!=item['source_sha256']:
            raise ValueError('Export archive is not an identical verified copy: '+name)
        remove_file(raw,'uncompressed_export_duplicates'); save()
    with sqlite3.connect(ROOT/'data'/'tv.sqlite') as db:
        for index,(sid,source_sha,text_sha) in enumerate(db.execute("SELECT id,source_sha256,sha256 FROM broadcast WHERE status='200' AND source_format='srt'"),1):
            cache=ROOT/'data'/'tv_transcripts'/sid[:4]/(sid+'.txt.gz')
            if not cache.exists(): continue
            original=ROOT/'data'/'tv_subtitles'/sid[:4]/(sid+'.srt.gz')
            raw=gzip.decompress(original.read_bytes()); body=srt_to_text(raw).encode('utf-8')
            if hashlib.sha256(raw).hexdigest()!=source_sha or hashlib.sha256(body).hexdigest()!=text_sha or hashlib.sha256(gzip.decompress(cache.read_bytes())).hexdigest()!=text_sha:
                raise ValueError('Subtitle is not an exact recoverable replacement: '+sid)
            remove_file(cache,'derived_srt_text_duplicates')
            if index%5000==0: save(); print(json.dumps({'checked_srt':index,'removed_bytes':report['removed_bytes']}),flush=True)
    sample=ROOT/'audit'/'srt_sample.srt'
    if sample.exists():
        original=ROOT/'data'/'tv_subtitles'/'1TV_'/'1TV_20261001_000000_Novosti.srt.gz'
        if sample.read_bytes()==gzip.decompress(original.read_bytes()): remove_file(sample,'duplicate_probe_sample')
    cache=ROOT/'__pycache__'
    if cache.exists():
        for path in cache.glob('*.pyc'): remove_file(path,'python_bytecode_cache')
        if not any(cache.iterdir()):
            if not cache.resolve().is_relative_to(workspace): raise ValueError('Cache directory outside project')
            cache.rmdir()
    report['state']='complete'
except Exception as error:
    report['state']='stopped_on_verification_error'; report['error']=str(error); raise
finally:
    report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat(); save(); print(json.dumps(report),flush=True)
