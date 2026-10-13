"""Archive consistency, frozen reproduction and bounded budget audit."""
import re
import numpy as np
from core import *


def audit(rows, cells, sources):
    frozen = read(FROZEN)
    fitrows = [r for r in rows if r['usable_for_fit']]
    assert {r['phase'] for r in fitrows} == {'practice'}, 'Formal results require separate frozen scoring first'
    checks = self_check(frozen['rd_curve_parameters'], rows)
    coefficients = {}
    equivalence = []
    for name, pool in [('A', [r for r in fitrows if r['market_id'] == 5]), ('B', fitrows)]:
        model = frozen['models'][name]['competitive']
        beta = old.fit(pool, old.feature_matrix(pool, frozen['rd_curve_parameters']), model['penalty'])
        difference = float(np.max(abs(beta - model['coefficients'])))
        assert difference < 1e-9
        coefficients[name] = dict(max_difference=difference, n=len(pool), coefficients=beta.tolist())
        normal = fit(pool, frozen['rd_curve_parameters'], .01)
        scaled = fit(pool, frozen['rd_curve_parameters'], .01 * len(pool), multiplier=len(pool))
        delta = float(np.max(abs(np.array(normal['beta']) - scaled['beta'])))
        assert delta < 1e-9
        equivalence.append(dict(model=name, n=len(pool), mean_lambda=.01, weighted_sum_lambda=.01 * len(pool),
                                max_difference=delta, note='B为n倍市场/国家等权损失，不等于未加权原始残差总和'))
    future = read(FUTURE)
    replay = old.prospective(rows, frozen['models'], frozen['rd_curve_parameters'], frozen['frozen_at'])
    fk = lambda r: tuple(r[k] for k in ['model','market_id','phase','round','team_id','country','competitor_strategy','scale_scenario'])
    saved = {fk(r): r for r in future['records']}
    assert {fk(r) for r in replay} == set(saved)
    max_difference = max(abs(r['predicted_demand'] - saved[fk(r)]['predicted_demand']) for r in replay)
    assert max_difference < 1e-9
    zeros = []
    for r in fitrows:
        if r['demand'] == 0:
            text = r['sources']['demand']['text']
            decimals = len(text.split('.')[-1]) if '.' in text else 0
            half = .5 * 10 ** (-decimals)
            zeros.append(dict(key=key(r), source=r['sources']['demand'], display=text,
                              rounding_interval_if_nearest=[0, half], nearest_rounding_verified=False,
                              note='零值显示精度可核；真实为零或小正值及舍入方式未独立证明，不添加伪小数'))
    long = []
    for r in rows:
        for field, category, unit in [('demand','actual_demand','千单位'),('sales','actual_sales','千单位'),
                                     ('price','historical_price','美元/单位'),('general','historical_general_proxy','千美元'),
                                     ('designer','historical_designer_proxy','千美元'),('rd','historical_rd','千美元')]:
            long.append(dict(key=key(r, category), market_id=r['market_id'], phase=r['phase'], round=r['round'],
                             team_id=r['team_id'], country=r['country'], category=category, value=r[field], unit=unit,
                             source=r['sources'][field], available=r[field] is not None))
    assert len({tuple(r['key']) for r in long}) == len(long)
    checks.update(frozen_coefficients=True, frozen_predictions=True, sources_traceable=True,
                  actual_budget_separated=True, missing_not_zero=True)
    return dict(checks=checks, n_rows=len(rows), n_fit=len(fitrows), source_files=sources,
                source_cell_count=len(cells), training_keys=[key(r) for r in fitrows],
                data_cutoff='最后可用实际标签为练习2；无正式实际，全部新版评分为回溯研究',
                frozen_coefficients=coefficients, frozen_predictions=dict(n=len(replay), max_difference=max_difference),
                loss_equivalence=equivalence, zero_demand=zeros, units=UNITS, data=long,
                stage1_gate='PASS_ARCHIVED_REPRODUCTION; independent budget mechanism validation remains separate')


