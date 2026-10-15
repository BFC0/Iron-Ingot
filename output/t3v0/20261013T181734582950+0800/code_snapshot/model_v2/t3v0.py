"""Append-only t3v0: formal2 training/state pairing; separate formal3 chart fits."""
import argparse
import json
import math
import re
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code'), str(Path(__file__).parent)]
sys.dont_write_bytecode = True
import numpy as np
from scipy.optimize import lsq_linear
import core
import new_data_value as nd
import operations_rho as ops
import interest_rate_model as interest
import material_unit_cost_model as material
import horizon
from archive_and_report import table_rows
from fit_chart_json import fit_points
from explore_six_models import shift_basis, origin_fit

AUDIT = ROOT/'output/round_close/20261012T221044.031+0800/audit/20261013T170300.748980+0800'
CURRENT = ROOT/'output/round_close/20261012T221044.031+0800/resume/20261013T_goal/current_2026-10-13T082849281Z'
CURVE2 = ROOT/'output/visible_coefficients/20261012_round2_json/coefficients.json'
OUTLOOK2 = ROOT/'output/formal_update/20261011T223000+0800_sources/formal2_outlook.json'
CURVE1 = ROOT/'output/visible_coefficients/20261012_archive_review/coefficients.json'


class Actuals:
    """Index the verified table once; join by team identity, never column alone."""
    def __init__(self, rows):
        self.index = defaultdict(list)
        for r in rows:
            if r['identity_status'] != 'verified' or r['phase'] not in ('formal','initial'):
                continue
            if r['category'] not in ('actual_result','actual_demand','actual_sales') or not r['team_order'] or len(r['cells']) != 11:
                continue
            for col, name in enumerate(r['team_order'], 1):
                val, half = nd.numeric(r['cells'][col])
                if val is not None:
                    label=re.sub(r'\s+', ' ',r['cells'][0]).strip().rstrip(' ?')
                    key = (r['market'],r['phase'],r['round'],nd.team_id(r['market'],name),r['panel'],label)
                    self.index[key].append(dict(value=val, half=half, source=r['source'], sha256=r['sha256'],
                        row=r['row_index'], table=r['table_index'], column=col, section=r['semantic_section']))

    def get(self, market, phase, round_, team, panel, label, section=None):
        values = self.index[(market,phase,round_,team,panel,label)]
        if section is not None:
            values = [v for v in values if v['section']==section]
        if len(values) != 1:
            raise ValueError(f'Ambiguous/missing actual field: {market}/{phase}/{round_}/{team}/{panel}/{label}/{section}; candidates={values}')
        return values[0]


def dataset(actual):
    rows, pairs = [], []
    for market in range(1,11):
        teams = sorted({k[3] for k in actual.index if k[:3]==(market,'formal',2) and k[4]=='marketdetails'})
        assert len(teams)==10
        for column, team in enumerate(teams,1):
            def field(round_, panel, label, section=None):
                return actual.get(market,'formal',round_,team,panel,label,section)
            def state(round_):
                fields = {
                    'capacity':('productiondetails','生产能力, 千单位'), 'workers':('productiondetails','生产线人工数量'),
                    'cash':('balancesheet','现金及现金等价物'), 'ar':('balancesheet','应收帐款'),
                    'ap':('balancesheet','应付账款'), 'machine_book':('balancesheet','机器'),
                    'building_book':('balancesheet','厂房'), 'long_debt':('balancesheet','长期贷款'),
                    'short_debt':('balancesheet','短期贷款'), 'assets':('balancesheet','资产 总计'),
                    'equity':('balancesheet','股东权益合计'), 'advance_receipts':('balancesheet','已收预付款'),
                    'rd':('incomestatement','研发'), 'operations':('incomestatement','运营改进')}
                refs={}
                for key,spec in fields.items():
                    try:refs[key]=field(round_,*spec)
                    except ValueError:
                        refs[key]=dict(value=None,status='MISSING_OR_WIDER_ROW_REJECTED',panel=spec[0],label=spec[1])
                assert all(refs[k]['value'] is not None for k in ('rd','operations')), (market,round_)
                return dict(values={key:v['value'] for key,v in refs.items()},refs=refs)
            initial, closing = state(1), state(2)
            pairs.append(dict(market_id=market,team_id=team,initial=initial,closing=closing,
                              initial_basis='formal1 actual closing',closing_basis='formal2 actual closing',
                              unknown=['tax_loss','complete_rd_stock','complete_operations_stock']))
            for country in core.COUNTRIES:
                refs={key:field(2,'incomestatement',label) for key,label in
                      [('general','一般营销'),('designer','设计师营销'),('rd','研发'),('operations','运营改进')]}
                refs['price']=field(2,'marketdetails',country+', 美元','价格')
                refs['demand']=field(2,'marketdetails',country,'需求, 千单位')
                refs['sales']=field(2,'marketdetails',country,'销售, 千单位')
                refs['initial_price']=field(1,'marketdetails',country+', 美元','价格')
                rows.append(dict(market_id=market,phase='formal',round=2,team_id=team,team_column=column,
                    country=country,product='复合梁',context_id='T3V0_FORMAL2_SHARED_ASSUMPTION',
                    **{key:ref['value'] for key,ref in refs.items()},previous_rd=initial['values']['rd'],
                    previous_operations=initial['values']['operations'],sources=refs,
                    initial_price_definition='initial0 actual price; piecewise threshold=1.5*initial0 price'))
                # The specification's price breakpoint uses initial0, not the previous price.
                rows[-1]['initial_price']=actual.get(market,'initial',0,team,'marketdetails',country+', 美元','价格')['value']
                rows[-1]['sources']['initial_price']=actual.get(market,'initial',0,team,'marketdetails',country+', 美元','价格')
                assert rows[-1]['sales'] <= rows[-1]['demand']+.015
    assert len(rows)==200 and len({tuple(core.key(r)) for r in rows})==200
    return rows,pairs


