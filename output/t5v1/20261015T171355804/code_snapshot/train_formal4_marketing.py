"""Formal4 change-response training; company expense proxies remain explicitly labeled."""
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'code'),str(ROOT/'work')]
import numpy as np
from scipy.optimize import lsq_linear
import t5v0
import solve_formal5_full as base

OUT=ROOT/(ROOT/'work/formal5_marketing_active.txt').read_text(encoding='utf-8-sig').strip()
read=base.read;sha=base.sha


def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def charts(doc):
    scripts=doc.get('scripts',[])
    if not scripts:scripts=[doc['html']]
    result=[]
    for script in scripts:
        for m in re.finditer(r'Chart\.create\("([^\"]+)",\s*"scatter",\s*',script):
            data,_=json.JSONDecoder().raw_decode(script[m.end():])
            result.append(dict(id=m[1],data=data))
    return result


def load_weights():
    allrows=[];sources=[]
    for round_ in [4,5]:
        for c,panel in [('泰国','marketreportdomestic'),('印尼','marketreportinternational1')]:
            path=(ROOT/f'output/round_close/20261013_formal3_close/formal4_initial/raw/market5_formal4_{panel}.json') if round_==4 else OUT/('latest/sales_thailand.json' if c=='泰国' else 'latest/sales_indonesia.json')
            doc=read(path);records=charts(doc)
            assert len(records)==2
            sources.append(path)
            for r in records:
                p='复合梁' if r['id'].endswith('Product1') else '连接件'
                for series in r['data']['dataset']:
                    point=series['data'][0]
                    assert point['x']>0 and np.isfinite(point['y'])
                    allrows.append(dict(round=round_,country=c,product=p,factor=series['seriesname'],importance=point['x'],
                        relative_position_pct=point['y'],source=str(path.relative_to(ROOT)),sha256=sha(path),
                        x_axis=r['data']['chart']['xAxisName'],y_axis=r['data']['chart']['yAxisName']))
    assert len(allrows)==32
    ratios={}
    for p in base.P:
        ratios[p]={}
        for c in base.C:
            ratios[p][c]={}
            for factor in ['价格','一般营销','设计师营销','研发']:
                pair=[next(x for x in allrows if (x['round'],x['country'],x['product'],x['factor'])==(r,c,p,factor)) for r in [4,5]]
                ratios[p][c][factor]=pair[1]['importance']/pair[0]['importance']
    save('sales_importance_4_5.json',dict(rows=allrows,ratios_5_over_4=ratios,
        mapping='ANALYSIS_ASSUMPTION: effective elasticity = trained shape * published relative importance; y-position is diagnostic, never multiplied as a demand factor'))
    return allrows,ratios,sources


