"""Formal5 share scenario: nine rivals use our archived round-opening prices."""
import argparse
import json
import math
from pathlib import Path

import t5v2
from t5v2 import np, decode


class ApplicationModel(t5v2.ApplicationModel):
    def rival_weights(self, cfg, t=0):
        if t and cfg.get('rival_prices_formal6') != 'freeze_formal5_common_defaults':
            raise ValueError('正式6对手价格未知；须显式指定延用正式5统一默认价情景')
        prices = np.asarray(self.competition['previous_prices'], float)
        target = np.asarray(self.competition['assumed_prices'], float)
        shares = np.asarray(self.competition['previous_shares'], float)
        if (prices.shape != (9, 2, 2) or target.shape != prices.shape or shares.shape != prices.shape
                or not np.isfinite([prices, target, shares]).all()
                or np.any(prices <= 0) or np.any(target <= 0) or np.any(shares < 0)
                or not np.allclose(shares.sum(axis=0), 1 - self.share, atol=1e-10)):
            raise ValueError('竞争输入须为九队两产品两国有效价格和需求份额，份额须与本组锚点一致')
        b = self.beta[cfg['response']]
        elasticity = np.array([[b[j, k, k] for k in range(2)] for j in range(2)])
        thresholds = np.array([[2700., 3000.], [1.5, 1.5]])
        log_change = -elasticity * np.log(target / prices) * cfg.get('price_elasticity', 1.)
        log_change -= self.tail[cfg['response']] * (
            np.maximum(np.log(target / thresholds), 0) - np.maximum(np.log(prices / thresholds), 0))
        # shortcut: preserve each rival's prior non-price attractiveness until its next decisions are known.
        return shares * np.exp(np.clip(log_change, -30, 30))

    def demand(self, x, cfg, t):
        cfg = dict(cfg)
        factor = self.rival_weights(cfg, t).sum(axis=0) / (1 - self.share)
        cfg['rival_attractiveness'] = factor[:, :, None] * cfg.get('rival_attractiveness', 1.)
        return super().demand(x, cfg, t)

    def forecast(self, x, cfg):
        x = np.asarray(x, float)
        x = x[:, None] if x.ndim == 1 else x
        demand = self.demand(x, cfg, 0)
        total = self.totals * np.array([1.07, .95])[None, :] * cfg.get('market_scale', 1.)
        own_share = demand / total[:, :, None]
        rivals = self.rival_weights(cfg)
        rival_shares = rivals[:, :, :, None] / rivals.sum(axis=0)[None, :, :, None] * (1 - own_share)
        return dict(own_share=own_share, own_demand_kunits=demand,
                    rival_shares=rival_shares, market_total_kunits=total,
                    rival_attractiveness_ratio=rivals.sum(axis=0) / (1 - self.share))


def apply_request(registry, request):
    if (registry.get('version'), registry.get('base_version'), registry.get('application_round')) != ('t5v3', 't5v2', 5):
        raise ValueError('需要t5v3注册表，基线t5v2，应用正式5')
    if (request.get('version'), request.get('market_id'), request.get('phase'), request.get('round')) != ('t5v3', 5, 'formal', 5):
        raise ValueError('需要t5v3／市场5／formal／正式5请求')
    if set(request) - {'version', 'market_id', 'phase', 'round', 'scenario', 'decision_vector'}:
        raise ValueError('未知请求字段；旧候选不自动作为新版推荐')
    cfgs = [c for c in registry['scenario_configs'] if c['name'] == request.get('scenario', '中性SHARE')]
    if len(cfgs) != 1:
        raise ValueError('未知情景')
    values = request.get('decision_vector', registry['application_state']['baseline']['__ndarray__'])
    if not isinstance(values, list) or len(values) != 20 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('decision_vector须为20个有限数')
    bounds = registry['application_state']['bounds']
    if (any(not lo <= v <= hi for v, (lo, hi) in zip(values, bounds))
            or any(v <= 0 for v in values[:4]) or any(values[i] != round(values[i]) for i in [15, 16, 19])
            or sum(values[4:8]) > 2700 + 1e-8 or sum(values[8:12]) > 3840 + 1e-8):
        raise ValueError('决策超出分析范围、档位或预算约束')
    model = ApplicationModel()
    model.__dict__.update(decode(registry['application_state']))
    result = model.forecast(values, cfgs[0])
    result = {k: (v[..., 0].tolist() if k in ['own_share', 'own_demand_kunits', 'rival_shares'] else v.tolist())
              for k, v in result.items()}
    result.update(version='t5v3', market_id=5, round=5, scenario=cfgs[0]['name'],
                  products=['复合梁', '连接件'], countries=['泰国', '印尼'],
                  rival_team_ids=model.competition['team_ids'],
                  assumption='九组统一使用本组正式5期初默认价格；对手非价格吸引力冻结',
                  empirical_accuracy_improvement_verified=False,
                  scope='正式5条件需求份额；不是销量份额、实际成绩或新优化方案')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--request', type=Path)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    print(json.dumps(apply_request(read(args.bundle / 'models_full.json'),
          read(args.request or args.bundle / 'example_request.json')), ensure_ascii=False, indent=2, allow_nan=False))