def published():
    rows = table_rows(nd.read(OUTLOOK2)['snapshot'])
    ledger = {}
    for r in rows:
        if len(r['cells'])==4:
            val,half=nd.numeric(r['cells'][1])
            if val is not None:
                ledger.setdefault(r['cells'][0],[]).append(dict(value=val,half=half,line=r['line']))
    return ledger


def curve3(out):
    doc=nd.read(CURRENT/'raw/productionplanning.json')
    assert (doc['market'],doc['phase'],doc['round'])==(5,'formal',3)
    result=dict(version='t3v0',phase='formal',round=3,training_use=False,curves={})
    for entry in nd.read(CURRENT/'charts.json'):
        chart=entry['chart']
        if entry['source']!='productionplanning' or chart['id'] not in ('quality.control.chart','cost.efficiency.chart'):
            continue
        form='power' if chart['id']=='quality.control.chart' else 'saturation'
        x=np.array([float(p['label']) for p in chart['data']['categories'][0]['category']])
        for series in chart['data']['dataset']:
            if not series['seriesname'].startswith('曲线,'):
                continue
            y=np.array([float(p['value']) for p in series['data']])
            assert len(x)==len(y)==200 and np.all(np.diff(x)>0) and np.all(np.isfinite(y))
            name=('rd/' if form=='power' else 'operations/')+series['seriesname'].split(', ',1)[1]
            fitted=fit_points(x,y,form)
            result['curves'][name]=dict(**fitted,form=form,points=np.c_[x,y].tolist(),x_range=[float(x[0]),float(x[-1])],
                source=str((CURRENT/'charts.json').relative_to(ROOT)),chart_id=chart['id'],series=series['seriesname'],
                input='本回合有效投资，千美元；并非当期支出',scope='正式3额外拟合，禁止用于正式2训练',
                x_rounding_half_unit=.5)
    assert set(result['curves'])=={'rd/复合梁','rd/连接件','operations/泰国'}
    nd.save(out/'formal3_curves.json',result)
    return result


class DemandFit:
    def __init__(self,rows,params):
        self.rows,self.params=rows,params
        self.cache={}
        self.calls=0

    def features(self,rho,piecewise):
        key=(rho,piecewise)
        if key not in self.cache:
            self.cache[key]=core.features(self.rows,self.params,rho,piecewise)
        return self.cache[key]

    def fit(self,ids,config):
        self.calls+=1
        return core.fit([self.rows[i] for i in ids],self.params,feature_values=self.features(config['rho'],config['piecewise'])[ids],**config)

    def select(self,ids,country_independent=False):
        markets=sorted({self.rows[i]['market_id'] for i in ids})
        folds=[markets[i:i+2] for i in range(0,len(markets),2)]
        path=[]
        def evaluate(config):
            scores=[]
            for held in folds:
                tr=[i for i in ids if self.rows[i]['market_id'] not in held]
                te=[i for i in ids if self.rows[i]['market_id'] in held]
                m=self.fit(tr,config)
                assert not {self.rows[i]['market_id'] for i in tr} & {self.rows[i]['market_id'] for i in te}
                rr=[self.rows[i] for i in te]
                p=core.predict(rr,self.features(config['rho'],config['piecewise'])[te],m['beta'])
                scores.append(dict(markets=held,mae_pp=100*core.score(rr,p),scale=m['scale']))
            path.append(dict(config=config,mae_pp=float(np.mean([s['mae_pp'] for s in scores])),folds=scores,
                             parameter_count=(4 if country_independent else 5)+(int(config['piecewise'])*(1 if country_independent else 2))))
        for standardized in (False,True):
            for piecewise in (False,True):
                for rho in core.RHOS:
                    for penalty in core.PENALTIES:
                        evaluate(dict(standardized=standardized,piecewise=piecewise,rho=rho,penalty=penalty,loss='log'))
        rho=min(path,key=lambda p:p['mae_pp'])['config']['rho']
        for piecewise in (False,True):
            for penalty in core.PENALTIES:
                evaluate(dict(standardized=True,piecewise=piecewise,rho=rho,penalty=penalty,loss='share'))
        best=min(p['mae_pp'] for p in path)
        chosen=min([p for p in path if p['mae_pp']<=best*1.01],key=lambda p:(p['parameter_count'],p['mae_pp']))
        model=self.fit(ids,chosen['config'])
        rr=[self.rows[i] for i in ids]
        p=core.predict(rr,self.features(model['rho'],model['piecewise'])[ids],model['beta'])
        model.update(cv_path=path,internal_selection_mae_pp=chosen['mae_pp'],training_mae_pp=100*core.score(rr,p),
                     evaluation='训练内整市场选参；已实现竞争策略；不能当独立或事前预测成绩')
        return model

    def nested(self,ids,country_independent):
        folds=[];predictions=[]
        for held in [list(range(i,i+2)) for i in range(1,11,2)]:
            tr=[i for i in ids if self.rows[i]['market_id'] not in held]
            te=[i for i in ids if self.rows[i]['market_id'] in held]
            m=self.select(tr,country_independent)
            rr=[self.rows[i] for i in te]
            p=core.predict(rr,self.features(m['rho'],m['piecewise'])[te],m['beta'])
            folds.append(dict(held_markets=held,selected={k:m[k] for k in ('rho','penalty','loss','standardized','piecewise')},
                beta=m['beta'],scale=m['scale'],training_keys=m['training_keys'],test_keys=[core.key(r) for r in rr],
                mae_pp=100*core.score(rr,p)))
            y=core.actual_shares(rr)
            predictions.extend(dict(key=core.key(r),actual_share=float(a),predicted_share=float(b)) for r,a,b in zip(rr,y,p))
        return dict(folds=folds,predictions=predictions,mae_pp=float(np.mean([f['mae_pp'] for f in folds])),
                    interpretation='嵌套整市场外层验证；同回合已实现对手策略；不是时间外或事前预测')


