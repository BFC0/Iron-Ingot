"""Read-only t4v1 residual diagnosis; save separate evidence, never update models."""
import hashlib
import itertools
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code'), str(ROOT/'code/model_v2')]
import numpy as np
import core
import operations_rho as ops

SOURCE = ROOT/'output/t4v1/20261014T153914569881+0800'
read = lambda name: json.loads((SOURCE/name).read_text(encoding='utf-8'))
out = ROOT/'output/t4v1_connector_diagnosis'/datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
out.mkdir(parents=True, exist_ok=False)
log = out/'work_log.md'
log.write_text('# t4v1连接件误差诊断日志\n\n授权：分析误差原因。只读已存正式3数据和参数；不改参数、不采集或填写平台。\n不要输出真名，姓名统一用首字母替代。本诊断仅使用团队匿名ID。\n状态：进行中。\n', encoding='utf-8')
data, models, validation = read('dataset.json'), read('models_full.json'), read('demand_validation.json')
results = dict(source=str(SOURCE.relative_to(ROOT)), source_hashes={n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in ['dataset.json','models_full.json','demand_validation.json']}, demand={}, efficiency={}, checks={})
for product, rows in data['competitive_rows_by_product'].items():
    rr = models['demand'][product]
    params = models['curves']['rd/'+product]['parameters']
    index = {tuple(core.key(r)):r for r in rows}
    assert len(index) == len(rows)
    pr = [dict(index[tuple(p['key'])], actual_share=p['actual_share'], predicted_share=p['predicted_share'], error_pp=100*(p['predicted_share']-p['actual_share'])) for p in validation if p['product']==product and p['model']=='SHARE']
    assert len(pr) == len(rows)
    groups = core.old.groups(rows)
    for ids in groups.values():
        assert abs(sum(pr[i]['predicted_share'] for i in ids)-1)<1e-10
        assert np.allclose([pr[i]['actual_share'] for i in ids], core.actual_shares([rows[i] for i in ids]))
    fold_mae = np.mean([100*core.score([r for r in pr if r['market_id']==m], [r['predicted_share'] for r in pr if r['market_id']==m]) for m in range(1,11)])
    assert abs(fold_mae-rr['SHARE']['nested_validation']['mae_pp']) < 1e-10
    simplified = lambda r: {k:r[k] for k in ['market_id','team_id','country','price','general','designer','rd','previous_rd','demand','actual_share','predicted_share','error_pp']}
    market_stats = []
    for market in range(1,11):
        sub = [r for r in pr if r['market_id']==market]
        uniform = [1/len(groups[(r['market_id'],r['phase'],r['round'],r['country'])]) for r in sub]
        market_stats.append(dict(market=market,n=len(sub),mae_pp=100*core.score(sub,[r['predicted_share'] for r in sub]),uniform_mae_pp=100*core.score(sub,uniform)))
    pairs = []
    x = core.features(rows,params,rr['SHARE']['rho'],False)
    scale = np.array(rr['SHARE']['scale'][:5])
    for ids in groups.values():
        for i,j in itertools.combinations(ids,2):
            distance=float(np.linalg.norm((x[i]-x[j])/scale))
            pairs.append(dict(feature_distance=distance,actual_gap_pp=abs(pr[i]['actual_share']-pr[j]['actual_share'])*100,left=simplified(pr[i]),right=simplified(pr[j])))
    # Fixed saved outer-fold configs: descriptive ablation, no model selection or deployment claim.
    ablations={}
    for variant,columns in [('saved_config_replay',[]),('without_rd',[4]),('without_marketing',[2,3])]:
        scores=[]
        for fold in rr['SHARE']['nested_validation']['folds']:
            held=fold['held_markets'][0];config=fold['selected']
            tr=[i for i,r in enumerate(rows) if r['market_id']!=held]
            te=[i for i,r in enumerate(rows) if r['market_id']==held]
            features=core.features(rows,params,config['rho'],config['piecewise']).copy()
            features[:,columns]=0
            fit=core.fit([rows[i] for i in tr],params,feature_values=features[tr],**config)
            pred=core.predict([rows[i] for i in te],features[te],fit['beta'])
            scores.append(dict(market=held,mae_pp=100*core.score([rows[i] for i in te],pred)))
        ablations[variant]=dict(mae_pp=float(np.mean([s['mae_pp'] for s in scores])),folds=scores)
    assert abs(ablations['saved_config_replay']['mae_pp']-fold_mae)<1e-8
    metrics={name:dict(training_pp=v['training_mae_pp'],nested_pp=v['nested_validation']['mae_pp'],rho=v['rho'],beta=v['beta'],piecewise=v['piecewise']) for name,v in rr.items() if name!='ABS'}
    abs_fit=rr['ABS'];selected=next(v for v in abs_fit['cv_path'] if v['penalty']==abs_fit['penalty'])
    results['demand'][product]=dict(n=len(rows),excluded_zero_price=sum(r['model']=='DEMAND' and r.get('product')==product for r in data['exclusions']),active_group_counts=dict(Counter(len(ids) for ids in groups.values())),metrics=metrics,markets=market_stats,top_errors=[simplified(r) for r in sorted(pr,key=lambda r:abs(r['error_pp']),reverse=True)[:12]],closest_pairs=sorted(pairs,key=lambda p:p['feature_distance'])[:12],identical_input_pairs=[p for p in pairs if p['feature_distance']<1e-10],ablations=ablations,abs_internal_selection_mae_kunits=selected['mae_kunits'],mean_demand=float(np.mean([r['demand'] for r in rows])),supply_shortfall_n=sum(r['sales']<r['demand']-.015 for r in rows))
    eff=models['efficiency'][product];erows=eff['rows'];predictions=[]
    for fold in eff['holdouts']:
        sub=[r for r in erows if r['market_id']==fold['market']]
        predicted=ops.predict(sub,models['curves']['operations/泰国']['parameters'],fold['fit'])
        for r,p in zip(sub,predicted):
            q=r['source']['production'];n=r['source']['workers'];lo=(q['value']-q['half'])/(n['value']+n['half']);hi=(q['value']+q['half'])/(n['value']-n['half'])
            predictions.append(dict(market=r['market_id'],team=r['team_id'],production=q['value'],workers=n['value'],actual=r['effective_observed'],predicted=float(p),error=float(p-r['effective_observed']),relative_error_pct=float(100*(p/r['effective_observed']-1)),display_interval=[lo,hi],rounding_compatible=bool(lo<=p<=hi)))
    results['efficiency'][product]=dict(n=len(erows),chosen=eff['chosen'],mean_observed=float(np.mean([r['effective_observed'] for r in erows])),market_strategy_mae=float(np.mean([f['metrics']['strategy_weighted_mae'] for f in eff['holdouts']])),team_mape_pct=float(np.mean([abs(p['relative_error_pct']) for p in predictions])),rounding_compatible_n=sum(p['rounding_compatible'] for p in predictions),top_errors=sorted(predictions,key=lambda p:abs(p['error']),reverse=True)[:8])
