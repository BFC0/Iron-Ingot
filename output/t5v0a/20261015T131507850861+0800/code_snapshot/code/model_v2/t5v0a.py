"""t5v0 frozen coefficients applied to formal5; no training or platform writes."""
import argparse
import copy
import os
from pathlib import Path

import t4v1a as app

ROOT = app.ROOT
BASE = ROOT/'output/t5v0/20261015T085218049188+0800'
CURVES = ROOT/'output/t5v0/20261015T090943259882+0800_formal5_curves'
INITIAL = ROOT/'output/round_close/20261014_formal4_close/formal5_initial'
PRODUCTS, COUNTRIES = app.PRODUCTS, app.COUNTRIES


def curve_at(registry, key, context, x):
    c = registry['application_curves']['curves'][key]
    expected = dict(market_id=5, area='PYT', phase='formal', round=5,
        previous_input=c['upstream_condition']['previous_formal4_actual_input']['value'],
        unit='千美元', coordinate_kind='effective_investment_scenario')
    if context != expected:
        raise ValueError('曲线回合、区域、上期投入或有效横轴情境不匹配')
    app.number(x)
    if not c['x_range'][0] <= x <= c['x_range'][1]:
        raise ValueError('禁止超出已归档曲线范围')
    value = float(app.curve_value(x, c['parameters'], c['form']))
    app.number(value, True)
    return dict(multiplier=value, effective_input_kusd=x, context=context,
        status='EXPLICIT_EFFECTIVE_COORDINATE_ONLY', historical_effect_added=False,
        spending_mapping_verified=False)


def material_scenarios(registry, product, quantity):
    price = registry['application_parameters']['material/'+product]['value']
    return {form: app.material.predict(model, price, quantity)
            for form, model in registry['materials'][product]['models'].items()}


