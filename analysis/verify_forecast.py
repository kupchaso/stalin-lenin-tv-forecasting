"""Numerical checks for count forecasts and chronological evaluation."""
import sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
sys.path.insert(0,str(Path(__file__).parent/'deps'))
import numpy as np
import pandas as pd
from scipy.stats import nbinom
from stalin_models import nb_logpmf, crps_sample, load_data, posterior_problem

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz').exists())
OUT=ROOT/'output/stalin_russia1'
def main():
    # Validate count likelihood against an independent library implementation.
    yy=np.arange(35);mu=2.3;k=.7
    np.testing.assert_allclose(nb_logpmf(yy,mu,k),nbinom.logpmf(yy,k,k/(k+mu)),rtol=1e-12,atol=1e-12)
    # CRPS sample identity checked by its explicit pairwise definition.
    draws=np.array([0,1,4,9])[:,None];y=np.array([3])
    brute=np.abs(draws-y).mean()-.5*np.abs(draws[:,None,:]-draws[None,:,:]).mean()
    np.testing.assert_allclose(crps_sample(draws,y)[0],brute)
    # Exact analytic gradient checked at two different parameter values.
    d,_=load_data();f,x,_=posterior_problem(d,True)
    for point in [x,x+np.linspace(-.03,.03,len(x))]:
        eps=1e-5;numeric=np.array([(f(point+np.eye(len(x))[j]*eps)[0]-f(point-np.eye(len(x))[j]*eps)[0])/(2*eps) for j in range(len(x))])
        np.testing.assert_allclose(f(point)[1],numeric,rtol=1e-5,atol=2e-5)
    b=pd.read_csv(OUT/'backtest_by_origin.csv')
    assert len(b)==84 and b.model.nunique()==4 and b.origin.nunique()==21
    assert (pd.to_datetime(b.origin)<pd.to_datetime(b.test_start)).all()
    assert (pd.to_datetime(b.test_start)>=pd.Timestamp('2025-01-01')).all()
    assert b.groupby('origin').n_days.nunique().eq(1).all()
    for _,r in b.iterrows():
        assert r.train_days==d[(d.date<=pd.Timestamp(r.origin)) & d.observed].shape[0]
    daily=pd.read_csv(OUT/'forecast_daily.csv');monthly=pd.read_csv(OUT/'forecast_month.csv')
    paths=np.load(OUT/'forecast_paths.npz')
    assert len(paths['dates'])==31 and paths['dates'][0]=='2026-10-03' and paths['dates'][-1]=='2026-11-02'
    for _,r in monthly.iterrows():
        s=paths[r.model];assert s.shape==(30000,31) and np.issubdtype(s.dtype,np.integer) and s.min()>=0
        np.testing.assert_allclose(daily[daily.model==r.model]['mean'].sum(),r['mean'])
        np.testing.assert_allclose(np.quantile(s.sum(1),[.025,.975]),[r.lo95,r.hi95])
        assert r.lo95<=r.lo80<=r['median']<=r.hi80<=r.hi95
    diag=json.loads((OUT/'backtest_diagnostics.json').read_text())
    assert max(x[m]['max_rank_split_rhat'] for x in diag for m in ['M2','M3'])<1.03
    assert min(x[m]['min_autocorrelation_ess'] for x in diag for m in ['M2','M3'])>250
    assert np.isfinite(pd.read_csv(OUT/'evaluation.csv').select_dtypes(include='number')).all().all()
    (OUT/'verification.json').write_text(json.dumps({'status':'passed','checks':[
      'NB probability agrees with scipy.stats.nbinom','CRPS agrees with pairwise definition',
      'analytic posterior gradient agrees with finite differences','84 chronological forecasts, 21 origins',
      'identical evaluation days across all four models','missing values excluded, never made zero',
      'month horizon and all 30000 nonnegative integer trajectories verified',
      'monthly intervals equal quantiles of summed trajectories','MCMC diagnostics checked']},indent=2),encoding='utf-8')
    print('All forecast verification checks passed.')
if __name__=='__main__':main()
