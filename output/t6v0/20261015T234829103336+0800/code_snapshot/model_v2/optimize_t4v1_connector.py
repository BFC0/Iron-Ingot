"""Append-only, offline connector experiments; never replace the t4v1 registry."""
import argparse
import copy
import itertools
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code'), str(Path(__file__).parent)]
import numpy as np
import t4v1 as t
import core
import operations_rho as ops

SOURCE = ROOT/'output/t4v1/20261014T153914569881+0800'
ANOMALY = 'M07-71cb3f984d9d1ad8'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def effective_operations(rows, rho, full):
    return np.array([r['operations'] + rho*r['previous_operations']
                     + (rho*rho*r['earlier_operations'] if full else 0) for r in rows])


def efficiency_predict(rows, params, model):
    x = effective_operations(rows, model['rho'], model['full_history'])
    a, b, c = params
    return model['theta']*(a+b*x/(c+x))


def efficiency_fit(rows, params, full):
    a, b, c = params
    x = np.stack([effective_operations(rows, rho, full) for rho in ops.GRID], axis=1)
    f = a+b*x/(c+x)
    # Preserve the original strategy weighting so this compares only history depth.
    w = ops.weights(rows)
    y = np.array([r['effective_observed'] for r in rows])
    theta = (w[:, None]*f*y[:, None]).sum(axis=0)/(w[:, None]*f*f).sum(axis=0)
    mse = (w[:, None]*(theta*f-y[:, None])**2).sum(axis=0)
    i = int(np.argmin(mse))
    return dict(theta=float(theta[i]), rho=float(ops.GRID[i]), full_history=full)


def demand_features(rows, params, config):
    x = core.features(rows, params, config['rho'], config.get('piecewise', False))
    decay = config.get('marketing_decay', 0)
    for i, row in enumerate(rows):
        for col, name in [(2, 'general'), (3, 'designer')]:
            stock = row[name] + decay*row['history'][name][1] + decay**2*row['history'][name][0]
            x[i, col] = np.log1p(stock/1000)
        if config.get('price_form', 'log') == 'linear':
            x[i, :2] = 0
            x[i, core.COUNTRIES.index(row['country'])] = -row['price']/100
    return x


def demand_fit(rows, params, features, ids, config):
    keys = ('rho', 'penalty', 'loss', 'standardized', 'piecewise')
    return core.fit([rows[i] for i in ids], params, feature_values=features[ids],
                    **{k: config[k] for k in keys})


def select_demand(rows, params, ids, configs, cache):
    path = []
    for config in configs:
        key = json.dumps(config, sort_keys=True)
        if key not in cache:
            cache[key] = demand_features(rows, params, config)
        x = cache[key]
        scores = []
        for market in sorted({rows[i]['market_id'] for i in ids}):
            tr = [i for i in ids if rows[i]['market_id'] != market]
            te = [i for i in ids if rows[i]['market_id'] == market]
            model = demand_fit(rows, params, x, tr, config)
            pred = core.predict([rows[i] for i in te], x[te], model['beta'])
            scores.append(100*core.score([rows[i] for i in te], pred))
        path.append(dict(config=config, mae_pp=float(np.mean(scores))))
    best = min(v['mae_pp'] for v in path)
    # The predeclared 1% tie rule favors no added history, then the original price form.
    chosen = min((v for v in path if v['mae_pp'] <= best*1.01),
                 key=lambda v: (int(v['config'].get('marketing_decay', 0)>0),
                                int(v['config'].get('price_form', 'log')!='log'), v['mae_pp']))
    config = chosen['config']
    model = demand_fit(rows, params, cache[json.dumps(config, sort_keys=True)], ids, config)
    return dict(config=config, model=model, inner_path=path)


