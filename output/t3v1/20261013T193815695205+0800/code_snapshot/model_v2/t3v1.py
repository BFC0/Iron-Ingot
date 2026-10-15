"""t3v1: tied single-product response curves and joint production allocation."""
import argparse
import copy
import json
import math
import shutil
import time
from datetime import datetime
from pathlib import Path
import numpy as np

import t3v0 as base
from joint_allocation import PRODUCTS, COUNTRIES, allocate, self_check as allocation_check

core, nd, ROOT = base.core, base.nd, base.ROOT
SOURCE_VERSION = ROOT/'output/t3v0/20261013T182432038858+0800'


def predict_demand(rows, registry, totals):
    if registry['version'] != 't3v1' or not registry['assumption']['enabled']:
        raise ValueError('Requires t3v1 explicit same-curve assumption')
    if not rows or set(r['product'] for r in rows) != set(PRODUCTS):
        raise ValueError('Both products must have competitor inputs')
    if len({(r['phase'], r['round']) for r in rows}) != 1:
        raise ValueError('One phase/round required')
    phase, round_ = rows[0]['phase'], rows[0]['round']
    if phase != 'formal' or round_ not in (2, 3):
        raise ValueError('Only formal2 replay/formal3 assumed transfer supported')
    for r in rows:
        if r['country'] not in COUNTRIES:
            raise ValueError('Unknown country')
        for key in ('price', 'initial_price', 'general', 'designer', 'rd', 'previous_rd'):
            v = r[key]
            if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or (key in ('price', 'initial_price') and v == 0):
                raise ValueError('Invalid demand input: '+key)
    params = registry['response_curves'][str(round_)]['rd']['parameters']
    predictions = []
    for product in PRODUCTS:
        for country in COUNTRIES:
            pool = [r for r in rows if r['product'] == product and r['country'] == country]
            if not pool:
                raise ValueError('Both countries required per product')
            keys = [(r['market_id'], r['team_id']) for r in pool]
            if len(set(keys)) != len(keys):
                raise ValueError('Duplicate product/country competitor key')
            if any(len(ids) != registry['competition_team_count'] for ids in core.old.groups(pool).values()):
                raise ValueError('Incomplete competitor group')
            m = registry['demand']['COUNTRY/'+country]
            shares = core.predict(pool, core.features(pool, params, m['rho'], m['piecewise']), m['beta'])
            for r, share in zip(pool, shares):
                total = totals[str(r['market_id'])][product][country]
                if not isinstance(total, (int, float)) or not math.isfinite(total) or total < 0:
                    raise ValueError('Invalid external product market total')
                predictions.append(dict(market_id=r['market_id'], team_id=r['team_id'], product=product,
                    country=country, predicted_share=float(share), demand_kunits=float(share*total),
                    basis='ASSUMED_PRODUCT_TRANSFER' if product == '连接件' or round_ == 3 else 'FORMAL2_CONDITIONAL_REPLAY'))
    return predictions


def predict_joint(request, registry):
    predictions = predict_demand(request['competitors'], registry, request['market_totals_kunits'])
    products = copy.deepcopy(request['production'])
    for product in PRODUCTS:
        own = [r for r in predictions if r['market_id'] == request['market_id'] and r['team_id'] == request['team_id'] and r['product'] == product]
        if len(own) != 2:
            raise ValueError('Target team missing from competitor inputs')
        products[product]['demand'] = {r['country']: r['demand_kunits'] for r in own}
        target = [r for r in request['competitors'] if r['market_id'] == request['market_id'] and r['team_id'] == request['team_id'] and r['product'] == product]
        prices = {r['country']: r['price'] for r in target}
        if products[product]['prices'] != prices:
            raise ValueError('Allocation prices differ from demand prediction inputs')
    return dict(version='t3v1', demand_predictions=predictions,
                allocation=allocate(products, request['worker_limit'], request['wage_kusd'], request['shift_multipliers']))


