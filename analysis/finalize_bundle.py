import sys,json,zipfile,hashlib,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'deps'))
import nbformat
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/stalin_russia1'
copy=(ROOT/'analysis/stalin_models.py').read_text(encoding='utf-8')
copy=copy.replace('ROOT=Path(__file__).resolve().parents[1]',"ROOT=next(p for p in Path(__file__).resolve().parents if (p/'data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz').exists())")
(OUT/'stalin_models.py').write_text(copy,encoding='utf-8')
shutil.copy2(ROOT/'analysis/verify_forecast.py',OUT/'verify_forecast.py')
nb=nbformat.read(OUT/'stalin_russia1_forecast.ipynb',as_version=4)
nbformat.validate(nb)
codes=[c for c in nb.cells if c.cell_type=='code']
assert all(c.execution_count is not None for c in codes)
assert not any(o.output_type=='error' for c in codes for o in c.outputs)
assert sum(o.output_type=='display_data' and 'image/png' in o.data for c in codes for o in c.outputs)==4
assert json.loads((OUT/'verification.json').read_text())['status']=='passed'
daily_path=OUT/'stalin_russia1_daily_forecast.ipynb'
daily_nb=nbformat.read(daily_path,as_version=4)
nbformat.validate(daily_nb)
daily_codes=[c for c in daily_nb.cells if c.cell_type=='code']
assert all(c.execution_count is not None for c in daily_codes)
assert not any(o.output_type=='error' for c in daily_codes for o in c.outputs)
daily_figures=sum(o.output_type=='display_data' and 'image/png' in o.data for c in daily_codes for o in c.outputs)
assert daily_figures==10
assert json.loads((OUT/'daily_notebook_validation.json').read_text())['status']=='passed'
wide=pd.read_csv(OUT/'forecast_daily_all_models.csv')
assert len(wide)==31 and all(m+'_mean' in wide for m in ['M1','M2','M3','M4'])
fc=pd.read_csv(OUT/'forecast_month.csv')
assert round(fc.loc[fc.model=='M4','mean'].iloc[0],2)==28.60
requirements=(OUT/'requirements.txt').read_text(encoding='utf-8')
run='''# Воспроизведение проекта

Распакуйте архив целиком и откройте output/stalin_russia1/stalin_russia1_daily_forecast.ipynb.
Установите зависимости из requirements.txt в Python 3.12, затем выполните Run All.
Все данные для расчёта уже включены. Внешние подключения и повторное скачивание не нужны.

Выполненная тетрадка открывается и без нового расчёта: в ней сохранены таблицы и 10 графиков.
Прогноз каждого дня для всех моделей: output/stalin_russia1/forecast_daily_all_models.csv.
Предыдущая тетрадка с подробным месячным исследованием: output/stalin_russia1/stalin_russia1_forecast.ipynb.
Пояснения и ограничения: output/stalin_russia1/README.md.
Основной измеряемый ряд: кандидаты по фамилии в ASR, не полностью проверенные упоминания человека.
'''
manifest={'executed_code_cells':len(codes),'embedded_figures':4,'notebook_schema':'validated',
          'daily_executed_code_cells':len(daily_codes),'daily_embedded_figures':daily_figures,
          'forecast_checks':'passed','source_unchanged_sha256':json.loads((OUT/'metadata.json').read_text())['source_sha256']}
(OUT/'delivery_validation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
dest=OUT/'stalin_russia1_project.zip'
with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    z.writestr('START_HERE.md',run)
    z.writestr('requirements.txt',requirements)
    for p in [ROOT/'analysis/stalin_models.py',ROOT/'analysis/verify_forecast.py',
              ROOT/'data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz']:
        z.write(p,p.relative_to(ROOT).as_posix())
    for p in OUT.rglob('*'):
        if p.is_file() and p!=dest and '__pycache__' not in p.parts:
            z.write(p,p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(dest) as z:
    assert z.testzip() is None
    print('Verified',len(z.namelist()),'files in archive;',dest.stat().st_size,'bytes; notebook',len(codes),'executed cells')
print('Daily notebook:',len(daily_codes),'executed cells,',daily_figures,'embedded figures,',len(wide),'forecast dates.')