def self_check():
    params = [.45, .75, 400.]
    rows = [dict(operations=o, previous_operations=p, earlier_operations=e)
            for o, p, e in [(0, 0, 900), (200, 300, 100), (800, 200, 500), (400, 600, 50)]]
    model = dict(theta=.18, rho=.63, full_history=True)
    y = efficiency_predict(rows, params, model)
    rows = [dict(r, effective_observed=float(v)) for r, v in zip(rows, y)]
    fit = efficiency_fit(rows, params, True)
    assert abs(fit['rho']-.63)<1e-10 and abs(fit['theta']-.18)<1e-10
    assert effective_operations(rows[:1], .5, True)[0] == 225
    assert effective_operations(rows[:1], .5, False)[0] == 0
    bad = copy.deepcopy(rows)
    for r in bad:
        r['earlier_operations'] = 0
    assert np.allclose(efficiency_predict(bad, params, model),
                       efficiency_predict(bad, params, dict(model, full_history=False)))
    return dict(synthetic_history_recovery=True, zero_current_and_previous_retains_history=True,
                zero_earlier_history_equivalence=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    checks = self_check()
    if args.self_check:
        print(json.dumps(checks)); return
    out = args.out or ROOT/'output/t4v1_connector_optimization'/datetime.now(
        timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True, exist_ok=args.out is not None)
    if (out/'results.json').exists():
        raise FileExistsError('Completed experiments are immutable; use a new output directory')
    log = out/'work_log.md'
    with log.open('a', encoding='utf-8') as f:
        f.write('\n开始离线历史状态/价格候选实验。不要输出真名，姓名统一用首字母替代。\n')
    hashes = {str(p.relative_to(ROOT)): t.nd.sha(p) for p in
              [SOURCE/'dataset.json', SOURCE/'models_full.json', SOURCE/'demand_validation.json',
               Path(__file__), ROOT/'code/model_v2/core.py', ROOT/'code/operations_rho.py',
               ROOT/'code/model_v2/t4v1.py', ROOT/'code/model_v2/t3v0.py',
               ROOT/'code/cross_market_validation.py']}
    data, models = read(SOURCE/'dataset.json'), read(SOURCE/'models_full.json')
    history_rows = t.load_previous()
    for row in history_rows:
        path = ROOT/row['source']
        if str(path.relative_to(ROOT)) not in hashes:
            assert t.nd.sha(path) == row['sha256']
            hashes[str(path.relative_to(ROOT))] = row['sha256']
    actual = t.Actuals(history_rows)
    history = []
    for pair in data['state_pairs']:
        refs = {name: [actual.get(pair['market_id'], rnd, pair['team_id'], 'incomestatement', label)
                       for rnd in (1, 2)] for name, label in
                [('general', '一般营销'), ('designer', '设计师营销'), ('operations', '运营改进')]}
        history.append(dict(market_id=pair['market_id'], team_id=pair['team_id'], refs=refs))
    index = {(r['market_id'], r['team_id']):r for r in history}
    assert len(index) == 100
    save(out/'history.json', history)
    # Available result tables disclose company totals, not competitor country/product decisions.
    coverage = dict(company_history_teams=len(index), own_allocated_rows=len(data['own_final_decision_rows']),
                    competitive_teams=len(data['state_pairs']), allocation_comparison='BLOCKED_MISSING_COMPETITOR_ALLOCATIONS',
                    new_product_marketing_inheritance='UNKNOWN; history variants are sensitivity assumptions',
                    history_origin='formal1; pre-formal1 state unknown, not asserted zero')
    save(out/'coverage.json', coverage)
    result = dict(scope='EXPLORATORY_SAME_ROUND_CONDITIONAL_RESEARCH_NOT_DEPLOYED', coverage=coverage,
                  checks=checks, efficiency={}, demand={})
    params = models['curves']['operations/泰国']['parameters']
    for product, original in models['efficiency'].items():
        rows = [dict(r, earlier_operations=index[r['market_id'], r['team_id']]['refs']['operations'][0]['value'])
                for r in original['rows']]
        variants = {}
        for full in (False, True):
            folds, predictions = [], []
            for held in range(1, 11):
                train = [r for r in rows if r['market_id'] != held]
                test = [r for r in rows if r['market_id'] == held]
                fit = efficiency_fit(train, params, full)
                pred = efficiency_predict(test, params, fit)
                if not full:
                    saved = next(f for f in original['holdouts'] if f['market']==held)
                    assert np.allclose(pred, ops.predict(test, params, saved['fit']), atol=1e-10)
                folds.append(dict(market=held, fit=fit, metrics=ops.metrics(test, pred),
                                  training_keys=[[r['market_id'],r['team_id']] for r in train],
                                  test_keys=[[r['market_id'],r['team_id']] for r in test]))
                for r, p in zip(test, pred):
                    q, n = r['source']['production'], r['source']['workers']
                    lo, hi = (q['value']-q['half'])/(n['value']+n['half']), (q['value']+q['half'])/(n['value']-n['half'])
                    predictions.append(dict(market=r['market_id'], team=r['team_id'], actual=r['effective_observed'],
                        predicted=float(p), error_pct=float(100*(p/r['effective_observed']-1)),
                        display_interval=[lo, hi], rounding_compatible=bool(lo<=p<=hi),
                        operations=[r['earlier_operations'],r['previous_operations'],r['operations']]))
            variants['full_history' if full else 'original_replay'] = dict(
                fit=efficiency_fit(rows, params, full), folds=folds, predictions=predictions,
                team_mape_pct=float(np.mean([abs(r['error_pct']) for r in predictions])),
                market_strategy_mae=float(np.mean([f['metrics']['strategy_weighted_mae'] for f in folds])),
                compatible_n=sum(r['rounding_compatible'] for r in predictions), n=len(rows),
                anomaly=[r for r in predictions if r['team']==ANOMALY])
        result['efficiency'][product] = variants
        print('EFFICIENCY', product, {k:v['team_mape_pct'] for k,v in variants.items()}, flush=True)
    save(out/'efficiency_results.json', result['efficiency'])
    rows = copy.deepcopy(data['competitive_rows_by_product']['连接件'])
    for r in rows:
        r['history'] = {k:[v['value'] for v in refs] for k,refs in index[r['market_id'],r['team_id']]['refs'].items()}
    params = models['curves']['rd/连接件']['parameters']
    saved_model = models['demand']['连接件']['SHARE']
    all_ids = list(range(len(rows)))
    cache, folds, predictions = {}, [], []
    configs = [dict(rho=rho, penalty=penalty, loss='log', standardized=True, piecewise=False,
                    marketing_decay=decay, price_form=price)
               for rho, penalty, decay, price in itertools.product(core.RHOS, core.PENALTIES, (0, .5, 1), ('log', 'linear'))]
    save(out/'experiment_plan.json', dict(configs=configs, loss='log plus frozen fold-local baseline candidate',
        tie_rule='within 1% prefer no marketing carry, then log price, then smaller inner MAE',
        demand_formula='softmax(country price term + beta_g log1p(Gstock/1000) + beta_d log1p(Dstock/1000) + beta_rd log(curve(R+rho Rprev)))',
        operations_formula='S_t=O_t+rho*S_(t-1); observed prefix O3+rho O2+rho^2 O1; pre-formal1 unknown',
        price_forms='log original, or linear negative price/100; no invented breakpoint',
        market_folds=list(range(1,11)), promotion='research only; same dataset informed diagnostics'))
    for held in range(1, 11):
        tr = [i for i in all_ids if rows[i]['market_id'] != held]
        te = [i for i in all_ids if rows[i]['market_id'] == held]
        assert not {rows[i]['market_id'] for i in tr} & {rows[i]['market_id'] for i in te}
        original_config = next(f['selected'] for f in saved_model['nested_validation']['folds'] if f['held_markets']==[held])
        baseline_x = core.features(rows, params, original_config['rho'], original_config['piecewise'])
        baseline_fit = demand_fit(rows, params, baseline_x, tr, original_config)
        rr = [rows[i] for i in te]
        baseline_pred = core.predict(rr, baseline_x[te], baseline_fit['beta'])
        baseline_score = 100*core.score(rr, baseline_pred)
        selected = select_demand(rows, params, tr, configs+[original_config], cache)
        x = cache[json.dumps(selected['config'], sort_keys=True)]
        pred = core.predict(rr, x[te], selected['model']['beta'])
        for group in core.old.groups(rr).values():
            assert abs(sum(pred[group])-1)<1e-10
        folds.append(dict(market=held, original_mae_pp=baseline_score, mae_pp=100*core.score(rr, pred), **selected))
        y = core.actual_shares(rr)
        predictions.extend(dict(key=core.key(r), actual_share=float(a), original_share=float(b), predicted_share=float(p))
                           for r,a,b,p in zip(rr,y,baseline_pred,pred))
        save(out/f'demand_fold_{held:02d}.json', folds[-1])
        print('DEMAND FOLD', held, baseline_score, folds[-1]['mae_pp'], selected['config'], flush=True)
    baseline_mae = float(np.mean([f['original_mae_pp'] for f in folds]))
    assert abs(baseline_mae-saved_model['nested_validation']['mae_pp'])<1e-9
    result['demand'] = dict(folds=folds, predictions=predictions, original_mae_pp=baseline_mae,
                            mae_pp=float(np.mean([f['mae_pp'] for f in folds])), n=len(rows))
    # The final candidate is selected within all ten markets; its training score is not validation.
    original_config = {k:saved_model[k] for k in ('rho','penalty','loss','standardized','piecewise')}
    result['demand']['final_candidate'] = select_demand(rows, params, all_ids, configs+[original_config], cache)
    result['checks'].update(original_demand_replay=True, original_efficiency_replay=True,
                            unchanged_competition_sets=True, fold_local_scaling=True, share_conservation=True,
                            no_team_deletion=True, no_zero_imputation=True)
    for path, digest in hashes.items():
        assert t.nd.sha(ROOT/path)==digest
    result['checks']['protected_hashes_unchanged'] = True
    save(out/'results.json', result)
    save(out/'manifest.json', dict(sources=hashes, outputs={p.name:t.nd.sha(p) for p in out.glob('*.json')}))
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    with log.open('a', encoding='utf-8') as f:
        f.write('\n数值实验完成；原需求/效率复算、市场隔离、份额守恒、历史源哈希及受保护模型哈希通过。未部署。\n')
    print('OUTPUT', out, flush=True)


if __name__ == '__main__':
    main()