def absolute_fit(rows,params):
    x=core.features(rows,params)
    x=np.c_[[[int(r['country']==c) for c in core.COUNTRIES] for r in rows],x]
    positive=np.array([r['demand']>0 for r in rows])
    def fit(ids,penalty):
        rr=[rows[i] for i in ids];xx=x[ids]; y=np.log([r['demand'] for r in rr]);w=core.equal_weights(rr)
        scale=np.sqrt(np.sum(w[:,None]*xx[:,2:]**2,axis=0));scale[scale<1e-12]=1
        z=xx.copy();z[:,2:]/=scale
        reg=np.diag([0,0]+[np.sqrt(penalty)]*5)
        m=lsq_linear(np.vstack([z*np.sqrt(w)[:,None],reg]),np.r_[y*np.sqrt(w),np.zeros(7)],
                     bounds=([-np.inf]*2+[0]*5,[np.inf]*7),tol=1e-12)
        assert m.success
        beta=m.x.copy();beta[2:]/=scale
        return beta
    ids=np.flatnonzero(positive).tolist();scores=[]
    for penalty in core.PENALTIES:
        errors=[]
        for held in range(1,11):
            tr=[i for i in ids if rows[i]['market_id']!=held];te=[i for i in ids if rows[i]['market_id']==held]
            beta=fit(tr,penalty)
            errors.append(float(np.mean(abs(np.exp(x[te]@beta)-[rows[i]['demand'] for i in te]))))
        scores.append(dict(penalty=penalty,mae_kunits=float(np.mean(errors))))
    chosen=min(scores,key=lambda s:s['mae_kunits']);beta=fit(ids,chosen['penalty'])
    return dict(beta=beta.tolist(),penalty=chosen['penalty'],cv_path=scores,training_keys=[core.key(rows[i]) for i in ids],
                zero_demand_exclusions=len(rows)-len(ids),curve_round=2,rho=.5,
                status='CONDITIONAL_RESEARCH',metric='训练内选择MAE；非独立验证；绝对需求受行业规模变化影响')