def assemble():
    source=ROOT/'output/t4v1/20261014T153914569881+0800/dataset.json'
    prior=read(source);r3=read(base.OLD/'models_full.json');r4=read(base.BUNDLE/'models_full.json')
    sources={str(source.relative_to(ROOT)):sha(source),str((base.OLD/'models_full.json').relative_to(ROOT)):sha(base.OLD/'models_full.json')}
    paired=[];excluded=[]
    for product,rows in prior['competitive_rows_by_product'].items():
        for old in rows:
            market=old['market_id'];country=old['country'];team=old['team_id']
            mp=ROOT/f'output/round_close/20261014_formal4_close/raw/market{market}_formal4_marketdetails.json'
            ip=ROOT/f'output/round_close/20261014_formal4_close/raw/market{market}_formal4_incomestatement.json'
            markettable=read(mp)['tables'][0];income=read(ip)['tables'][0]
            columns=[i for i,name in enumerate(markettable[1][1:],1) if t5v0.nd.team_id(market,name)==team]
            assert len(columns)==1;col=columns[0]
            incomehead=next(r for r in income if len(r)==11 and not r[0].strip())
            icol=next(i for i,name in enumerate(incomehead[1:],1) if t5v0.nd.team_id(market,name)==team)
            j=base.P.index(product);k=base.C.index(country)
            def inc(label):return base.number(next(r for r in income if r and r[0]==label)[icol])
            end=dict(price=base.number(markettable[[[3,4],[6,7]][j][k]][col]),
                demand=base.number(markettable[[[20,21],[24,25]][j][k]][col]),
                general=inc('一般营销'),designer=inc('设计师营销'),rd=inc('研发'))
            refs={key:old['sources'][key] for key in ['price','demand','general','designer','rd']}
            for ref in refs.values():
                path=ROOT/ref['source'];assert sha(path)==ref['sha256'];sources[str(path.relative_to(ROOT))]=sha(path)
            sources[str(mp.relative_to(ROOT))]=sha(mp);sources[str(ip.relative_to(ROOT))]=sha(ip)
            begin={key:old[key] for key in end}
            entry=dict(market=market,team_id=team,product=product,country=country,initial_round=3,closing_round=4,
                initial=begin,closing=end,category='ACTUAL_FORMAL4_INITIAL_TO_CLOSING_COMPANY_MARKETING_EXPENSE_PROXY',
                initial_refs=refs,closing_refs=dict(market=str(mp.relative_to(ROOT)),income=str(ip.relative_to(ROOT)),market_column=col,income_column=icol))
            paired.append(entry)
            reason=[]
            if min(begin['price'],end['price'],begin['demand'],end['demand'])<=0:reason.append('zero_price_or_demand_log_undefined')
            curve3=r3['curves']['rd/'+product];curve4=r4['curves']['rd/'+product]
            if not curve3['x_range'][0]<=begin['rd']<=curve3['x_range'][1] or not curve4['x_range'][0]<=end['rd']<=curve4['x_range'][1]:reason.append('company_rd_proxy_outside_known_curve_domain')
            entry['fit_eligible']=not reason
            if reason:excluded.append(dict(market=market,team_id=team,product=product,country=country,reasons=reason))
            else:
                beta=r3['demand'][product]['SHARE']['beta']
                threshold=1.5*old['initial_price']
                price_log=float(np.log(end['price']/begin['price']))
                tail_log=float(max(np.log(end['price']/threshold),0)-max(np.log(begin['price']/threshold),0))
                rd_log=float(np.log(base.curve(end['rd'],curve4)/base.curve(begin['rd'],curve3)))
                fixed=-beta[k]*price_log+(0 if len(beta)<=5 else -beta[5+k]*tail_log)+beta[4]*rd_log
                entry.update(features=[float(np.log((1000+end[name])/(1000+begin[name]))) for name in ['general','designer']],
                    target=float(np.log(end['demand']/begin['demand'])-fixed),known_price_rd_offset=float(fixed),
                    known_features=dict(price_log=price_log,tail_log=tail_log,rd_log=rd_log),raw_log_demand_change=float(np.log(end['demand']/begin['demand'])))
    assert len(paired)==376
    save('training_pairs.json',paired);save('training_exclusions.json',excluded);save('training_source_hashes.json',sources)
    return paired,r3


def centered(rows):
    x=np.array([r['features'] for r in rows]);y=np.array([r['target'] for r in rows])
    weights=np.zeros(len(rows))
    groups={}
    for i,r in enumerate(rows):groups.setdefault((r['market'],r['country']),[]).append(i)
    for ids in groups.values():
        if len(ids)<2:continue
        x[ids]-=x[ids].mean(axis=0);y[ids]-=y[ids].mean();weights[ids]=1/len(ids)/len(groups)
    return x,y,weights


def fit(rows,prior,penalty):
    x,y,w=centered(rows);sw=np.sqrt(w)
    a=np.vstack([x*sw[:,None],np.sqrt(penalty)*np.eye(2)])
    b=np.r_[y*sw,np.sqrt(penalty)*prior]
    z=lsq_linear(a,b,bounds=(0,np.inf),tol=1e-12,max_iter=1000)
    assert z.success
    return z.x


def error(rows,beta):
    x,y,w=centered(rows)
    return float(np.sqrt(np.sum(w*(x@beta-y)**2)))


