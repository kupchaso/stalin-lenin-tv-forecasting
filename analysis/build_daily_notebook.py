"""Build and execute a daily-focused notebook with model mechanism plots."""
from pathlib import Path
import ast, json, os, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'analysis/deps'))
import nbformat
from nbclient import NotebookClient

OUT=ROOT/'output/stalin_russia1'
source=(ROOT/'analysis/stalin_models.py').read_text(encoding='utf-8')
functions={n.name:ast.get_source_segment(source,n) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
def definitions(*names):return '\n\n'.join(functions[n] for n in names)
nb=nbformat.v4.new_notebook()
nb.metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
             'language_info':{'name':'python','version':sys.version.split()[0]}}
cells=[]
def md(s):cells.append(nbformat.v4.new_markdown_cell(s))
def code(s):cells.append(nbformat.v4.new_code_cell(s.strip()))

md('''# Россия 1: прогноз упоминаний Сталина на каждый день

**Период прогноза: 3 октября — 2 ноября 2026 года, 31 день.** Последнее наблюдение: 2 октября 2026 года. Месяц считается вперёд от этой даты, как в предыдущем расчёте.

В тетрадке есть таблица для каждого дня, четыре прогнозные модели, графики их работы и историческая оценка. Все ячейки выполнены, результаты сохранены. Прогноз строится сразу на весь месяц; будущие наблюдения не используются для обновлений внутри горизонта.

Измеряемый ряд — совпадения фамилии «Сталин» и её падежных форм в автоматических расшифровках всех сохранённых программ. Это приближение к упоминаниям Иосифа Сталина: полная ручная проверка контекстов не проведена, архив не гарантирует покрытие всего эфира. Пропуски в архиве не считаются нулями.

Модели: **M1 Gamma–Poisson → M2 Negative Binomial → M3 календарная иерархия и тренд → M4 динамический скрытый уровень**. Историческая оценка каждого расширения сохранена; улучшение по одной метрике не означает улучшения по всем метрикам.
''')
md('''## 1. Настройки

Для повторного запуска нужны папка проекта и зависимости из `requirements.txt`. Внешние подключения не требуются. По умолчанию дневной прогноз пересчитывается, а длительная историческая проверка загружается из сохранённых результатов. `RUN_BACKTEST=True` заново выполняет и эту проверку по тем же правилам.
''')
code('''from pathlib import Path
import sys, os, json
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
ROOT=next((p for p in [Path.cwd(),*Path.cwd().parents] if (p/'data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz').exists()),None)
if ROOT is None:
    raise FileNotFoundError('Распакуйте архив целиком и откройте тетрадку внутри папки проекта.')
sys.path.insert(0,str(ROOT/'analysis/deps'))
sys.path.insert(0,str(ROOT/'analysis'))
import gzip, hashlib, time
import numpy as np
import pandas as pd
from scipy.special import gammaln, digamma, logsumexp, expit
from scipy.optimize import minimize
from scipy.stats import multivariate_t, norm, rankdata, t as student_t
from scipy.linalg import helmert
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from IPython.display import display, Image
BASE=ROOT/'data_collection'
OUT=ROOT/'output/stalin_russia1'
FIG=OUT/'figures/daily_models'
FIG.mkdir(parents=True,exist_ok=True)
SEED=20261004
N_DRAWS=30000
RUN_BACKTEST=False
NAMES={'M1':'Gamma–Poisson','M2':'Negative Binomial','M3':'NB + календарь и тренд','M4':'NB + динамический уровень'}
COLORS={'M1':'#777777','M2':'#dc7c32','M3':'#396cb0','M4':'#247c68'}
DOW=['Пн','Вт','Ср','Чт','Пт','Сб','Вс']
MONTHS=['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']
plt.rcParams.update({'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False,'figure.dpi':120,'savefig.dpi':170})
def show_plot(fig,name):
    fig.tight_layout()
    path=FIG/name
    fig.savefig(path,bbox_inches='tight')
    plt.close(fig)
    display(Image(filename=str(path)))
print('Проект:',ROOT)
''')
code(definitions('load_data')+'''

d,source_hash=load_data()
meta=json.loads((OUT/'metadata.json').read_text(encoding='utf-8'))
assert source_hash==meta['source_sha256'], 'Входные данные изменились: пересчитайте историческую оценку.'
forecast_start=d.date.max()+pd.Timedelta(days=1)
forecast_end=d.date.max()+pd.DateOffset(months=1)
dates=pd.date_range(forecast_start,forecast_end)
q=float(meta['q_selected_on_development'])
print(f'Данные: {d.date.min():%d.%m.%Y} — {d.date.max():%d.%m.%Y}')
print(f'Пригодных дней: {d.observed.sum()}; исключено: {(~d.observed).sum()}')
print(f'Прогноз: {forecast_start:%d.%m.%Y} — {forecast_end:%d.%m.%Y}, {len(dates)} день; q={q}')
''')
code('''fig,axes=plt.subplots(2,1,figsize=(12,6.2))
axes[0].plot(d.date,d.y,color='#aaaaaa',lw=.6,label='Дневное количество')
axes[0].plot(d.date,d.y.rolling(28,min_periods=28).mean(),color='#333333',lw=1.7,label='Среднее за 28 дней без пропусков')
for date in d.loc[~d.observed,'date']:
    axes[0].axvline(date,color='#c95050',alpha=.18,lw=1)
axes[0].set(title='Исходный ряд и пропуски архива',ylabel='Совпадений в день')
axes[0].legend(fontsize=9)
counts=np.minimum(d.y.dropna().to_numpy(int),12)
freq=np.bincount(counts,minlength=13)/len(counts)
axes[1].bar(range(13),freq,color='#5f7891')
axes[1].set(xticks=range(13),xticklabels=[str(x) for x in range(12)]+['12+'],xlabel='Дневное количество',ylabel='Доля наблюдаемых дней',title='Нули и редкие всплески')
show_plot(fig,'01_data.png')
''')
md('''## 2. Общие вычисления для Bayesian моделей

Для M2/M3 используется Metropolis–Hastings: четыре цепи по 1 200 сохранённых draws после warmup. Нормальная аппроксимация около моды нужна только для построения предложения; принятие считается по точной posterior плотности. Код проверяет rank-normalized split/folded R-hat и ESS по автокорреляциям.
''')
code(definitions('nb_logpmf','design','posterior_problem','diagnostics','fit_nb','static_predict'))
md(r'''## 3. M1: постоянный уровень

$$Y_tmidlambdasimmathrm{Poisson}(lambda),qquad lambdasimmathrm{Gamma}(1,1).$$

После наблюдений Gamma posterior рассчитывается аналитически. В каждой будущей траектории один общий draw интенсивности используется для всех дней. Поэтому модель даёт одинаковое ожидаемое количество по дням и сохраняет зависимость из-за неизвестного общего уровня.
''')
code('''prediction_seed=SEED+5000
rng=np.random.default_rng(prediction_seed)
shape=1+d.y.sum()
rate=1+d.observed.sum()
lambda_draws=rng.gamma(shape,1/rate,N_DRAWS)
mu1=np.repeat(lambda_draws[:,None],len(dates),axis=1)
forecasts={'M1':(rng.poisson(mu1),mu1.mean(0),{'mu':mu1})}
print(f'M1: ожидаемое количество за день ≈ {mu1.mean():.3f}')
''')
md(r'''## 4. M2: дополнительная дисперсия

$$Y_tsimmathrm{NB}(mu,kappa),qquad mathrm{Var}(Y_t)=mu+mu^2/kappa.$$

Средний уровень остаётся постоянным, но дневные значения могут колебаться сильнее, чем в Poisson. Priors: $logmusim N(log 2,1.5^2)$, $logkappasim N(0,1.5^2)$. На следующем графике сравниваются прогнозные распределения M1/M2; последний столбец объединяет значения 12 и выше.
''')
code('''fit2=fit_nb(d,False,prediction_seed+2)
forecasts['M2']=static_predict(fit2,dates,N_DRAWS,prediction_seed+12)
display(pd.DataFrame([{'Модель':'M2','R-hat максимум':fit2['diagnostics']['max_rank_split_rhat'],'ESS минимум':fit2['diagnostics']['min_autocorrelation_ess'],'Медиана kappa':np.median(np.exp(fit2['theta'][:,-1]))}]).round(3))
fig,ax=plt.subplots(figsize=(10,4))
for model,shift in [('M1',-.18),('M2',.18)]:
    draws=forecasts[model][0][:,0]
    probabilities=np.bincount(np.minimum(draws,12),minlength=13)/len(draws)
    ax.bar(np.arange(13)+shift,probabilities,width=.35,color=COLORS[model],label=model)
ax.set(xticks=range(13),xticklabels=[str(x) for x in range(12)]+['12+'],ylabel='Прогнозная вероятность',xlabel='Совпадений в день',title='M2 допускает более широкий разброс вокруг постоянного среднего')
ax.legend()
show_plot(fig,'02_poisson_vs_nb.png')
''')
md(r'''## 5. M3: календарь, тренд и частичное объединение

$$logmu_t=alpha+eta u_t+b_{	ext{месяц}(t)}+c_{	ext{день недели}(t)}.$$

Эффекты календарных групп имеют общий prior с масштабом 0,4 и нулевую сумму. Priors стягивают шумные группы к общему уровню; масштабы фиксированы. Для тренда $etasim N(0,0.5^2)$, время измерено в годах и центрировано на обучающем периоде.

График показывает **множители среднего количества**, а не вероятности: 1 означает общий уровень, 0,5 — половину общего уровня. Черты показывают 80%-е posterior интервалы календарных эффектов. Это оценённые ассоциации, а не установленное влияние дня недели на эфир.
''')
code('''fit3=fit_nb(d,True,prediction_seed+3)
forecasts['M3']=static_predict(fit3,dates,N_DRAWS,prediction_seed+13)
month_multipliers=np.exp(fit3['theta'][:,2:13]@helmert(12,full=False))
weekday_multipliers=np.exp(fit3['theta'][:,13:19]@helmert(7,full=False))
fig,axes=plt.subplots(1,2,figsize=(12,4))
for ax,values,labels,title in [(axes[0],month_multipliers,MONTHS,'Месяц года'),(axes[1],weekday_multipliers,DOW,'День недели')]:
    lo,med,hi=np.quantile(values,[.1,.5,.9],axis=0)
    ax.errorbar(np.arange(len(labels)),med,yerr=[med-lo,hi-med],fmt='o',color=COLORS['M3'],capsize=4)
    ax.axhline(1,color='#555555',ls='--',lw=1)
    ax.set(xticks=range(len(labels)),xticklabels=labels,ylabel='Множитель среднего уровня',title=title)
show_plot(fig,'03_calendar_effects.png')
display(pd.DataFrame([{'Модель':'M3','R-hat максимум':fit3['diagnostics']['max_rank_split_rhat'],'ESS минимум':fit3['diagnostics']['min_autocorrelation_ess'],'Медиана годового log-тренда':np.median(fit3['theta'][:,1])}]).round(3))
''')
md(r'''## 6. M4: фильтр скрытого уровня

$$logmu_t=alpha+eta u_t+b_{	ext{месяц}(t)}+c_{	ext{день недели}(t)}+ell_t,$$
$$ell_t=ell_{t-1}+arepsilon_t,qquadarepsilon_tsim N(0,q^2).$$

$q=0.03$ выбран в предыдущем расчёте по отдельному development-периоду 2024 года. Для обновления состояния используется NB-вероятность нового наблюдения. При пропуске выполняется только движение состояния. На будущих днях обновления по неизвестным исходам не выполняются.

Вычисление модульное: 128 draws статических параметров M3, по 64 частицы состояния для каждого draw. Веса между статическими draws не переоцениваются. Это приближение к совместному Bayesian анализу; все ограничения описаны в `README.md`.
''')
code(definitions('filter_state','dynamic_predict')+'''

s4,m4,dist4,particle_diag=dynamic_predict(d,fit3,dates,q,N_DRAWS,prediction_seed+14)
forecasts['M4']=(s4,m4,dist4)
_,final_states,trace_diag=filter_state(d,fit3,q,8192,prediction_seed+14,trace=True)
trace=pd.DataFrame(trace_diag.pop('history'))
trace['date']=pd.to_datetime(trace.date)
trace.to_csv(OUT/'filtered_state_history.csv',index=False,encoding='utf-8-sig')
assert len(trace)==len(d)
print('Частиц:',particle_diag['groups']*particle_diag['particles_per_group'])
''')
md('''### Как наблюдения меняют уровень M4

График ниже — **ретроспективная иллюстрация механизма фильтра**, условная на статических параметрах, оценённых по всему доступному прошлому. Состояния не сглаживаются будущими состояниями, но статические параметры используют весь период. Поэтому этот график не заменяет хронологическую историческую проверку.

Зелёная полоса — 80%-й интервал скрытой ожидаемой интенсивности. Он отличается от прогнозного интервала для фактического дневного количества: наблюдения имеют дополнительный NB-разброс.
''')
code('''static_history_mu=np.exp(fit3['theta'][:,:-1]@design(d.date,True,fit3['center']).T).mean(0)
recent=(d.date>=pd.Timestamp('2026-06-01')).to_numpy()
view=trace.loc[recent]
fig,axes=plt.subplots(2,1,figsize=(12,6),sharex=True)
axes[0].plot(d.loc[recent,'date'],d.loc[recent,'y'],color='#aaaaaa',lw=.8,label='Наблюдения')
axes[0].plot(d.loc[recent,'date'],static_history_mu[recent],color=COLORS['M3'],lw=1.3,label='M3: статическая интенсивность')
axes[0].plot(view.date,view.intensity_mean,color=COLORS['M4'],lw=1.5,label='M4: после обновления по наблюдению')
axes[0].fill_between(view.date,view.intensity_lo80,view.intensity_hi80,color=COLORS['M4'],alpha=.15,label='M4: 80% интервал интенсивности')
axes[0].set(ylabel='Количество / интенсивность',title='Скрытый уровень реагирует на последовательность наблюдений')
axes[0].legend(fontsize=8,ncol=2)
axes[1].plot(view.date,view.state_mean,color=COLORS['M4'])
axes[1].axhline(0,color='#555555',ls='--',lw=1)
axes[1].set(ylabel='Среднее скрытого log-уровня',xlabel='Дата')
axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
show_plot(fig,'04_dynamic_filter.png')
''')
md('''## 7. Прогноз каждого дня

Главный точечный прогноз — **среднее**, подходящее для квадратичной функции потерь. Оно может быть дробным: 0,32 означает ожидаемое количество по распределению, а не треть произнесённого слова. Медиана M4 дополнительно приведена как целое число; при большой вероятности нуля она равна нулю даже при положительном среднем.

Для дискретных количеств границы интервалов вычислены через обратную эмпирическую CDF (`method="inverted_cdf"`), поэтому они целые. Вероятность хотя бы одного упоминания рассчитана по прогнозным траекториям. Интервалы относятся к измеряемому ASR-ряду и не учитывают ошибки распознавания или неизвестную неполноту эфира.
''')
code('''daily_rows=[]
monthly_rows=[]
for model,(draws,mean,distribution) in forecasts.items():
    quant=np.quantile(draws,[.025,.1,.5,.9,.975],axis=0,method='inverted_cdf')
    for i,date in enumerate(dates):
        daily_rows.append({'model':model,'date':date.strftime('%Y-%m-%d'),'weekday':DOW[date.dayofweek],
          'mean':float(mean[i]),'median':int(quant[2,i]),'lo80':int(quant[1,i]),'hi80':int(quant[3,i]),
          'lo95':int(quant[0,i]),'hi95':int(quant[4,i]),'probability_at_least_one':float((draws[:,i]>=1).mean())})
    sums=draws.sum(1)
    qs=np.quantile(sums,[.025,.1,.5,.9,.975],method='inverted_cdf')
    monthly_rows.append({'model':model,'mean':float(mean.sum()),'median':int(qs[2]),'lo80':int(qs[1]),'hi80':int(qs[3]),'lo95':int(qs[0]),'hi95':int(qs[4])})
daily=pd.DataFrame(daily_rows)
monthly=pd.DataFrame(monthly_rows)
daily.to_csv(OUT/'forecast_daily_discrete.csv',index=False,encoding='utf-8-sig')
wide=daily.pivot(index='date',columns='model',values='mean').rename(columns=lambda x:x+'_mean')
best=daily[daily.model=='M4'].set_index('date')
wide.insert(0,'weekday',best.weekday)
for col in ['median','lo80','hi80','lo95','hi95','probability_at_least_one']:
    wide['M4_'+col]=best[col]
wide.to_csv(OUT/'forecast_daily_all_models.csv',encoding='utf-8-sig')
pretty=wide.copy()
pretty.index=pd.to_datetime(pretty.index).strftime('%d.%m.%Y')
pretty=pretty.rename(columns={'weekday':'День недели','M1_mean':'M1 среднее','M2_mean':'M2 среднее','M3_mean':'M3 среднее','M4_mean':'M4 среднее','M4_median':'M4 медиана'})
pretty['M4 80% интервал']=best.lo80.astype(str).to_numpy()+'–'+best.hi80.astype(str).to_numpy()
pretty['M4 95% интервал']=best.lo95.astype(str).to_numpy()+'–'+best.hi95.astype(str).to_numpy()
pretty['M4 P(≥1)']=best.probability_at_least_one.map(lambda x:f'{100*x:.1f}%').to_numpy()
pretty=pretty[['День недели','M1 среднее','M2 среднее','M3 среднее','M4 среднее','M4 медиана','M4 80% интервал','M4 95% интервал','M4 P(≥1)']]
with pd.option_context('display.max_rows',40,'display.max_columns',12):
    display(pretty.round(2))
''')
code('''fig,axes=plt.subplots(2,2,figsize=(13,7),sharex=True,sharey=True)
for ax,model in zip(axes.flat,NAMES):
    a=daily[daily.model==model].copy();a['date']=pd.to_datetime(a.date)
    ax.fill_between(a.date,a.lo95,a.hi95,color=COLORS[model],alpha=.12,label='95% прогнозный интервал')
    ax.fill_between(a.date,a.lo80,a.hi80,color=COLORS[model],alpha=.24,label='80% прогнозный интервал')
    ax.plot(a.date,a['mean'],'o-',color=COLORS[model],lw=1.5,ms=3,label='Среднее')
    ax.set(title=f'{model}: {NAMES[model]}',ylabel='Совпадений в день',ylim=(0,daily.hi95.max()+1))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
axes[0,0].legend(fontsize=8)
fig.suptitle('Каждый день 03.10–02.11.2026: одинаковая шкала для четырёх моделей')
show_plot(fig,'05_daily_four_models.png')
''')
md('''### Ожидаемое количество: сравнение моделей

Постоянные M1/M2 имеют одинаковый уровень для всех будущих дней. M3/M4 учитывают день недели и месяц года. Перепад на 1 ноября отражает календарный коэффициент месяца, а не известное будущее событие. Календарный рисунок — модельная оценка; конкретные будущие выпуски программ неизвестны.
''')
code('''fig,ax=plt.subplots(figsize=(12,4))
for model in NAMES:
    a=daily[daily.model==model]
    ax.plot(pd.to_datetime(a.date),a['mean'],'o-',color=COLORS[model],label=model,ms=3,lw=1.6)
ax.set(title='Ожидаемое количество по каждому дню',ylabel='Средний прогноз',xlabel='Дата')
ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
ax.legend(ncol=4)
show_plot(fig,'06_daily_comparison.png')
''')
md('''### Вероятности разных дневных количеств

Для иллюстрации выбраны понедельник 5 октября и суббота 10 октября. Это примеры формы прогнозных распределений, а не отдельные проверки точности: будущие исходы неизвестны. Последний столбец содержит всю вероятность количества 12 и выше.
''')
code('''fig,axes=plt.subplots(1,2,figsize=(12,4),sharey=True)
for ax,date in zip(axes,pd.to_datetime(['2026-10-05','2026-10-10'])):
    i=dates.get_loc(date)
    for model,shift in zip(NAMES,[-.27,-.09,.09,.27]):
        samples=forecasts[model][0][:,i]
        prob=np.bincount(np.minimum(samples,12),minlength=13)/len(samples)
        ax.bar(np.arange(13)+shift,prob,width=.17,color=COLORS[model],label=model)
    ax.set(xticks=range(13),xticklabels=[str(x) for x in range(12)]+['12+'],xlabel='Совпадений за день',title=f'{date:%d.%m.%Y}, {DOW[date.dayofweek]}')
axes[0].set_ylabel('Прогнозная вероятность')
axes[1].legend(fontsize=8)
show_plot(fig,'07_daily_distributions.png')
''')
md('''## 8. Сумма за месяц

Дневные средние суммируются. Интервалы месячного итога рассчитываются отдельно из сумм совместных траекторий: складывать верхние и нижние границы дневных интервалов нельзя. M4 даёт около 29 совпадений за весь период, хотя для многих отдельных дней медиана равна нулю.
''')
code('''display(monthly.round({'mean':2}))
fig,ax=plt.subplots(figsize=(12,4))
for model,(draws,mean,_) in forecasts.items():
    cumulative=draws.cumsum(axis=1)
    ax.plot(dates,np.cumsum(mean),color=COLORS[model],label=model,lw=1.8)
    if model=='M4':
        lo,hi=np.quantile(cumulative,[.025,.975],axis=0,method='inverted_cdf')
        ax.fill_between(dates,lo,hi,color=COLORS[model],alpha=.14,label='M4: 95% интервал накопленной суммы')
ax.set(title='Как дневные прогнозы складываются в месячный итог',ylabel='Накопленная сумма',xlabel='Дата')
ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
ax.legend(ncol=3,fontsize=8)
show_plot(fig,'08_cumulative_forecast.png')
''')
md('''## 9. Историческая оценка моделей

Backtest включает 21 прогноз всего следующего месяца, январь 2025 — сентябрь 2026. Каждый прогноз обучается только на предыдущих пригодных днях. Дневная оценка охватывает 626 наблюдений; месячная — 16 месяцев без пропусков. На этом наборе месячный CRPS улучшается при каждом расширении. Дневной MAE и месячный RMSE не обязаны улучшаться на каждом шаге.

Это ретроспективная проверка по текущему снимку архива. Исторические версии расшифровок и время их фактической публикации не восстановлены. M4 выбрана по месячному CRPS; статистическое преимущество над M3 пограничное. Таблица и графики ниже используют сохранённые результаты расчёта с тем же SHA-256 источника. В следующей ячейке содержится весь код исторической проверки для повторного запуска.
''')
code(definitions('crps_sample','score','forecast_set','summarize','paired_comparisons','plots','main')+'''

if RUN_BACKTEST:
    main()
evaluation=pd.read_csv(OUT/'evaluation.csv')
origins=pd.read_csv(OUT/'backtest_by_origin.csv')
display(evaluation[['model','daily_rmse','daily_mae','daily_crps','daily_nll','monthly_rmse','monthly_crps','monthly_coverage95']].round(3))
''')
code('''fig,axes=plt.subplots(1,3,figsize=(13,4))
for ax,metric,title in [(axes[0],'daily_rmse','Дневной RMSE'),(axes[1],'daily_crps','Дневной CRPS'),(axes[2],'monthly_crps','Месячный CRPS')]:
    ax.bar(evaluation.model,evaluation[metric],color=[COLORS[x] for x in evaluation.model])
    for i,v in enumerate(evaluation[metric]):ax.text(i,v,f'{v:.2f}',ha='center',va='bottom',fontsize=9)
    ax.set(title=title,ylabel='Меньше лучше')
show_plot(fig,'09_backtest_metrics.png')
''')
code('''back=pd.read_csv(OUT/'backtest_daily.csv')
back['date']=pd.to_datetime(back.date)
window=(back.date>='2026-06-01')&(back.date<='2026-09-30')
fig,axes=plt.subplots(2,2,figsize=(13,7),sharex=True,sharey=True)
for ax,model in zip(axes.flat,NAMES):
    a=back[window&(back.model==model)]
    ax.fill_between(a.date,a.lo95,a.hi95,color=COLORS[model],alpha=.15,label='95% прогнозный интервал')
    ax.plot(a.date,a.actual,color='#777777',lw=.7,label='Факт')
    ax.plot(a.date,a['mean'],color=COLORS[model],lw=1.3,label='Прогноз до начала месяца')
    ax.set(title=model,ylabel='Совпадений в день')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
axes[0,0].legend(fontsize=8)
fig.suptitle('Последние четыре тестовых месяца: дневные прогнозы и фактические исходы')
show_plot(fig,'10_backtest_daily.png')
''')
md('''## 10. Проверка и сохранённые файлы

Проверяем количество дней, одинаковые прогнозные даты, целочисленные интервалы, согласованность месячных и дневных средних, воспроизведение предыдущих прогнозов и неизменность фильтра при включении истории для графика.

Основной дневной файл — `forecast_daily_all_models.csv`: 31 строка, средние четырёх моделей и интервалы M4. `forecast_daily_discrete.csv` содержит интервалы и вероятности для каждой модели, 124 строки. `filtered_state_history.csv` хранит данные графика работы фильтра. Все новые графики находятся в `figures/daily_models` и встроены в эту тетрадку.
''')
code('''assert len(dates)==31 and dates[0]==pd.Timestamp('2026-10-03') and dates[-1]==pd.Timestamp('2026-11-02')
assert len(wide)==31 and len(daily)==124 and daily.groupby('model').size().eq(31).all()
assert (daily[['lo80','hi80','lo95','hi95','median']].to_numpy()%1==0).all()
assert (daily[['lo80','hi80','lo95','hi95','median','mean']].to_numpy()>=0).all()
assert daily.probability_at_least_one.between(0,1).all()
previous=pd.read_csv(OUT/'forecast_daily.csv')
np.testing.assert_allclose(daily['mean'],previous['mean'],rtol=1e-12,atol=1e-12)
for _,row in monthly.iterrows():
    np.testing.assert_allclose(daily.loc[daily.model==row.model,'mean'].sum(),row['mean'])
_,states_without_trace,_=filter_state(d,fit3,q,8192,prediction_seed+14,trace=False)
np.testing.assert_array_equal(final_states,states_without_trace)
assert trace.observed.sum()==d.observed.sum()
validation={'status':'passed','days':31,'models':4,'daily_rows':124,'wide_rows':31,
            'forecast_reproduced':True,'trace_does_not_change_filter':True,
            'interval_quantile_method':'inverted_cdf','source_sha256':source_hash}
(OUT/'daily_notebook_validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
print('Все проверки прошли. Дневной прогноз сохранён для 31 дня и четырёх моделей.')
''')
md('''## Методологические источники

Использованы материалы предыдущего расчёта: L1 Forecast Evaluation (форма прогноза, калибровка и оценка), L3 Bayesian Computation и `ha15491_6191_3.ipynb` (posterior predictive averaging, NB и MH), L4 Hierarchical Modeling и S4 (частичное объединение), L5 Sequential Forecasting (модель состояния, хронологическая оценка и фильтр частиц). Подробная привязка к страницам и все ограничения находятся в `README.md` рядом с тетрадкой.
''')
nb.cells=cells
path=OUT/'stalin_russia1_daily_forecast.ipynb'
nbformat.write(nb,path)
os.environ['JUPYTER_PATH']=str(ROOT/'analysis/jupyter')
print('Executing daily notebook',flush=True)
NotebookClient(nb,timeout=300,kernel_name='stalin-project-python',resources={'metadata':{'path':str(ROOT)}}).execute()
nb.metadata['kernelspec']={'display_name':'Python 3','language':'python','name':'python3'}
nbformat.validate(nb)
nbformat.write(nb,path)
print('Saved executed daily notebook',flush=True)

if __name__=='__main__':pass
