"""Actual demand research with explicit aggregate proxies and training-only screening."""
import numpy as np
import core

CONFIG = dict(penalty=.001, standardized=True, piecewise=False, rho=.5, loss='log')


def fit(rows, params):
    return core.fit(rows, params, **CONFIG)


def screen(rows, params):
    """Conservative input fences; residuals alone never remove an observation."""
    reasons = [[] for _ in rows]
    fences = {}
    for country in core.COUNTRIES:
        ids = [i for i,r in enumerate(rows) if r['country']==country]
        if not ids: continue
        for name in ('price','general','designer','rd'):
            values = np.log1p([rows[i][name] for i in ids])
            q1,q3 = np.quantile(values,[.25,.75]); width=q3-q1
            # A zero IQR cannot distinguish a genuine tail from a discrete common choice.
            if width <= 1e-9: continue
            low,high=q1-3*width,q3+3*width
            fences[country+'/'+name]=[float(low),float(high)]
            for i,v in zip(ids,values):
                if not low<=v<=high: reasons[i].append('extreme_input/'+name)
    clean=[r for i,r in enumerate(rows) if not reasons[i]]
    preliminary=fit(clean,params)
    x=core.features(rows,params,CONFIG['rho'],False)
    prediction=core.predict(rows,x,preliminary['beta'])
    shares=core.actual_shares(rows)
    residual=np.log(np.maximum(shares,1e-30)/np.maximum(prediction,1e-30))
    reference=np.array([v for i,v in enumerate(residual) if not reasons[i]])
    median=float(np.median(reference));mad=float(1.4826*np.median(abs(reference-median)))
    limit=max(np.log(2),4*mad)
    for i,r in enumerate(rows):
        if residual[i]<median-limit and r['supply_evidence']:
            reasons[i].append('suspected_supply_distorted_low_demand')
    audits=[dict(key=core.key(r),excluded=bool(why),reasons=why,observed_demand=r['demand'],
        preliminary_implied_demand=float(prediction[i]*sum(q['demand'] for q in rows if core.old.group_key(q)==core.old.group_key(r))),
        log_share_residual=float(residual[i]),supply_evidence=r['supply_evidence'],supply_refs=r['supply_refs']) for i,(r,why) in enumerate(zip(rows,reasons))]
    return [r for r,why in zip(rows,reasons) if not why],dict(audits=audits,input_fences_log1p=fences,
        residual_median=median,residual_mad_scale=mad,low_residual_distance=limit,
        preliminary_beta=preliminary['beta'],rule='log1p input 3 IQR fence; low log-share residual below median-max(log(2),4 scaled MAD) AND (actual unmet demand OR >=98% machine utilization with retail sales >= production within display intervals); suspected supply effect, not proof')


