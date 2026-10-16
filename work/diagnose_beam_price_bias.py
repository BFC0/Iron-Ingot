"""Read-only counterfactuals for the frozen Indonesia beam price recommendation."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'work/python_packages'), str(ROOT / 'code/model_v2')]
import numpy as np
import t5v2
import t5v3

read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
BUNDLE = ROOT / 'output/formal5_two_policies_t5v2/20261015T214235442505+0800'
PRICES = ROOT / 'output/beam_indonesia_price/20261015T215842559575+0800'


def main():
    reg = read(ROOT / 'output/t5v2/20261015_effective_investment/models_full.json')
    result = read(BUNDLE / 'full_result.json')
    ns = dict(vars(t5v2))
    exec(compile((PRICES / 'price_isolation_runtime.py').read_text(encoding='utf-8'),
                 str(PRICES / 'price_isolation_runtime.py'), 'exec'), ns)
    cls = type('FrozenDiagnostic', (t5v2.ApplicationModel,),
               {'demand': ns['demand'], 'evaluate': ns['evaluate']})
    model = cls()
    model.__dict__.update(t5v2.decode(reg['application_state']))
    model.r = {'risk': reg['risk']}
    x = np.array(result['comparisons'][1]['x'])
    cfg = result['configs'][0]
    reference = model.evaluate(x, cfg, True)
    assert abs(reference['profit_5_to_6'] - result['comparisons'][1]['evaluations'][0]['profit_5_to_6']) < 1e-8
    grid = np.arange(1888., 3101.)
    batch = np.repeat(x[:, None], len(grid), axis=1)
    batch[1] = grid
    profiles = {}

    def profile(name, m, c):
        profits, _, penalties = m.evaluate(batch, c)
        i = int(np.argmax(profits))
        profiles[name] = dict(price=float(grid[i]), profit56=float(profits[i]),
                              feasible_at_peak=bool(penalties[i] < 1e-6))

    profile('original_shared_5_6_price', model, cfg)
    profile('only_formal5_price_varies', model, dict(cfg, _future_prices=x[:4].tolist()))
    profile('price_elasticity_plus20pct', model, dict(cfg, price_elasticity=1.2))
    for name, columns in [('no_incremental_rd_response', [4]),
                          ('no_incremental_marketing_response', [2, 3])]:
        other = copy.deepcopy(model)
        for b in other.beta.values():
            b[:, :, columns] = 0
        profile(name, other, cfg)
    rival = t5v3.ApplicationModel()
    rival.__dict__.update(t5v3.decode(read(ROOT / 'output/t5v3/20261015_common_default_prices/models_full.json')['application_state']))
    factor = rival.rival_weights(cfg).sum(axis=0) / (1 - rival.share)
    profile('common_rival_defaults_frozen_both_periods', model,
            dict(cfg, rival_attractiveness=factor[:, :, None]))
    sensitivity = []
    for price in [2180, 2600, 2759]:
        z = x.copy()
        z[1] = price
        e = model.evaluate(z, cfg, True)
        a = e['periods'][0]
        sensitivity.append(dict(price=price, profit5=a['profit'], profit6=e['periods'][1]['profit'],
            beam_demand=a['demand'][0], beam_sales=a['sales'][0], beam_production=a['production'][0],
            beam_materials=a['materials'][0], beam_payroll=a['payroll'][0],
            beam_efficiency=a['efficiency'][0], beam_capacity=a['capacity'][0]))
    coefficients = dict(price=float(model.beta['SHARE'][0, 1, 1]),
                        general=float(model.beta['SHARE'][0, 1, 2]),
                        designer=float(model.beta['SHARE'][0, 1, 3]),
                        rd=float(model.beta['SHARE'][0, 1, 4]),
                        tail=float(model.tail['SHARE'][0, 1]))
    assert profiles['original_shared_5_6_price']['price'] == 2759
    for row in sensitivity:
        assert np.all(np.array(row['beam_sales']) <= np.array(row['beam_demand']) + 1e-8)
    sources = [BUNDLE / 'full_result.json', PRICES / 'price_isolation_runtime.py',
               ROOT / 'code/model_v2/t5v2.py', ROOT / 'code/model_v2/t5v3.py']
    output = dict(profiles=profiles, coefficients=coefficients, sensitivity=sensitivity,
                  rival_factor=factor.tolist(), validation='PASS: frozen replay, archived optimum, sales bounds',
                  scope='Fixed other decisions, diagnostic counterfactuals; not reoptimized recommendations',
                  source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    out = ROOT / 'output/beam_indonesia_price/20261015_bias_diagnosis'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'diagnostics.json').write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
