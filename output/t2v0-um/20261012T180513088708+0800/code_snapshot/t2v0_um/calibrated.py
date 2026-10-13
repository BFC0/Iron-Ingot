"""Practice2-only calibration and explicit financial dependencies for t2v0-um."""
import copy
import json
import math
import numpy as np
import pipeline as t2
import interest_rate_model as interest
import material_unit_cost_model as material
from model_v2.finance import accounts

OLD_INTEREST = 'output/interest_rate/20261012T174038098990+0800/model.json'
OLD_MATERIAL = 'output/material_unit_cost/20261012T175213319382+0800/model.json'


def published_parameters():
    background = t2.core.read(t2.BACKGROUND)
    source = background['linked_dom']
    if t2.core.digest(t2.ROOT / source['file']) != source['sha256']:
        raise ValueError('Practice2 outlook source changed')
    records = []
    for row in background['parameters']:
        text = row['cells'][1]
        value = t2.core.old.numeric(text.removesuffix(' 美元') if row['section'] == '货币汇率' else text)
        records.append(dict(section=row['section'], label=row['cells'][0], value=value, display_value=text, unit=row['unit'],
            source=dict(file=source['file'], sha256=source['sha256'], line=row['line'], column=1),
            phase='practice', round=2))

    def get(section, label, factor=1):
        row = next(r for r in records if (r['section'], r['label']) == (section, label))
        return row['value'] * factor

    p = dict(wage=get('生产工资', '泰国'), second_shift=get('工资乘数', '两班倒'),
        third_shift=get('工资乘数', '三班倒'), attrition=get('人员流动', '年人员离职率（without costs），%', .01),
        severance=get('人员流动', '裁员成本，占薪资%', .01), material_cost=get('原材料成本', '复合梁'),
        transport=[get('运输成本', '泰国 -> 泰国'), get('运输成本', '泰国 -> 印尼')],
        marketing_fixed=get('固定成本', '市场调研'),
        overhead_fixed=sum(r['value'] for r in records if r['section'] == '行政管理'),
        machine_unit_capex=get('投资成本', '机器, 复合梁'), machine_depreciation=get('年折旧', '机器', .01),
        machine_capacity_decline=get('年产能下降', '机器', .01), cash_rate=get('利率', '现金及现金等价物', .01),
        tax_rate=get('财务', '企业所得税率, %', .01), minimum_cash=get('财务', '最低现金, 千 美元'))
    return dict(records=records, financial_parameters=p, base_rate_percent=get('利率', '基准利率'),
        short_spread_percent=get('利率', '高于基准的短期利率溢价'),
        unknown_financial_parameters=['building_capex', 'building_depreciation', 'ar_days', 'ap_days'])


def component_dataset(rows, published):
    t2.validate_rows(rows, 'practice')
    result = []
    for r in rows:
        if r['country'] != t2.core.COUNTRIES[0]:
            continue
        if r['kind'] != 'actual_result':
            raise ValueError('Only practice2 actual results can train components')
        path, col = t2.ROOT / r['sources']['demand']['file'], r['team_column']
        definitions = [('production', '生产规模, 千单位', 0), ('material_cost', '原材料购买', 0),
            ('rate_percent', '长期贷款利率，%', 0), ('equity', '股东权益合计', 0),
            ('assets', '资产总计', 0), ('long_debt', '长期贷款', 0), ('short_debt', '短期贷款', 1)]
        refs = {key: t2.formal.field(path, label, col, occurrence) for key, label, occurrence in definitions}
        values = {key: ref['value'] for key, ref in refs.items()}
        if any(v is None or not math.isfinite(v) for v in values.values()):
            raise ValueError('Missing/nonfinite practice2 component label')
        state = {key: values[key] for key in ('equity', 'assets', 'long_debt', 'short_debt')}
        ratios = interest.ratios(state)
        q, cost = values['production'], values['material_cost']
        base = published['financial_parameters']['material_cost']
        if q <= .005 or cost < 0 or values['rate_percent'] < published['base_rate_percent'] - .005:
            raise ValueError('Outside supported practice2 component scope')
        result.append(dict(market_id=r['market_id'], market=r['market_id'], team_column=col,
            team_id=r['team_id'], team=r['team_id'], phase='practice', round=2, context_id=t2.CONTEXT,
            **ratios, state=state, production=q, published_material=base, material_cost=cost,
            implied_low=(cost - .5) / (q + .005), implied_high=(cost + .5) / (q - .005),
            rate_percent=values['rate_percent'], premium=values['rate_percent'] / 100 - published['base_rate_percent'] / 100,
            sources=refs))
    if len(result) != 100 or len({(r['market_id'], r['team_column']) for r in result}) != 100:
        raise ValueError('Need 100 unique practice2 companies')
    return result


