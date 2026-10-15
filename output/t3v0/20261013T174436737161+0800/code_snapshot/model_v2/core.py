"""Read-only source adapters and shared, fold-local demand calculation."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares, lsq_linear

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'code'))
import cross_market_validation as old
import stepwise_model as step

PENALTIES = [1e-6, 1e-5, 1e-4, 3e-4, .001, .003, .01, .03, .1, .3, 1]
RHOS = [0, .25, .5, .75, 1]
COUNTRIES = old.COUNTRIES
FROZEN = 'output/cross_market/parameters_20261011T081705179804Z.json'
FUTURE = 'output/cross_market/future_predictions_20261011T081705179804Z.json'
UNITS = dict(quantity='千单位', finance='千美元', price='美元/单位', interest='小数', efficiency='千单位/人')


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def key(r, category='actual_demand'):
    return [r['market_id'], r['phase'], r['round'], r['team_id'], r['country'], category, r.get('context_id','LEGACY_CONTEXT_UNSPECIFIED')]


def equal_weights(rows):
    """Mean over countries within each market, then equal mean over markets."""
    counts = Counter((r['market_id'], r['country']) for r in rows)
    countries = Counter(m for m, _ in counts)
    return np.array([1 / (len(countries) * countries[r['market_id']] * counts[r['market_id'], r['country']]) for r in rows])


def features(rows, params, rho=.5, piecewise=False):
    x = old.feature_matrix([dict(r, previous_rd=r['previous_rd'] * rho / .5) for r in rows], params)
    if piecewise:
        tail = np.zeros((len(rows), 2))
        for i, r in enumerate(rows):
            tail[i, COUNTRIES.index(r['country'])] = -max(np.log(r['price'] / (1.5 * r['initial_price'])), 0)
        x = np.c_[x, tail]
    return x


def predict(rows, x, beta):
    return old.predict_shares(rows, x, np.asarray(beta))


def fit(rows, params, penalty, standardized=False, piecewise=False, rho=.5, loss='log', multiplier=1, feature_values=None):
    assert rows and penalty >= 0 and multiplier > 0
    x = features(rows, params, rho, piecewise) if feature_values is None else np.asarray(feature_values, float)
    if x.shape != (len(rows), 7 if piecewise else 5) or not np.all(np.isfinite(x)):
        raise ValueError('Invalid prepared demand features')
    keep = [i for i, r in enumerate(rows) if loss == 'share' or r['demand'] > 0]
    rr = [rows[i] for i in keep]
    xx = x[keep].copy()
    y = np.log([r['demand'] for r in rr]) if loss == 'log' else np.array([r['demand'] for r in rr])
    for ids in old.groups(rr).values():
        assert len(ids) >= 2
        xx[ids] -= xx[ids].mean(axis=0)
        if loss == 'log':
            y[ids] -= y[ids].mean()
        else:
            assert sum(y[ids]) > 0
            y[ids] /= sum(y[ids])
    w = equal_weights(rr)
    scale = np.sqrt(np.sum(w[:, None] * xx ** 2, axis=0)) if standardized else np.ones(xx.shape[1])
    inactive = scale < 1e-12
    scale[inactive] = 1
    active = ~inactive
    zz = xx[:, active] / scale[active]
    sw = np.sqrt(w * multiplier)
    reg = np.sqrt(penalty) * np.eye(sum(active))
    if loss == 'log':
        solver = lsq_linear(np.vstack([zz * sw[:, None], reg]), np.r_[y * sw, np.zeros(sum(active))],
                            bounds=(0, np.inf), tol=1e-12, max_iter=1000)
    else:
        def residual(b):
            return np.r_[(predict(rr, zz, b) - y) * sw, reg @ b]
        start = np.full(sum(active), .1)
        solver = least_squares(residual, start, bounds=(0, np.inf), max_nfev=1000,
                               xtol=1e-10, ftol=1e-10, gtol=1e-10)
    if not solver.success:
        raise RuntimeError(f'Demand solver failed: {solver.message}')
    beta = np.zeros(xx.shape[1])
    beta[active] = solver.x / scale[active]
    return dict(beta=beta.tolist(), scale=scale.tolist(), inactive_columns=np.flatnonzero(inactive).tolist(),
                penalty=penalty, standardized=standardized, piecewise=piecewise, rho=rho, loss=loss,
                training_keys=[key(r) for r in rows], positive_fit_n=len(rr),
                inverse_transform='original_beta = scaled_beta / training_weighted_centered_RMS',
                objective='market/country equal mean squared residual + lambda * squared penalized coefficients',
                converged=True)


def actual_shares(rows):
    y = np.array([r['demand'] for r in rows])
    for ids in old.groups(rows).values():
        assert sum(y[ids]) > 0
        y[ids] /= sum(y[ids])
    return y


def score(rows, predicted):
    error = abs(actual_shares(rows) - predicted)
    return float(equal_weights(rows) @ error)


def self_check(params, rows):
    rr = [r for r in rows if r['market_id'] == 5 and r['phase'] == 'practice']
    a = fit(rr, params, .01)
    b = fit(rr, params, .01 * len(rr), multiplier=len(rr))
    assert np.max(abs(np.array(a['beta']) - b['beta'])) < 1e-9
    z = features(rr, params)
    p = predict(rr, z, a['beta'])
    for ids in old.groups(rr).values():
        assert abs(sum(p[ids]) - 1) < 1e-12
    assert abs(sum(equal_weights(rr)) - 1) < 1e-12
    assert features(rr, params, piecewise=True).shape[1] == 7
    assert len(set(tuple(key(r)) for r in rows)) == len(rows)
    return dict(loss_equivalence=True, share_conservation=True, unique_keys=True,
                fitted_beta_max_difference=float(np.max(abs(np.array(a['beta']) - b['beta']))))
