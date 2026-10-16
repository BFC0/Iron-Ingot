"""Read-only demand diagnosis; saved candidates are counterfactuals, not new advice."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
import numpy as np
import core
import t6v1n as app

TRAIN = ROOT/'output/t6v0/20261015T235330003362+0800'
BUNDLE = ROOT/'output/t6v1n_optimization/20261016T173718998'
OUT = ROOT/'output/beam_indonesia_price/20261016_round5_actual_diagnosis'
read = app.read


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'work_log.md').write_text('用户要求：检查当前模型印尼复合梁售价过高的问题，对照回合5真实值。仅离线诊断，不改模型系数、候选或平台。\n', encoding='utf-8')
    m = app.ApplicationModel(BUNDLE)
    rows = [r for r in read(TRAIN/'demand_actual_rows.json')['复合梁'] if r['country']=='印尼']
    market = sorted([r for r in rows if r['market_id']==5], key=lambda r:r['team_id'])
    own = m.r['own_indices']['复合梁']['印尼']
    actual = market[own]
    total = sum(r['demand'] for r in market)
    share = actual['demand']/total
    spec = m.r['demand']['复合梁']['COUNTRY/印尼']
    params = m.r['training_curves']['rd/复合梁']['parameters']
    features = core.features(market, params, .5, False)
    fit = core.predict(market, features, spec['beta'])
    fold = next(f for f in spec['nested_validation']['folds'] if f['held_market']==5)
    held = core.predict(market, features, fold['beta'])
    audits = read(TRAIN/'demand_screening.json')['复合梁/COUNTRY/印尼']['audits']
    audit = next(r for r in audits if r['key'][0]==5 and r['key'][3]==actual['team_id'])
    replay = m.baseline.copy()
    replay[1] = actual['price']
    _, replay_shares = m.demand(replay, dict(replay_training=True))
    assert np.allclose(replay_shares[0,1,:,0], fit)
    # Estimate own residual in odds, holding the nine competitors' attraction fixed.
    factor = (share/(1-share))/(fit[own]/(1-fit[own]))
    checks = dict(training_recipe_reproduced=True, actual_demand_equals_sales=actual['demand']==actual['sales'])
    candidates = []
    for candidate in read(BUNDLE/'result.json')['candidates']:
        x = np.array(candidate['x'])
        ev = m.evaluate(x, details=True)
        s = ev['own_shares'][0][1]
        calibrated = factor*s/(1-s+factor*s)
        profiles = []
        for price in [1800., 2000., 2200., 2400., float(x[1]), 2759.]:
            xx = x.copy(); xx[1] = price
            e = m.evaluate(xx, details=True)
            profiles.append(dict(price=price, demand=e['demand'][0][1], share=e['own_shares'][0][1],
                profit=e['profit'], production=e['production'][0], feasible=e['feasible']))
        stresses = []
        for scale in [1., 1.2, 1.5]:
            e = m.evaluate(x, dict(old_price=scale), True)
            stresses.append(dict(price_elasticity_scale=scale, demand=e['demand'][0][1],
                share=e['own_shares'][0][1], profit=e['profit']))
        # Same aggregate designer spending, radically different local allocation.
        xx = x.copy(); xx[12] += xx[13]; xx[13] = 0
        e = m.evaluate(xx, details=True)
        assert np.allclose(e['demand'], ev['demand'])
        checks['designer_reallocation_invariant'] = True
        changed = x.copy(); changed[19] += 100
        cross = m.evaluate(changed, details=True)
        assert abs(cross['demand'][0][1]-ev['demand'][0][1]) < 1e-10
        checks['connector_rd_has_no_beam_demand_effect'] = True
        candidates.append(dict(name=candidate['name'], price=float(x[1]), demand=ev['demand'][0][1], share=s,
            total=ev['market_totals'][0][1], local_elasticity=spec['beta'][1]*(1-s),
            residual_calibrated_share=calibrated, residual_calibrated_demand=calibrated*ev['market_totals'][0][1],
            general_total=float(x[6:12].sum()), designer_total=float(x[12:18].sum()),
            beam_rd=float(x[18]), connector_rd=float(x[19]), profiles=profiles, stresses=stresses))
    price_only = []
    for price in [2200., 2508.2, 2759.]:
        rr = [dict(r, price=price) if i==own else r for i,r in enumerate(market)]
        ss = core.predict(rr, core.features(rr, params, .5, False), spec['beta'])[own]
        price_only.append(dict(price=price, share=float(ss), demand=float(ss*total)))
    # Centered pairwise ratio makes the model's price versus proxy contribution inspectable.
    pairwise = []
    b = np.array(spec['beta'])
    for i, r in enumerate(market):
        if i==own: continue
        components = (features[own]-features[i])*b
        pairwise.append(dict(team_id=r['team_id'], price=r['price'], demand=r['demand'],
            observed_ratio=actual['demand']/r['demand'], predicted_ratio=float(np.exp(components.sum())),
            price_log_effect=float(components[:2].sum()), general_log_effect=float(components[2]),
            designer_log_effect=float(components[3]), rd_log_effect=float(components[4])))
    files = [TRAIN/'demand_actual_rows.json', TRAIN/'demand_screening.json', BUNDLE/'models_full.json',
        BUNDLE/'result.json', ROOT/'code/model_v2/t6v1.py', ROOT/'code/model_v2/t6v1n.py',
        ROOT/'code/model_v2/t6v0_demand.py', Path(__file__)]
    result = dict(actual={k:actual[k] for k in ['team_id','price','demand','sales','general','designer','rd','previous_rd','supply_evidence','sources']},
        total=total, actual_share=share, fit_share=float(fit[own]), fit_demand=float(fit[own]*total),
        held_market_share=float(held[own]), held_market_demand=float(held[own]*total), held_market_beta=fold['beta'],
        beta=spec['beta'], own_screening=audit, residual_odds_factor=float(factor),
        original_estimate=9.73, original_estimate_error_pct=(9.73/actual['demand']-1)*100,
        market_rows=[{k:r[k] for k in ['team_id','price','demand','sales']} for r in market],
        candidates=candidates, price_only=price_only, pairwise=pairwise, checks=checks,
        source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    assert abs(total-120.62)<1e-8 and actual['price']==2759 and actual['demand']==6.45
    assert not audit['excluded'] and len(market)==10
    (OUT/'diagnostics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['source_hashes','market_rows','pairwise','own_screening','actual']}, ensure_ascii=False, indent=2))


if __name__=='__main__':
    main()
