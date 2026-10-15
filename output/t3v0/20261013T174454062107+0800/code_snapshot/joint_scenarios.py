"""Offline formal-1 joint scenarios; reuse frozen demand and financial models.
Run python code/joint_scenarios.py. Does not retrain or change browser decisions.
"""
import csv
import hashlib
import json
from datetime import datetime, timezone
from itertools import product

import numpy as np

from audit_incremental import ROOT
from cross_market_validation import load_dataset, feature_matrix
from stepwise_model import (COUNTRIES, current_state, live_decision, curve_value,
                            shares, accounts_from_state, risk_linked_accounts)


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def main():
    frozen_path = 'output/cross_market/parameters_20261011T081705179804Z.json'
    frozen = read(frozen_path)
    model = read('分步模型拟合与验证.json')
    rows, _, sources = load_dataset()
    rows = [r for r in rows if r['market_id'] == 5]
    state = current_state(None)
    baseline, manual_demand, manual_efficiency = live_decision()
    risk = min(model['finance']['risk_candidates'], key=lambda r: r['training_mae_basis_points'])
    uplift = model['finance']['materials']['uplift_usd_per_unit']
    initial = [r for r in rows if r['phase'] == 'initial']
    initial_map = {(r['team'], r['country']): r for r in initial}
    previous_ops = 700  # Initial-0 operations, not practice-2 state.
    scenarios = []
    for name, phase, rnd in [('initial0', 'initial', 0), ('practice1', 'practice', 1)]:
        groups = []
        for country in COUNTRIES:
            group = [dict(r, previous_rd=initial_map[r['team'], country]['rd'])
                     for r in rows if r['phase'] == phase and r['round'] == rnd and r['country'] == country]
            assert len(group) == 10 and sum(r['team'] == '营销团队' for r in group) == 1
            groups.append(group)
        for scale, total_phase in [('flat', 'initial'), ('practice1_growth', 'practice')]:
            totals = [sum(r['demand'] for r in rows if r['phase'] == total_phase and
                          r['round'] == (0 if total_phase == 'initial' else 1) and r['country'] == c)
                      for c in COUNTRIES]
            for label in ['A', 'B']:
                scenarios.append(dict(label=f'{label}/{name}/{scale}', model=label, groups=groups, totals=totals))

    def demand_for(decision, scenario):
        demands = []
        for c, group, total in zip(COUNTRIES, scenario['groups'], scenario['totals']):
            candidates = [dict(r) for r in group]
            own = next(r for r in candidates if r['team'] == '营销团队')
            own.update(price=decision['prices'][COUNTRIES.index(c)], general=sum(decision['general']),
                       designer=sum(decision['designer']), rd=decision['rd'])
            weights = shares(feature_matrix(candidates, frozen['rd_curve_parameters']),
                             np.array(frozen['models'][scenario['model']]['competitive']['coefficients']))
            assert abs(sum(weights) - 1) < 1e-12
            demands.append(float(weights[candidates.index(own)] * total))
        return demands

    def evaluate(decision, demands, stress=False):
        efficiency = model['efficiency']['selected']['technology_scale'] * float(curve_value(
            decision['operations'] + .5 * previous_ops, model['curves']['operations']['parameters'], 'saturation'))
        details = []
        for scenario, demand in zip(scenarios, demands):
            # shortcut: 30% demand shock and lower efficiency are assumptions; replace with formal evidence when available.
            used = [d * .7 for d in demand] if stress else demand
            linked = risk_linked_accounts(state, decision, used, efficiency - (.005 if stress else 0),
                                          dict(material_cost=900), uplift, risk)
            out = linked['output']
            assert abs(sum(out['sales']) - out['production']['production']) < 1e-8
            assert abs(out['balance_error']) < 1e-6
            details.append(dict(scenario=scenario['label'], demand=used,
                                long_rate=linked.get('predicted_long_rate_percent'), **out))
        return dict(decision=decision, feasible=all(r['fully_computed_in_scope'] and r['equity'] > 0 for r in details),
                    worst_profit=min(r['profit'] for r in details), best_profit=max(r['profit'] for r in details),
                    min_cash=min(r['cash'] for r in details), details=details)

    # Independent replay checks prevent silently changing the established calculation chain.
    replay = accounts_from_state(state, baseline, manual_demand, manual_efficiency, dict(material_cost=900), uplift)
    assert abs(replay['profit'] - (-3649)) < .65 and abs(replay['cash'] - 13651) < .65
    frozen_predictions = read('output/cross_market/future_predictions_20261011T081705179804Z.json')['records']
    baseline_demands = [demand_for(baseline, s) for s in scenarios]
    for scenario, demand in zip(scenarios, baseline_demands):
        label, strategy, scale = scenario['label'].split('/')
        for country, value in zip(COUNTRIES, demand):
            expected = next(r['predicted_demand'] for r in frozen_predictions if r['model'] == label and
                            r['competitor_strategy'] == strategy and r['scale_scenario'] == scale and
                            r['country'] == country and r['team'] == '营销团队')
            assert abs(value - expected) < 1e-10
    grid = dict(thailand=[1790, 1800, 2000, 2200, 2500, 2800, 3000],
                indonesia=[1888, 2000, 2200, 2400, 2500, 2700, 2900], operations=[400, 700, 1000],
                machine_investment=[0, 10, 20], allocation=[20, 60, 100], long_change=[0, -5000, -10000, -15000])
    for c, prices in zip(COUNTRIES, [grid['thailand'], grid['indonesia']]):
        observed = [r['price'] for r in rows if r['phase'] == 'practice' and r['country'] == c]
        assert min(prices) >= min(observed) and max(prices) <= max(observed)
    ranked = []
    best = []
    safe_best = []
    for p1, p2 in product(grid['thailand'], grid['indonesia']):
        price_decision = dict(baseline, prices=[p1, p2], priority=sorted(range(2), key=lambda i: [p1-30, p2-120][i], reverse=True))
        demands = [demand_for(price_decision, s) for s in scenarios]
        for ops, investment, allocation, loan in product(grid['operations'], grid['machine_investment'],
                                                       grid['allocation'], grid['long_change']):
            decision = dict(price_decision, operations=ops, machine_investment=investment,
                            allocation=allocation, long_change=loan)
            result = evaluate(decision, demands)
            stressed = evaluate(decision, demands, True) if result['feasible'] else None
            stress_safe = stressed is not None and stressed['feasible']
            ranked.append(dict(thailand=p1, indonesia=p2, operations=ops, machine_investment=investment,
                               allocation=allocation, long_change=loan,
                               stress_safe=stress_safe, stress_min_cash=stressed['min_cash'] if stressed else None,
                               **{k: result[k] for k in ['feasible', 'worst_profit', 'best_profit', 'min_cash']}))
            if result['feasible']:
                best.append(result)
                best.sort(key=lambda r: r['worst_profit'], reverse=True)
                del best[5:]
            if stress_safe:
                safe_best.append(result)
                safe_best.sort(key=lambda r: r['worst_profit'], reverse=True)
                del safe_best[5:]
    assert best and safe_best and len(ranked) == int(np.prod([len(v) for v in grid.values()]))
    ranked.sort(key=lambda r: (r['feasible'], r['worst_profit']), reverse=True)
    comparisons = [dict(label='归档基准', **evaluate(baseline, baseline_demands))]
    for name, decision in [('仅改价格', dict(baseline, prices=best[0]['decision']['prices'])),
                           ('经营候选但不还贷', dict(best[0]['decision'], long_change=0))]:
        comparisons.append(dict(label=name, **evaluate(decision, [demand_for(decision, s) for s in scenarios])))
    stress = [dict(label='归档基准', **evaluate(baseline, baseline_demands, True))]
    for i, candidate in enumerate(best):
        decision = candidate['decision']
        stress.append(dict(label=f'候选{i+1}', **evaluate(decision, [demand_for(decision, s) for s in scenarios], True)))
    for i, candidate in enumerate(safe_best):
        decision = candidate['decision']
        stress.append(dict(label=f'压力现金达标候选{i+1}', **evaluate(decision, [demand_for(decision, s) for s in scenarios], True)))
    alternate_risk = next(r for r in model['finance']['risk_candidates'] if r['form'] != risk['form'])
    alternate_details = []
    for scenario in scenarios:
        decision = safe_best[0]['decision']
        efficiency = model['efficiency']['selected']['technology_scale'] * float(curve_value(
            decision['operations'] + .5 * previous_ops, model['curves']['operations']['parameters'], 'saturation'))
        linked = risk_linked_accounts(state, decision, demand_for(decision, scenario), efficiency,
                                      dict(material_cost=900), uplift, alternate_risk)
        alternate_details.append(dict(scenario=scenario['label'], **linked))
    out = ROOT / 'output' / 'joint_scenarios'
    out.mkdir(parents=True, exist_ok=True)
    paths = [frozen_path, '分步模型拟合与验证.json', 'code/joint_scenarios.py', 'code/stepwise_model.py',
             'code/cross_market_validation.py', 'code/build_model_inputs.py', 'raw/initial0_printable.json',
             'raw/20261011_model_v2_round1_checklist.json', 'raw/20261011_production_strategy_help.json']
    paths.extend(s['file'] for s in sources if s['market_id'] == 5)
    result = dict(generated_at=datetime.now(timezone.utc).isoformat(), status='OFFLINE_CONDITIONAL_ONE_ROUND_SEARCH',
                  source_hashes={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(set(paths))},
                  state=state, grid=grid, candidate_count=len(ranked), feasible_count=sum(r['feasible'] for r in ranked),
                  scenario_labels=[s['label'] for s in scenarios], risk_model=risk['form'], comparisons=comparisons,
                  top_candidates=best, stress_safe_candidates=safe_best, stress_safe_count=sum(r['stress_safe'] for r in ranked),
                  stress=stress, alternate_risk_sensitivity=alternate_details,
                  checks=dict(budget_replay=True, frozen_demand_replay=True, quantity_and_balance=True, browser_modified=False),
                  limits=['仅最大化八个指定情景的当期最小利润，不是六回合累计最优',
                          '正式需求、竞争、国别营销、未来前景未识别；冻结参数没有重训',
                          '机器账面净值计入资产但不加到当期利润；未来投资/运营收益没有计分',
                          '需求驱动、零期初库存、零大客户；现金不足2000的分支排除',
                          '压力是假定两国需求同时下降30%、效率减少0.005，不是置信区间',
                          '输入范围按历史价格及本地模型约束检查，未实时核验网页控件和成员改动'])
    (out/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with (out/'ranking.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(ranked[0]))
        writer.writeheader(); writer.writerows(ranked)
    lines = ['# 正式1联合情景研究', '', '基于归档个人基准，未实时确认页面。金额为千美元，数量为千单位。',
             '', f'共比较{len(ranked)}组固定决策，{result["feasible_count"]}组在八个情景内现金≥2000。',
             f'另将压力情景现金≥2000设为约束，{result["stress_safe_count"]}组达标；按常规情景最小利润排序。',
             '情景：A/B冻结模型 × 初始0/练习1对手策略 × 行业规模不变/练习1增长。', '',
             '| 方案 | 泰/印价格 | 运营 | 机器新增 | 产能分配% | 贷款变化 | 最小利润 | 最大利润 | 最低现金 |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for label, r in ([(r['label'], r) for r in comparisons] + [(f'候选{i+1}', r) for i, r in enumerate(best)] +
                     [(f'压力现金达标候选{i+1}', r) for i, r in enumerate(safe_best)]):
        d = r['decision']
        lines.append(f'| {label} | {d["prices"][0]}/{d["prices"][1]} | {d["operations"]} | {d["machine_investment"]} | {d["allocation"]} | {d["long_change"]} | {r["worst_profit"]:.1f} | {r["best_profit"]:.1f} | {r["min_cash"]:.1f} |')
    lines += ['', '## 压力检验', '', '| 方案 | 最小利润 | 最低现金 | 全部现金达标 |', '| --- | ---: | ---: | --- |']
    lines += [f'| {r["label"]} | {r["worst_profit"]:.1f} | {r["min_cash"]:.1f} | {r["feasible"]} |' for r in stress]
    lines += ['', f'压力现金达标首选在另一风险函数下，常规最小利润为{min(r["output"]["profit"] for r in alternate_details):.1f}，'
              f'最低现金为{min(r["output"]["cash"] for r in alternate_details):.1f}。此项只作敏感性，不重排全部网格。']
    chosen = safe_best[0]
    lines += ['', '## 研究判断', '',
              f'压力现金达标首选相对常规首选少赚{best[0]["worst_profit"]-chosen["worst_profit"]:.1f}千美元的常规最小利润，'
              '但减少5000千美元还贷，保留更多现金。这是当前网格的现金余量选择，不是精确最优偿债额。',
              '归档基准20%产能分配把无机器投资的产量上限压在3.4千单位；仅改价格仍然亏损。'
              '候选同时改变生产上限、班次结构和效率，收益差不能全部归因于调价。',
              '新增机器10千单位花费1000千美元，扩大三班总产能至27千单位，第一班上限从5.67升至9千单位。'
              '它在模型中也有降低班次工资的作用；机器投资的未来现金需求和收益仍需滚动分析。',
              '基准损益使用模型需求和效率，不是手填2.5/11、效率0.15的网页预算；后者仅用于独立回算自检。',
              '压力下仍可能亏损，现金达标不表示盈利有保证。现金不足分支的利润未补齐短贷利息，不能作完整利润比较。',
              '', '| 候选固定字段 | 归档基准 | 压力现金达标首选 |', '| --- | --- | --- |']
    for key in ['prices', 'operations', 'machine_investment', 'allocation', 'long_change', 'priority']:
        lines.append(f'| {key} | {baseline[key]} | {chosen["decision"][key]} |')
    lines += ['', '| 需求模型 | 常规最小利润 | 常规最大利润 | 泰国需求范围 | 印尼需求范围 |',
              '| --- | ---: | ---: | --- | --- |']
    for name in ['A', 'B']:
        rr = [r for r in chosen['details'] if r['scenario'].startswith(name+'/')]
        lines.append(f'| {name} | {min(r["profit"] for r in rr):.1f} | {max(r["profit"] for r in rr):.1f} | '
                     f'{min(r["demand"][0] for r in rr):.3f}–{max(r["demand"][0] for r in rr):.3f} | '
                     f'{min(r["demand"][1] for r in rr):.3f}–{max(r["demand"][1] for r in rr):.3f} |')
    lines += ['', '## 适用边界', ''] + ['- '+v for v in result['limits']]
    lines += ['', '一般营销50/200、设计师营销0/150、研发600保持归档基准；不对未识别的国别营销作优化。',
              '货源不足时按售价减运输单价排序；候选采用同一固定策略覆盖所有情景，未按未来需求选不同决策。',
              '', '源码：`code/joint_scenarios.py`；完整情景、期末财务及自检：`results.json`；全部候选：`ranking.csv`。',
              '复现：`python code/joint_scenarios.py`。原冻结参数及预测档案保持原样。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(candidate_count=len(ranked), feasible_count=result['feasible_count'], best=ranked[0],
                          stress_best={k: stress[1][k] for k in ['worst_profit', 'min_cash', 'feasible']}), ensure_ascii=False))


if __name__ == '__main__':
    main()