def mechanisms(actual,rows,pairs,curve,ledger):
    base_rate=ledger['基准利率'][0]['value']/100
    published_material=ledger['复合梁'][0]['value']
    er,rr,mr=[],[],[]
    for pair in pairs:
        market,team=pair['market_id'],pair['team_id']
        def f(panel,label):return actual.get(market,'formal',2,team,panel,label)
        q,n=f('productiondetails','生产规模, 千单位'),f('productiondetails','生产线人工数量')
        start,end=pair['initial']['values'],pair['closing']['values']
        if q['value']>0 and n['value']>0:
            er.append(dict(market_id=market,team_id=team,operations=end['operations'],previous_operations=start['operations'],
                effective_observed=q['value']/n['value'],source=dict(production=dict(value=q['value']),workers=dict(value=n['value']))))
            cost=f('incomestatement','原材料购买')['value']
            lo=(cost-.5)/(q['value']+q['half']);hi=(cost+.5)/(q['value']-q['half'])
            mr.append(dict(market=market,phase='formal',team=team,production=q['value'],published_material=published_material,
                           material_cost=cost,implied_low=lo,implied_high=hi))
        ratio=interest.ratios(end)
        rr.append(dict(market_id=market,team_id=team,**ratio,premium=f('ratios','长期贷款利率，%')['value']/100-base_rate))
    op=ops.select(er,curve['operations']['parameters'])
    op_folds=[]
    for market in range(1,11):
        tr=[r for r in er if r['market_id']!=market];te=[r for r in er if r['market_id']==market]
        fitted=ops.select(tr,curve['operations']['parameters'])
        op_folds.append(dict(market=market,fit=fitted,metrics=ops.metrics(te,ops.predict(te,curve['operations']['parameters'],fitted))))
    risks={}
    for form in interest.FORMS:
        folds=[]
        for market in range(1,11):
            tr=[r for r in rr if r['market_id']!=market];te=[r for r in rr if r['market_id']==market]
            fitted=interest.fit(form,tr)
            folds.append(dict(market=market,parameters=fitted,mae_bp=float(np.mean(abs(interest.premium(form,fitted,te)-[r['premium'] for r in te])))*10000))
        risks[form]=dict(parameters=interest.fit(form,rr),holdouts=folds,mae_bp=float(np.mean([f['mae_bp'] for f in folds])))
    chosen,interest_scores=interest.select(rr)
    materials={form:dict(**material.fit(mr,form),evaluation=material.evaluate(material.fit(mr,form),mr)) for form in material.FORMS}
    winner,material_scores=material.select(mr)
    return dict(efficiency=dict(chosen=op,market_holdouts=op_folds,curve_round=2,rows=er,
                    limitation='单期有效投入代理；累计运营库存仍不可识别'),risk=risks,
                interest=dict(form=chosen,parameters=risks[chosen]['parameters'],scores=interest_scores,base_rate=base_rate,
                    limitation='依赖实际期末资产负债；计息时点/预测状态误差未包含'),materials=materials,
                material_selection=dict(form=winner,scores=material_scores),datasets=dict(risk=rr,materials=mr))


def self_check():
    rows=[dict(market_id=m,phase='formal',round=2,team_id=f'{m}-{t}',country=c,
          price=1800+t*50,initial_price=1800,general=t*100,designer=t*70,rd=t*80,previous_rd=100,demand=1+t)
          for m in (1,2) for c in core.COUNTRIES for t in range(1,4)]
    params=[.1,.2,.5,.2];cfg=dict(penalty=.01,standardized=True,rho=.5,piecewise=False,loss='log')
    a=core.fit(rows,params,**cfg);b=core.fit(rows,params,feature_values=core.features(rows,params),**cfg)
    assert np.array_equal(a['beta'],b['beta'])
    for bad in (np.zeros((1,5)),np.full((len(rows),5),np.nan)):
        try:core.fit(rows,params,feature_values=bad,**cfg)
        except ValueError:pass
        else:raise AssertionError('Invalid feature array accepted')
    p=core.predict(rows,core.features(rows,params),a['beta'])
    assert all(abs(sum(p[ids])-1)<1e-12 for ids in core.old.groups(rows).values())
    return dict(prepared_fit_exact_replay=True,invalid_features_rejected=True,share_conservation=True,
                operations=ops.self_test(),horizon=horizon.self_check())


