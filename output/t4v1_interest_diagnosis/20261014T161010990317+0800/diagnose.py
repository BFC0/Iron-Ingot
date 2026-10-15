"""Reproduce saved conditional errors; diagnostic fits never replace t4v1."""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUN = ROOT / 'output/t4v1/20261014T153914569881+0800'
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'work/python_packages'), str(RUN / 'code_snapshot'), str(ROOT / 'code'), str(ROOT / 'code/model_v2')]
import numpy as np
from scipy.optimize import least_squares, minimize_scalar
import interest_rate_model as model


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def metrics(errors):
    e = np.asarray(errors)
    return dict(n=len(e), mae_bp=float(np.mean(abs(e))), rmse_bp=float(np.sqrt(np.mean(e**2))),
                max_abs_bp=float(np.max(abs(e))), median_abs_bp=float(np.median(abs(e))))


data = read(RUN / 'dataset.json')
registry = read(RUN / 'models_full.json')['risk']
rows = data['risk']
states = {(r['market_id'], r['team_id']): r for r in data['state_pairs']}
hashes = {}
for path in [RUN / 'dataset.json', RUN / 'models_full.json', RUN / 'code_snapshot/interest_rate_model.py']:
    hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
for r in rows:
    state = states[r['market_id'], r['team_id']]['closing']
    features = model.ratios(state['values'])
    assert all(abs(features[k] - r[k]) < 1e-10 for k in features)
    assert abs(r['premium'] - (r['rate']['value']/100 - .04)) < 1e-12
    for ref in [r['rate'], *[state['refs'][k] for k in ('equity', 'assets', 'long_debt', 'short_debt')]]:
        key = Path(ref['source']).as_posix()
        if key not in hashes:
            hashes[key] = hashlib.sha256((ROOT / ref['source']).read_bytes()).hexdigest()
        assert hashes[key] == ref['sha256']

predictions, folds, training = [], [], {}
for form, fit in registry.items():
    training[form] = metrics((model.premium(form, fit['parameters'], rows) - [r['premium'] for r in rows])*10000)
    for f in fit['market_holdouts']:
        tr = [r for r in rows if r['market_id'] != f['market']]
        te = [r for r in rows if r['market_id'] == f['market']]
        p = model.fit(form, tr)
        errors = (model.premium(form, p, te) - [r['premium'] for r in te])*10000
        assert np.allclose(p, f['parameters'], rtol=1e-7, atol=1e-10)
        assert np.isclose(np.mean(abs(errors)), f['mae_bp'], rtol=1e-7, atol=1e-7)
        folds.append(dict(form=form, market=f['market'], parameters=p,
                          train_leverage_max=max(r['leverage'] for r in tr),
                          test_leverage_max=max(r['leverage'] for r in te), **metrics(errors)))
        for r, error in zip(te, errors):
            values = states[r['market_id'], r['team_id']]['closing']['values']
            predictions.append(dict(form=form, market=r['market_id'], column=r['rate']['column'],
                leverage=r['leverage'], equity_ratio=r['equity_ratio'],
                equity=values['equity'], assets=values['assets'], debt=values['long_debt']+values['short_debt'],
                actual_rate_percent=r['rate']['value'], predicted_rate_percent=r['rate']['value']+float(error)/100,
                error_bp=float(error)))

def profile_fit(sample, form):
    y = np.array([r['premium'] for r in sample])
    x = np.array([r['leverage'] if form == 'leverage_power' else r['equity_ratio'] for r in sample])
    def loss(b, full=False):
        z = x**b if form == 'leverage_power' else np.exp(-b*x)
        a = float(np.clip(z@y/(z@z), 0, 10))
        sse = float(np.sum((a*z-y)**2))
        return [a, float(b), sse] if full else sse
    grid = np.linspace(.000001, 30, 3001)
    i = int(np.argmin([loss(b) for b in grid]))
    opt = minimize_scalar(loss, bounds=(grid[max(0, i-1)], grid[min(len(grid)-1, i+1)]), method='bounded', options={'xatol':1e-12})
    return loss(opt.x, True)

