"""Generate a source-grounded Russian report and executable notebook."""
import sys, json, os, shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'deps'))
import numpy as np
import pandas as pd
import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/stalin_russia1'
def table(frame):
    cols=list(frame.columns)
    rows=['| '+' | '.join(cols)+' |','| '+' | '.join(['---']*len(cols))+' |']
    for row in frame.itertuples(index=False,name=None):
        rows.append('| '+' | '.join(str(x) for x in row)+' |')
    return '\n'.join(rows)

def main():
    meta=json.loads((OUT/'metadata.json').read_text(encoding='utf-8'))
    ev=pd.read_csv(OUT/'evaluation.csv');fc=pd.read_csv(OUT/'forecast_month.csv')
    comp=pd.read_csv(OUT/'model_comparisons.csv');stab=pd.read_csv(OUT/'particle_stability.csv')
    diag=json.loads((OUT/'final_diagnostics.json').read_text())
    backdiag=json.loads((OUT/'backtest_diagnostics.json').read_text())
    d=pd.read_csv(OUT/'daily_data.csv')
    percent=100*(1-ev.loc[3,'monthly_crps']/ev.loc[0,'monthly_crps'])
    rmse_percent=100*(1-ev.loc[3,'monthly_rmse']/ev.loc[0,'monthly_rmse'])
    summaries=ev[['model','monthly_rmse','monthly_crps','monthly_coverage80','monthly_coverage95']].copy()
    summaries.columns=['Модель','RMSE месячного итога','CRPS месячного итога','Покрытие 80%','Покрытие 95%']
    for col in summaries.columns[1:3]:summaries[col]=summaries[col].map(lambda x:f'{x:.2f}')
    for col in summaries.columns[3:]:summaries[col]=summaries[col].map(lambda x:f'{100*x:.1f}%')
    forecasts=fc[['model','mean','median','lo80','hi80','lo95','hi95']].copy()
    forecasts['Среднее']=forecasts['mean'].map(lambda x:f'{x:.2f}')
    forecasts['Медиана']=forecasts['median'].astype(int)
    forecasts['80% интервал']=forecasts.apply(lambda r:f"{r.lo80:.0f}–{r.hi80:.0f}",axis=1)
    forecasts['95% интервал']=forecasts.apply(lambda r:f"{r.lo95:.0f}–{r.hi95:.0f}",axis=1)
    forecasts=forecasts[['model','Среднее','Медиана','80% интервал','95% интервал']]
    forecasts=forecasts.rename(columns={'model':'Модель'})
    daytable=ev[['model','daily_rmse','daily_mae','daily_crps','daily_nll']].copy().round(3)
    daytable.columns=['Модель','Дневной RMSE','Дневной MAE','Дневной CRPS','Дневной NLL']
    comparisons=comp[comp.loss=='monthly_crps'].copy()
    comparisons['Переход']=comparisons.earlier+' → '+comparisons.later
    comparisons['Снижение CRPS']=comparisons.mean_loss_improvement.map(lambda x:f'{x:.2f}')
    comparisons['p (приблизительный DM)']=comparisons.approx_p_two_sided.map(lambda x:f'{x:.3f}')
    comparisons['95% блоковый bootstrap']=comparisons.apply(lambda r:f'{r.block_bootstrap_lo95:.2f}…{r.block_bootstrap_hi95:.2f}',axis=1)
    comparisons=comparisons[['Переход','Снижение CRPS','p (приблизительный DM)','95% блоковый bootstrap']]
    zero=float((d.loc[d.observed,'y']==0).mean());mean=float(d.y.mean());var=float(d.y.var())
    full=pd.read_csv(OUT/'backtest_by_origin.csv');excluded=full[(full.model=='M1')&(full.n_days!=full.horizon)]
    excluded_months=', '.join(excluded.test_start.str[:7])
    text=rf'''# Прогноз упоминаний Сталина на «России 1»

Расчёт выполнен 4 октября 2026 года по локальной выгрузке, которая заканчивается 2 октября 2026 года (Europe/Moscow). Лучший результат по выбранной метрике дала M4: **28,60 совпадения фамилии за 03.10–02.11.2026**, округлённо **29**, с **80%-м прогнозным интервалом 15–45** и **95%-м интервалом 10–59**. Медиана равна 26. Среднее используется как точечный прогноз при квадратичной функции потерь.

## 1. Что именно прогнозируется

Содержательная цель: количество упоминаний Иосифа Сталина в эфире «России 1» за месяц. Доступная измеримая переменная: число токенов `Сталин`, `Сталина`, `Сталину`, `Сталиным`, `Сталине` без учёта регистра в автоматических расшифровках всех передач из сохранённого архива. Показатель считает каждое произнесённое/распознанное совпадение, а не число сюжетов или дней с упоминанием. Повторы в разных выпусках учитываются. «Сталинград» и «сталинский» не подходят под исходный шаблон.

**Это приближение к числу упоминаний конкретного человека.** Полная ручная разметка 2 351 контекста не проводилась. Выборочная проверка обнаружила ошибки распознавания: например, «в сталину» в развлекательной передаче 13.01.2024, вероятно, соответствует «в старину». Есть также название танка «Иосиф Сталин». Такие случаи остаются в исходном ряду; модели не превращают кандидатов в проверенные персональные упоминания. Прогноз относится к доступному корпусу, а не к доказанно полному суточному эфиру. Для строго персонального ряда потребуется разметка контекстов и повторный расчёт тем же кодом.

Поскольку запрос касается канала, используются все сохранённые программы: новости, политические ток-шоу, развлекательные передачи и прочие фрагменты. Фильтр «только новости» не добавлялся. Будущие политические события и изменения сетки вещания неизвестны и не вводились как будто наблюдаемые признаки.

Один месяц определён как промежуток после последней даты до той же даты следующего месяца: с 03.10.2026 по 02.11.2026 включительно, **31 день**. Суточные распределения моделируются совместно, затем суммируются в месячный итог. Месячные интервалы получены из сумм целых траекторий; складывать границы дневных интервалов было бы ошибкой.

## 2. Данные и пропуски

Локальный источник: `data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz`; исходные передачи, статусы и контексты находятся в `data/tv.sqlite`. Для расчёта не требуются BigQuery или повторное скачивание текстов. Использован канал `RUSSIA1`.

Период: 01.01.2023–02.10.2026, всего **1 371 календарный день**. Имеются **1 327 пригодных наблюдений**, **44 дня исключены**. Пригодный день требует доступного перечня (`inventory_status == 200`) и всех расшифровок перечисленных передач (`coverage_status == observed_listed_broadcasts`). Из 44 дней 43 уже помечены в выгрузке как неполные; дополнительно исключён 07.10.2025: расшифровки есть, но перечень имеет статус 404. Это консервативный критерий полноты относительно архива.

За пригодные дни найдено **2 350 совпадений**; за все имеющиеся фрагменты, включая неполные дни, 2 351. Пропуски остаются `NaN`, не заменяются нулями. В динамической модели состояние продолжает двигаться в пропущенный день, но обновления по наблюдению нет. Частично доступные дневные количества также не используются как полные наблюдения.

Среднее по пригодным дням: **{mean:.3f}**, дисперсия: **{var:.3f}**, доля нулевых дней: **{zero:.1%}**. Дисперсия значительно больше среднего. Часть избыточного разброса связана с разными программами, повторными выпусками, меняющимся уровнем и доступностью архива. NB полезна как модель этого разброса; это ещё не доказательство конкретного причинного механизма.

При исключении пропусков предполагается, что наблюдаемые дни достаточно представительны. Это предположение нельзя проверить полностью: сбои архива и смена объёма расшифровок могут быть связаны с содержанием передач. Число слов известно только после эфира, поэтому будущий фактический объём текстов не используется в качестве предиктора. Интервалы ниже не покрывают систематическую ошибку измерения или неизвестную неполноту архива.

## 3. Четыре последовательных расширения

### M1. Постоянная интенсивность: Gamma–Poisson

$$Y_t\mid\lambda\sim\mathrm{{Poisson}}(\lambda),\qquad \lambda\sim\mathrm{{Gamma}}(1,1).$$

Здесь второй параметр Gamma — rate. После $n$ пригодных дней:

$$\lambda\mid D\sim\mathrm{{Gamma}}\left(1+\sum y_t,\;1+n\right).$$

Это разумная базовая модель: все наблюдаемые дни одного канала считаются сопоставимыми. Она не учитывает календарь и изменения уровня. Параметр $\lambda$ интегрируется, поэтому даже при пуассоновском условном распределении прогнозный разброс не равен точно среднему. Для каждой будущей траектории берётся один общий draw $\lambda$, затем независимые условные дневные количества. Это сохраняет зависимость из-за общей неопределённой интенсивности.

### M2. M1 + дополнительная дневная дисперсия

$$Y_t\mid\mu,\kappa\sim\mathrm{{NB}}(\mu,\kappa),\qquad
\operatorname{{Var}}(Y_t\mid\mu,\kappa)=\mu+\mu^2/\kappa.$$

Представление Gamma–Poisson: $\Lambda_t\mid\mu,\kappa\sim\mathrm{{Gamma}}(\kappa,\kappa/\mu)$, затем $Y_t\sim\mathrm{{Poisson}}(\Lambda_t)$. В M1 постоянен общий уровень; в M2 вокруг него допускаются дополнительные дневные колебания. При $\kappa\to\infty$ условное распределение приближается к Poisson.

Priors: $\log\mu\sim N(\log2,1.5^2)$, $\log\kappa\sim N(0,1.5^2)$. Иные priors относительно сопряжённой M1 нужны для этой параметризации и указаны явно. Posterior M2 вычисляется методом Metropolis–Hastings из L3. Прогноз усредняется по posterior draws, а не строится только в оценке среднего параметра.

Ожидаемое улучшение: более реалистичные хвосты и интервалы при всплесках. Само добавление дисперсии почти не меняет средний уровень; улучшение точечной ошибки не гарантируется.

### M3. M2 + календарная иерархия и тренд

$$\log\mu_t=\alpha+\beta u_t+b_{{m(t)}}+c_{{w(t)}}.$$

$u_t$ — время в годах, центрированное на среднем дне обучающего периода. $m(t)$ — месяц года, $w(t)$ — день недели. Для идентификации эффекты месяцев и дней недели имеют нулевую сумму. Ортонормированные контрасты реализуют это ограничение.

Priors: $\alpha\sim N(\log2,1.5^2)$, $\beta\sim N(0,0.5^2)$; календарные контрасты имеют общий внутри группы prior $N(0,0.4^2)$; $\log\kappa\sim N(0,1.5^2)$. Это частичное объединение: эффекты редких или шумных групп стягиваются к общему уровню. Масштабы 0,4 фиксированы, а не оценены как неизвестные гиперпараметры. Иерархия организована по календарным группам одного канала; данные других каналов не подмешиваются.

Решение из L4 адаптировано к счётным данным. Тренд нужен, поскольку постоянная интенсивность усредняет высокий исторический уровень вместе с более низкими недавними значениями. Календарь может отражать регулярную сетку передач и сезонные изменения. Posterior M3 также вычисляется Metropolis–Hastings. Ни будущие количества, ни будущие объёмы расшифровок не входят в признаки.

### M4. M3 + меняющийся скрытый уровень

$$\log\mu_t=\alpha+\beta u_t+b_{{m(t)}}+c_{{w(t)}}+\ell_t,$$
$$\ell_t=\ell_{{t-1}}+\varepsilon_t,\quad \varepsilon_t\sim N(0,q^2),\quad \ell_0\sim N(0,0.3^2).$$

Здесь появляется модель движения скрытого состояния и отдельная NB-модель наблюдения, как в L5. Нелинейная связь и счётные наблюдения требуют фильтра частиц вместо точного линейного Gaussian Kalman filter. Фильтр выполняет шаг движения, перевзвешивание по вероятности наблюдения и systematic resampling при ESS ниже половины числа частиц. Без resampling предыдущие веса сохраняются.

Для прогноза состояние движется вперёд без обновления по неизвестным наблюдениям. Случайное блуждание имеет нулевое среднее приращение в логарифме; неопределённость состояния растёт. В шкале количества ожидание включает эффект экспоненты, поэтому его нельзя получить просто экспонентой среднего состояния.

**Вычислительное приближение M4:** используется модульная смесь фильтров, условных на 128 draws статических параметров из M3; в каждом фильтре 64 частицы состояния, всего 8 192. Веса между статическими draws остаются равными. Это условный/модульный подход, а не полный совместный Bayesian posterior всех статических параметров и состояний. Статические параметры оцениваются на том же прошлом, на котором фильтруются состояния; фильтр здесь нужен для условной оценки состояния, а не для повторного независимого обновления статических параметров. При полном совместном анализе результаты и интервалы могут измениться.

$q$ выбран по среднему месячному CRPS на полностью наблюдаемых development-месяцах июня–декабря 2024 года из сетки $0;0.03;0.07;0.15$. Выбрано **$q=0.03$**. Development-прогнозы также используют только прошлые данные. Октябрь 2024 года неполон и в месячный критерий не входит. Тестовые месяцы 2025–2026 годов не использовались для выбора $q$.

## 4. Как выполнена оценка

Проведён expanding-window backtest: **21 точка прогнозирования** перед началом каждого месяца с января 2025 по сентябрь 2026. Для каждой точки все модели заново обучаются на доступных пригодных днях строго до начала месяца; затем сразу прогнозируется весь следующий месяц, без обновления внутри него. Подход отвечает горизонту задачи, в отличие от оценки однодневных прогнозов с ежедневным переобучением.

**Дневные метрики:** 626 наблюдаемых тестовых дней. Для всех четырёх моделей используются одинаковые дни. Прогнозы для пропусков строятся, но не оцениваются.

**Основная месячная оценка:** 16 полностью наблюдаемых месяцев. Месяцы {excluded_months} исключены из неё. Для них отдельно сохранены результаты суммы только наблюдаемых дней в `backtest_by_origin.csv`; такие суммы не выдаются за полный месячный итог.

Основной критерий выбора — **CRPS месячного распределения**, поскольку задача включает прогноз количества и его неопределённость. Для случайных величин $X,X'$ из прогнозного распределения:

$$\operatorname{{CRPS}}(F,y)=E|X-y|-\tfrac12E|X-X'|.$$

CRPS вычисляется по траекториям без подбора границ после наблюдения результата. Меньше лучше; единица измерения такая же, как у количества. Дополнительно вычислены RMSE и MAE для posterior predictive mean, отрицательный log score (NLL) дневного количества, покрытие и ширина 80%/95% интервалов, randomized PIT для дискретных прогнозов. Brier score не применяется к самому счётному исходу.

Для каждого backtest используется 6 000 траекторий; для финального прогноза — 30 000. Общие параметры и состояние сохраняются внутри траектории, поэтому месячный разброс учитывает зависимость между будущими днями.

Это **ретроспективный pseudo-out-of-sample backtest по текущему снимку расшифровок**. Исторические версии архива и время фактической публикации каждого текста не восстановлены. Схема обучения исключает будущие исходы, но не доказывает, что такой же корпус был доступен исследователю в реальном времени на каждой старой дате. M4 выбирается среди четырёх заранее заданных моделей по этому тесту; отдельного второго теста после выбора победителя нет.

## 5. Результаты

{table(summaries)}

По основному месячному CRPS каждое расширение улучшает предыдущую модель: **16,72 → 14,49 → 13,38 → 11,06**. M2 улучшает распределение и покрытие, но слегка ухудшает RMSE: 23,86 → 23,94. Поэтому утверждение «каждая модель лучше по всем метрикам» было бы неверным. Также M4 имеет немного больший дневной MAE, чем M3; выбор делается по месячной задаче.

M4 снижает месячный CRPS относительно M1 на **{percent:.1f}%**, а RMSE на **{rmse_percent:.1f}%** в этой исторической выборке. 80%-й месячный интервал M4 покрывает 13 из 16 результатов, 95%-й — 15 из 16. Это согласуется с заданными уровнями приблизительно, но 16 месяцев мало для точной проверки калибровки. У M1 95%-й интервал покрывает только 7 из 16 месячных итогов.

{table(daytable)}

![Оценка месячных прогнозов](figures/evaluation.png)

![Исторические месячные прогнозы](figures/backtest_months.png)

Randomized PIT рассчитывается как $F(y-1)+U\,P(Y=y)$, $U\sim U(0,1)$, по симулированным дневным распределениям. У M1 виден избыток низких PIT; M3/M4 ближе к равномерному ориентиру. Этот график показывает маргинальную дневную калибровку, но не подтверждает правильную зависимость дней или калибровку месячного итога.

![Randomized PIT](figures/pit.png)

### Значимость различий

Сравнения пар выполнены по потерям на одних и тех же 16 неперекрывающихся месяцах. Сохранены приблизительный Diebold–Mariano с HAC lag 1 и двусторонним t-ориентиром, а также circular moving-block bootstrap с блоками по два месяца. В таблице положительное снижение потерь означает преимущество более поздней модели.

{table(comparisons)}

M2 убедительно улучшает CRPS относительно M1 в этой проверке. Для M3 против M2 убедительного преимущества не получено. У M4 против M3 результат пограничный: приблизительный DM даёт $p\approx0.051$, а двухмесячный bootstrap-интервал положителен. Разные проверки дают разные выводы возле порога 5%; при 16 месяцах, выбранной длине блока и нескольких сравнениях нельзя заявлять устойчивое доказанное преимущество M4. M4 имеет лучший средний результат, поэтому используется для итогового прогноза. Значения $p$ представлены без поправки за несколько сравнений.

## 6. Прогноз на 03.10–02.11.2026

{table(forecasts)}

Все интервалы **прогнозные для фактического будущего количества**, а не интервалы только для неизвестного среднего. Точечный итог — среднее; округление до целого выполняется лишь для удобства чтения. Вероятность хотя бы 50 совпадений по M4 составляет **{fc.loc[3,'probability_ge_50']:.1%}**. Это модельная вероятность для измеряемого ряда.

![Дневной прогноз](figures/daily_forecast.png)

M1/M2 сохраняют усреднённый за всю историю уровень и дают около 55 совпадений. M3 учитывает спад и календарь, прогнозируя около 33. M4 дополнительно корректирует уровень по недавним данным, прогнозируя около 29. Это интерпретация модели, а не установленная причина изменения внимания к Сталину.

## 7. Проверка вычислений и воспроизводимость

M2/M3: четыре MH-цепи, 300 warmup и 1 200 сохранённых draws на цепь; при недостаточных диагностических показателях код увеличивает длину. Локальная Laplace-аппроксимация используется только для предложения multivariate t в MH; принятие/отклонение считается по точной posterior плотности. Поэтому M2/M3 не подменены нормальной аппроксимацией posterior.

В финальной M3 максимальный rank-normalized split/folded R-hat **{diag['M3']['max_rank_split_rhat']:.4f}**, минимальный autocorrelation ESS **{diag['M3']['min_autocorrelation_ess']:.0f}**. По всем тестовым подгонкам M2/M3 максимальный R-hat **{max(x[m]['max_rank_split_rhat'] for x in backdiag for m in ['M2','M3']):.4f}**, минимальный ESS **{min(x[m]['min_autocorrelation_ess'] for x in backdiag for m in ['M2','M3']):.0f}**. ESS здесь оценён по автокорреляциям цепей, а не выдан за ArviZ bulk ESS.

Дополнительно M4 повторена на трёх seeds с 8 192 и 32 768 частицами. Средние месячные итоги составили **{stab['mean'].min():.2f}–{stab['mean'].max():.2f}**, нижние 95%-е границы 10, верхние 56–58; основной расчёт дал 28,60 и верхнюю границу 59. Размер частиц и случайные posterior draws вносят небольшую вычислительную погрешность. Поэтому итог сообщается как «около 29», а границы не следует трактовать как точные вне модели. Эта проверка контролирует Monte Carlo устойчивость, но не устраняет модульное приближение M4.

Автоматические проверки подтвердили NB-вероятности независимой реализацией SciPy, CRPS прямой попарной формулой, аналитические градиенты численным дифференцированием, даты обучения, одинаковые тестовые дни, неотрицательные целые траектории и месячные интервалы из сумм траекторий. Результат — `verification.json`.

Файлы:

- `stalin_russia1_forecast.ipynb`: выполненная тетрадка с кодом всех моделей, таблицами и графиками.
- `forecast_daily.csv`, `forecast_month.csv`: прогнозы четырёх моделей по дням и на весь месяц.
- `evaluation.csv`, `backtest_by_origin.csv`, `backtest_daily.csv`: оценка и исходные прогнозы исторической проверки.
- `development_scores.csv`: выбор $q$ только на development-периоде.
- `model_comparisons.csv`: статистические сравнения.
- `daily_data.csv`: использованный ряд и признаки доступности; пропуски сохранены.
- `posterior_samples.npz`, `forecast_paths.npz`: posterior draws M2/M3 и все финальные траектории.
- `final_diagnostics.json`, `backtest_diagnostics.json`, `particle_stability.csv`, `metadata.json`: диагностика и происхождение результатов.

Для повторного расчёта в проекте: `python analysis/stalin_models.py`, затем `python analysis/verify_forecast.py`. Тетрадка запускается через Run All и сама находит папку проекта. Для переноса нужны исходная суточная выгрузка и сохранённая структура папок. Анализ не изменяет вложенные Library-файлы и исходную ТВ-базу.

Версии зависимостей записаны в `requirements.txt`. Seed: **20261004**. SHA-256 входного сжатого файла: `{meta['source_sha256']}`.

## 8. Связь с предоставленными материалами

- **Forecasting Project Instructions**, стр. 1–2: целевая величина, горизонт, несколько моделей, оценка на нескольких событиях, сравнение и интерпретация. Два приложенных файла инструкций имеют одинаковый SHA-256; содержание совпадает. Указанные там обязанности по proposal, команде и презентации не трактуются как отдельный запрос пользователя на их создание.
- **L1 Forecast Evaluation A**, стр. 12, 18, 22–24: точечный, интервальный и вероятностный прогноз; калибровка, sharpness, proper scores и связь среднего с квадратичной потерей. CRPS — выбранная здесь конкретная реализация принципа proper scoring; он не приписывается отдельному слайду как показанная там формула.
- **L1 Forecast Evaluation B**: разделение качества решения и качества прогнозного распределения.
- **L2 Bayesian Mechanics B**, стр. 23–25: Bayesian update и недопустимость повторного счёта одного и того же сигнала как независимого свидетельства.
- **L3 Bayesian Computation**: posterior predictive averaging, Metropolis–Hastings и диагностика выборки; стр. 65–70: вероятностный score и неопределённость разницы scores.
- **ha15491_6191_3.ipynb**, Problem 3: NB-параметризация $\mu+\mu^2/\kappa$, сравнение с Poisson, posterior predictive score; предупреждение, что LOO по историческим дням не равно прогнозу будущего. Поэтому основной расчёт здесь использует хронологический backtest.
- **L4 Hierarchical Modeling**, стр. 17–27, и **S4_Hierarchical_Models.ipynb**, разделы 2 и 4: partial pooling и счётная иерархия. **HA4_Hierarchical_Models.ipynb** использован как дополнительный учебный контекст; его домашние задания не выполняются вместо пользовательского прогноза.
- **L5 Sequential Forecasting**, стр. 8–9, 37–42, 68–69, 79: модель состояния и наблюдения, оценка прогноза, доступного на соответствующую дату, фильтр частиц, сохранение весов без resampling и проверка устойчивости.

Первичный источник корпуса указан в README исходного проекта: [GDELT Visual Explorer: перечни и расшифровки ТВ](https://blog.gdeltproject.org/visual-explorer-quick-workflow-for-downloading-belarusian-russian-ukrainian-transcripts-translations/). Этот расчёт использует сохранённую локальную выгрузку и не подтверждает заново доступность внешнего архива.
'''
    text=text.replace(chr(92)*2,chr(92))
    (OUT/'README.md').write_text(text,encoding='utf-8')
    import scipy, matplotlib, nbclient, ipykernel
    (OUT/'requirements.txt').write_text('\n'.join([f'numpy=={np.__version__}',f'pandas=={pd.__version__}',
        f'scipy=={scipy.__version__}',f'matplotlib=={matplotlib.__version__}',
        f'nbformat=={nbformat.__version__}',f'nbclient=={nbclient.__version__}',f'ipykernel=={ipykernel.__version__}'])+'\n',encoding='utf-8')
    shutil.copy2(ROOT/'analysis/stalin_models.py',OUT/'stalin_models.py')
    copy=(OUT/'stalin_models.py').read_text(encoding='utf-8')
    copy=copy.replace("ROOT=Path(__file__).resolve().parents[1]","ROOT=next(p for p in Path(__file__).resolve().parents if (p/'data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz').exists())")
    (OUT/'stalin_models.py').write_text(copy,encoding='utf-8')
    shutil.copy2(ROOT/'analysis/verify_forecast.py',OUT/'verify_forecast.py')
    nb=nbformat.v4.new_notebook()
    nb.metadata.update({'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
                        'language_info':{'name':'python','version':sys.version.split()[0]}})
    def md(s):return nbformat.v4.new_markdown_cell(s)
    def code(s):return nbformat.v4.new_code_cell(s)
    setup='''from pathlib import Path
import sys, os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
ROOT = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p/'data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz').exists()), None)
if ROOT is None:
    raise FileNotFoundError('Откройте тетрадку внутри папки проекта forecasting с локальной ТВ-выгрузкой.')
sys.path.insert(0, str(ROOT/'analysis/deps'))
sys.path.insert(0, str(ROOT/'analysis'))
import numpy as np, pandas as pd
from IPython.display import display, Image
OUT=ROOT/'output/stalin_russia1'
print('Папка проекта:',ROOT)
'''
    source=(ROOT/'analysis/stalin_models.py').read_text(encoding='utf-8')
    source=source.replace("ROOT=Path(__file__).resolve().parents[1]","# ROOT определён в первой ячейке")
    source=source.replace("sys.path.insert(0, str(Path(__file__).parent/'deps'))","# Зависимости подключены в первой ячейке")
    source=source.replace("if __name__=='__main__':main()",'')
    parts=text.split('\n## ')
    nb.cells=[md(parts[0]),code(setup)]
    for part in parts[1:5]:nb.cells.append(md('## '+part))
    nb.cells += [md('## Код четырёх моделей\n\nСледующая ячейка содержит все определения; затем расчёт запускается заново на локальном источнике.'),
      code(source),code('main()'),
      md('## Таблицы исторической оценки'),
      code("evaluation=pd.read_csv(OUT/'evaluation.csv')\ndisplay(evaluation)\ndisplay(pd.read_csv(OUT/'model_comparisons.csv'))"),
      md('## Месячный и дневной прогноз'),
      code("display(pd.read_csv(OUT/'forecast_month.csv'))\ndisplay(pd.read_csv(OUT/'forecast_daily.csv').query(\"model=='M4'\"))"),
      md('## Графики проверки и прогноза'),
      code("for name in ['evaluation.png','backtest_months.png','pit.png','daily_forecast.png']:\n    display(Image(filename=str(OUT/'figures'/name)))"),
      md('## Контроль вычислений'),
      code("import runpy\nrunpy.run_path(str(ROOT/'analysis/verify_forecast.py'),run_name='__main__')\nprint((OUT/'final_diagnostics.json').read_text(encoding='utf-8'))\ndisplay(pd.read_csv(OUT/'particle_stability.csv'))")]
    # Results interpretation is kept alongside the calculation, not just in chat.
    for part in parts[5:]:nb.cells.append(md('## '+part))
    path=OUT/'stalin_russia1_forecast.ipynb';nbformat.write(nb,path)
    # Local temporary kernelspec uses the bundled interpreter and project deps.
    kernel_root=ROOT/'analysis/jupyter';kp=kernel_root/'kernels/stalin-project-python';kp.mkdir(parents=True,exist_ok=True)
    spec={'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],
          'display_name':'Forecasting project Python','language':'python',
          'env':{'PYTHONPATH':str(ROOT/'analysis/deps'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1',
                 'IPYTHONDIR':str(kernel_root/'ipython'),'JUPYTER_RUNTIME_DIR':str(kernel_root/'runtime')}}
    (kp/'kernel.json').write_text(json.dumps(spec),encoding='utf-8')
    os.environ['JUPYTER_PATH']=str(kernel_root)
    print('Executing notebook',flush=True)
    client=NotebookClient(nb,timeout=300,kernel_name='stalin-project-python',resources={'metadata':{'path':str(ROOT)}})
    client.execute()
    # Keep portable default kernel metadata for the delivered notebook.
    nb.metadata['kernelspec']={'display_name':'Python 3','language':'python','name':'python3'}
    nbformat.write(nb,path)
    print('Saved executed notebook and report',flush=True)

if __name__=='__main__':main()