def supplementary(bundle,actual,rows,pairs,curve,ledger,out):
    samples,evidence,exclusions,conflicts=nd.extract(bundle)
    samples=[s for s in samples if s['phase']=='formal' and s['round']==2]
    p=dict(base_wage=ledger['泰国'][0]['value'],second_shift=ledger['两班倒'][0]['value'],
           third_shift=ledger['三班倒'][0]['value'],attrition=ledger['年人员离职率（without costs），%'][0]['value']/100,
           severance_ratio=ledger['裁员成本，占薪资%'][0]['value']/100)
    base=core.read('分步模型拟合与验证.json')
    base['curves']=curve['curves']
    experiments,predictions,splits,fits,calibration=nd.run_experiments(samples,{('formal',2):dict(values=p)},base,refit=True)
    nd.save(out/'supplementary.json',dict(curve_round=2,parameters=p,experiments=experiments,predictions=predictions,
        splits=splits,fits=fits,calibration=calibration,exclusions=exclusions,conflicts=conflicts))
    wages=[];severance=[];replay=[]
    for pair in pairs:
        market,team=pair['market_id'],pair['team_id']
        def f(panel,label,round_=2):return actual.get(market,'formal',round_,team,panel,label)
        try:
            q,capacity,n,wage=[f('productiondetails',s)['value'] for s in
                               ('生产规模, 千单位','生产能力, 千单位','生产线人工数量','工资分摊, 千 美元')]
            if min(q,capacity,n)>0 and q<=capacity:
                wages.append(dict(market=market,team_id=team,x=shift_basis(q,capacity).tolist(),
                                  y=wage/(p['base_wage']*n)-1,scale=p['base_wage']*n,actual=wage))
        except ValueError:pass
        try:
            event=f('productionhr','招聘 + / 裁员 -')['value'];actual_cost=f('incomestatement','解雇成本')['value']
            severance.append(dict(market=market,team_id=team,actual=actual_cost,
                                  predicted=max(-event,0)*p['base_wage']*p['severance_ratio']))
        except ValueError:pass
        try:
            labels=('净销售额','可变成本总和','营销和销售成本总和','杂费成本总和','税息折旧及摊销前利润（EBITDA）',
                    '息税前利润（EBIT）','利息收入','长期贷款利息','短期贷款利息','税前利润','直接税','本回合利润')
            refs={label:f('incomestatement',label) for label in labels}
            v={label:ref['value'] for label,ref in refs.items()}
            values=[('ebitda',v[labels[0]]-v[labels[1]]-v[labels[2]]-v[labels[3]],v[labels[4]],labels[:5]),
                    ('pretax',v[labels[5]]+v[labels[6]]-v[labels[7]]-v[labels[8]],v[labels[9]],labels[5:10]),
                    ('aftertax',v[labels[9]]-v[labels[10]],v[labels[11]],labels[9:12])]
            for name,pred,observed,used in values:
                tol=sum(refs[label]['half'] for label in used)
                replay.append(dict(market=market,team_id=team,check=name,actual=observed,predicted=pred,
                                   tolerance=tol,passed=abs(pred-observed)<=tol+1e-8))
        except ValueError:
            replay.append(dict(market=market,team_id=team,check='income_chain',status='MISSING_OR_WIDER_ROWS',passed=None))
    c_folds=[]
    for market in range(1,11):
        train=[w for w in wages if w['market']!=market];test=[w for w in wages if w['market']==market]
        x=np.asarray([w['x'] for w in train]);rank=int(np.linalg.matrix_rank(x))
        if rank<2:
            c_folds.append(dict(market=market,status='UNIDENTIFIABLE',rank=rank));continue
        beta=origin_fit(x,[w['y'] for w in train],[w['market'] for w in train])
        preds=[dict(actual=w['actual'],baseline=w['scale']*(1+np.asarray(w['x'])@np.array([p['second_shift']-1,p['third_shift']-1])),
                    candidate=float(w['scale']*(1+np.asarray(w['x'])@beta))) for w in test]
        c_folds.append(dict(market=market,beta=beta.tolist(),predictions=preds))
    fullx=np.asarray([w['x'] for w in wages]);rank=int(np.linalg.matrix_rank(fullx))
    c=dict(rank=rank,parameters=(1+origin_fit(fullx,[w['y'] for w in wages],[w['market'] for w in wages])).tolist() if rank==2 else None,
           folds=c_folds,published_multipliers=[p['second_shift'],p['third_shift']],deployment=False,
           explanation='给定当期实际产量/人数的班次费用校准；同源平均工资不视为新增独立标签')
    nd.save(out/'labor_and_accounts.json',dict(wage_candidate=c,severance_rule=severance,accounts_replay=replay,
        complete_forecast=False,limits=['附加列和缺失值不猜测','预算不能作实际标签','税亏及完整跨期状态未知']))
    assert all(r['passed'] is not False for r in replay)
    return experiments,c,replay