results['own_allocation']=[{k:r[k] for k in ['product','country','general','designer','rd']} for r in data['own_final_decision_rows']]
results['materials']={p:dict(n=v['training_n'],selected=v['selected'],scores=v['holdout_scores']) for p,v in models['materials'].items()}
results['checks']=dict(unique_keys=True,share_conservation=True,actual_share_replay=True,saved_mae_replay=True,outer_config_prediction_replay=True,scope='消融沿用原外折所选配置，未独立重选；仅解释诊断，非新模型验收')
(out/'diagnostics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
(out/'diagnose_t4v1_connector.py').write_bytes(Path(__file__).read_bytes())
with log.open('a',encoding='utf-8') as f:
    f.write('\n数值诊断完成：唯一键、份额守恒、实际份额和原嵌套MAE复算、原外折配置预测复算均通过。参数未改；报告待整理。\n')
print('OUTPUT',out)
for p,v in results['demand'].items():
    print(p,json.dumps({k:v[k] for k in ['n','active_group_counts','metrics','markets','ablations','abs_internal_selection_mae_kunits','mean_demand']},ensure_ascii=False))
    print('top',json.dumps(v['top_errors'][:4],ensure_ascii=False))
    print('identical',json.dumps(v['identical_input_pairs'][:5],ensure_ascii=False))
    print('closest',json.dumps(v['closest_pairs'][:2],ensure_ascii=False))
print('eff',json.dumps(results['efficiency'],ensure_ascii=False))
