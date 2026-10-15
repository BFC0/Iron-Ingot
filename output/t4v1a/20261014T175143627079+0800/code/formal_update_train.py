"""Append-only formal-round update; run after all ten selected reports are captured."""
import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code/model_v2'))
import core
import country_demand
import demand
import fit_demand
import operations_rho as ops
import cross_market_validation as old
import parameter_priority as priority
from archive_and_report import table_rows

SOURCE = ROOT / 'output/formal_update/20261011T223000+0800_sources'
V2 = ROOT / 'output/model_v2/20261011T210536542951+0800/demand.json'
COUNTRY = ROOT / 'output/country_demand/20261011T205528470485+0800/model.json'
OPS = ROOT / 'output/operations_rho/20261011T213209904415+0800/model.json'
PRIORITY = ROOT / 'output/parameter_priority/20261011T215006575364+0800/results.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def field(path, label, column, occurrence=0):
    rows = [r for r in table_rows(read(path)['snapshot'])
            if len(r['cells']) == 11 and r['cells'][0] == label]
    row = rows[occurrence]
    return dict(value=old.numeric(row['cells'][column]), file=path.relative_to(ROOT).as_posix(),
                line=row['line'], column=column, label=label, occurrence=occurrence)


def common_initial(path, label, occurrence=0):
    refs = [field(path, label, i, occurrence) for i in range(1, 11)]
    assert len({r['value'] for r in refs}) == 1, ('Initial condition not common', path, label)
    return refs[0]


def dataset(source):
    rows, cells, sources, links = [], [], [], []
    for market in range(1, 11):
        path = source / f'market_{market}_formal1.json'
        doc = read(path)
        assert doc['phase'] == 'formal' and doc['round'] == 1
        assert doc['market_id'] == market and doc['kind'] == 'actual_result' and doc['selection_verified']
        selection = ROOT / doc['selection_file']
        snap = read(selection)['snapshot']
        assert f'option "{doc["selected_market"]}" [selected]' in snap
        assert f'option "{doc["selected_round"]}" [selected]' in snap
        rr, cc, ss = old.parse_report(path, dict(market_id=market, phase='formal', round=1))
        assert len(rr) == 20 and any(r['cells'] == ss['teams'] for r in table_rows(snap))
        initial = ROOT / ('raw/initial0_printable.json' if market == 5 else
                          f'raw/cross_market/market_{market:02}_initial_0.json')
        reset = []
        for col in range(1, 11):
            cash = common_initial(initial, '现金及现金等价物', 1)
            retained = common_initial(initial, '留存收益')
            profit = common_initial(initial, '本回合利润, 千 美元')
            current_cash = field(path, '1月1日的流动资产', col)
            current_retained = field(path, '留存收益', col)
            assert abs(current_cash['value'] - cash['value']) <= .01
            assert abs(current_retained['value'] - retained['value'] - profit['value']) <= 1.01
            reset.append(dict(column=col, initial_cash=cash, formal_start_cash=current_cash,
                              initial_retained=retained, initial_profit=profit, formal_retained=current_retained))
        for r in rr:
            prev_rd = common_initial(initial, '研发')
            prev_ops = common_initial(initial, '运营改进')
            price = common_initial(initial, r['country'] + ', 美元')
            r.update(initial_price=price['value'], previous_rd=prev_rd['value'],
                     previous_operations=prev_ops['value'], previous_rd_source=prev_rd,
                     previous_operations_source=prev_ops, initial_price_source=price,
                     context_id='M5_P1_FORMAL1_VISIBLE' if market == 5 else f'UNVERIFIED_M{market}_formal1',
                     context_verified=market == 5, context_fit_eligible=market == 5,
                     usable_for_fit=True, team_history_verified=False,
                     initial_linkage='common initial conditions; cash and retained-earnings reset reconciled; no team-name history join')
            assert all(r[k] is not None for k in ['price', 'demand', 'general', 'designer', 'rd', 'operations'])
            assert r['demand'] >= 0
        rows.extend(rr); cells.extend(cc); sources.append(ss)
        sources.extend([dict(file=initial.relative_to(ROOT).as_posix(), sha256=core.digest(initial)),
                        dict(file=selection.relative_to(ROOT).as_posix(), sha256=core.digest(selection))])
        links.append(dict(market_id=market, initial_common_conditions_checked=True, reset_checks=reset))
    assert len({tuple(core.key(r)) for r in rows}) == 200
    return rows, cells, sources, links