def lagged_efficiency(actual,pairs,curve2):
    curve1=nd.read(CURVE1)['curves']['operations']['parameters']
    paths=[];excluded=[]
    for pair in pairs:
        market,team=pair['market_id'],pair['team_id']
        try:
            history=[]
            for round_ in (1,2):
                f=lambda panel,label:actual.get(market,'formal',round_,team,panel,label)['value']
                q,n=f('productiondetails','生产规模, 千单位'),f('productiondetails','生产线人工数量')
                if min(q,n)<=0:raise ValueError('zero quantity/workers')
                initial=pair['initial']['values']
                history.append(dict(market_id=market,team_id=team,operations=f('incomestatement','运营改进'),
                    previous_operations=actual.get(market,'initial',0,team,'productionhr','运营改进, 千 美元')['value'] if round_==1 else initial['operations'],
                    effective_observed=q/n))
            previous_workers=actual.get(market,'formal',1,team,'productionhr','生产人员数量, 上回合')['value']
            event=actual.get(market,'formal',1,team,'productionhr','招聘 + / 裁员 -')['value']
            if previous_workers<=0:raise ValueError('zero previous workers')
            paths.append(dict(previous=history[0],current=history[1],hire=max(event,0)/previous_workers,
                              fire=max(-event,0)/previous_workers))
        except ValueError:excluded.append(dict(market=market,team_id=team,reason='缺正式1→2初终值或历史人员标签'))
    if len({p['current']['market_id'] for p in paths})<5:
        return dict(status='INSUFFICIENT_PAIRED_MARKETS',excluded=excluded,deploy=False)
    def fit(train,test):
        prev=ops.select([p['previous'] for p in train],curve1)
        nxt=ops.select([p['current'] for p in train],curve2)
        def design(records):
            a=ops.predict([p['previous'] for p in records],curve1,prev)
            b=ops.predict([p['current'] for p in records],curve2,nxt)
            x=[[math.log(p['previous']['effective_observed']/f),p['hire'],p['fire']] for p,f in zip(records,a)]
            y=[math.log(p['current']['effective_observed']/f) for p,f in zip(records,b)]
            return np.array(x),np.array(y),b
        x,y,_=design(train);model,predict=nd.select_ridge(x,y,[p['current']['market_id'] for p in train])
        xt,yt,base=design(test)
        correction=predict(model,xt)
        records=[dict(market=p['current']['market_id'],team_id=p['current']['team_id'],actual=p['current']['effective_observed'],
            baseline=float(b),candidate=float(b*math.exp(c))) for p,b,c in zip(test,base,correction)]
        return dict(residual_model=model,previous_base=prev,current_base=nxt,rank=int(np.linalg.matrix_rank(x-x.mean(axis=0)))),records
    folds=[];records=[]
    for held in sorted({p['current']['market_id'] for p in paths}):
        train=[p for p in paths if p['current']['market_id']!=held];test=[p for p in paths if p['current']['market_id']==held]
        model,pred=fit(train,test);folds.append(dict(held_market=held,fit=model));records+=pred
    model,_=fit(paths,paths)
    return dict(status='RESEARCH_REFIT_SINGLE_FORMAL_TRANSITION',model=model,folds=folds,predictions=records,
        comparison=nd.paired_summary(records,'baseline','candidate'),excluded=excluded,curve_rounds=[1,2],deploy=False,
        limitation='内层残差基准共享训练信息，内层选参仍可能偏乐观；外层市场完全隔离。仅一个转移且已实现当期投入；不是时间外预测')