def budget():
    previous = read('分步模型拟合与验证.json')
    inp = previous['decisions']['current_inputs']
    decision = dict(inp['decision'])
    # Old adapter receives percent; the public v2 input stores rates as decimals.
    decimal_decision = dict(decision, long_rate=decision['long_rate'] / 100)
    uplift = previous['finance']['materials']['uplift_usd_per_unit']
    calc = step.accounts_from_state(inp['state'], decision, inp['demand'], inp['efficiency'],
                                    dict(material_cost=900), uplift)
    old_output = previous['decisions']['current_budget_replay']
    discrepancies = {k:calc[k] - v for k,v in old_output.items() if isinstance(v, (int,float)) and not isinstance(v, bool)}
    assert max(abs(v) for v in discrepancies.values()) < 1e-9
    comparisons = []
    for row in previous['decisions']['current_replay_checks']:
        difference = calc[row['metric']] - row['observed']
        # 0.5 per integer monetary display; chained totals use the sum of displayed component half-widths.
        components = {'profit': ['revenue','materials','payroll','transport','marketing','overhead','machine_depreciation',
                                  'building_depreciation','cash_interest','long_interest','tax'],
                      'cash':['opening_cash','ebitda','interest','opening_ar','closing_ar','opening_ap','closing_ap','capex','tax']}
        bound = .5 * len(components[row['metric']]) if row['metric'] in components else .5
        comparisons.append(dict(**{k:v for k,v in row.items() if k not in ['passed','error']}, error=difference,
                                rounding_envelope_kusd=bound, within_display_envelope=abs(difference)<=bound,
                                envelope_basis=components.get(row['metric'], ['target_integer_display']),
                                limit='显示舍入包络为诊断；来源输入、隐藏连续值和机制仍须独立试验'))
    assert all(r['within_display_envelope'] for r in comparisons)
    materials = []
    for r in previous['finance']['materials']['records']:
        q = r['predicted'] / ((900 if r['round']==1 else 1053) + uplift)
        base = 900 if r['round']==1 else 1053
        error = q * base - r['observed']
        envelope = .005 * base + .5
        materials.append(dict(round=r['round'],team=r['team'], displayed_quantity=q,
                              official_base_unit_cost=base, raw_base_error_kusd=error,
                              quantity_half_width=.005, output_half_width_kusd=.5,
                              rounding_envelope_kusd=envelope, explained_by_rounding=abs(error)<=envelope,
                              empirical_uplift_usd_per_unit=uplift, calibrated_error_kusd=r['error'], source=r['source']))
    return dict(archived_only=True, latest_personal_baseline_verified=False, units=UNITS,
                decision=decimal_decision, input_demand=inp['demand'], input_efficiency=inp['efficiency'],
                old_replay_max_difference=max(abs(v) for v in discrepancies.values()),
                output=calc, checks=comparisons, materials=materials,
                correction='旧报告约±5美元为错误单位；0.005千单位×900/1053美元每单位为±4.5/5.265千美元，再加报表0.5千美元',
                parameters=dict(material_cost=dict(value=900,unit='美元/单位',status='当期前景',source='raw/20261011_model_v2_round1_outlook.json'),
                    uplift=dict(value=uplift,unit='美元/单位',status='练习1经验校准',source='分步模型拟合与验证.json'),
                    building_capex=dict(value=800,unit='千美元',status='历史经验，时序未试验',source='raw/practice1_printable.json')),
                unidentified=['短贷计息','亏后转盈税亏','非零库存计价结转','大客户中标交付','厂房投资时序','未来当期参数'],
                live_trials=dict(attempts=['新建Cesim主页标签页30秒超时','绑定已打开主页30秒超时'],
                                 mutation_count=0, saved_samples=0, restored_samples=0,
                                 status='ACCESS_TIMEOUT_NO_CURRENT_BASELINE'),
                stage3_gate=False, stage3_gate_reason='实时身份/回合/基准及独立保留预算试验尚未取得；历史回算不等于机制通过')
