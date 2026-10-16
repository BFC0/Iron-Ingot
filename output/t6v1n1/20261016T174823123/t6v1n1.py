"""Formal6 Philippine demand transferred from frozen Thailand parameters."""
import argparse
import json
from pathlib import Path

import numpy as np
import t6v1n as prior

ROOT, PRODUCTS, COUNTRIES, ORDERS = prior.ROOT, prior.PRODUCTS, prior.COUNTRIES, prior.ORDERS
read = prior.read


class ApplicationModel(prior.ApplicationModel):
    def __init__(self, bundle):
        self.r = read(Path(bundle)/'models_full.json')
        if (self.r.get('version'), self.r.get('application_round'), self.r.get('base_version')) != ('t6v1n1', 6, 't6v1n'):
            raise ValueError('需要t6v1n1／t6v1n／formal6应用包')
        if self.r.get('philippines_transfer', {}).get('country') != '泰国':
            raise ValueError('菲律宾必须显式迁移泰国参数')
        self.s = self.r['state']
        self.bounds = np.array(self.r['bounds'], float)
        self.baseline = np.array(self.r['baseline'], float)
        for p in PRODUCTS:
            assert [q['team_id'] for q in self.r['competition'][p]['泰国']] == [q['team_id'] for q in self.r['competition'][p]['印尼']]
            assert self.r['own_indices'][p]['泰国'] == self.r['own_indices'][p]['印尼']
        self.market_forecast({})

    def demand(self, x, cfg):
        # Keep both old countries exactly on their existing inference path.
        _, shares = super().demand(x, cfg)
        x = np.asarray(x, float)
        x = x[:, None] if x.ndim == 1 else x
        n = x.shape[1]
        rival_price = float(prior.numeric(cfg.get('ph_rival_price', 1.), (), '菲律宾对手价格倍数', np.finfo(float).tiny))
        for j, p in enumerate(PRODUCTS):
            rows = self.r['competition'][p]['泰国']
            b = np.array(self.r['demand'][p]['COUNTRY/泰国']['beta'])
            own = self.r['own_indices'][p]['泰国']
            pp = np.full((10, n), self.r['guide_prices'][j]*rival_price)
            pp[own] = x[j*3+2]
            g = np.broadcast_to(np.array([q['general'] for q in rows])[:, None], (10, n)).copy()
            d = np.broadcast_to(np.array([q['designer'] for q in rows])[:, None], (10, n)).copy()
            if not cfg.get('replay_training'):
                g[own] = x[6:12].sum(axis=0)
                d[own] = x[12:18].sum(axis=0)
            old_rd = np.array([q['rd']+.5*q['previous_rd'] for q in rows])
            rdlog = np.broadcast_to(np.log(prior.base.curve(old_rd, self.r['training_curves']['rd/'+p]))[:, None], (10, n)).copy()
            if not cfg.get('replay_training'):
                mapping = self.r['investment_mapping']
                previous = self.r['previous_rd'][j]
                effective = mapping['rd_current']*x[18+j]+mapping['rd_previous']*previous
                anchor = (mapping['rd_current']+mapping['rd_previous'])*previous
                rdlog[own] += np.log(prior.base.curve(effective, self.r['curves']['rd/'+p])/prior.base.curve(anchor, self.r['curves']['rd/'+p]))
            utility = (-b[0]*cfg.get('ph_price', 1.)*np.log(pp/self.r['guide_prices'][j])
                       + cfg.get('ph_marketing', 1.)*(b[2]*np.log1p(g/1000)+b[3]*np.log1p(d/1000))+b[4]*rdlog)
            utility -= utility.max(axis=0)
            attraction = np.exp(utility)
            attraction[np.arange(10) != own] *= cfg.get('rival_scale', 1.)
            shares[j, 2] = attraction/attraction.sum(axis=0)
        own = np.stack([np.stack([shares[j, k, self.r['own_indices'][p][COUNTRIES[0 if k == 2 else k]]]
                                 for k in range(3)]) for j, p in enumerate(PRODUCTS)])
        return self.market_forecast(cfg)[:, :, None]*own, shares

    def evaluate(self, decision, cfg=None, details=False, priorities=None):
        result = super().evaluate(decision, cfg, details, priorities)
        if details:
            result.update(version='t6v1n1', philippines_parameter_country='泰国',
                          ph_sales_shares=[result['sales'][j][2]/result['market_totals'][j][2]
                                           if result['market_totals'][j][2] else 0. for j in range(2)])
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--request', required=True, type=Path)
    args = parser.parse_args()
    m = ApplicationModel(args.bundle)
    request = read(args.request)
    if set(request) != {'version', 'round', 'decision_vector', 'scenario'} or request['version'] != 't6v1n1' or type(request['round']) is not int or request['round'] != 6:
        raise ValueError('请求须包含version=t6v1n1、round=6、decision_vector、scenario')
    scenarios = [q for q in m.r['scenarios'] if q['name'] == request['scenario']]
    if len(scenarios) != 1:
        raise ValueError('未知情景')
    print(json.dumps(m.evaluate(m.validate(request['decision_vector']), scenarios[0], True), ensure_ascii=False, indent=2, allow_nan=False))
