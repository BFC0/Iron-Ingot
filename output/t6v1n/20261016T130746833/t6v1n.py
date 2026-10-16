"""Formal6 top-down market forecast and decision-dependent competition shares."""
import argparse
import json
from pathlib import Path

import t6v1 as base
import numpy as np

ROOT = base.ROOT
PRODUCTS, COUNTRIES, ORDERS = base.PRODUCTS, base.COUNTRIES, base.ORDERS
read = base.read


def numeric(value, shape, label, minimum=0.):
    a = np.asarray(value)
    if a.shape != shape or a.dtype.kind not in 'fiu' or not np.isfinite(a).all() or np.any(a < minimum):
        raise ValueError(f'{label}须为形状{shape}、不小于{minimum}的有限数值')
    return a.astype(float)


class ApplicationModel(base.ApplicationModel):
    def __init__(self, bundle):
        self.r = read(Path(bundle)/'models_full.json')
        if (self.r.get('version'), self.r.get('application_round'), self.r.get('base_version')) != ('t6v1n', 6, 't6v1'):
            raise ValueError('需要t6v1n／t6v1／formal6应用包')
        self.s = self.r['state']
        self.bounds = np.array(self.r['bounds'], float)
        self.baseline = np.array(self.r['baseline'], float)
        self.market_forecast({})

    def market_forecast(self, cfg):
        f = self.r['market_forecast']
        history = numeric(f['previous_totals'], (2, 2), '上回合真实需求总量')
        growth = numeric(cfg.get('market_growth', f['growth_rates']), (2, 2), '增长率', -1.)
        new = numeric(cfg.get('new_market_totals', f['new_market_totals']), (2,), '菲律宾总量')
        scale = numeric(cfg.get('market_scale', 1.), (), '总量压力系数')
        totals = np.column_stack([history*(1+growth), new])*scale
        if cfg.get('disable_ph'):
            totals[:, 2] = 0.
        if not np.isfinite(totals).all():
            raise ValueError('预估总量溢出')
        return totals

    def demand(self, x, cfg):
        totals = self.market_forecast(cfg)
        numeric(cfg.get('rival_scale', 1.), (), '竞争强度', np.finfo(float).tiny)
        # Keep the frozen share recipe; the inherited demand level is replaced below.
        _, shares = super().demand(x, cfg)
        own = np.stack([np.stack([shares[j, k, self.r['own_indices'][p][COUNTRIES[min(k, 1)]]]
                                 for k in range(3)]) for j, p in enumerate(PRODUCTS)])
        return totals[:, :, None]*own, shares

    def evaluate(self, decision, cfg=None, details=False, priorities=None):
        cfg = cfg or {}
        result = super().evaluate(decision, cfg, details, priorities)
        if details:
            totals = self.market_forecast(cfg)
            shares = np.array(result['shares'])
            own = [[float(shares[j, k, self.r['own_indices'][p][COUNTRIES[min(k, 1)]]])
                    for k in range(3)] for j, p in enumerate(PRODUCTS)]
            result.update(version='t6v1n', market_totals=totals.tolist(), own_shares=own,
                          demand_method='market_total_times_competitive_share')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--request', required=True, type=Path)
    args = parser.parse_args()
    model = ApplicationModel(args.bundle)
    request = read(args.request)
    if set(request) != {'version', 'round', 'decision_vector', 'scenario'} or request['version'] != 't6v1n' or type(request['round']) is not int or request['round'] != 6:
        raise ValueError('请求须包含version=t6v1n、round=6、decision_vector、scenario')
    scenarios = [c for c in model.r['scenarios'] if c['name'] == request['scenario']]
    if len(scenarios) != 1:
        raise ValueError('未知情景')
    result = model.evaluate(model.validate(request['decision_vector']), scenarios[0], True)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