def apply_request(registry, request):
    if (registry.get('version'), registry.get('base_version'), registry.get('training_round'),
            registry.get('application_round')) != ('t5v0a', 't5v0', 4, 5):
        raise ValueError('模型注册表版本或训练/应用回合不匹配')
    if (request.get('version'), request.get('market_id'), request.get('phase'), request.get('round')) != ('t5v0a', 5, 'formal', 5):
        raise ValueError('需要t5v0a／市场5／正式5情境')
    allowed = {'version', 'market_id', 'phase', 'round', 'curve_coordinates',
               'production', 'financial_state', 'connector', 'product_growth'}
    if set(request)-allowed:
        raise ValueError('未知请求字段: '+','.join(sorted(set(request)-allowed)))
    result = dict(version='t5v0a', application_round=5, training_performed=False,
        full_profit_available=False, complete_profit=None, deployment_enabled=False,
        remaining_profit_ranking=False, materials={}, labor={}, curves={})
    for key, item in request.get('curve_coordinates', {}).items():
        result['curves'][key] = curve_at(registry, key, item['context'], item['effective_x_kusd'])
    for product, plan in request.get('production', {}).items():
        if product not in PRODUCTS:
            raise ValueError('未知产品')
        result['materials'][product] = material_scenarios(registry, product, plan['production_kunits'])
        if plan.get('efficiency_basis') != 'EXPLICIT_SCENARIO':
            result['labor'][product] = app.missing('缺显式效率；不以运营乘数代替绝对效率')
        else:
            result['labor'][product] = app.labor_cost(registry, plan, plan['efficiency_kunits_per_person'])
    result['finance'] = app.missing('缺显式财务状态；不推定计息时点或自动短贷')
    if 'financial_state' in request:
        result['finance'] = app.rate_scenario(registry, request['financial_state'])
    result['market_totals'] = app.missing('建筑市场增速到产品需求的映射未核验；需显式产品/国家增长情景')
    if 'product_growth' in request:
        growth = request['product_growth']
        if set(growth) != set(PRODUCTS) or any(set(growth[p]) != set(COUNTRIES) for p in PRODUCTS):
            raise ValueError('需给定两产品两国的增长情景')
        totals = {}
        for p in PRODUCTS:
            totals[p] = {}
            for c in COUNTRIES:
                g = growth[p][c]
                if isinstance(g, bool) or not isinstance(g, (int, float)) or not app.math.isfinite(g) or g < -1:
                    raise ValueError('增长率须为有限数且不低于-100%')
                totals[p][c] = registry['formal4_market_totals_kunits'][p][c]*(1+g)
        result['market_totals'] = dict(status='EXPLICIT_PRODUCT_GROWTH_SCENARIO',
            totals_kunits=totals, product_growth=growth, forecast_validated=False)
    result['demand'] = app.missing('缺99队最终决策；SHARE/COUNTRY/ABS沿用暂停，不重训或调用旧响应冒充正式5预测')
    result['connector'] = app.missing('缺显式生产/需求/价格/效率及订单前数量情景')
    if 'connector' in request:
        item = request['connector']
        if set(item) != {'product', 'allocation_pct', 'country_priority', 'material_form', 'scope'} or item['scope'] != 'BEFORE_UNVERIFIED_ORDERS':
            raise ValueError('连接件仅支持显式订单前数量情景；合同、库存计价和投资时序跳过')
        product = copy.deepcopy(item['product'])
        if set(product) != {'capacity', 'efficiency', 'demand', 'prices'}:
            raise ValueError('需显式capacity/efficiency/demand/prices，不接受覆盖公布成本')
        costs = material_scenarios(registry, '连接件', 0)
        product.update(material_cost=costs[item['material_form']]['unit_cost_usd'],
                       transport_costs=registry['connector_transport_usd'])
        params = registry['application_parameters']
        plan = dict(allocation_pct=item['allocation_pct'], country_priority=item['country_priority'],
            opening_inventory_kunits=registry['opening_inventory_kunits']['连接件'],
            holding_cost_per_unit=params['holding']['value'])
        result['connector'] = app.connector.project(product, plan, params['wage']['value'],
            [1., params['second_shift']['value'], params['third_shift']['value']])
        result['connector'].update(status='BEFORE_UNVERIFIED_ORDERS_QUANTITY_SCENARIO',
            material_form=item['material_form'], full_profit_available=False)
    result['administration'] = dict(base_cost_kusd=registry['application_parameters']['administration']['value'],
        increase_kusd=4000., pretax_profit_delta_kusd=-4000., cash_delta_kusd=None,
        scope='仅行政基础费较正式4的税前增量，不重复叠加；付款时点和税亏未知')
    result['new_tender_available'] = False
    result['existing_orders'] = app.missing('没有新招标不代表没有历史合同；交付及收付款未核验')
    result['investment_timing'] = app.missing('公布机器价格已更新；生效时点未知，不推断扩产收益')
    result['spending_to_curve'] = app.missing('研发/运营存量及衰减不可识别，自动支出映射跳过')
    result['horizon'] = app.horizon.remaining_profit(5, [dict(round=r, profit=None,
        in_scope=False, end_state=None) for r in (5, 6)])
    return result


