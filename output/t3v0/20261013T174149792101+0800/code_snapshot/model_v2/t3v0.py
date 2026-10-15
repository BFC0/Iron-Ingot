"""Append-only t3v0: formal2 training/state pairing; separate formal3 chart fits."""
import argparse
import json
import math
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


class Actuals:
    """Index the verified table once; join by team identity, never column alone."""
    def __init__(self, rows):
        self.index = defaultdict(list)
        for r in rows:
            if r['identity_status'] != 'verified' or r['phase'] not in ('formal','initial'):
                continue
            if r['category'] != 'actual_result' or not r['team_order'] or len(r['cells']) != 11:
                continue
            for col, name in enumerate(r['team_order'], 1):
                val, half = nd.numeric(r['cells'][col])
                if val is not None:
                    key = (r['market'],r['phase'],r['round'],nd.team_id(r['market'],name),r['panel'],r['cells'][0].strip().rstrip(' ?'))
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
                refs={key:field(round_,*spec) for key,spec in fields.items()}
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
    for path in [CURVE2,OUTLOOK2,CURRENT/'charts.json',CURRENT/'verification.json',CURRENT/'raw/productionplanning.json']:
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
        nd.save(out/(name.replace('/','_')+'.json'),models[name])
    models['ABS']=absolute_fit(rows,curve['curves']['rd']['parameters'])
    print('TRAIN efficiency/risk/interest/material',flush=True)
    mech=mechanisms(actual,rows,pairs,curve['curves'],ledger)
    nd.save(out/'mechanisms.json',mech)
    nd.save(out/'models.json',dict(version='t3v0',training_phase='formal',training_round=2,demand=models,mechanisms=mech,
                                 deployment_enabled=False,formal3_curve_file='formal3_curves.json'))
    nd.assert_unchanged(bundle)
    checks.update(input_hashes_unchanged=True,formal2_actual_only=True,state_pairs=100,training_rows=200,
                  formal3_not_used_in_training=True,curve2_sha256=nd.sha(CURVE2),old_outputs_not_overwritten=True)
    nd.save(out/'checks.json',checks)
    nd.save(out/'performance.json',dict(elapsed_seconds=time.perf_counter()-start,solver_calls=engine.calls,
        feature_builds=len(engine.cache),cache_scope='single immutable dataset/run',
        optimization='复用有效投入/价格特征；每折仍独立中心化和标准化；不缓存不同回合/数据的参数'))
    (out/'work_log.md').open('a',encoding='utf-8').write('核心训练完成；继续全模型清单、计算流程与补充核验。\n')
    print('CORE_TRAINING_DONE',out,flush=True)


if __name__=='__main__':main()