def self_check():
    params = [.1, .2, .5, .2]
    rows = [dict(market_id=1, phase='formal', round=3, team_id=str(t), country=c, product=p,
                 price=27.+t, initial_price=27., general=100.*t, designer=50.*t, rd=80.*t, previous_rd=0.)
            for p in PRODUCTS for c in COUNTRIES for t in range(3)]
    m = dict(beta=[2., 1., .3, .2, .4], rho=.5, piecewise=False)
    reg = dict(version='t3v1', assumption={'enabled': True}, competition_team_count=3,
               response_curves={'3': {'rd': {'parameters': params}}},
               demand={'COUNTRY/'+c: m for c in COUNTRIES})
    totals = {'1': {p: {c: 100. for c in COUNTRIES} for p in PRODUCTS}}
    pred = predict_demand(rows, reg, totals)
    for country in COUNTRIES:
        a = [r['predicted_share'] for r in pred if r['product'] == PRODUCTS[0] and r['country'] == country]
        b = [r['predicted_share'] for r in pred if r['product'] == PRODUCTS[1] and r['country'] == country]
        assert a == b and abs(sum(a)-1) < 1e-12
    changed = [dict(r, price=100.) if r['product'] == PRODUCTS[1] and r['team_id'] == '0' else r for r in rows]
    altered = predict_demand(changed, reg, totals)
    assert pred[:6] == altered[:6]
    for bad in (rows[:-1], rows+[rows[0]], [dict(r, round=4) for r in rows], [dict(r, price=float('nan')) for r in rows]):
        try:
            predict_demand(bad, reg, totals)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid prediction inputs accepted')
    p = dict(capacity=9., efficiency=1., material_cost=1., prices={'泰国': 27., '印尼': 27.},
             transport_costs={'泰国': 0., '印尼': 1.})
    req = dict(competitors=rows, market_totals_kunits=totals, market_id=1, team_id='0',
               production={name: copy.deepcopy(p) for name in PRODUCTS}, worker_limit=4.,
               wage_kusd=1., shift_multipliers=[1., 1.65, 2.56])
    assert predict_joint(req, reg)['allocation']['total_workers'] <= 4.+1e-9
    return dict(equal_inputs_equal_product_response=True, product_groups_isolated=True,
                guards=True, demand_to_joint_allocation=True, allocation=allocation_check())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--predict', type=Path, help='Complete scenario request JSON')
    parser.add_argument('--registry', type=Path, help='Trained t3v1 models.json')
    args = parser.parse_args()
    checks = self_check()
    if args.self_check:
        print(json.dumps(checks, ensure_ascii=False)); return
    if bool(args.predict) != bool(args.registry):
        parser.error('--predict and --registry must be supplied together')
    out = ROOT/'output/t3v1'/datetime.now(nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
    out.mkdir(parents=True, exist_ok=False)
    print('OUTPUT', out, flush=True)
    if args.predict:
        request, registry = nd.read(args.predict), nd.read(args.registry)
        nd.save(out/'prediction.json', predict_joint(request, registry))
        nd.save(out/'prediction_inputs.json', request)
        nd.save(out/'manifest.json', dict(version='t3v1', mode='scenario_prediction',
            input_hashes={str(p.resolve()): nd.sha(p) for p in (args.predict, args.registry)},
            output_hashes={p.name: nd.sha(p) for p in out.iterdir() if p.is_file()}))
        print('COMPLETE', out, flush=True); return
    start = time.perf_counter()
    bundle = nd.input_bundle(base.AUDIT)
    paths = [base.CURVE2, base.OUTLOOK2, base.CURRENT/'charts.json', base.CURRENT/'raw/outlook.json',
             base.CURRENT/'raw/productionplanning.json', base.CURRENT/'raw/productioninvestments.json',
             SOURCE_VERSION/'manifest.json', SOURCE_VERSION/'models.json']
    for p in paths:
        bundle['files'][str(p)] = nd.sha(p)
    source = nd.read(base.CURRENT/'raw/outlook.json')
    assert (source['market'], source['phase'], source['round']) == (5, 'formal', 3)
    paragraph = next(s for s in source['text'].splitlines() if '每组产品' in s and '产品组合' in s)
    assumption = dict(id='SAME_SINGLE_PRODUCT_CURVES', enabled=True,
        statement='现假设连接件的单产品曲线与复合梁相同。',
        source_phrase=['每组产品', '产品组合'], source_excerpt=paragraph,
        source=str((base.CURRENT/'raw/outlook.json').relative_to(ROOT)), source_sha256=nd.sha(base.CURRENT/'raw/outlook.json'),
        classification='USER_AUTHORIZED_MODEL_ASSUMPTION_NOT_OFFICIAL_EQUALITY_PROOF',
        scope='归一化价格/营销/研发响应共用复合梁系数与同回合曲线；不等同原始售价、成本、效率基底、市场规模或跨产品需求替代',
        cross_round_transfer='正式2行为系数用于正式3亦属未验证迁移；正式3使用其当期复合梁研发曲线',
        connector_actual_training_rows=0)
    curve = nd.read(base.CURVE2)
    assert curve['round'] == 2 and nd.sha(ROOT/curve['source']) == curve['source_sha256']
    bundle['files'][str(ROOT/curve['source'])] = curve['source_sha256']
    actual = base.Actuals(nd.read(base.AUDIT/'rows.json'))
    rows, pairs = base.dataset(actual)
    extra = base.curve3(out)
    extra['version'] = 't3v1'
    nd.save(out/'formal3_observed_curves.json', extra)
    # Preserve observed unequal product charts separately; the model uses the authorized tie.
    tied3 = {'rd': copy.deepcopy(extra['curves']['rd/复合梁']), 'operations': copy.deepcopy(extra['curves']['operations/泰国'])}
    response = {'2': curve['curves'], '3': tied3}
    nd.save(out/'response_curves.json', dict(version='t3v1', product_mapping={p: '复合梁' for p in PRODUCTS}, curves=response, assumption=assumption))
    (out/'formal3_curves.json').unlink()
    nd.save(out/'assumption.json', assumption)
    nd.save(out/'dataset.json', dict(rows=rows, state_pairs=pairs, connector_actual_rows=0, synthetic_training_rows=0))
    engine = base.DemandFit(rows, curve['curves']['rd']['parameters'])
    models = {}
    for name, ids in [('SHARE', list(range(len(rows)))), *[('COUNTRY/'+c, [i for i,r in enumerate(rows) if r['country']==c]) for c in COUNTRIES]]:
        print('TRAIN', name, flush=True)
        models[name] = engine.select(ids, name.startswith('COUNTRY'))
        models[name]['nested_validation'] = engine.nested(ids, name.startswith('COUNTRY'))
    models['ABS'] = base.absolute_fit(rows, curve['curves']['rd']['parameters'])
    mech = base.mechanisms(actual, rows, pairs, curve['curves'], base.published())
    registry = dict(version='t3v1', training_phase='formal', training_round=2,
        training_actual_rows=200, connector_actual_rows=0, assumption=assumption,
        competition_team_count=10, demand=models, mechanisms=mech, response_curves=response,
        product_parameter_mapping={p: 'SHARED_BEAM_ESTIMATE' for p in PRODUCTS},
        efficiency_scope='材料/利率/效率基底仅复合梁正式2训练；连接件必须提供独立效率和当期成本',
        joint_allocation=dict(model='JOINT_ALLOCATION_V1', status='RULE_AND_LINEAR_OPTIMIZATION_NOT_SUPERVISED_TRAINING',
            dedicated_product_capacity=True, objective='one_round_variable_contribution', actual_validation=False),
        inherited_components=dict(path=str(SOURCE_VERSION.relative_to(ROOT)),
            scope='其余t3v0规则/附加研究保持原状态；本次不重训、不宣布通过'),
        deployment_enabled=False)
    nd.save(out/'models.json', registry)
    base_models = nd.read(SOURCE_VERSION/'models.json')
    checks['same_estimator_replay_max_beta_difference'] = max(float(np.max(np.abs(np.array(m['beta'])-base_models['demand'][name]['beta']))) for name,m in models.items())
    checks.update(actual_training_rows=200, connector_actual_rows=0, synthetic_training_rows=0,
                  formal3_not_used_as_actual_labels=True, joint_actual_validation=False)
    assert checks['same_estimator_replay_max_beta_difference'] < 1e-8
    scenario_rows = []
    for product in PRODUCTS:
        for r in rows:
            if r['market_id'] != 5:
                continue
            item = {k: r[k] for k in ('market_id','phase','team_id','country','price','initial_price','general','designer','rd','previous_rd')}
            item.update(round=3, product=product)
            if product == '连接件':
                item.update(price=27*r['price']/r['initial_price'], initial_price=27., previous_rd=0.)
            scenario_rows.append(item)
    target = scenario_rows[0]['team_id']
    production = {}
    for product, capacity, efficiency, material, transport in [('复合梁',21.5,.17,1053.,[30.,120.]), ('连接件',80.,17.,14.2,[.5,2.])]:
        production[product] = dict(capacity=capacity, efficiency=efficiency, material_cost=material,
            prices={r['country']:r['price'] for r in scenario_rows if r['product']==product and r['team_id']==target},
            transport_costs=dict(zip(COUNTRIES,transport)))
    request = dict(category='SYNTHETIC_DEMONSTRATION_NOT_CURRENT_RECOMMENDATION',
        assumptions='对手复用正式2决策；连接件价格按27美元归一化；连接件80千单位产能为假定；复合梁市场总量使用正式2实际；250/150千单位解释为每市场连接件行业需求亦为情景假设',
        competitors=scenario_rows, market_id=5, team_id=target,
        market_totals_kunits={'5':{'复合梁':{c:sum(r['demand'] for r in rows if r['market_id']==5 and r['country']==c) for c in COUNTRIES},
                                 '连接件':dict(zip(COUNTRIES,[250.,150.]))}},
        production=production, worker_limit=100., wage_kusd=30., shift_multipliers=[1.,1.65,2.56])
    nd.save(out/'example_request.json', request)
    nd.save(out/'example_prediction.json', dict(category=request['category'], **predict_joint(request,registry)))
    checks['example_prediction_replay'] = predict_joint(nd.read(out/'example_request.json'), nd.read(out/'models.json')) == {k:v for k,v in nd.read(out/'example_prediction.json').items() if k!='category'}
    checks['nested_market_disjoint'] = all(not set(f['held_markets']) & {k[0] for k in f['training_keys']} for name,m in models.items() if name!='ABS' for f in m['nested_validation']['folds'])
    assert checks['example_prediction_replay'] and checks['nested_market_disjoint']
    snapshot = out/'code_snapshot'
    for p in [*(ROOT/'code').glob('*.py'), *(ROOT/'code/model_v2').glob('*.py')]:
        dest = snapshot/p.relative_to(ROOT/'code')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p,dest)
        bundle['files'][str(p)] = nd.sha(p)
    nd.assert_unchanged(bundle)
    checks['input_hashes_unchanged'] = True
    nd.save(out/'checks.json', checks)
    nd.save(out/'performance.json', dict(elapsed_seconds=time.perf_counter()-start, solver_calls=engine.calls, feature_builds=len(engine.cache)))
    lines = ['# t3v1 · 同曲线假设与联合分配', '', assumption['statement'],
        '来源：正式3市场前景的“产品组合”“每组产品”。这是用户指定的建模假设，原文不直接证明曲线相同。',
        '', '> '+paragraph, '',
        '200条正式2复合梁实际、100组状态配对重新训练；连接件共用估计参数，新增真实/合成训练标签均为0。正式3同回合复合梁曲线用于两产品；连接件原始图线另存，未覆盖。',
        '相同输入产生相同单产品响应；价格按各产品基准归一化。产品/国家独立竞争组，禁止把两产品的玩家放进同一个softmax。正式2系数迁移到正式3尚未实际验证。',
        '', '| 模型 | 嵌套整市场MAE，百分点 |', '|---|---:|']
    lines += [f"| {name} | {m['nested_validation']['mae_pp']:.6f} |" for name,m in models.items() if name!='ABS']
    lines += ['', '上述误差仅针对复合梁正式2条件验证。连接件与联合分配均无独立实际成绩。',
        '重训参数与t3v0最大差值：'+str(checks['same_estimator_replay_max_beta_difference'])+'；相同真实样本和同曲线约束下系数不变是预期结果。',
        '', '联合分配：先按产品、国家预测份额，乘外部行业规模得到需求。再在线性规划中求各产品三个班次产量及两国交付，限制各自机器产能和给定共享用工。目标为当期收入减材料、班次工资及运输。负贡献可停产。',
        '填写产能比例=本产品产量/本产品产能；数量占比=本产品产量/两产品总产量；用工占比=本产品用工/总用工。两项产能比例各自0–100%，不要求合计100%。无产量时数量占比置0，无产能时产能比例置0。',
        '效率基底、价格、市场规模及成本单独输入；不能用复合梁效率或材料成本替代连接件。正式3归档连接件机器产能为0，因此在该产能下连接件产量必为0；演示的80千单位是合成场景。',
        '模型没有从历史“最佳分配比例”标签监督训练；联合分配为训练后需求预测驱动的约束计算模型。输出贡献不等于净利润或六回合最优。',
        '', '[完整参数](models.json) · [假设与源哈希](assumption.json) · [示例输入](example_request.json) · [示例结果](example_prediction.json) · [核验](checks.json)',
        '示例全部标记为合成演示；其中对手、产能和市场规模假设不能当作当前本人推荐。',
        '', '未包含库存、订单、裁员、投资选择、研发/运营/固定费用、利息、税及跨期收益；其他t3v0组件沿用原门槛状态。',
        '复现：`python code/model_v2/t3v1.py`；自检：`python code/model_v2/t3v1.py --self-check`；情景：`python code/model_v2/t3v1.py --registry <models.json> --predict <request.json>`。',
        '旧原件、t3v0模型不改写；未操作或提交平台。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'work_log.md').write_text('# t3v1 工作日志\n正式3原文核验→显式同曲线假设→真实复合梁重训→双产品隔离预测→联合分配→自检/留出/哈希及演示回放。\n',encoding='utf-8')
    nd.save(out/'manifest.json', dict(version='t3v1', status='COMPLETE_RESEARCH_WITH_EXPLICIT_GAPS',
        input_hashes=bundle['files'], output_hashes={p.relative_to(out).as_posix():nd.sha(p) for p in out.rglob('*') if p.is_file()},
        training_actual_rows=200, connector_actual_rows=0, protected_inputs_unchanged=True, automatic_deployment=False))
    print('COMPLETE', out, flush=True)


if __name__ == '__main__':
    main()