def report(out,models,mech,extra,experiments,c,replay,performance):
    trained={name:dict(status='RETRAINED',artifact='models.json') for name in ('ABS','SHARE','COUNTRY','EFF','RISK_POWER','RISK_EXP','MATERIAL','MATERIAL_PROP','INTEREST')}
    trained.update(RD=dict(status='FORMAL2_BOUND_PLUS_SEPARATE_FORMAL3_FIT',artifact='formal3_curves.json'),
                   OPS=dict(status='FORMAL2_BOUND_PLUS_SEPARATE_FORMAL3_FIT',artifact='formal3_curves.json'))
    for name in ('TOTAL','BASELINE','GROWTH'):
        trained[name]=dict(status='ACTUAL_DIAGNOSTICS_AND_EXPLICIT_SCENARIO',artifact='industry.json',reason='行业总量/增长为实际诊断或情景，非已识别预测函数')
    for name in ('CAPACITY','LABOR','OPERATING','FINANCE'):
        trained[name]=dict(status='RULE_REPLAY_WITH_EXPLICIT_GAPS',artifact='labor_and_accounts.json',reason='确定规则无需训练；缺失跨期分支不能生成完整利润')
    trained['HORIZON']=dict(status='GUARDED_REMAINING_3_TO_6',artifact='calculation_flow.json',reason='未来前景和完整状态缺失，不输出最优排名')
    trained['METRICS']=dict(status='SHARED_CALCULATION_CHECKED',artifact='checks.json')
    for name in ('UNIFIED','T2V0'):
        trained[name]=dict(status='HISTORICAL_COMPOSITION_REPLACED_BY_T3V0_REGISTRY',artifact='models.json',reason='组合入口非额外独立估计参数；旧版本保留')
    trained['A']=dict(status='FORMAL2_GATED_REFIT_EVALUATED',artifact='supplementary.json')
    trained['B']=dict(status='PUBLISHED_SEVERANCE_RULE_REPLAYED',artifact='labor_and_accounts.json')
    trained['C']=dict(status='CONDITIONAL_WAGE_CANDIDATE_REFITTED',artifact='labor_and_accounts.json')
    trained['D']=dict(status='LAGGED_RESEARCH_REFIT_NOT_DEPLOYED',artifact='lagged_efficiency.json',reason='正式1人员事件→正式2残差；两期各自绑定曲线；单一转移，无时间外验证')
    for name in ('E','F'):
        trained[name]=dict(status='KNOWN_INTENSITY_FORMULA_CHECKED',artifact='supplementary.json',reason='官方单位强度×数量；不重复训练已给系数')
    nd.save(out/'model_inventory.json',dict(version='t3v0',models=trained,count=len(trained),deployment=False))
    lines=['# t3v0 全模型更新报告','',f'独立运行：{out.name}（北京时间）。',
        '训练：正式2实际结果，10市场、100队、200条国别需求；初值绑定正式1期末，终值绑定正式2实际。正式2研发与运营曲线绑定原始哈希。',
        '正式3曲线额外保存：研发图包含复合梁和连接件两条产品序列，运营图包含泰国序列；这些参数没有进入正式2训练。',
        '同回合同国家跨市场共享系数仍属授权研究假设；未证明跨回合参数不变。连接件没有正式2实际训练标签，不生成其需求系数。',
        '', '| 需求模型 | 嵌套整市场MAE，百分点 | 样本内MAE，百分点 | 研发延续ρ |','|---|---:|---:|---:|']
    for name,m in models.items():
        if name=='ABS':continue
        lines.append(f"| {name} | {m['nested_validation']['mae_pp']:.6f} | {m['training_mae_pp']:.6f} | {m['rho']:g} |")
    lines+=['','5个外层折各留2个整个市场；只在剩余市场内选参数，逐折计算尺度；两国等权。以上为同回合、给定已实现对手策略的条件验证，不是正式3事前预测成绩。',
        '比较原始/标准化惩罚、线性/分段价格、5档研发延续、11档正则；share损失在训练内选出的log延续处比较，沿用现有分阶段选参。误差≤1%优先较少参数。ABS单列正需求研究，零需求不伪造小数。',
        '', '| 正式3额外曲线 | 留点MAE | 留点最大误差 |','|---|---:|---:|']
    lines += [f"| {name} | {m['held_mae']:.9g} | {m['held_max_error']:.9g} |" for name,m in extra['curves'].items()]
    lines+=['','每序列200点：偶数索引拟合、奇数索引核验，再全点拟合。横轴标签有取整误差；曲线成绩不是经营预测成绩。',
        '', f"计算流程：{performance['solver_calls']}次需求拟合复用{performance['feature_builds']}份特征矩阵；逐折的标准化及优化仍独立。耗时{performance['elapsed_seconds']:.3f}秒；没有据此声称相对旧流程的加速倍数。",
        '', '| 模型 | 状态 |','|---|---|']
    lines += [f"| {name} | {m['status']} |" for name,m in trained.items()]
    lines+=['','研发/运营当期曲线、费用和历史投入明确绑定。效率保留有效投入代理，不冒充完整累计状态；风险与利率依赖实际期末状态，仅作条件关联。',
        '工资候选已重新拟合；解聘费和环境/运输关系保留公布系数，避免把派生指标再训练成新证据。A类校准逐项按增量门槛决定是否保存研究参数，未通过项保留结果。',
        '财务附加列不截取；缺失期初/期末字段保留null。实际损益恒等式通过并不证明完整财务预测、订单中标/预付款或六回合最优。',
        '未操作平台、未自动部署、未覆盖冻结参数和旧运行；生产策略/库存、自动短贷仍按现有简化范围。',
        '', '[完整参数](models.json) · [模型清单](model_inventory.json) · [初终值与原行列](dataset.json) · [来源哈希](input_manifest.json) · [验证](checks.json) · [计算流程](calculation_flow.json)',
        '', '复现：`python code/model_v2/t3v0.py`；每次创建独立目录。自检：`python code/model_v2/t3v0.py --self-check`。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check',action='store_true')
    args=parser.parse_args()
    checks=self_check()
    if args.self_check:
        print(json.dumps(checks,ensure_ascii=False));return
    out=ROOT/'output/t3v0'/datetime.now(nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
    out.mkdir(parents=True,exist_ok=False)
    (out/'work_log.md').write_text('# t3v0 工作日志\n正式2训练曲线与初终值配对；正式3曲线额外保存；平台不操作。\n',encoding='utf-8')
    print('OUTPUT',out,flush=True)
    start=time.perf_counter();bundle=nd.input_bundle(AUDIT)
    for path in [CURVE1,CURVE2,OUTLOOK2,CURRENT/'charts.json',CURRENT/'verification.json',CURRENT/'raw/productionplanning.json']:
        bundle['files'][str(path)]=nd.sha(path)
    curve=nd.read(CURVE2)
    assert curve['round']==2 and nd.sha(ROOT/curve['source'])==curve['source_sha256']
    bundle['files'][str(ROOT/curve['source'])]=curve['source_sha256']
    assert nd.read(CURRENT/'verification.json')['personal_values_stable']
    snapshot=out/'code_snapshot';snapshot.mkdir()
    for path in [* (ROOT/'code').glob('*.py'),* (ROOT/'code/model_v2').glob('*.py')]:
        target=snapshot/path.relative_to(ROOT/'code');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    nd.save(out/'input_manifest.json',dict(version='t3v0',input_hashes=bundle['files'],curve_training_round=2,
        extra_curve_round=3,training_cutoff='formal2 actual results',units=core.UNITS,
        assumption='同回合同国家跨市场共享系数；沿用授权研究假设；未证实跨回合不变'))
    actual=Actuals(nd.read(AUDIT/'rows.json'));rows,pairs=dataset(actual)
    ledger=published();nd.save(out/'dataset.json',dict(rows=rows,state_pairs=pairs,published_formal2=ledger))
    nd.save(out/'formal2_curves.json',curve)
    extra=curve3(out)
    print('DATA: 200 formal2 demand rows, 100 matched state pairs; formal3 separate',flush=True)
    # Score old frozen parameters before refitting; use each model's original curves.
    frozen=core.read(core.FROZEN)
    baseline={}
    for mode,m in frozen['models']['B'].items():
        x=core.old.feature_matrix(rows,frozen['rd_curve_parameters'])
        if mode=='competitive':
            p=core.predict(rows,x,m['coefficients']);baseline[mode]=dict(mae_pp=100*core.score(rows,p),prospective=False)
    nd.save(out/'frozen_evaluation_before_refit.json',baseline)
    engine=DemandFit(rows,curve['curves']['rd']['parameters']);models={}
    for name,ids in [('SHARE',list(range(len(rows)))),*[(f'COUNTRY/{c}',[i for i,r in enumerate(rows) if r['country']==c]) for c in core.COUNTRIES]]:
        print('TRAIN',name,flush=True)
        models[name]=engine.select(ids,name.startswith('COUNTRY'))
        models[name]['nested_validation']=engine.nested(ids,name.startswith('COUNTRY'))
        nd.save(out/(name.replace('/','_')+'.json'),models[name])
    models['ABS']=absolute_fit(rows,curve['curves']['rd']['parameters'])
    print('TRAIN efficiency/risk/interest/material',flush=True)
    mech=mechanisms(actual,rows,pairs,curve['curves'],ledger)
    print('TRAIN supplementary A-F and rule/account checks',flush=True)
    experiments,wages,replay=supplementary(bundle,actual,rows,pairs,curve,ledger,out)
    nd.save(out/'lagged_efficiency.json',lagged_efficiency(actual,pairs,curve['curves']['operations']['parameters']))
    industry=[]
    for market in range(1,11):
        for country in core.COUNTRIES:
            current=sum(r['demand'] for r in rows if r['market_id']==market and r['country']==country)
            previous=sum(actual.get(market,'formal',1,s['team_id'],'marketdetails',country,'需求, 千单位')['value'] for s in pairs if s['market_id']==market)
            industry.append(dict(market=market,country=country,formal1=previous,formal2=current,observed_growth=current/previous,
                equal_share_baseline=current/10,formal3_constant_growth_scenario=current**2/previous,forecast=False))
    nd.save(out/'industry.json',dict(records=industry,scope='实际总量诊断；等份额基线；常增长情景不是官方预测'))
    nd.save(out/'calculation_flow.json',dict(version='t3v0',training_round=2,extra_curve_round=3,
        steps=['核验原件哈希与类别','按市场/阶段/回合/团队/国家/产品配初终值','读取对应回合曲线和公布参数',
               '冻结旧参数先评分','缓存原始特征','训练内选参及嵌套整市场验证','效率→数量/用工→费用规则回放',
               '逐字段保留财务状态未知','未来情景及正式3附加曲线独立保存'],
        dependencies=dict(demand='formal2 RD + formal1 RD input + formal2 decisions/actual demand',
                          efficiency='formal2 OPS + formal1 OPS input + formal2 actual quantity/workers',
                          lagged_residual='formal1 curve/actual/events + formal2 curve/actual'),
        remaining=horizon.remaining_profit(3,[dict(round=i,profit=None,in_scope=False,end_state=None) for i in range(3,7)]),
        complete_profit_forecast=False,automatic_deployment=False))
    nd.save(out/'mechanisms.json',mech)
    nd.save(out/'models.json',dict(version='t3v0',training_phase='formal',training_round=2,demand=models,mechanisms=mech,
                                 deployment_enabled=False,formal3_curve_file='formal3_curves.json'))
    nd.assert_unchanged(bundle)
    checks.update(input_hashes_unchanged=True,formal2_actual_only=True,state_pairs=100,training_rows=200,
                  formal3_not_used_in_training=True,curve2_sha256=nd.sha(CURVE2),old_outputs_not_overwritten=True)
    nd.save(out/'checks.json',checks)
    performance=dict(elapsed_seconds=time.perf_counter()-start,solver_calls=engine.calls,
        feature_builds=len(engine.cache),cache_scope='single immutable dataset/run',
        optimization='复用有效投入/价格特征；每折仍独立中心化和标准化；不缓存不同回合/数据的参数')
    nd.save(out/'performance.json',performance)
    report(out,models,mech,extra,experiments,wages,replay,performance)
    with (out/'work_log.md').open('a',encoding='utf-8') as log:
        log.write('全部模型清单及训练/规则核验完成；未知、未部署和缺口逐项保留。\n')
    nd.save(out/'manifest.json',dict(version='t3v0',status='COMPLETE_RESEARCH_WITH_EXPLICIT_GAPS',
        input_hashes=bundle['files'],output_hashes={p.relative_to(out).as_posix():nd.sha(p) for p in out.rglob('*') if p.is_file()},
        protected_inputs_unchanged=True,training_round=2,extra_curve_round=3))
    print('COMPLETE',out,flush=True)


if __name__=='__main__':main()