def share_score(rows, model, params):
    predicted = core.predict(rows, core.features(rows, params, model.get('rho', .5),
                                               model.get('piecewise', False)), model['beta'])
    return dict(n=len(rows), share_mae_pp=100 * core.score(rows, predicted),
                predicted_shares=predicted.tolist(), actual_shares=core.actual_shares(rows).tolist(),
                actual_industry_total_used_only_to_score_shares=True,
                realized_competitor_decisions=True, independent_future_demand_validation=False)


def absolute_score(rows, beta, params):
    x = old.feature_matrix(rows, params)
    z = np.c_[[[float(r['country'] == c) for c in core.COUNTRIES] for r in rows], x]
    y = np.array([r['demand'] for r in rows])
    p = np.exp(z @ np.asarray(beta))
    return dict(**old.metric(y, p), predictions=p.tolist())


def train(rows, out):
    frozen = read(ROOT / core.FROZEN)
    params = frozen['rd_curve_parameters']
    legacy = read(ROOT / '分步模型拟合与验证.json')
    previous_v2, previous_country = read(V2), read(COUNTRY)
    outlook_path = Path(rows[0]['sources']['demand']['file']).parent
    outlook = read(ROOT/outlook_path/'formal1_outlook.json')
    outlook_rows = table_rows(outlook['snapshot'])
    def published(label):
        candidates=[r['cells'] for r in outlook_rows if r['cells'] and r['cells'][0]==label and len(r['cells'])==4]
        assert len(candidates)==1,(label,candidates)
        return old.numeric(candidates[0][1])
    base_rate,material_base=published('基准利率')/100,published('复合梁')
    models, evaluations, inventory = {}, {}, []
    m5 = [r for r in rows if r['market_id'] == 5]
    future = read(ROOT/core.FUTURE)
    actual = {(r['market_id'],r['team_id'],r['country']):r for r in rows}
    prospective=[]
    for record in future['records']:
        observed=actual[(record['market_id'],record['team_id'],record['country'])]
        prospective.append(dict(record,formal_actual=observed['demand'],
            formal_source=observed['sources']['demand'],
            error=record['predicted_demand']-observed['demand']))
    scenario_scores=[]
    for model,strategy,scale in sorted({(r['model'],r['competitor_strategy'],r['scale_scenario']) for r in prospective}):
        subset=[r for r in prospective if (r['model'],r['competitor_strategy'],r['scale_scenario'])==(model,strategy,scale)]
        scenario_scores.append(dict(model=model,competitor_strategy=strategy,scale_scenario=scale,
            **old.metric([r['formal_actual'] for r in subset],[r['predicted_demand'] for r in subset])))
    core.write(out/'prospective_scenarios_evaluation.json',dict(source=core.FUTURE,sha256=core.digest(ROOT/core.FUTURE),
        scores=scenario_scores,records=prospective,
        interpretation='Original frozen pre-result demand scenarios; actual own/competitor strategies may differ; all scenarios scored without selecting a hindsight winner'))
    # Freeze-score before any fitting. Archived candidates remain immutable.
    for name, pool in [('A', m5), ('B', rows)]:
        for mode, prior in frozen['models'][name].items():
            mid = f'cross_market/{name}/{mode}'
            evaluations[mid] = (share_score(pool, dict(beta=prior['coefficients']), params) if mode == 'competitive'
                                else absolute_score(pool, prior['coefficients'], params))
    prior_v2 = previous_v2['pools']['A/M5_P1_FORMAL1_VISIBLE']['refit_model']
    evaluations['model_v2/verified_context'] = share_score(m5, prior_v2, params)
    for country in core.COUNTRIES:
        pool = [r for r in m5 if r['country'] == country]
        prior = previous_country['models'][f'M5_P1_FORMAL1_VISIBLE/{country}']
        evaluations[f'country/{country}'] = share_score(pool, prior, params)
    old_abs = read(ROOT / '需求拟合与留出核验.json')
    absolute_rows = [dict(r, market=r['country'], demand_source=r['sources']['demand']) for r in m5]
    xabs = fit_demand.features(absolute_rows, old_abs['rd_persistence'])
    yabs = np.array([r['demand'] for r in absolute_rows])
    evaluations['fit_demand/absolute'] = old.metric(yabs, np.exp(xabs @ np.array(old_abs['coefficients'])))
    evaluations['stepwise/share'] = share_score(m5, dict(beta=legacy['demand']['frozen_round1_beta']), params)
    priority_prior=read(PRIORITY)
    for country in core.COUNTRIES:
        pool=[r for r in m5 if r['country']==country]
        for name,previous in priority_prior['models'][f'M5_P1_FORMAL1_VISIBLE/{country}']['models'].items():
            mid=f'parameter_priority/{country}/{name}'
            p=priority.prediction(pool,params,previous['config'],previous['fitted'])
            evaluations[mid]=dict(share_mae_pp=100*core.score(pool,p),realized_competitor_decisions=True)
    core.write(out / 'demand_frozen_evaluation_before_fit.json', evaluations)
    for name, pool in [('A', m5), ('B', rows)]:
        for mode, prior in frozen['models'][name].items():
            mid = f'cross_market/{name}/{mode}'
            x = old.feature_matrix(pool, params)
            penalty, cv = old.choose_penalty(pool, x, mode)
            beta = old.fit(pool, x.copy(), penalty, mode).tolist()
            models[mid] = dict(beta=beta, penalty=penalty, internal_selection_scores=cv,
                               parameter_change=(np.array(beta)-prior['coefficients']).tolist(),
                               training_keys=[core.key(r) for r in pool],
                               scope='verified visible market5' if name == 'A' else 'unverified cross-market mechanism research',
                               training_score=share_score(pool, dict(beta=beta), params) if mode == 'competitive'
                               else absolute_score(pool, beta, params))
            inventory.append(dict(model=mid, status='RETRAINED_FORMAL1_ONLY'))
    # Reuse the previous verified-context specification, not validation-driven rho selection.
    config = previous_v2['pools']['A/M5_P1_FORMAL1_VISIBLE']['selected']
    model = core.fit(m5, params, **config)
    error, scales = demand.cv(m5, params, config)
    models['model_v2/verified_context'] = dict(model, internal_team_holdout_share_mae_pp=100*error,
        holdout_scale_records=scales, parameter_change=(np.array(model['beta'])-prior_v2['beta']).tolist(),
        training_score=share_score(m5, model, params), specification='prior frozen configuration; formal1 labels used for refit only')
    inventory.append(dict(model='model_v2/verified_context', status='RETRAINED_FORMAL1_ONLY'))
    for country in core.COUNTRIES:
        pool=[r for r in m5 if r['country']==country]
        for name,previous in priority_prior['models'][f'M5_P1_FORMAL1_VISIBLE/{country}']['models'].items():
            mid=f'parameter_priority/{country}/{name}'
            fitted=priority.fit(pool,params,previous['config'])
            models[mid]=dict(config=previous['config'],fitted=fitted,
                parameter_change=(np.array(fitted['beta'])-previous['fitted']['beta']).tolist(),
                internal_fixed_configuration_holdout_share_mae_pp=priority.cv(pool,params,previous['config']),
                specification='Prior frozen rho, marketing scale and penalty retained; parameters refitted; no hindsight selection')
            inventory.append(dict(model=mid,status='RETRAINED_FORMAL1_ONLY'))
    for market in range(1, 11):
        for country in core.COUNTRIES:
            pool = [r for r in rows if r['market_id'] == market and r['country'] == country]
            mid = f'country/market{market}/{country}'
            if market == 5:
                fitted = country_demand.fit_country(pool, params)
                prior = previous_country['models'][f'M5_P1_FORMAL1_VISIBLE/{country}']
                fitted['parameter_change'] = (np.array(fitted['beta'])-prior['beta']).tolist()
            else:
                # Unverified markets never pass fit_country's verified-context guard.
                cfg, path = country_demand.select(pool, params)
                fitted = core.fit(pool, params, **cfg)
                fitted.update(cv_path=path, selected_cv_share_mae_pp=min(p['cv_share_mae_pp'] for p in path))
            models[mid] = dict(fitted, training_score=share_score(pool, fitted, params),
                               status='VERIFIED_VISIBLE_CONTEXT_RESEARCH' if market == 5 else 'UNVERIFIED_CONTEXT_QUARANTINED_RESEARCH',
                               country=country, market_id=market)
            inventory.append(dict(model=mid, status='RETRAINED_FORMAL1_ONLY'))
        print('COUNTRY_COMPLETED', market, flush=True)
    beta = fit_demand.fit(xabs, yabs, old_abs['penalty'])
    teams = sorted({r['team'] for r in absolute_rows})
    splits = [(team, [i for i,r in enumerate(absolute_rows) if r['team'] != team],
               [i for i,r in enumerate(absolute_rows) if r['team'] == team]) for team in teams]
    models['fit_demand/absolute'] = dict(beta=beta.tolist(), penalty=old_abs['penalty'],
        parameter_change=(beta-old_abs['coefficients']).tolist(), training_keys=[core.key(r) for r in m5],
        training_score=old.metric(yabs, np.exp(xabs @ beta)),
        internal_team_holdout=fit_demand.evaluate(absolute_rows,xabs,yabs,old_abs['penalty'],splits))
    inventory.append(dict(model='fit_demand/absolute',status='RETRAINED_FORMAL1_ONLY'))
    # Keep the legacy sum-loss regularizer; cross-market mean loss changes its penalty scale.
    penalty = legacy['demand']['selected_penalty']
    step_x = core.step.demand_features(absolute_rows,legacy['curves'])
    step_ids = list(range(len(absolute_rows)))
    beta = core.step.fit_share(absolute_rows,step_x,step_ids,penalty).tolist()
    models['stepwise/share'] = dict(beta=beta, penalty=penalty,
        parameter_change=(np.array(beta)-legacy['demand']['frozen_round1_beta']).tolist(),
        training_keys=[core.key(r) for r in m5], training_score=share_score(m5,dict(beta=beta),params),
        internal_fixed_penalty_holdout_share_mae_pp=100*core.step.share_cv(absolute_rows,step_x,step_ids,penalty))
    inventory.append(dict(model='stepwise/share',status='RETRAINED_FORMAL1_ONLY'))
    growth=[]
    for country in core.COUNTRIES:
        initial_refs=[field(ROOT/'raw/initial0_printable.json',country,col,1) for col in range(1,11)]
        initial_total=sum(r['value'] for r in initial_refs)
        completed_total=sum(r['demand'] for r in m5 if r['country']==country)
        growth.append(dict(country=country,initial_total=initial_total,formal1_total=completed_total,
            observed_growth_ratio=completed_total/initial_total,
            formal2_constant_growth_scenario=completed_total**2/initial_total,
            initial_sources=initial_refs,formula='M1*(M1/M0)',
            assumption='Constant historical growth scenario only; formal2 outlook change can invalidate continuation'))
    models['stepwise/industry_growth']=dict(rows=growth,forecast_status='SCENARIO_NOT_OFFICIAL_MECHANISM')
    inventory.append(dict(model='stepwise/industry_growth',status='UPDATED_FORMAL1_ACTUAL_GROWTH_SCENARIO'))
    efficiency, risk, material = [], [], []
    for r in [r for r in m5 if r['country'] == '泰国']:
        path = ROOT / r['sources']['demand']['file']; col = r['team_column']
        q, workers = field(path,'生产规模, 千单位',col), field(path,'生产线人工数量',col)
        assert q['value'] > 0 and workers['value'] > 0
        efficiency.append(dict(team=r['team'],team_id=r['team_id'],operations=r['operations'],
            previous_operations=r['previous_operations'],effective_observed=q['value']/workers['value'],
            source=dict(production=q,workers=workers)))
        refs = {k:field(path,label,col) for k,label in [('equity','股东权益合计'),('assets','资产总计'),
             ('long','长期贷款'),('short','短期贷款'),('rate','长期贷款利率，%')]}
        f = {k:v['value'] for k,v in refs.items()}
        risk.append(dict(team=r['team'],equity_ratio=f['equity']/f['assets'],
                         leverage=(f['long']+f['short'])/f['equity'],premium=f['rate']/100-base_rate,
                         sources=refs,base_rate=base_rate))
        material.append(dict(team=r['team'],production=q['value'],
                             cost=field(path,'原材料购买',col)['value'],
                             sources=dict(production=q,materials=field(path,'原材料购买',col))))
    op_prior = read(OPS)
    op_params = legacy['curves']['operations']['parameters']
    evaluations['operations/rho'] = ops.metrics(efficiency,ops.predict(efficiency,op_params,op_prior['chosen']))
    legacy_eff = dict(rho=legacy['efficiency']['rho'],theta=legacy['efficiency']['selected']['technology_scale'])
    evaluations['stepwise/efficiency_and_v2_sensitivity'] = ops.metrics(efficiency,ops.predict(efficiency,op_params,legacy_eff))
    chosen = ops.select(efficiency,op_params)
    models['operations/rho'] = dict(chosen=chosen,parameter_change={k:chosen[k]-op_prior['chosen'][k] for k in ['rho','theta']},
        strategy_cv=ops.strategy_cv(efficiency,op_params),rows=efficiency,
        curve_parameters=op_params,rounding_compatibility=ops.rounding_profile(efficiency,op_params),
        limit='rho and technology scale remain confounded; fixed initial operations; formal2 trend unknown')
    scales = []
    for rho in [0,.25,.5,.75,1]:
        factor=ops.factors(efficiency,op_params,np.array([rho]))[:,0]
        ratios=np.array([r['effective_observed'] for r in efficiency])/factor
        theta=float(np.mean(ratios))
        strategies={}
        for r,ratio in zip(efficiency,ratios):
            strategies.setdefault((r['operations'],r['previous_operations']),[]).append(float(ratio))
        fitted=dict(rho=rho,theta=theta)
        scales.append(dict(fitted,strategy_balanced_scale=float(np.mean([np.mean(v) for v in strategies.values()])),
            training_score=ops.metrics(efficiency,ops.predict(efficiency,op_params,fitted)),
            estimator='legacy mean observed/factor ratios; separate balanced mean for v2 sensitivity'))
    models['stepwise/efficiency_and_v2_sensitivity'] = dict(candidates=scales, selected=scales[2],
        selection='rho=.5 retained rather than selected by formal1 score')
    inventory.extend([dict(model='operations/rho',status='RETRAINED_FORMAL1_ONLY'),
                      dict(model='stepwise/efficiency_and_v2_sensitivity',status='RETRAINED_FORMAL1_ONLY')])
    for prior in legacy['finance']['risk_candidates']:
        form = prior['form']
        def predict(p, rr):
            return p[0]*np.array([r['leverage'] for r in rr])**p[1] if form == 'leverage_power' else p[0]*np.exp(-p[1]*np.array([r['equity_ratio'] for r in rr]))
        target = np.array([r['premium'] for r in risk])
        evaluation = float(np.mean(abs(predict(prior['parameters'],risk)-target))*10000)
        fitted = least_squares(lambda p:predict(p,risk)-target,prior['parameters'],bounds=([0,0],[10,30]))
        assert fitted.success
        folds=[]
        for i in range(len(risk)):
            tr=[r for j,r in enumerate(risk) if j!=i]
            fit=least_squares(lambda p:predict(p,tr)-[r['premium'] for r in tr],prior['parameters'],bounds=([0,0],[10,30]))
            assert fit.success
            folds.append(dict(team=risk[i]['team'],error_basis_points=float((predict(fit.x,[risk[i]])[0]-target[i])*10000)))
        mid=f'finance/risk/{form}'
        evaluations[mid]=dict(conditional_end_state_mae_basis_points=evaluation,forecast=False)
        models[mid]=dict(parameters=fitted.x.tolist(),parameter_change=(fitted.x-prior['parameters']).tolist(),
                         rows=risk,internal_team_holdout=folds,forecast=False)
        inventory.append(dict(model=mid,status='RETRAINED_CONDITIONAL_DIAGNOSTIC'))
    uplift=float(np.median([r['cost']/r['production']-material_base for r in material]))
    evaluations['finance/material_uplift']=dict(mae_kusd=float(np.mean([abs(r['production']*(material_base+legacy['finance']['materials']['uplift_usd_per_unit'])-r['cost']) for r in material])))
    models['finance/material_uplift']=dict(uplift_usd_per_unit=uplift,
        parameter_change=uplift-legacy['finance']['materials']['uplift_usd_per_unit'],rows=material,material_base=material_base,
        limit='display rounding and unidentified cost components; not a published parameter')
    inventory.append(dict(model='finance/material_uplift',status='RECALIBRATED_FORMAL1_ONLY'))
    for model,reason in [('rd_and_operations_curve','No new chart points; archived curve unchanged; investment budgets are not curve labels'),
        ('finance/accounts','Deterministic equations have no trainable fit; new round2 state supplied separately; inventory/short-debt branches may reject state'),
        ('country/practice2_context','No new formal observations assigned to practice2 context; retain separate historical model'),
        ('horizon_and_joint_scenarios','Finite rounds2..6 and unknown future data remain; no future realized labels or complete identifiable finance'),
        ('audit_reports_price_diagnostics','Data adapters/audits/diagnostic profiles, not additional trainable model families; core fit retrained above')]:
        inventory.append(dict(model=model,status='RETAINED_OR_NOT_TRAINABLE',reason=reason))
    core.write(out/'frozen_evaluation.json',evaluations)
    core.write(out/'models.json',models)
    core.write(out/'model_inventory.json',inventory)
    return inventory


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=SOURCE)
    args=parser.parse_args()
    rows,cells,sources,links=dataset(args.source.resolve())
    protected=[ROOT/core.FROZEN,ROOT/core.FUTURE,V2,COUNTRY,OPS,PRIORITY,ROOT/'分步模型拟合与验证.json',ROOT/'需求拟合与留出核验.json',
               *[ROOT/s['file'] for s in sources],args.source.resolve()/'formal1_outlook.json']
    hashes={p.relative_to(ROOT).as_posix():core.digest(p) for p in protected}
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out=ROOT/'output/formal_update'/f'{stamp}_training'
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),out/'formal_update_train.py')
    snapshot=out/'code_snapshot'
    snapshot.mkdir()
    for module in [core,country_demand,demand,fit_demand,ops,old,priority,core.step]:
        shutil.copy2(Path(module.__file__),snapshot/Path(module.__file__).name)
    core.write(out/'dataset.json',dict(rows=rows,source_cells=cells,sources=sources,reset_links=links))
    inventory=train(rows,out)
    assert all(core.digest(ROOT/p)==sha for p,sha in hashes.items()),'Input source changed during training'
    assert len(rows)==200 and all(r['phase']=='formal' and r['round']==1 for r in rows)
    core.write(out/'checks.json',dict(formal_only=True,unique_training_keys=True,reset_cash_retained_reconciled=True,
        no_historical_model_overwrite=True,ops_self_test=ops.self_test(),source_and_model_hashes_before_after_unchanged=hashes,
        code_hashes={p.relative_to(out).as_posix():core.digest(p) for p in snapshot.iterdir()}))
    core.write(out/'manifest.json',dict(status='COMPLETED',inventory=inventory,output=str(out),
        limitations=['Only market5 formal1 outlook verified; other markets quarantined mechanism research',
                    'Frozen conditional share scores use realized rival decisions; not pre-decision absolute forecast scores',
                    'Formal1 refit scores/internal holdouts are not formal2 external verification',
                    'No future round beyond6, no invented terminal liquidation or repayment']))
    print('OUTPUT',out,flush=True)


if __name__=='__main__':
    main()