optimizer = {}
for label, sample in [('all', rows), ('without_market5', [r for r in rows if r['market_id'] != 5])]:
    y = np.array([r['premium'] for r in sample])
    results = []
    for initial in ([.02, 2], [.002, .5], [.002, 3], [.1, 1]):
        fit = least_squares(lambda p: model.premium('leverage_power', p, sample)-y, initial,
            bounds=([0, .000001], [10, 30]), max_nfev=4000)
        results.append(dict(initial=initial, parameters=fit.x.tolist(), success=bool(fit.success), sse=float(2*fit.cost)))
    optimum = profile_fit(sample, 'leverage_power')
    assert abs(results[0]['sse'] - optimum[2]) < 1e-8
    optimizer[label] = dict(multistart=results, profiled_optimum=optimum)

summary = dict(training=training, folds=folds, optimizer=optimizer,
    ranges={k:np.quantile([r[k] for r in rows], [0, .5, .9, .95, .99, 1]).tolist() for k in ('leverage', 'equity_ratio', 'premium')},
    exclusions=[dict(market=r['market'], equity=states[r['market'], r['team_id']]['closing']['values']['equity']) for r in data['exclusions'] if r.get('model')=='RISK'],
    zero_debt=[r for r in predictions if r['form']=='leverage_power' and r['debt']==0])
for form, fit in registry.items():
    items = [r for r in predictions if r['form']==form]
    macro = float(np.mean([f['mae_bp'] for f in folds if f['form']==form]))
    assert np.isclose(macro, fit['mae_bp'], rtol=1e-7)
    summary[form] = dict(macro_mae_bp=macro, pooled=metrics([r['error_bp'] for r in items]),
        without_market5=metrics([r['error_bp'] for r in items if r['market']!=5]),
        worst=sorted(items, key=lambda r:abs(r['error_bp']), reverse=True)[:8])
tail = sorted(rows, key=lambda r:r['leverage'], reverse=True)[:8]
summary['tail'] = [dict(market=r['market_id'], column=r['rate']['column'], leverage=r['leverage'], equity_ratio=r['equity_ratio'],
    rate_percent=r['rate']['value'], state=states[r['market_id'], r['team_id']]['closing']['values']) for r in tail]
summary['baseline_evidence'] = dict(actual_min_percent=min(r['rate']['value'] for r in rows),
    actual_max_percent=max(r['rate']['value'] for r in rows), below_5percent=sum(r['rate']['value']<5 for r in rows),
    note='Changing base from 4% to 5% yields negative observed premiums below 5%, inconsistent with constrained nonnegative premium.')
power_errors = [r for r in predictions if r['form']=='leverage_power']
worst = max(power_errors, key=lambda r:abs(r['error_bp']))
ordinary = [r for r in rows if r['leverage']<2]
ordinary_fit = model.fit('leverage_power', ordinary)
summary['single_extreme_influence'] = dict(
    contribution_to_pooled_absolute_error=float(abs(worst['error_bp'])/sum(abs(r['error_bp']) for r in power_errors)),
    cv_without_single_extreme=metrics([r['error_bp'] for r in power_errors if r is not worst]),
    ordinary_only_fit=ordinary_fit,
    ordinary_only_training=metrics((model.premium('leverage_power', ordinary_fit, ordinary)-[r['premium'] for r in ordinary])*10000),
    ordinary_training_with_all_fit=metrics((model.premium('leverage_power', registry['leverage_power']['parameters'], ordinary)-[r['premium'] for r in ordinary])*10000))
extreme_row = max(rows, key=lambda r:r['leverage'])
extreme_state = states[extreme_row['market_id'], extreme_row['team_id']]['closing']
half = extreme_state['refs']['equity']['half']
value = extreme_state['values']['equity']
debt = extreme_state['values']['long_debt']+extreme_state['values']['short_debt']
fold5 = next(f for f in registry['leverage_power']['market_holdouts'] if f['market']==5)
summary['equity_rounding_sensitivity'] = dict(equity=value, half=half,
    leverages=[debt/(value+half), debt/(value-half)],
    predicted_rate_percent=[.04*100+fold5['parameters'][0]*(debt/e)**fold5['parameters'][1]*100 for e in (value+half, value-half)])
assert len(ordinary)==92 and len(rows)==93 and len(predictions)==186
save('diagnostics.json', summary)
with (OUT / 'conditional_predictions.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer=csv.DictWriter(f, fieldnames=list(predictions[0])); writer.writeheader(); writer.writerows(predictions)
save('input_hashes.json', hashes)
print(json.dumps({k:summary[k] for k in ('single_extreme_influence', 'equity_rounding_sensitivity')}, ensure_ascii=False, indent=2))
