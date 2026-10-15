"""Source-backed connector lifecycle checks; no training or platform writes."""
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2')]
import t3v1 as model
from connector_free_production import project

nd = model.nd
OUT = ROOT/'output/connector_model_update'/datetime.now(nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
OLD = ROOT/'output/t3v1/20261013T193815695205+0800'
CURRENT = model.base.CURRENT


def save(name, data):
    path = OUT/name
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def run():
    OUT.mkdir(parents=True, exist_ok=False)
    protected = [CURRENT/'raw/outlook.json', CURRENT/'raw/productionplanning.json',
                 CURRENT/'tables.json', CURRENT/'charts.json', OLD/'models.json',
                 OLD/'example_request.json', OLD/'example_prediction.json', OLD/'manifest.json',
                 ROOT/'raw/20261011_case.txt', ROOT/'raw/online_manual.txt',
                 ROOT/'output/help_review/20261012/help_index.json',
                 OLD/'formal3_observed_curves.json']
    hashes = {str(p.relative_to(ROOT)): nd.sha(p) for p in protected}
    manifest = nd.read(OLD/'manifest.json')
    assert all(nd.sha(OLD/p) == h for p, h in manifest['output_hashes'].items())
    outlook = nd.read(CURRENT/'raw/outlook.json')
    assert (outlook['market'], outlook['phase'], outlook['round']) == (5, 'formal', 3)
    tables = nd.read(CURRENT/'tables.json')
    parameter_rows = tables['outlook']['tables'][-1]
    def value(label):
        rows = [r for r in parameter_rows if r[0] == label]
        assert len(rows) == 1
        return float(rows[0][1].replace('\xa0', '').replace(' ', ''))
    def section_value(section, label):
        begin = next(i for i, r in enumerate(parameter_rows) if r == [section])
        return float(next(r[1] for r in parameter_rows[begin+1:] if r[0] == label).replace('\xa0', '').replace(' ', ''))
    environment = dict(production_co2_kg=2.30, energy_kwh=7.89, water_l=18.56,
                       domestic_transport_co2_g=6.2, export_transport_co2_g=74.5)
    # Check the unique archived connector parameter block, rather than silently copying beam values.
    assert ['每单位碳排放, kg, 泰国', '2.30', '+0%', '2.30'] in parameter_rows
    assert ['每单位能源消耗, kWh, 泰国', '7.89', '+0%', '7.89'] in parameter_rows
    assert ['每单位用水量, l, 泰国', '18.56', '+0%', '18.56'] in parameter_rows
    assert ['泰国 -> 泰国', '6.2', '+0%', '6.2'] in parameter_rows
    assert ['泰国 -> 印尼', '74.5', '+0%', '74.5'] in parameter_rows
    parameters = dict(phase='formal', round=3, market=5, category='ARCHIVED_PUBLISHED_CONDITIONS',
        source=str((CURRENT/'tables.json').relative_to(ROOT)), source_sha256=nd.sha(CURRENT/'tables.json'),
        reference_price_usd=27., initial_demand_phrase_kunits={'泰国':250., '印尼':150.},
        initial_demand_scope='原文每组产品，不能自动当本队需求或行业总量',
        material_cost=section_value('原材料成本', '连接件'),
        transport_costs={c:section_value('运输成本, 连接件', label) for c,label in zip(model.COUNTRIES, ['泰国 -> 泰国','泰国 -> 印尼'])},
        holding_cost_per_unit=value('库存持有成本'), investment_unit_cost=value('机器, 连接件'),
        capacity_decay_pct=section_value('年产能下降，%', '机器'), wage_kusd=section_value('生产工资, 千 美元', '泰国'),
        shift_multipliers=[1.,value('两班倒'),value('三班倒')],
        efficiency_range=[16.,18.], archived_input_efficiency=16.7,
        tender_kunits=350., tender_is_confirmed_order=False, environment_per_unit=environment)
    assert parameters['material_cost'] == 14.2 and parameters['investment_unit_cost'] == 1.1
    assert parameters['capacity_decay_pct'] == 15 and parameters['wage_kusd'] == 30
    registry = nd.read(OLD/'models.json')
    observed = nd.read(OLD/'formal3_observed_curves.json')['curves']['rd/连接件']
    registry['observed_connector_rd'] = dict(round=3, actual_validation=False, **observed)
    registry['joint_allocation']['connector_inventory_valuation'] = 'WEIGHTED_AVERAGE_SCENARIO_ONLY'
    registry['joint_allocation']['connector_lifecycle_path'] = 'request.connector_plan.lifecycle'
    registry['connector_path_version'] = 'CONNECTOR_LIFECYCLE_V2'
    request = nd.read(OLD/'example_request.json')
    baseline = model.predict_joint(request, registry)
    old_prediction = nd.read(OLD/'example_prediction.json')
    assert baseline == {k:v for k,v in old_prediction.items() if k != 'category'}
    life = dict(opening_inventory_book_value_kusd=80., orders_due=[], orders_awarded=[],
        rd_kusd=0., marketing_kusd=0., attributed_operations_kusd=0.,
        investment_kunits=20., investment_unit_cost=parameters['investment_unit_cost'],
        capacity_decay_pct=parameters['capacity_decay_pct'], environment_per_unit=environment)
    plan = dict(allocation_pct=100., opening_inventory_kunits=5.,
        holding_cost_per_unit=parameters['holding_cost_per_unit'], country_priority=list(model.COUNTRIES), lifecycle=life)
    product = dict(capacity=100., efficiency=16.7, material_cost=parameters['material_cost'],
        demand={'泰国':30., '印尼':10.}, prices={'泰国':27., '印尼':27.}, transport_costs=parameters['transport_costs'])
    award = dict(status='CONFIRMED', quantity_kunits=20., price=26., advance_received_kusd=52.)
    due = dict(status='CONFIRMED', quantity_kunits=10., price=25., advance_received_kusd=25.)
    life.update(orders_due=[due], orders_awarded=[award])
    a = project(product, plan, parameters['wage_kusd'], parameters['shift_multipliers'])
    assert a['closing_inventory_kunits'] == 55. and a['orders_delivered_kunits'] == 10.
    assert a['order_cash_movement_kusd'] == 225.+52. and a['closing_contract_liability_kusd'] == 52.
    assert a['next_capacity_kunits'] == 105. and a['investment_expenditure_kusd'] == 22.
    assert abs(a['operating_contribution_kusd']-a['contribution_kusd']-(a['inventory_book_value_kusd']-80.)) < 1e-8
    next_life = dict(life, opening_inventory_book_value_kusd=a['next_state']['opening_inventory_book_value_kusd'],
        orders_due=a['next_state']['orders_due'], orders_awarded=[], investment_kunits=0.)
    next_plan = dict(plan, allocation_pct=0., opening_inventory_kunits=a['closing_inventory_kunits'], lifecycle=next_life)
    b = project(dict(product, capacity=a['next_capacity_kunits']), next_plan, 30., parameters['shift_multipliers'])
    assert b['orders_delivered_kunits'] == 20. and b['closing_inventory_kunits'] == 0.
    assert b['sales_kunits'] == {'泰国':30., '印尼':5.} and b['order_balance_due_kusd'] == 468.
    assert b['production_kunits'] == 0. and b['cost_of_goods_sold_kusd'] == a['inventory_book_value_kusd']
    assert b['environment']['production_co2_kg'] == 0.
    zero = project(dict(product, capacity=0., prices=dict.fromkeys(model.COUNTRIES,0.), demand=dict.fromkeys(model.COUNTRIES,0.)),
        dict(plan, opening_inventory_kunits=0., lifecycle=dict(life, opening_inventory_book_value_kusd=0., orders_due=[], orders_awarded=[], investment_kunits=0.)),
        30., parameters['shift_multipliers'])
    assert zero['operating_contribution_kusd'] == 0.
    bad_plans = [dict(plan, lifecycle=dict(life, orders_due=[dict(due, status='TENDER')])),
                 dict(plan, lifecycle=dict(life, orders_due=[dict(due, quantity_kunits=1000., advance_received_kusd=2500.)])),
                 dict(plan, lifecycle=dict(life, opening_inventory_book_value_kusd=float('nan'))),
                 dict(plan, lifecycle=dict(life, capacity_decay_pct=101.)),
                 dict(plan, lifecycle=dict(life, orders_due=[dict(due, advance_received_kusd=0.)]))]
    for bad in bad_plans:
        try:
            project(product, bad, 30., parameters['shift_multipliers'])
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid connector lifecycle accepted')
    own = [r for r in request['competitors'] if r['product']=='连接件' and r['team_id']==request['team_id']]
    request['connector_plan'] = dict(plan, allocation_pct=80., lifecycle=dict(life,
        rd_kusd=own[0]['rd'], marketing_kusd=sum(r['general']+r['designer'] for r in own)))
    enhanced = model.predict_joint(request, registry)
    assert enhanced['allocation']['model'] == 'JOINT_ALLOCATION_CONNECTOR_LIFECYCLE_V2'
    bounded_request = copy.deepcopy(request)
    for r in bounded_request['competitors']:
        if r['product'] == '连接件':
            r['rd'] = min(r['rd'], observed['x_range'][1])
    bounded_request['connector_plan']['lifecycle']['rd_kusd'] = min(own[0]['rd'], observed['x_range'][1])
    bounded_tied = model.predict_joint(bounded_request, registry)
    sensitivity_request = dict(bounded_request, connector_rd_mode='observed_sensitivity')
    sensitivity = model.predict_joint(sensitivity_request, registry)
    beam_before = [r for r in bounded_tied['demand_predictions'] if r['product']=='复合梁']
    assert beam_before == [r for r in sensitivity['demand_predictions'] if r['product']=='复合梁']
    assert any(x['predicted_share'] != y['predicted_share'] for x,y in zip(bounded_tied['demand_predictions'], sensitivity['demand_predictions']))
    assert enhanced['allocation']['total_workers'] <= request['worker_limit']+1e-8
    scarce_plan = dict(plan,allocation_pct=0.)
    try:
        project(product,scarce_plan,30.,parameters['shift_multipliers'])
    except ValueError:
        pass
    else:
        raise AssertionError('Orders were allowed to lose priority under shortage')
    expensive = project(product,dict(plan,lifecycle=dict(life,rd_kusd=100.,marketing_kusd=20.,attributed_operations_kusd=30.)),30.,parameters['shift_multipliers'])
    assert abs(expensive['operating_contribution_kusd']-(a['operating_contribution_kusd']-150.)) < 1e-8
    assert expensive['next_state']['previous_rd_kusd'] == 100.
    mismatched = copy.deepcopy(request)
    mismatched['connector_plan']['lifecycle']['marketing_kusd'] += 1.
    try:
        model.predict_joint(mismatched, registry)
    except ValueError:
        pass
    else:
        raise AssertionError('Demand and expense mismatch accepted')
    out_of_range = copy.deepcopy(sensitivity_request)
    for r in out_of_range['competitors']:
        if r['product'] == '连接件':
            r['rd'] = 2000.
    try:
        model.predict_joint(out_of_range, registry)
    except ValueError:
        pass
    else:
        raise AssertionError('Out-of-range observed R&D accepted')
    efficiency_sensitivity = {str(e):project(dict(product,efficiency=e),plan,30.,parameters['shift_multipliers']) for e in [16.,16.7,18.]}
    assert efficiency_sensitivity['16.0']['payroll_kusd'] > efficiency_sensitivity['18.0']['payroll_kusd']
    checks = dict(legacy=model.self_check(), frozen_prediction_replay=True,
        inventory_cost_conservation=True, two_round_order_and_inventory_chain=True,
        advances_not_revenue=True, orders_before_retail=True, next_capacity=True,
        zero_activity_supported=True, invalid_state_rejected=True, environment_units=True,
        independent_rd_sensitivity_isolates_beam=True, rd_extrapolation_rejected=True,
        connector_actual_training_rows=0, demand_retrained=False, platform_modified=False)
    assert all(nd.sha(ROOT/p)==h for p,h in hashes.items())
    save('published_parameters.json', parameters)
    save('models.json', registry)
    save('request.json', request)
    save('prediction.json', dict(category='SYNTHETIC_LIFECYCLE_NOT_RECOMMENDATION', **enhanced))
    save('observed_rd_sensitivity.json', dict(category='UNVALIDATED_BEHAVIOR_TRANSFER_SENSITIVITY',
        scenario='连接件对手研发投入超过1600的值仅在本敏感性情景设为1600；两种曲线比较使用相同输入，非原演示回放',
        request=sensitivity_request,tied_prediction=bounded_tied,prediction=sensitivity))
    save('two_round_demo.json',dict(category='SYNTHETIC_STATE_CHAIN',product=product,plan=plan,first=a,next_plan=next_plan,second=b))
    save('efficiency_sensitivity.json',efficiency_sensitivity)
    save('checks.json',checks)
    snapshot = OUT/'code_snapshot'
    snapshot.mkdir(exist_ok=False)
    for name in ['connector_free_production.py','joint_allocation.py','t3v1.py']:
        (snapshot/name).write_bytes((ROOT/'code/model_v2'/name).read_bytes())
    (OUT/'report.md').write_text('''# 连接件模型与影响路径V2验收

基于正式3归档条件升级公共生产路径；旧t3v1冻结预测逐值回放通过，原件与旧交付哈希不变，连接件真实训练样本仍为0。

新增：加权平均库存数量/成本结转；确认订单优先交付、10%预付款、交付时余款及下期合同负债；研发/营销/归属运营费用；投资支出及15%产能下降后的下期产能；生产与零售运输环境影响；独立连接件研发曲线敏感性入口。350千单位招标不自动变成已中标订单。

两期合成自检：第一期100千单位产量加5千单位库存，先交10千单位订单，再交40千单位零售，结余55；下一期零生产，先交20千单位订单，再交35千单位零售，库存清零且成本完整转出。订单当期现金为225余款加52新预收，下期余款468；预收不计收入。增加20千单位投资，100千单位机器产能按15%下降后下期为105千单位。

敏感性演示采用相同且范围内的对手研发输入。16/16.7/18千单位每人效率情景验证效率提高时用工和工资下降；不声称实际效率已达到情景值。自检同时覆盖非法状态、订单不足拒绝、费用扣除、环境单位、共享用工及旧模式兼容。

库存加权平均法、期末数量计持有费、投资下期生效为显式情景，尚未以连接件实际结果验证。输出经营贡献仍不含折旧、税、利息、共享固定费用；资源贡献非完整现金流。行业价格弹性、跨产品替代、学习效应、累计运营与完整六回合最优仍未定量识别。未修改平台。
''',encoding='utf-8')
    hashes['work/verify_connector_model_v2.py'] = nd.sha(ROOT/'work/verify_connector_model_v2.py')
    save('manifest.json',dict(input_hashes=hashes, output_hashes={p.relative_to(OUT).as_posix():nd.sha(p) for p in OUT.rglob('*') if p.is_file() and p.name != 'work_log.md'},
        source_inputs_unchanged=True, validation='RULE_SELF_CHECK_NOT_ACTUAL_CONNECTOR_VALIDATION'))
    print('PASS', OUT)


if __name__ == '__main__':
    run()
