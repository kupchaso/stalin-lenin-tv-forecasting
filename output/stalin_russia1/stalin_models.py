"""Four nested count forecasting models. Only historical observations enter a fit.

Requires numpy, pandas, scipy and matplotlib. Optional project-local deps supported.
Models 2/3 use exact-posterior independent Metropolis-Hastings, with a Laplace
approximation used only to construct proposals. Model 4 is a modular particle
filter: static parameters are sampled from model 3, then held fixed per particle.
Its dynamic update is conditional on these static draws (not full joint Bayes).
"""
from pathlib import Path
import sys, json, gzip, hashlib, time
sys.path.insert(0, str(Path(__file__).parent/'deps'))
import numpy as np
import pandas as pd
from scipy.special import gammaln, digamma, logsumexp, expit
from scipy.optimize import minimize
from scipy.stats import multivariate_t, norm, rankdata, t as student_t
from scipy.linalg import helmert

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'data_collection/data/bigquery_upload/tv_daily_coverage.jsonl.gz').exists())
BASE=ROOT/'data_collection'
OUT=ROOT/'output/stalin_russia1'
OUT.mkdir(parents=True,exist_ok=True)
SEED=20261004
NAMES={'M1':'Gamma-Poisson: постоянный уровень',
       'M2':'Negative binomial: дополнительная дисперсия',
       'M3':'NB: календарная иерархия и тренд',
       'M4':'NB: календарь, тренд и динамический уровень'}

def load_data():
    p=BASE/'data/bigquery_upload/tv_daily_coverage.jsonl.gz'
    with gzip.open(p,'rt',encoding='utf-8') as f:
        d=pd.DataFrame(json.loads(line) for line in f)
    d=d[d.channel=='RUSSIA1'].copy().sort_values('day')
    d['date']=pd.to_datetime(d.day)
    d['observed']=(d.coverage_status=='observed_listed_broadcasts') & (d.inventory_status=='200')
    d['y']=d.stalin_candidates.where(d.observed)
    assert len(d)==len(pd.date_range(d.date.min(),d.date.max()))
    assert d.date.is_unique and d.y.dropna().ge(0).all()
    d.to_csv(OUT/'daily_data.csv',index=False,encoding='utf-8-sig')
    return d, hashlib.sha256(p.read_bytes()).hexdigest()

def nb_logpmf(y,mu,k):
    return (gammaln(y+k)-gammaln(k)-gammaln(y+1)+k*(np.log(k)-np.log(k+mu))
            +y*(np.log(mu)-np.log(k+mu)))

def design(dates,calendar=False,center=0):
    dates=pd.DatetimeIndex(dates)
    if not calendar:return np.ones((len(dates),1))
    years=np.asarray((dates-pd.Timestamp('2023-01-01')).days)/365.25-center
    # Orthonormal contrasts give exactly sum-zero population effects.
    month=helmert(12,full=False).T[dates.month-1]
    dow=helmert(7,full=False).T[dates.dayofweek]
    return np.column_stack([np.ones(len(dates)),years,month,dow])

def posterior_problem(d,calendar):
    ok=d.observed.to_numpy()
    dates=d.date[ok]
    center=float(np.mean((dates-pd.Timestamp('2023-01-01')).dt.days)/365.25) if calendar else 0
    X=design(dates,calendar,center)
    y=d.y[ok].to_numpy(float)
    sd=np.array([1.5,.5]+[.4]*17+[1.5]) if calendar else np.array([1.5,1.5])
    prior=np.zeros(len(sd));prior[0]=np.log(2)
    initial=prior.copy();initial[0]=np.log(max(y.mean(),.1));initial[-1]=np.log(.7)
    fact=gammaln(y+1)
    def fun(theta):
        eta=X@theta[:-1]
        if np.max(np.abs(eta))>35 or abs(theta[-1])>15:
            return 1e100,np.zeros_like(theta)
        mu=np.exp(eta);k=np.exp(theta[-1]);den=mu+k
        ll=gammaln(y+k)-gammaln(k)-fact+k*(theta[-1]-np.log(den))+y*(eta-np.log(den))
        g_eta=k*(y-mu)/den
        gk=k*(digamma(y+k)-digamma(k)+theta[-1]-np.log(den)+1-(k+y)/den)
        diff=(theta-prior)/sd
        grad=np.r_[X.T@g_eta,gk.sum()]-(theta-prior)/sd**2
        return float(-ll.sum()+.5*np.dot(diff,diff)),-grad
    return fun,initial,center

