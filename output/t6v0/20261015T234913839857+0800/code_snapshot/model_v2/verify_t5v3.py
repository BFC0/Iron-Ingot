"""Offline invariants for the common-default-price demand scenario."""
import copy
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import t5v2
import t5v3
from t5v2 import np

ROOT = Path(__file__).resolve().parents[2]
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def rejected(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError('Expected invalid input rejection')


def verify(bundle):
    for name in ['t5v2_before_hashes.json', 'source_manifest.json']:
        for path, expected in read(bundle / name).items():
            assert sha(ROOT / path) == expected, path
    manifest = read(bundle / 'version_manifest.json')
    for path, expected in manifest.items():
        assert sha(ROOT / path) == expected, path
    reg = read(bundle / 'models_full.json')
    m = t5v3.ApplicationModel()
    m.__dict__.update(t5v2.decode(reg['application_state']))
    old = t5v2.ApplicationModel()
    old.__dict__.update(copy.deepcopy(m.__dict__))
    x = m.baseline[:, None]
    assert np.array_equal(np.asarray(m.competition['assumed_prices']), np.broadcast_to(m.baseprices, (9, 2, 2)))
    assert len(set(m.competition['team_ids'])) == 9
    assert m.competition['own_team_id'] not in m.competition['team_ids']
    assert all(f['modified_state'] == 'notchanged' for f in m.competition['default_fields'])
    for cfg in reg['scenario_configs']:
        out = m.forecast(x, cfg)
        assert np.allclose(out['own_share'] + out['rival_shares'].sum(axis=0), 1, atol=1e-12)
        assert np.all(out['own_share'] > 0) and np.all(out['own_share'] < 1)
        assert np.allclose(out['own_demand_kunits'], out['own_share'] * out['market_total_kunits'][:, :, None])
        # Independent scalar denominator including the piecewise price term.
        for j in range(2):
            for k in range(2):
                weights = []
                for p, target, s in zip(m.competition['previous_prices'], m.competition['assumed_prices'], m.competition['previous_shares']):
                    threshold = [[2700., 3000.], [1.5, 1.5]][j][k]
                    log_change = -m.beta[cfg['response']][j, k, k] * math.log(target[j][k] / p[j][k])
                    log_change *= cfg.get('price_elasticity', 1.)
                    log_change -= m.tail[cfg['response']][j, k] * (max(math.log(target[j][k] / threshold), 0) - max(math.log(p[j][k] / threshold), 0))
                    weights.append(s[j][k] * math.exp(max(-30, min(30, log_change))))
                old_s = old.demand(x, cfg, 0)[j, k, 0] / out['market_total_kunits'][j, k]
                expected = old_s / (old_s + (1 - old_s) * sum(weights) / (1 - m.share[j, k]))
                assert abs(expected - out['own_share'][j, k, 0]) < 1e-12
        unchanged = copy.deepcopy(m)
        unchanged.competition['assumed_prices'] = copy.deepcopy(unchanged.competition['previous_prices'])
        assert np.allclose(unchanged.demand(x, cfg, 0), old.demand(x, cfg, 0), atol=1e-10)
    cfg = reg['scenario_configs'][0]
    anchor = x.copy()
    anchor[:4, 0] = m.baseprices.ravel()
    anchor[4:8, 0] = m.local_general.ravel()
    anchor[8:12, 0] = m.local_designer.ravel()
    anchor[12:14, 0] = m.rdbase
    assert np.allclose(old.demand(anchor, cfg, 0) / (m.totals * [1.07, .95])[:, :, None], m.share[:, :, None])
    # Own and rival price effects must have opposite signs in all four markets.
    for i in range(4):
        lower = x.copy(); lower[i] *= .9
        assert m.demand(lower, cfg, 0).reshape(4)[i] > m.demand(x, cfg, 0).reshape(4)[i]
        cheaper = copy.deepcopy(m)
        cheaper.competition['assumed_prices'] = (np.asarray(m.competition['assumed_prices']) * .9).tolist()
        assert np.all(cheaper.demand(x, cfg, 0) < m.demand(x, cfg, 0))
    batch = np.repeat(x, 3, axis=1); batch[:4] *= [1, .9, 1.1]
    assert np.allclose(m.demand(batch, cfg, 0), np.concatenate([m.demand(batch[:, i:i+1], cfg, 0) for i in range(3)], axis=2))
    symmetric = copy.deepcopy(m)
    symmetric.share = np.full((2, 2), .1)
    symmetric.competition['previous_shares'] = np.full((9, 2, 2), .1).tolist()
    symmetric.competition['previous_prices'] = copy.deepcopy(symmetric.competition['assumed_prices'])
    assert np.allclose(symmetric.forecast(anchor, cfg)['own_share'], .1)
    rejected(lambda: m.demand(x, cfg, 1))
    assert np.isfinite(m.demand(x, dict(cfg, rival_prices_formal6='freeze_formal5_common_defaults'), 1)).all()
    invalid = copy.deepcopy(m); invalid.competition['assumed_prices'][0][0][0] = 0
    rejected(lambda: invalid.demand(x, cfg, 0))
    request = read(bundle / 'example_request.json')
    assert t5v3.apply_request(reg, request) == read(bundle / 'example_prediction.json')
    for value in [float('nan'), True, -1]:
        vals = m.baseline.tolist(); vals[0] = value
        rejected(lambda: t5v3.apply_request(reg, dict(request, decision_vector=vals)))
    rejected(lambda: t5v3.apply_request(reg, dict(request, round=6)))
    rejected(lambda: t5v3.apply_request(reg, dict(request, scenario='unknown')))
    for path in [bundle / 'report.md', ROOT / 'code/model_v2/t5v3_README.md']:
        for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            assert (path.parent / link).resolve().exists(), link
    return dict(status='PASS', scenarios=3, normalized_markets=12,
                original_price_replay=True, independent_scalar_formula=True,
                price_monotonicity=True, symmetric_market=True, batch_prediction=True,
                invalid_inputs_rejected=True, formal6_requires_explicit_assumption=True,
                source_and_runtime_hashes=True, t5v2_preserved=True,
                empirical_accuracy_improvement_verified=False)


if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1])), ensure_ascii=False, indent=2))