def select(rows,prior):
    path=[]
    markets=sorted({r['market'] for r in rows})
    for penalty in [0.,.0001,.001,.01,.1,1.]:
        scores=[]
        for held in markets:
            train=[r for r in rows if r['market']!=held];test=[r for r in rows if r['market']==held]
            b=fit(train,prior,penalty);scores.append(error(test,b))
        path.append(dict(penalty=penalty,held_market_log_change_rmse=float(np.mean(scores))))
    winner=min(path,key=lambda p:p['held_market_log_change_rmse'])
    return winner['penalty'],path


def train(pairs,r3):
    models={}
    for product in base.P:
        models[product]={}
        for kind in ['SHARE','COUNTRY/泰国','COUNTRY/印尼']:
            country=kind.split('/')[-1] if kind!='SHARE' else None
            rows=[r for r in pairs if r['product']==product and r['fit_eligible'] and (country is None or r['country']==country)]
            if country is not None:
                beta=r3['demand'][product][kind]['beta'];k=base.C.index(country)
                rows=[dict(r,target=r['raw_log_demand_change']-(-beta[k]*r['known_features']['price_log']+
                    beta[4]*r['known_features']['rd_log']+(0 if len(beta)<=5 else -beta[5+k]*r['known_features']['tail_log']))) for r in rows]
            assert len(rows)>=20 and len({r['market'] for r in rows})>=7
            prior=np.array(r3['demand'][product][kind]['beta'][2:4])
            penalty,path=select(rows,prior)
            coef=fit(rows,prior,penalty)
            holdouts=[]
            for held in sorted({r['market'] for r in rows}):
                tr=[r for r in rows if r['market']!=held];te=[r for r in rows if r['market']==held]
                selected,_=select(tr,prior);b=fit(tr,prior,selected)
                holdouts.append(dict(held_market=held,train_n=len(tr),test_n=len(te),penalty=selected,
                    beta=b.tolist(),log_change_rmse=error(te,b),old_beta_log_change_rmse=error(te,prior)))
            m5=[r for r in rows if r['market']==5]
            models[product][kind]=dict(beta_general=float(coef[0]),beta_designer=float(coef[1]),n=len(rows),
                market_count=len({r['market'] for r in rows}),known_coefficient_prior=prior.tolist(),penalty=penalty,selection_path=path,
                in_sample_log_change_rmse=error(rows,coef),old_coefficient_error=error(rows,prior),
                nested_holdouts=holdouts,nested_market_mean_rmse=float(np.mean([h['log_change_rmse'] for h in holdouts])),
                old_nested_market_mean_rmse=float(np.mean([h['old_beta_log_change_rmse'] for h in holdouts])),
                own_market_rows=len(m5),scope='formal4 actual initial/final changes; aggregate marketing expense proxy; two marketing coefficients fit, price/RD offset held at known coefficients')
    save('marketing_models_formal4.json',models)
    return models


def main():
    assert not (OUT/'marketing_models_formal4.json').exists()
    weights,ratios,sources=load_weights();pairs,r3=assemble();models=train(pairs,r3)
    checks=dict(status='PASS',weights=32,source_pairs=len(pairs),eligible=sum(r['fit_eligible'] for r in pairs),
        actual_rounds=[3,4],marketing_source='COMPANY_TOTAL_ACTUAL_EXPENSE_PROXY',no_player_estimates_or_sales_targets=True)
    synthetic=[]
    for m in range(1,5):
        for i in range(5):synthetic.append(dict(market=m,country='泰国',features=[i/10,(i%3)/10],target=.7*i/10+.2*(i%3)/10))
    assert np.allclose(fit(synthetic,np.array([.1,.1]),0),[.7,.2],atol=1e-8)
    assert any(w['relative_position_pct']<0 for w in weights)
    checks['synthetic_coefficient_recovery']=True;checks['negative_y_not_used_as_demand_multiplier']=True
    save('training_validation.json',checks)
    print(json.dumps(checks,ensure_ascii=False))
    print(json.dumps({p:{k:{a:v for a,v in x.items() if a in ['beta_general','beta_designer','n','nested_market_mean_rmse','old_nested_market_mean_rmse']} for k,x in d.items()} for p,d in models.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