def diagnostics(chains):
    # Rank-normalized split Rhat, also folded, following the modern diagnostic.
    m,n,p=chains.shape
    half=n//2
    c=np.concatenate([chains[:,:half],chains[:,-half:]],axis=0)
    def rh(z):
        W=z.var(axis=1,ddof=1).mean(axis=0)
        B=z.shape[1]*z.mean(axis=1).var(axis=0,ddof=1)
        return np.sqrt(((z.shape[1]-1)/z.shape[1]*W+B/z.shape[1])/W)
    z=np.empty_like(c);fold=np.empty_like(c)
    for j in range(p):
        a=c[:,:,j];N=a.size
        z[:,:,j]=norm.ppf((rankdata(a.ravel()).reshape(a.shape)-.375)/(N+.25))
        a=np.abs(a-np.median(a))
        fold[:,:,j]=norm.ppf((rankdata(a.ravel()).reshape(a.shape)-.375)/(N+.25))
    rhat=np.maximum(rh(z),rh(fold))
    # Conservative per-chain autocorrelation ESS, aggregated over chains.
    ess=[]
    for j in range(p):
        total=0
        for a in chains[:,:,j]:
            a=a-a.mean();ft=np.fft.rfft(a,n=2*n)
            ac=np.fft.irfft(ft*np.conj(ft))[:n];ac=ac/ac[0]
            pairs=ac[1:-1:2]+ac[2::2]
            end=np.flatnonzero(pairs<0)
            positive=pairs[:end[0]] if len(end) else pairs
            total+=n/max(1,1+2*np.minimum.accumulate(positive).sum())
        ess.append(total)
    return float(rhat.max()),float(min(ess))

def fit_nb(d,calendar,seed,draws=1200,warm=300):
    fun,x0,center=posterior_problem(d,calendar)
    opt=minimize(fun,x0,jac=True,method='BFGS',options={'gtol':1e-6,'maxiter':350})
    # Build the local Hessian directly; do not trust the BFGS inverse approximation.
    x=opt.x;p=len(x);eps=1e-4
    H=np.column_stack([(fun(x+np.eye(p)[j]*eps)[1]-fun(x-np.eye(p)[j]*eps)[1])/(2*eps) for j in range(p)])
    eigen,U=np.linalg.eigh((H+H.T)/2)
    cov=(U/np.maximum(eigen,1e-4))@U.T
    proposal=multivariate_t(loc=x,shape=cov,df=8)
    rng=np.random.default_rng(seed)
    samples=np.empty((4,draws,p));accepted=[]
    # Batched proposal generation avoids sampling overhead inside MH.
    for chain in range(4):
        candidates=proposal.rvs(size=draws+warm,random_state=rng)
        q=proposal.logpdf(candidates)
        current=x.copy();target=-fun(current)[0]-float(proposal.logpdf(current));acc=0
        logu=np.log(rng.random(draws+warm))
        for i,candidate in enumerate(candidates):
            proposed=-fun(candidate)[0]-q[i]
            if logu[i]<proposed-target:
                current=candidate;target=proposed
                if i>=warm:acc+=1
            if i>=warm:samples[chain,i-warm]=current
        accepted.append(acc/draws)
    rhat,ess=diagnostics(samples)
    diag={'calendar':calendar,'n_train':int(d.observed.sum()),'max_rank_split_rhat':rhat,
          'min_autocorrelation_ess':ess,'acceptance':accepted,
          'gradient_max':float(abs(fun(x)[1]).max()),'optimizer_success':bool(opt.success),
          'draws_per_chain':draws,'warmup':warm,'center_years':center,
          'map':x.tolist()}
    if rhat>1.03 or ess<250:
        if draws<4800:return fit_nb(d,calendar,seed,draws*2,warm*2)
        raise RuntimeError(f'Unreliable posterior sampling: {diag}')
    return {'theta':samples.reshape(-1,p),'center':center,'calendar':calendar,'diagnostics':diag}