def build_bundle(out):
    out = Path(out)
    if not (out/'work_log.md').is_file() or (out/'models_full.json').exists():
        raise FileExistsError('需先创建独立工作日志；拒绝覆盖已有版本')
    sources = {}
    def read(path):
        sources[path.relative_to(ROOT).as_posix()] = app.sha(path)
        return app.read(path)
    original = read(BASE/'models_full.json')
    curves = read(CURVES/'formal5_curves.json')
    assert read(CURVES/'acceptance.json')['status'] == 'PASS'
    parameters = read(INITIAL/'published_parameters.json')
    outlook = read(INITIAL/'published_outlook_five_parts.json')
    carry = read(INITIAL/'carryover_comparison.json')
    industry = read(BASE/'industry.json')
    assert original['version'] == 't5v0' and original['training_round'] == 4
    assert curves['round'] == 5 and curves['valid_period'] == 'formal5'
    def refs(value):
        if isinstance(value, dict):
            path = value.get('source_path', value.get('source'))
            digest = value.get('sha256', value.get('source_sha256'))
            if isinstance(path, str) and isinstance(digest, str) and len(digest) == 64:
                assert app.sha(ROOT/path) == digest, path
                sources[path] = digest
            for v in value.values(): refs(v)
        elif isinstance(value, list):
            for v in value: refs(v)
    for value in (parameters, outlook, curves, carry): refs(value)
    def parameter(label, unit, factor=1, occurrence=0):
        row = [p for p in parameters if p['label'] == label][occurrence]
        return dict(value=row['current_numeric']*factor, unit=unit, source=row, round=5)
    p = dict(base_rate=parameter('基准利率', '小数', .01),
        short_spread=parameter('高于基准的短期利率溢价', '小数', .01),
        wage=parameter('泰国', '千美元/人'), second_shift=parameter('两班倒', '乘数'),
        third_shift=parameter('三班倒', '乘数'),
        attrition=parameter('年人员离职率（without costs），%', '小数', .01),
        severance=parameter('裁员成本，占薪资%', '小数', .01),
        administration=parameter('基础成本', '千美元'), holding=parameter('库存持有成本', '美元/单位'),
        minimum_cash=parameter('最低现金, 千 美元', '千美元'), tax_rate=parameter('企业所得税率, %', '小数', .01))
    for product in PRODUCTS:
        p['material/'+product] = parameter(product, '美元/单位')
        p['machine/'+product] = parameter('机器, '+product, '美元/单位')
    registry = copy.deepcopy(original)
    registry.update(version='t5v0a', base_version='t5v0', application_round=5, application_market=5,
        training_performed=False, application_parameters=p, application_curves=curves,
        published_parameters=parameters, published_outlook=outlook, carryover_evidence=carry,
        construction_market_growth={'泰国': .07, '印尼': -.05},
        product_growth_mapping_verified=False, new_tender_available=False,
        formal4_market_totals_kunits={pr:{c:next(r['total'] for r in industry
            if (r['market'],r['product'],r['country']) == (5,pr,c)) for c in COUNTRIES} for pr in PRODUCTS},
        opening_inventory_kunits={pr:next(r['formal5_opening']['value'] for r in carry
            if r['metric'] == pr+'期初库存数量') for pr in PRODUCTS},
        connector_transport_usd={c:parameter('泰国 -> '+c, '美元/单位', occurrence=1)['value'] for c in COUNTRIES},
        status='FROZEN_FORMAL5_APPLICATION_PARTIAL_NO_RETRAIN')
    # The existing rate evaluator calls the same frozen training bounds "ranges".
    registry['risk']['solvency_exponential']['ranges'] = copy.deepcopy(original['risk']['solvency_exponential']['training_ranges'])
    adjusted = {'TOTAL','BASELINE','GROWTH','MATERIAL','MATERIAL_PROP','LABOR','OPERATING',
                'FINANCE','RD','OPS','CONNECTOR','CAPACITY','RISK_EXP','INTEREST','HORIZON'}
    blocked = {'ABS','SHARE','COUNTRY','EFF','A','D','CONNECTOR_V2','JOINT_ALLOCATION'}
    actions = {}
    for name, item in registry['model_inventory'].items():
        actions[name] = dict(action='条件应用调整' if name in adjusted else '缺数据跳过' if name in blocked else '沿用历史证据',
            historical_status=item['status'], retrained=False, full_forward_validation=False)
        src = BASE/item['artifact']
        assert src.is_file(), src
        sources[src.relative_to(ROOT).as_posix()] = app.sha(src)
        item['artifact'] = Path(os.path.relpath(src, out)).as_posix()
    registry['application_actions'] = actions
    registry['source_sha256'] = sources
    app.save(out/'models_full.json', registry)
    app.save(out/'model_adjustments.json', actions)
    app.save(out/'example_request.json', dict(version='t5v0a', market_id=5, phase='formal', round=5))
    return registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--request', type=Path)
    args = parser.parse_args()
    with app.no_training():
        registry = build_bundle(args.bundle) if args.build else app.read(args.bundle/'models_full.json')
        request = app.read(args.request or args.bundle/'example_request.json')
        result = apply_request(registry, request)
        if args.build:
            app.save(args.bundle/'example_result.json', result)
    print(app.json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
