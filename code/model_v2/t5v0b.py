"""Formal5 country demand ratios and stable published machine prices; no retraining."""
import argparse
import copy
import os
from pathlib import Path

import t5v0a as prior

app = prior.app
ROOT = prior.ROOT
BASE = ROOT/'output/t5v0a/20261015T131507850861+0800'
GROWTH = {'泰国': .07, '印尼': -.05}
PRODUCTS, COUNTRIES = prior.PRODUCTS, prior.COUNTRIES


def apply_request(registry, request):
    if (registry.get('version'), registry.get('base_version'), registry.get('training_round'),
            registry.get('application_round')) != ('t5v0b', 't5v0a', 4, 5):
        raise ValueError('需要t5v0b注册表，训练正式4、应用正式5')
    if (request.get('version'), request.get('market_id'), request.get('phase'), request.get('round')) != ('t5v0b', 5, 'formal', 5):
        raise ValueError('需要t5v0b／市场5／正式5请求')
    expected = {p:dict(GROWTH) for p in PRODUCTS}
    if 'product_growth' in request and request['product_growth'] != expected:
        raise ValueError('t5v0b固定使用用户假设：两产品泰国+7%、印尼-5%')
    converted = copy.deepcopy(request)
    investments = converted.pop('investments_kunits', None)
    demand_basis = converted.pop('demand_basis', None)
    if demand_basis not in (None, 'FORMAL4_OWN_SHARE_HELD'):
        raise ValueError('只支持显式正式4本组份额保持情景')
    own_demand = None
    if demand_basis:
        own_demand = {p:{c:registry['formal4_own_demand_kunits'][p][c]*(1+GROWTH[c])
                        for c in COUNTRIES} for p in PRODUCTS}
        if 'connector' in converted:
            product = converted['connector']['product']
            if 'demand' in product and product['demand'] != own_demand['连接件']:
                raise ValueError('连接件需求与本次份额保持情景不一致')
            product['demand'] = own_demand['连接件']
    converted.update(version='t5v0a', product_growth=expected)
    # Reuse the frozen application paths; this adapter does not alter their source version.
    compatible = dict(registry, version='t5v0a', base_version='t5v0')
    result = prior.apply_request(compatible, converted)
    result.update(version='t5v0b', assumptions=registry['application_assumptions'])
    result['market_totals'].update(status='USER_ASSUMPTION_COUNTRY_DEMAND_RATIO',
        mapping_empirically_verified=False)
    totals = result['market_totals']['totals_kunits']
    result['equal_share_baseline_kunits'] = {p:{c:totals[p][c]/registry['competition_team_count']
                                               for c in COUNTRIES} for p in PRODUCTS}
    if own_demand is not None:
        result['demand'] = dict(status='FORMAL4_OWN_SHARE_HELD_SCENARIO',
            demand_kunits=own_demand, demand_basis=demand_basis,
            competitive_response_verified=False,
            scope='额外假设本组各国各产品份额保持；非SHARE/COUNTRY/ABS重新预测，销量仍受供给和订单约束')
    result['machines'] = dict(status='FORMAL5_STABLE_PUBLISHED_UNIT_PRICES',
        unit_prices_usd={p:registry['application_parameters']['machine/'+p]['value'] for p in PRODUCTS},
        future_round6_unit_prices=None, investment_purchase_amount_kusd=None,
        cash_payment_kusd=None, incremental_capacity_kunits=None,
        scope='趋稳按正式5公布固定价解释；不改回正式4旧价，不再自动叠加上涨趋势。金额不代表付款时点或生效产能')
    if investments is not None:
        if set(investments) != set(PRODUCTS):
            raise ValueError('投资数量须包含两产品，千单位；未投资请显式填0')
        amounts = {p:app.number(investments[p])*result['machines']['unit_prices_usd'][p]
                   for p in PRODUCTS}
        if not all(app.math.isfinite(v) for v in amounts.values()):
            raise ValueError('投资金额溢出')
        result['machines'].update(investment_quantity_kunits=copy.deepcopy(investments),
            investment_purchase_amount_kusd=amounts, total_purchase_amount_kusd=sum(amounts.values()))
    result['investment_timing'] = app.missing('机器单价和采购金额可计算；产能生效、支付时点及正式6参数仍未知')
    return result