def static_predict(fit,dates,n,seed):
    rng=np.random.default_rng(seed)
    theta=fit['theta'][rng.integers(len(fit['theta']),size=n)]
    X=design(dates,fit['calendar'],fit['center'])
    mu=np.exp(theta[:,:-1]@X.T);k=np.exp(theta[:,-1,None])
    draws=rng.negative_binomial(k,k/(k+mu))
    return draws,mu.mean(axis=0),{'mu':mu,'k':k}

def filter_state(d,fit,q,particles=8192,seed=1,trace=False):
    """Modular posterior mixture: filter separately conditional on static draws.

    128 static posterior draws, each with an independent state particle filter.
    Observations update states within each draw, not static-draw weights.
    Thus this is deliberately a cut/modular posterior, not exact full Bayes.
    """
    rng=np.random.default_rng(seed)
    groups=128;per=max(32,particles//groups)
    theta=fit['theta'][rng.integers(len(fit['theta']),size=groups)]
    X=design(d.date,True,fit['center']);base=theta[:,:-1]@X.T
    k=np.exp(theta[:,-1,None])
    state=rng.normal(0,.3,(groups,per))
    logweights=np.full((groups,per),-np.log(per))
    miness=[];meaness=[];history=[]
    for i,y in enumerate(d.y):
        state+=rng.normal(0,q,state.shape)
        if np.isfinite(y):
            mu=np.exp(base[:,i,None]+state)
            lw=logweights+nb_logpmf(y,mu,k)
            logweights=lw-logsumexp(lw,axis=1,keepdims=True)
            w=np.exp(logweights)
            if trace:
                # Conditional filtering summary, using current weights, not future states.
                weights=w.ravel()/groups;values=mu.ravel()
                order=np.argsort(values);cdf=np.cumsum(weights[order]);cdf[-1]=1
                lo,med,hi=np.interp([.1,.5,.9],cdf,values[order])
                history.append({'date':str(d.date.iloc[i].date()),'observed':True,
                  'state_mean':float(np.sum(w*state)/groups),
                  'intensity_mean':float(np.sum(w*mu)/groups),
                  'intensity_lo80':float(lo),'intensity_median':float(med),'intensity_hi80':float(hi)})
            ess=1/(w*w).sum(axis=1)
            miness.append(float(ess.min()));meaness.append(float(ess.mean()))
            # Resample only concentrated groups; preserve weights otherwise.
            resample=np.flatnonzero(ess<per/2)
            for g in resample:
                u=(rng.random()+np.arange(per))/per
                cdf=w[g].cumsum();cdf[-1]=1
                state[g]=state[g,np.searchsorted(cdf,u)]
                logweights[g]=-np.log(per)
        elif trace:
            w=np.exp(logweights);mu=np.exp(base[:,i,None]+state)
            weights=w.ravel()/groups;values=mu.ravel();order=np.argsort(values)
            cdf=np.cumsum(weights[order]);cdf[-1]=1
            lo,med,hi=np.interp([.1,.5,.9],cdf,values[order])
            history.append({'date':str(d.date.iloc[i].date()),'observed':False,
              'state_mean':float(np.sum(w*state)/groups),'intensity_mean':float(np.sum(w*mu)/groups),
              'intensity_lo80':float(lo),'intensity_median':float(med),'intensity_hi80':float(hi)})
    # Final resampling produces equally weighted draws from each filtering belief.
    for g in range(groups):
        u=(rng.random()+np.arange(per))/per
        cdf=np.exp(logweights[g]).cumsum();cdf[-1]=1
        state[g]=state[g,np.searchsorted(cdf,u)]
    result={'groups':groups,'particles_per_group':per,'q':q,
                       'min_pre_resampling_ess':min(miness),
                       'mean_pre_resampling_ess':float(np.mean(meaness))}
    if trace:result['history']=history
    return theta,state,result

def dynamic_predict(d,fit,dates,q,n,seed,particles=8192):
    theta,state,diag=filter_state(d,fit,q,particles,seed)
    rng=np.random.default_rng(seed+100000)
    g=rng.integers(len(theta),size=n);j=rng.integers(state.shape[1],size=n)
    level=state[g,j].copy();theta=theta[g]
    X=design(dates,True,fit['center']);base=theta[:,:-1]@X.T
    k=np.exp(theta[:,-1,None]);mu=np.empty((n,len(dates)));draws=np.empty_like(mu,dtype=int)
    for i in range(len(dates)):
        level+=rng.normal(0,q,n)
        mu[:,i]=np.exp(base[:,i]+level)
        draws[:,i]=rng.negative_binomial(k[:,0],k[:,0]/(k[:,0]+mu[:,i]))
    return draws,mu.mean(axis=0),{'mu':mu,'k':k},diag

def crps_sample(draws,y):
    draws=np.sort(np.asarray(draws),axis=0)
    n=len(draws);weights=(2*np.arange(1,n+1)-n-1)/n**2
    return np.abs(draws-y).mean(axis=0)-np.sum(weights[:,None]*draws,axis=0)

def score(draws,mean,y,distribution=None,seed=1):
    y=np.asarray(y,float);ok=np.isfinite(y)
    yy=y[ok].astype(int);s=draws[:,ok];m=mean[ok]
    result={'n_days':len(yy),'daily_mae':float(np.abs(m-yy).mean()),
            'daily_mse':float(((m-yy)**2).mean()),
            'daily_crps':float(crps_sample(s,yy).mean())}
    for level in [.8,.95]:
        a=(1-level)/2;lo,hi=np.quantile(s,[a,1-a],axis=0)
        result[f'daily_coverage_{int(100*level)}']=float(((yy>=lo)&(yy<=hi)).mean())
        result[f'daily_width_{int(100*level)}']=float((hi-lo).mean())
    rng=np.random.default_rng(seed)
    if distribution is not None:
        mu=distribution['mu'][:,ok];k=distribution.get('k')
        if k is not None:lp=nb_logpmf(yy[None,:],mu,k)
        else:lp=yy[None,:]*np.log(mu)-mu-gammaln(yy[None,:]+1)
        result['daily_nll']=float(-(logsumexp(lp,axis=0)-np.log(len(lp))).mean())
    lower=(s<yy).mean(axis=0);mass=(s==yy).mean(axis=0)
    pit=lower+rng.random(len(yy))*mass
    total=s.sum(axis=1);actual=int(yy.sum());point=float(m.sum())
    lo80,hi80=np.quantile(total,[.1,.9]);lo95,hi95=np.quantile(total,[.025,.975])
    result.update({'actual_sum_observed':actual,'predicted_sum_observed':point,
      'monthly_error':point-actual,'monthly_ae':abs(point-actual),'monthly_se':(point-actual)**2,
      'monthly_crps':float(crps_sample(total[:,None],np.array([actual]))[0]),
      'monthly_lo80':float(lo80),'monthly_hi80':float(hi80),'monthly_lo95':float(lo95),'monthly_hi95':float(hi95),
      'monthly_coverage80':bool(lo80<=actual<=hi80),'monthly_coverage95':bool(lo95<=actual<=hi95),
      'monthly_width80':float(hi80-lo80),'monthly_width95':float(hi95-lo95)})
    return result,pit

def forecast_set(train,dates,n,seed,q=.07,save=False):
    rng=np.random.default_rng(seed)
    a=1+train.y.sum();b=1+train.observed.sum()
    lam=rng.gamma(a,1/b,n);mu=np.repeat(lam[:,None],len(dates),axis=1)
    forecasts={'M1':(rng.poisson(mu),mu.mean(axis=0),{'mu':mu})}
    fit2=fit_nb(train,False,seed+2);fit3=fit_nb(train,True,seed+3)
    forecasts['M2']=static_predict(fit2,dates,n,seed+12)
    forecasts['M3']=static_predict(fit3,dates,n,seed+13)
    a,b,c,diag=dynamic_predict(train,fit3,dates,q,n,seed+14)
    forecasts['M4']=(a,b,c)
    diagnostics_out={'M2':fit2['diagnostics'],'M3':fit3['diagnostics'],'M4':diag}
    if save:
        np.savez_compressed(OUT/'posterior_samples.npz',M2=fit2['theta'],M3=fit3['theta'])
        (OUT/'final_diagnostics.json').write_text(json.dumps(diagnostics_out,ensure_ascii=False,indent=2),encoding='utf-8')
    return forecasts,diagnostics_out,fit3

def summarize(records):
    frame=pd.DataFrame(records)
    rows=[]
    for model,g in frame.groupby('model',sort=False):
        complete=g[g.n_days==g.horizon]
        weights=g.n_days.to_numpy()
        row={'model':model,'name':NAMES[model],'origins':len(g),'observed_test_days':int(g.n_days.sum()),
             'full_months':len(complete)}
        for col in ['daily_mae','daily_mse','daily_crps','daily_nll','daily_coverage_80','daily_coverage_95','daily_width_80','daily_width_95']:
            row[col]=float(np.average(g[col],weights=weights))
        row['daily_rmse']=np.sqrt(row.pop('daily_mse'))
        for col in ['monthly_ae','monthly_crps','monthly_coverage80','monthly_coverage95','monthly_width80','monthly_width95']:
            row[col]=float(complete[col].mean())
        row['monthly_rmse']=float(np.sqrt(complete.monthly_se.mean()))
        rows.append(row)
    return pd.DataFrame(rows)

def paired_comparisons(records):
    # Non-overlapping monthly windows; paired loss differences, lag-1 HAC variance.
    frame=pd.DataFrame(records);frame=frame[frame.n_days==frame.horizon]
    out=[]
    for a,b in [('M1','M2'),('M2','M3'),('M3','M4'),('M1','M4')]:
        A=frame[frame.model==a].set_index('origin');B=frame[frame.model==b].set_index('origin')
        for loss in ['monthly_se','monthly_crps']:
            diff=(A[loss]-B[loss]).to_numpy();N=len(diff);center=diff-diff.mean()
            gamma0=np.dot(center,center)/N;gamma1=np.dot(center[1:],center[:-1])/N
            variance=max(0,gamma0+gamma1)  # Bartlett weight for lag 1 is .5
            se=np.sqrt(variance/N)
            stat=diff.mean()/se if se else 0
            p=2*student_t.sf(abs(stat),df=N-1)
            rng=np.random.default_rng(SEED+N)
            # Circular moving-block bootstrap, two months per block.
            starts=rng.integers(0,N,size=(10000,(N+1)//2))
            inds=np.stack([starts,(starts+1)%N],axis=-1).reshape(10000,-1)[:,:N]
            means=diff[inds].mean(axis=1);lo,hi=np.quantile(means,[.025,.975])
            out.append({'earlier':a,'later':b,'loss':loss,'n_full_months':N,
              'mean_loss_improvement':float(diff.mean()),'DM_HAC_lag1':float(stat),
              'approx_p_two_sided':float(p),'block_bootstrap_lo95':float(lo),'block_bootstrap_hi95':float(hi)})
    return pd.DataFrame(out)

def main():
    started=time.time();d,source_hash=load_data()
    # Development uses 2024 only. Test: Jan 2025-Sep 2026, 21 monthly occasions.
    # No test month is used to tune q or the calendar priors.
    qs=[0.,.03,.07,.15]
    dev=[];devdiag=[]
    for fold,start in enumerate(pd.date_range('2024-06-01','2024-12-01',freq='MS')):
        end=start+pd.DateOffset(months=1)-pd.Timedelta(days=1)
        train=d[d.date<start];test=d[(d.date>=start)&(d.date<=end)]
        fit=fit_nb(train,True,SEED+100+fold)
        for q in qs:
            s,m,dist,diag=dynamic_predict(train,fit,test.date,q,3000,SEED+200+fold)
            result,_=score(s,m,test.y,dist,SEED+fold)
            dev.append({'origin':(start-pd.Timedelta(days=1)).date().isoformat(),'q':q,
                        'horizon':len(test),**result})
        print('development',start.date(), 'elapsed',round(time.time()-started),flush=True)
    devframe=pd.DataFrame(dev);devframe.to_csv(OUT/'development_scores.csv',index=False)
    complete=devframe[devframe.n_days==devframe.horizon]
    q=float(complete.groupby('q').monthly_crps.mean().idxmin())
    print('frozen q',q,flush=True)
    records=[];pits={m:[] for m in NAMES};diags=[];daily_records=[]
    for fold,start in enumerate(pd.date_range('2025-01-01','2026-09-01',freq='MS')):
        end=start+pd.DateOffset(months=1)-pd.Timedelta(days=1)
        train=d[d.date<start];test=d[(d.date>=start)&(d.date<=end)]
        forecasts,diagnostic,_=forecast_set(train,test.date,6000,SEED+1000+fold*20,q)
        diags.append({'origin':(start-pd.Timedelta(days=1)).date().isoformat(),**diagnostic})
        for model,(s,m,dist) in forecasts.items():
            result,pit=score(s,m,test.y,dist,SEED+3000+fold)
            records.append({'origin':(start-pd.Timedelta(days=1)).date().isoformat(),
                            'test_start':start.date().isoformat(),'test_end':end.date().isoformat(),
                            'model':model,'horizon':len(test),'train_days':int(train.observed.sum()),**result})
            pits[model].extend(pit.tolist())
            lo,hi=np.quantile(s,[.025,.975],axis=0)
            for date,y,point,low,high in zip(test.date,test.y,m,lo,hi):
                daily_records.append({'model':model,'date':date.date().isoformat(),
                                      'actual':y,'mean':point,'lo95':low,'hi95':high})
        pd.DataFrame(records).to_csv(OUT/'backtest_by_origin.csv',index=False)
        print('test',start.date(),'elapsed',round(time.time()-started),flush=True)
    summary=summarize(records);summary.to_csv(OUT/'evaluation.csv',index=False,encoding='utf-8-sig')
    paired_comparisons(records).to_csv(OUT/'model_comparisons.csv',index=False)
    pd.DataFrame(daily_records).to_csv(OUT/'backtest_daily.csv',index=False)
    (OUT/'backtest_diagnostics.json').write_text(json.dumps(diags,indent=2),encoding='utf-8')
    start=d.date.max()+pd.Timedelta(days=1)
    end=d.date.max()+pd.DateOffset(months=1)
    dates=pd.date_range(start,end)
    forecasts,_,fit=forecast_set(d,dates,30000,SEED+5000,q,True)
    future=[];monthly=[]
    for model,(s,m,dist) in forecasts.items():
        total=s.sum(axis=1);quant=np.quantile(total,[.025,.1,.5,.9,.975])
        monthly.append({'model':model,'name':NAMES[model],'start':start.date().isoformat(),
          'end':end.date().isoformat(),'days':len(dates),'mean':float(m.sum()),'median':float(quant[2]),
          'lo80':float(quant[1]),'hi80':float(quant[3]),'lo95':float(quant[0]),'hi95':float(quant[4]),
          'probability_ge_50':float((total>=50).mean())})
        quant_daily=np.quantile(s,[.025,.1,.5,.9,.975],axis=0)
        for i,date in enumerate(dates):
            future.append({'model':model,'date':date.date().isoformat(),'mean':m[i],
              'median':quant_daily[2,i],'lo80':quant_daily[1,i],'hi80':quant_daily[3,i],
              'lo95':quant_daily[0,i],'hi95':quant_daily[4,i]})
    np.savez_compressed(OUT/'forecast_paths.npz',dates=np.asarray(dates.strftime('%Y-%m-%d'),dtype='<U10'),
                        **{model:f[0] for model,f in forecasts.items()})
    pd.DataFrame(future).to_csv(OUT/'forecast_daily.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(monthly).to_csv(OUT/'forecast_month.csv',index=False,encoding='utf-8-sig')
    # Particle stability, held apart from predictive model selection.
    stability=[]
    for particles in [8192,32768]:
        for seed in [SEED+6000,SEED+6001,SEED+6002]:
            s,m,_,diag=dynamic_predict(d,fit,dates,q,15000,seed,particles)
            stability.append({'particles':particles,'seed':seed,'mean':float(m.sum()),
                              'lo95':float(np.quantile(s.sum(1),.025)),
                              'hi95':float(np.quantile(s.sum(1),.975)),**diag})
    pd.DataFrame(stability).to_csv(OUT/'particle_stability.csv',index=False)
    metadata={'source':str(BASE/'data/bigquery_upload/tv_daily_coverage.jsonl.gz'),
      'source_sha256':source_hash,'timezone':'Europe/Moscow','channel':'RUSSIA1',
      'count_definition':'Surname-token candidates in all archived ASR broadcasts, not fully disambiguated person mentions',
      'first_date':d.day.min(),'last_date':d.day.max(),'calendar_days':len(d),
      'observed_days':int(d.observed.sum()),'excluded_days':int((~d.observed).sum()),
      'sum_complete_days':int(d.y.sum()),'sum_all_available':int(d.stalin_candidates.sum()),
      'q_selected_on_development':q,'development':'2024-06 through 2024-12',
      'test':'2025-01 through 2026-09','test_origins':21,
      'primary_selection_metric':'Monthly CRPS on months with all days observed',
      'selected_model':str(summary.loc[summary.monthly_crps.idxmin(),'model']),
      'seed':SEED,'runtime_seconds':round(time.time()-started,1)}
    (OUT/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    plots(d,summary,records,future,monthly,pits)
    print(summary.to_string(index=False),flush=True)
    print(pd.DataFrame(monthly).to_string(index=False),flush=True)
    print('DONE',metadata,flush=True)

def plots(d,summary,records,future,monthly,pits):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','axes.spines.top':False,
      'axes.spines.right':False,'figure.dpi':140,'savefig.dpi':180})
    colors={'M1':'#969696','M2':'#dc7c32','M3':'#396cb0','M4':'#247c68'}
    figs=OUT/'figures';figs.mkdir(exist_ok=True)
    f=pd.DataFrame(future);f['date']=pd.to_datetime(f.date)
    fig,ax=plt.subplots(figsize=(11,4.6))
    hist=d[d.date>='2026-07-01'];ax.plot(hist.date,hist.y,color='#444444',lw=1,label='Наблюдения')
    for model in NAMES:
        a=f[f.model==model];ax.plot(a.date,a['mean'],label=model,color=colors[model],lw=1.8)
    a=f[f.model=='M4'];ax.fill_between(a.date,a.lo95,a.hi95,color=colors['M4'],alpha=.14,label='M4: 95% прогнозный интервал')
    ax.axvline(pd.Timestamp('2026-10-02'),color='#777',ls='--',lw=1)
    ax.set(ylabel='Совпадения фамилии в день',title='Россия 1: прогноз на 03.10–02.11.2026')
    ax.legend(ncol=3,fontsize=8);fig.autofmt_xdate();fig.tight_layout();fig.savefig(figs/'daily_forecast.png');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,col,title in zip(axes,['monthly_rmse','monthly_crps'],['Ошибка месячного итога (RMSE)','Вероятностная ошибка (CRPS)']):
        ax.bar(summary.model,summary[col],color=[colors[x] for x in summary.model]);ax.set_title(title);ax.set_ylabel('Меньше лучше')
        for i,v in enumerate(summary[col]):ax.text(i,v,f'{v:.1f}',ha='center',va='bottom')
    fig.suptitle(f'Историческая проверка: {int(summary.full_months.iloc[0])} полностью наблюдаемых месяцев')
    fig.tight_layout();fig.savefig(figs/'evaluation.png');plt.close(fig)
    fig,axes=plt.subplots(1,4,figsize=(12,3),sharey=True)
    for ax,model in zip(axes,NAMES):
        ax.hist(pits[model],bins=np.linspace(0,1,11),density=True,color=colors[model],alpha=.8)
        ax.axhline(1,color='#333',ls='--',lw=1);ax.set_title(model);ax.set_xlabel('Randomized PIT')
    axes[0].set_ylabel('Плотность');fig.suptitle('Калибровка дневных распределений: ориентир — равномерность')
    fig.tight_layout();fig.savefig(figs/'pit.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4.3))
    r=pd.DataFrame(records);full=r[r.n_days==r.horizon]
    actual=full[full.model=='M1'];ax.plot(pd.to_datetime(actual.test_start),actual.actual_sum_observed,'k.-',label='Факт',lw=2)
    for model in NAMES:
        a=full[full.model==model];ax.plot(pd.to_datetime(a.test_start),a.predicted_sum_observed,'o-',color=colors[model],label=model,ms=3)
    ax.set(ylabel='Совпадения за месяц',title='Месячные итоги: прогнозы сделаны до начала каждого месяца')
    ax.legend(ncol=5);fig.autofmt_xdate();fig.tight_layout();fig.savefig(figs/'backtest_months.png');plt.close(fig)

if __name__=='__main__':main()
