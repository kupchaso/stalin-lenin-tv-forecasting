"""Summarize actual transcript coverage separately from archive inventories."""
import datetime as dt, json, sqlite3
from collect_tv import ROOT

def main():
    db=sqlite3.connect(ROOT/'data'/'tv.sqlite'); db.row_factory=sqlite3.Row
    report={
        'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'day_timezone':'Europe/Moscow',
        'channels':[dict(r) for r in db.execute('''SELECT channel,COUNT(*) AS available,
            MIN(json_extract(metadata,'$.start_localtime')) AS first_start_local,
            MAX(json_extract(metadata,'$.start_localtime')) AS last_start_local
            FROM broadcast WHERE status='200' GROUP BY channel''')],
        'by_year_and_status':[dict(r) for r in db.execute('''SELECT channel,
            substr(json_extract(metadata,'$.start_localtime'),1,4) AS year,
            status,COUNT(*) AS broadcasts FROM broadcast GROUP BY channel,year,status''')],
        'by_source_format':[dict(r) for r in db.execute("SELECT COALESCE(source_format,'txt') AS source_format,COUNT(*) AS available FROM broadcast WHERE status='200' GROUP BY COALESCE(source_format,'txt')")],
        'inventories_by_status':[dict(r) for r in db.execute('SELECT status,COUNT(*) AS channel_days FROM inventory GROUP BY status')],
        'empty_transcripts':db.execute("SELECT COUNT(*) FROM broadcast WHERE status='200' AND word_count=0").fetchone()[0],
        'caveat':'Dates are observed endpoints, not proof of uninterrupted coverage or news-only programming.'
    }
    (ROOT/'audit'/'tv_coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False)); db.close()

if __name__=='__main__': main()