def fit_interest(rows, base_rate):
    outer = []
    for market in range(1, 11):
        train, test = [r for r in rows if r['market_id'] != market], [r for r in rows if r['market_id'] == market]
        form, scores = interest.select(train)
        p = interest.fit(form, train)
        outer.append(dict(held_market=market, training_markets=sorted({r['market_id'] for r in train}),
            form=form, parameters=p, inner_scores_bp=scores,
            records=[dict(market_id=r['market_id'], team_column=r['team_column'],
                actual_rate_percent=r['rate_percent'], predicted_rate_percent=base_rate + float(v) * 100,
                error_bp=float(v - r['premium']) * 10000) for r, v in zip(test, interest.premium(form, p, test))]))
    form, scores = interest.select(rows)
    errors = np.array([r['error_bp'] for fold in outer for r in fold['records']])
    model = dict(form=form, parameters=interest.fit(form, rows), candidate_cv_mae_basis_points=scores,
        model_id=t2.MODEL_ID + '/interest_rate', training_phase='practice', training_round=2, training_n=100,
        target_phase='formal', target_round=2, base_rate_percent=base_rate,
        training_keys=[[r['market_id'], 'practice', 2, r['team_column']] for r in rows],
        nested_market_holdout_mae_basis_points=float(np.mean(abs(errors))),
        nested_market_holdout_max_error_basis_points=float(np.max(abs(errors))),
        conditional_error_p90_basis_points=float(np.quantile(abs(errors), .9)),
        ranges={key: [min(r[key] for r in rows), max(r[key] for r in rows)] for key in ('equity_ratio', 'leverage')},
        formula='r_long = r_base + a*leverage**b' if form == 'leverage_power' else 'r_long = r_base + a*exp(-b*equity/assets)',
        short_formula='r_short = r_long + published_short_spread',
        validation_scope='Practice2 actual end-state conditional validation; not prospective formal2 validation',
        short_rate_status='published rule; actual short interest not independently fitted')
    return model, outer


def fit_material(rows):
    # shortcut: only one practice2 base price is observed; retain the requested proportional form, re-identify cross-price shape when new regimes are authorized.
    model = material.fit(rows, 'proportional')
    holdouts = []
    for market in range(1, 11):
        train, test = [r for r in rows if r['market_id'] != market], [r for r in rows if r['market_id'] == market]
        fitted = material.fit(train, 'proportional')
        holdouts.append(dict(held_market=market, training_markets=sorted({r['market_id'] for r in train}),
            fitted=fitted, evaluation=material.evaluate(fitted, test)))
    errors = [r['error_kusd'] for fold in holdouts for r in fold['evaluation']['records']]
    price = rows[0]['published_material']
    model.update(model_id=t2.MODEL_ID + '/material_unit_cost', training_phase='practice', training_round=2,
        target_phase='formal', target_round=2, training_n=100,
        training_keys=[[r['market_id'], 'practice', 2, r['team_column']] for r in rows],
        published_price_range=[price, price], unit_cost_usd=material.predict(model, price, 1)['unit_cost_usd'],
        formula='unit_cost = published_price*(1+parameter)', cost_formula='cost_kusd = production_kunits*unit_cost',
        market_holdout_mae_kusd=float(np.mean(abs(np.array(errors)))),
        market_holdout_max_error_kusd=float(np.max(abs(np.array(errors)))),
        validation_scope='Practice2 actual production conditional validation; not prospective formal2 validation',
        identification_limit='A single published price cannot distinguish proportional from additive adjustments',
        rounding_assumption='production ±0.005 kunits and cost ±0.5 kusd; not a confidence interval')
    return model, holdouts