def build_bundle(out):
    out = Path(out)
    if not (out/'work_log.md').is_file() or (out/'models_full.json').exists():
        raise FileExistsError('需独立工作日志，拒绝覆盖已有模型')
    registry = app.read(BASE/'models_full.json')
    assert registry['version'] == 't5v0a'
    sources = dict(registry['source_sha256'])
    sources[(BASE/'models_full.json').relative_to(ROOT).as_posix()] = app.sha(BASE/'models_full.json')
    for path, digest in sources.items():
        assert app.sha(ROOT/path) == digest, path
    dataset_path = prior.BASE/'dataset.json'
    data = app.read(dataset_path)
    sources[dataset_path.relative_to(ROOT).as_posix()] = app.sha(dataset_path)
    own = data['own_final_decision_rows']
    assert len(own) == 4 and len({(r['product'],r['country']) for r in own}) == 4
    for row in own:
        ref = row['sources']['demand']
        assert ref['category'] == 'actual_result' and ref['round'] == 4
        assert app.sha(ROOT/ref['source']) == ref['sha256']
        assert ref['value'] == row['demand']
        sources[ref['source']] = ref['sha256']
    teams = {r['team_id'] for r in data['state_pairs'] if r['market_id'] == 5}
    assert len(teams) == 10
    registry.update(version='t5v0b', base_version='t5v0a', root_training_version='t5v0',
        product_growth_mapping_enabled=True, product_growth_mapping_verified=False,
        application_assumptions=dict(country_growth_is_product_demand_growth=True,
            country_growth=GROWTH, basis='USER_ASSUMPTION_2026_10_15',
            formal5_machine_prices_stable=True, formal6_machine_prices_known=False),
        formal4_own_demand_kunits={p:{c:next(r['demand'] for r in own
            if (r['product'],r['country']) == (p,c)) for c in COUNTRIES} for p in PRODUCTS},
        competition_team_count=len(teams), source_sha256=sources,
        status='FORMAL5_USER_ASSUMPTION_APPLICATION_NO_RETRAIN')
    impacts = {
        'TOTAL':'正式4两国两产品总量分别乘1.07/0.95',
        'BASELINE':'按相同总量重算十队等份额基线；非本组预测',
        'GROWTH':'两产品按国别固定需求变化率；公司份额变化仍需额外信息',
        'SHARE':'市场总量已接通；缺竞争输入，份额响应不重训，支持显式本组历史份额保持情景',
        'COUNTRY':'国别外生需求分别更新；缺竞争输入，国别响应系数不变',
        'ABS':'保留独立绝对需求诊断，不与总量再次相乘以免双计；缺数据仍暂停',
        'CAPACITY':'正式5机器固定价78/1.10计算采购金额，不推断生效产能',
        'FINANCE':'投资金额改用稳定公布价，支付时点、融资和完整现金链未解',
        'HORIZON':'仅正式5-6；没有把一次正式5增速重复施加正式6，也未固定正式6机器价',
        'CONNECTOR':'订单前数量场景可接入显式份额保持需求，库存和当期成本一致重算',
        'CONNECTOR_V2':'正式5库存数量/成本可沿用，但历史合同及库存计价仍缺数据跳过',
        'JOINT_ALLOCATION':'需求总量条件已更新；缺完整需求响应及生命周期，联合完整优化继续跳过',
    }
    for name, item in registry['model_inventory'].items():
        source = (BASE/item['artifact']).resolve()
        assert source.is_file()
        item['artifact'] = Path(os.path.relpath(source,out)).as_posix()
        registry['application_actions'][name].update(
            t5v0b_impact=impacts.get(name,'不由这两项假设直接改变；沿用t5v0a冻结参数、正式5输入与限制'),
            retrained=False, full_forward_validation=False)
    app.save(out/'models_full.json',registry)
    app.save(out/'model_adjustments.json',registry['application_actions'])
    app.save(out/'example_request.json',dict(version='t5v0b',market_id=5,phase='formal',round=5))
    return registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True,type=Path)
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--request',type=Path)
    args = parser.parse_args()
    with app.no_training():
        registry = build_bundle(args.bundle) if args.build else app.read(args.bundle/'models_full.json')
        result = apply_request(registry,app.read(args.request or args.bundle/'example_request.json'))
        if args.build: app.save(args.bundle/'example_result.json',result)
    print(app.json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
