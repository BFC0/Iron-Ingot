"""Consistent company-expense demand proxies and explicit response-failure stresses."""
import argparse
import json
from pathlib import Path

import numpy as np
import t6v1n1 as prior

ROOT, PRODUCTS, COUNTRIES, ORDERS = prior.ROOT, prior.PRODUCTS, prior.COUNTRIES, prior.ORDERS
read = prior.read
numeric = prior.prior.numeric
curve = prior.prior.base.curve


class ApplicationModel(prior.ApplicationModel):
    def __init__(self, bundle):
        self.r = read(Path(bundle)/'models_full.json')
        if (self.r.get('version'), self.r.get('application_round'), self.r.get('base_version')) != ('t6v1n2', 6, 't6v1n1'):
            raise ValueError('需要t6v1n2／t6v1n1／formal6应用包')
        if self.r.get('philippines_transfer', {}).get('country') != '泰国':
            raise ValueError('菲律宾必须显式迁移泰国参数')
        self.s = self.r['state']
        self.bounds = np.array(self.r['bounds'], float)
        self.baseline = np.array(self.r['baseline'], float)
        for product in PRODUCTS:
            if ([q['team_id'] for q in self.r['competition'][product]['泰国']] !=
                    [q['team_id'] for q in self.r['competition'][product]['印尼']] or
                    self.r['own_indices'][product]['泰国'] != self.r['own_indices'][product]['印尼']):
                raise ValueError('两个旧国家的竞争队及本组索引必须对齐')
        self.market_forecast({})

    def demand(self, x, cfg):
        x = np.asarray(x, float)
        x = x[:, None] if x.ndim == 1 else x
        scales = {key:float(numeric(cfg.get(key, 1.), (), key, np.finfo(float).tiny))
                  for key in ['old_price', 'ph_price', 'old_marketing', 'ph_marketing',
                              'old_rival_price', 'ph_rival_price', 'rival_scale']}
        gains = {key:float(numeric(cfg.get(key, 1.), (), key)) for key in ['marketing_gain', 'rd_gain']}
        if any(v > 1 for v in gains.values()):
            raise ValueError('新增投入收益保留比例须在0至1之间')
        if x.shape[0] != 28 or not np.isfinite(x).all() or np.any(x[:6] <= 0) or np.any(x[6:21] < 0):
            raise ValueError('需求输入须为28维有限数值，售价为正，投入非负')
        shares = np.empty((2, 3, 10, x.shape[1]))
        for j, product in enumerate(PRODUCTS):
            for k in range(3):
                country = COUNTRIES[k if k < 2 else 0]
                rows = self.r['competition'][product][country]
                b = np.array(self.r['demand'][product]['COUNTRY/'+country]['beta'])
                own = self.r['own_indices'][product][country]
                ph = k == 2
                prefix = 'ph_' if ph else 'old_'
                reference = self.r['guide_prices'][j] if ph else 1.
                prices = np.array([reference if ph else r['price'] for r in rows])[:, None]
                prices = np.broadcast_to(prices*scales[prefix+'rival_price'], (10, x.shape[1])).copy()
                prices[own] = x[j*3+k]
                utility = -b[0 if ph else k]*scales[prefix+'price']*np.log(np.maximum(prices, 1e-12)/reference)
                params = self.r['training_curves']['rd/'+product]
                rd = np.array([r['rd']+.5*r['previous_rd'] for r in rows])
                proxies = [np.log1p([r['general']/1000 for r in rows]),
                           np.log1p([r['designer']/1000 for r in rows]), np.log(curve(rd, params))]
                own_new = [np.log1p(x[6:12].sum(axis=0)/1000), np.log1p(x[12:18].sum(axis=0)/1000),
                           np.log(curve(x[18:20].sum(axis=0)+.5*rows[own]['rd'], params))]
                for col, (values, future) in enumerate(zip(proxies, own_new)):
                    feature = np.broadcast_to(np.array(values)[:, None], utility.shape).copy()
                    if not cfg.get('replay_training'):
                        delta = future-values[own]
                        retention = gains['rd_gain' if col == 2 else 'marketing_gain']
                        # Losing old spending still loses its fitted benefit; only unverified new gains fail.
                        feature[own] += np.minimum(delta, 0)+retention*np.maximum(delta, 0)
                    coefficient = b[col+2]*(scales[prefix+'marketing'] if col < 2 else 1.)
                    utility += coefficient*feature
                active = np.ones(10, bool) if ph else np.array([r['price'] > 0 for r in rows])
                active[own] = True
                utility[~active] = -np.inf
                utility -= utility.max(axis=0)
                attraction = np.exp(utility)
                attraction[np.arange(10) != own] *= scales['rival_scale']
                shares[j, k] = attraction/attraction.sum(axis=0)
        own = np.stack([np.stack([shares[j, k, self.r['own_indices'][p][COUNTRIES[k if k < 2 else 0]]]
                                 for k in range(3)]) for j, p in enumerate(PRODUCTS)])
        return self.market_forecast(cfg)[:, :, None]*own, shares

    def evaluate(self, decision, cfg=None, details=False, priorities=None):
        result = super().evaluate(decision, cfg, details, priorities)
        if details:
            result.update(version='t6v1n2', rd_demand_scope='公司当期研发合计+0.5×上期公司合计；冻结训练曲线尺度')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--request', required=True, type=Path)
    args = parser.parse_args()
    m = ApplicationModel(args.bundle)
    req = read(args.request)
    if set(req) != {'version', 'round', 'decision_vector', 'scenario'} or req['version'] != 't6v1n2' or type(req['round']) is not int or req['round'] != 6:
        raise ValueError('请求须包含version=t6v1n2、round=6、decision_vector、scenario')
    configs = [c for c in m.r['scenarios'] if c['name'] == req['scenario']]
    if len(configs) != 1:
        raise ValueError('未知情景')
    print(json.dumps(m.evaluate(m.validate(req['decision_vector']), configs[0], True), ensure_ascii=False, indent=2, allow_nan=False))