def train_components(rows, gate):
    published = published_parameters()
    data = component_dataset(rows, published)
    interest.self_check()
    material.self_check()
    rate_model, rate_folds = fit_interest(data, published['base_rate_percent'])
    material_model, material_folds = fit_material(data)
    artifact = dict(model_id=t2.MODEL_ID, training_phase='practice', training_round=2, target_phase='formal', target_round=2,
        interest_rate=rate_model, material_unit_cost=material_model, published=published,
        migration_gate_passed=gate['passed'], formal2_prediction_enabled=gate['passed'],
        whole_model_trained=False, market_sharing='user-authorized same-round unified-market assumption')
    old_rate, old_material = t2.core.read(OLD_INTEREST), t2.core.read(OLD_MATERIAL)
    changes = dict(model_id=t2.MODEL_ID,
        interest_rate=dict(before=old_rate['parameters'], before_training='formal/1 comparison only',
            after=rate_model['parameters'], form_before=old_rate['form'], form_after=rate_model['form'], training='practice/2'),
        material_unit_cost=dict(before=old_material['parameter'], before_training='practice1/practice2/formal1 comparison only',
            after=material_model['parameter'], unit_cost_after=material_model['unit_cost_usd'], training='practice/2'),
        given_parameters=dict(status='28 items rebound to practice2 and compared with formal2 archive', records=published['records']),
        legacy_uplift=dict(status='REPLACED_FOR_NEW_FINANCIAL_CALLS', after=material_model['unit_cost_usd'] - published['financial_parameters']['material_cost'],
            rule='new material cost already includes adjustment; never add old residual again'),
        demand_coefficients=dict(status='NOT_RETRAINED_MISSING_PRACTICE2_CURVE_BINDING',
            reason='Interest and material cost are not demand feature inputs; no old coefficients silently inherited'),
        efficiency=dict(status='NOT_RETRAINED_MISSING_PRACTICE2_OPERATIONS_CURVE',
            reason='Technology scale and operations carry need the matching upstream curve'),
        fixed_assumptions=dict(rd_rho=.5, marketing_scale=1000, status='UNCHANGED_DEFINITION_NOT_NEW_ESTIMATE'),
        financial_feedback=['production→new materials→EBITDA→profit/cash/equity/assets',
                            'predicted closing debt/equity/assets→new rate→interest→profit/cash/equity/assets'],
        incomplete_finance=published['unknown_financial_parameters'] + ['tax_loss', 'technology_stocks', 'inventory/short-debt/bulk branches', 'interest timing'],
        baseline_sources=[dict(file=p, sha256=t2.core.digest(t2.ROOT / p), use='parameter comparison only, excluded from fitting') for p in (OLD_INTEREST, OLD_MATERIAL)])
    validation = dict(interest_nested_market_holdouts=rate_folds, material_market_holdouts=material_folds,
        material_training=material.evaluate(material_model, data),
        interpretation='conditional actual-state/production validation; no full-finance or formal2 prospective claim')
    return artifact, data, validation, changes


def check_component_period(components, phase, round_number):
    if components['model_id'] != t2.MODEL_ID or round_number != 2 or phase not in ('practice', 'formal'):
        raise ValueError('Only t2v0-um round2 components are accepted')
    if phase == 'formal' and not components['migration_gate_passed']:
        raise ValueError('Formal2 migration gate is closed')
    for name in ('interest_rate', 'material_unit_cost'):
        model = components[name]
        if (model['training_phase'], model['training_round'], model['model_id']) != ('practice', 2, t2.MODEL_ID + '/' + name):
            raise ValueError('Wrong component training period/version')


def conditional_accounts(components, state, decision, demand, efficiency, assumptions, *, phase, round_number):
    """Reuse existing account equations with both new costs and an iterated risk rate."""
    check_component_period(components, phase, round_number)
    if any(state.get(key) is None for key in ('inventory', 'short_debt', 'tax_loss')):
        raise ValueError('Inventory, debt and tax-loss state must be explicit')
    if state['inventory'] != 0 or state['short_debt'] != 0 or state.get('orders'):
        raise ValueError('Existing account equations only cover zero opening inventory/short debt and no bulk orders')
    unknown = components['published']['unknown_financial_parameters']
    if set(assumptions) != set(unknown) or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in assumptions.values()):
        raise ValueError('Provide each unidentified financial parameter explicitly; no old defaults')
    p = dict(components['published']['financial_parameters'], **assumptions)
    unit_cost = material.predict(components['material_unit_cost'], p['material_cost'], 1)['unit_cost_usd']
    p['uplift'] = unit_cost - p['material_cost']
    base = components['published']['base_rate_percent']
    spread = components['published']['short_spread_percent']
    rate = base / 100
    for iteration in range(200):
        d = dict(decision, long_rate=rate)
        result = accounts(state, d, demand, efficiency, p)
        if not result['fully_computed_in_scope']:
            raise ValueError('New costs require an unidentified short-debt branch')
        closing = {key: result[key] for key in ('equity', 'assets', 'long_debt')}
        closing['short_debt'] = 0
        forecast_rate = interest.predict(components['interest_rate'], closing, base, spread)
        target = forecast_rate['long_rate_percent'] / 100
        if abs(target - rate) < 1e-10:
            result.update(model_id=t2.MODEL_ID, phase=phase, round=round_number, iterations_risk_rate=iteration + 1,
                long_rate=rate, short_rate=forecast_rate['short_rate_percent'] / 100, unit_material_cost=unit_cost,
                explicit_assumptions=copy.deepcopy(assumptions), status='CONDITIONAL_ACCOUNT_SCENARIO',
                scope='Existing conditional accounts plus new material/rate models; interest timing remains assumed')
            return result
        rate = (rate + target) / 2
    raise RuntimeError('Financial/risk feedback did not converge')
