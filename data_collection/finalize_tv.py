"""Wait for the already-running TV collector, then export its completed results."""
import argparse, datetime as dt, json, sqlite3, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(); parser.add_argument('--retry-errors',action='store_true'); args=parser.parse_args()
last_change=time.monotonic(); last=None
while True:
    try: current=json.loads((ROOT/'audit'/'tv_progress.json').read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError): time.sleep(3); continue
    if current!=last: last=current; last_change=time.monotonic()
    if current.get('stage')=='complete':
        if args.retry_errors:
            import collect_tv
            for attempt in range(2):
                with sqlite3.connect(ROOT/'data'/'tv.sqlite') as db:
                    errors=db.execute("SELECT COUNT(*) FROM broadcast WHERE status IS NULL OR status NOT IN ('200','404')").fetchone()[0]
                if not errors: break
                print(json.dumps({'retry_network_errors':errors,'pass':attempt+1}),flush=True)
                sys.argv=['collect_tv.py','--transcripts-only','--workers','48']
                collect_tv.main()
            current=json.loads((ROOT/'audit'/'tv_progress.json').read_text(encoding='utf-8'))
        import export_tv
        export_tv.main()
        import audit_tv_coverage
        audit_tv_coverage.main()
        result={'state':'tv_local_collection_and_export_complete','completed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'progress':current,'bigquery_upload':'pending'}
        if args.retry_errors:
            result['integrity_exit_code']=subprocess.run([sys.executable,str(ROOT/'verify_saved.py')],cwd=ROOT.parent).returncode
            with sqlite3.connect(ROOT/'data'/'tv.sqlite') as db:
                totals=dict(db.execute('SELECT status,COUNT(*) FROM broadcast GROUP BY status'))
            result['final_status_counts']=totals
            result['errors_remaining']=sum(n for status,n in totals.items() if status not in ('200','404'))
            if result['errors_remaining'] or result['integrity_exit_code']:
                result['state']='tv_retry_finished_with_unresolved_errors'
            for path in (ROOT/'config.json', ROOT/'audit'/'second_run.json'):
                state=json.loads(path.read_text(encoding='utf-8'))
                state.update(tv_transcripts_saved=totals.get('200',0),tv_transcripts_not_found=totals.get('404',0),tv_pending_transcripts=result['errors_remaining'],tv_bigquery_upload='pending',tv_retry_completed_at=result['completed_at'])
                path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
            (ROOT/'audit'/'tv_retry_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (ROOT/'audit'/'tv_completion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result),flush=True); break
    if time.monotonic()-last_change>900:
        result={'state':'collector_progress_stalled','last_progress':current}; (ROOT/'audit'/'tv_completion.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); raise SystemExit('Collector has not updated progress for 15 minutes; exports not overwritten.')
    time.sleep(3)
