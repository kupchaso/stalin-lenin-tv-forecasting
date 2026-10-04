"""Verify every saved transcript against its stored checksum; no network."""
import gzip, hashlib, json, sqlite3
from collect_tv import srt_to_text
from pathlib import Path
ROOT=Path(__file__).resolve().parent
db=sqlite3.connect(ROOT/'data'/'tv.sqlite')
checked=0; srt_checked=0; errors=[]; compressed=0; derived=0
for sid,text_sha,fmt,source_sha in db.execute("SELECT id,sha256,COALESCE(source_format,'txt'),source_sha256 FROM broadcast WHERE status='200'"):
    path=ROOT/'data'/('tv_subtitles' if fmt=='srt' else 'tv_transcripts')/sid[:4]/(sid+('.srt.gz' if fmt=='srt' else '.txt.gz'))
    try:
        raw=gzip.decompress(path.read_bytes()); compressed+=path.stat().st_size
        body=srt_to_text(raw).encode('utf-8') if fmt=='srt' else raw
        if hashlib.sha256(raw).hexdigest()!=(source_sha or text_sha) or hashlib.sha256(body).hexdigest()!=text_sha:
            errors.append({'id':sid,'error':'original source or extracted text checksum mismatch'})
        checked+=1; srt_checked+=fmt=='srt'
        cache=ROOT/'data'/'tv_transcripts'/sid[:4]/(sid+'.txt.gz')
        if fmt=='srt' and cache.exists():
            derived+=1
            if hashlib.sha256(gzip.decompress(cache.read_bytes())).hexdigest()!=text_sha:
                errors.append({'id':sid,'error':'derived cache checksum mismatch'})
    except (OSError,EOFError,ValueError,UnicodeError) as e: errors.append({'id':sid,'error':str(e)})
report={'verified_transcript_files':checked,'verified_original_srt_files':srt_checked,'derived_cache_files':derived,'compressed_source_bytes':compressed,'errors':errors,'data_folder_bytes':sum(p.stat().st_size for p in (ROOT/'data').rglob('*') if p.is_file()),'local_tv_export_bytes':{str(p.relative_to(ROOT/'data')):p.stat().st_size for p in (ROOT/'data').rglob('*.jsonl*')}}
(ROOT/'audit'/'integrity.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(report)); db.close()
raise SystemExit(bool(errors))