def train(actual, curves, out, nd):
    training={p:[] for p in ('复合梁','连接件')}; invalid=[]
    for market in range(1,11):
        for team in actual.teams(market):
            common={k:actual.get(market,5,team,'incomestatement',label) for k,label in [('general','一般营销'),('designer','设计师营销'),('rd','研发')]}
            previous=actual.get(market,4,team,'incomestatement','研发')
            for product in training:
                q=actual.get(market,5,team,'productiondetails','生产规模, 千单位',product)
                cap=actual.get(market,5,team,'productiondetails',f'机器产能, {product}, 千单位')
                retail=[actual.get(market,5,team,'marketdetails',c,product,'销售, 千单位') for c in core.COUNTRIES]
                sold_through_production=(q['value']>q['half'] and cap['value']>0 and q['value']/cap['value']>=.98
                    and sum(r['value'] for r in retail)>=q['value']-q['half']-sum(r['half'] for r in retail))
                for country in core.COUNTRIES:
                    price=actual.get(market,5,team,'marketdetails',country+', 美元',product,'价格')
                    demand=actual.get(market,5,team,'marketdetails',country,product,'需求, 千单位')
                    sales=actual.get(market,5,team,'marketdetails',country,product,'销售, 千单位')
                    row=dict(market_id=market,team_id=team,phase='formal',round=5,product=product,country=country,
                        context_id='T6V0_ACTUAL_COMPANY_EXPENSE_PROXY',initial_price=1.,price=price['value'],demand=demand['value'],sales=sales['value'],
                        **{k:v['value'] for k,v in common.items()},previous_rd=previous['value'],
                        sources=dict(**common,previous_rd=previous,price=price,demand=demand,sales=sales),
                        supply_evidence=bool(demand['value']-sales['value']>demand['half']+sales['half'] or sold_through_production),
                        supply_refs=dict(production=q,capacity=cap,demand=demand,sales=sales,retail_sales=retail),
                        input_scope='ACTUAL_COMPANY_TOTAL_EXPENSE_PROXY_NOT_PRODUCT_COUNTRY_DECISION')
                    if price['value']<=0 or demand['value']<=0:
                        invalid.append(dict(row,reason='nonpositive_price_or_demand_log_undefined'));continue
                    training[product].append(row)
    nd.save(out/'demand_invalid_rows.json',invalid)
    nd.save(out/'demand_actual_rows.json',training)
    models={};diagnostics={}
    for product,rows in training.items():
        params=curves['rd/'+product]['parameters']; models[product]={}
        for kind in ('SHARE','COUNTRY/泰国','COUNTRY/印尼'):
            pool=[r for r in rows if kind=='SHARE' or r['country']==kind.split('/')[1]]
            print('TRAIN demand',product,kind,len(pool),flush=True)
            selected,audit=screen(pool,params); m=fit(selected,params); folds=[];predictions=[]
            for held in range(1,11):
                tr=[r for r in pool if r['market_id']!=held];te=[r for r in pool if r['market_id']==held]
                kept,train_audit=screen(tr,params);fm=fit(kept,params)
                p=core.predict(te,core.features(te,params,.5,False),fm['beta'])
                raw_fit=fit(tr,params);raw=core.predict(te,core.features(te,params,.5,False),raw_fit['beta'])
                folds.append(dict(held_market=held,train_markets=sorted({r['market_id'] for r in kept}),train_n=len(tr),retained_n=len(kept),test_n=len(te),
                    beta=fm['beta'],mae_pp=100*core.score(te,p),unscreened_mae_pp=100*core.score(te,raw),training_screen=train_audit))
                y=core.actual_shares(te)
                predictions.extend(dict(key=core.key(r),actual_share=float(a),predicted_share=float(b)) for r,a,b in zip(te,y,p))
            m.update(training_round=5,curve_round=5,n_before=len(pool),n_retained=len(selected),excluded_n=len(pool)-len(selected),
                nested_validation=dict(folds=folds,predictions=predictions,mae_pp=float(np.mean([f['mae_pp'] for f in folds])),unscreened_mae_pp=float(np.mean([f['unscreened_mae_pp'] for f in folds]))),
                scope='固定正则0.001/rho0.5/线性价格；真实价格及需求，公司合计营销研发代理；筛选只在各训练折；留出全量评分，非事前精度')
            models[product][kind]=m;diagnostics[product+'/'+kind]=audit
    nd.save(out/'demand_screening.json',diagnostics)
    return models


def self_check():
    rows=[]
    for m in range(1,4):
        for i in range(10):
            rows.append(dict(market_id=m,phase='formal',round=5,team_id=str(i),country='泰国',price=100+i,initial_price=1,
                general=100,designer=100,rd=10,previous_rd=10,demand=10+i/10,supply_evidence=False,supply_refs={}))
    kept,audit=screen(rows,[1.,.1,1.,.2])
    assert len(kept)==len(rows) and all(not a['excluded'] for a in audit['audits'])
    rows[-1]=dict(rows[-1],price=1e8)
    kept,audit=screen(rows,[1.,.1,1.,.2])
    assert len(kept)<len(rows) and 'extreme_input/price' in audit['audits'][-1]['reasons']
    rows[-1]=dict(rows[-2],team_id='supply-test',demand=.01,supply_evidence=True)
    kept,audit=screen(rows,[1.,.1,1.,.2])
    assert 'suspected_supply_distorted_low_demand' in audit['audits'][-1]['reasons']
    rows[-1]['supply_evidence']=False
    _,audit=screen(rows,[1.,.1,1.,.2])
    assert not audit['audits'][-1]['excluded']
    return True
