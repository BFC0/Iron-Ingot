"""Check frozen coefficients, formal5 scenarios and rejection boundaries without fitting."""
import copy
import sys
from pathlib import Path
import t5v0a as t


def verify(out):
    app = t.app
    model = app.read(out/'models_full.json')
    base = app.read(t.BASE/'models_full.json')
    checks = {}
    for path, digest in model['source_sha256'].items():
        assert app.sha(t.ROOT/path) == digest, path
    checks['sources_unchanged'] = len(model['source_sha256'])
    for key in ('materials', 'labor', 'demand', 'efficiency', 'interest', 'curves'):
        assert model[key] == base[key], key
    risk = copy.deepcopy(model['risk'])
    assert risk['solvency_exponential'].pop('ranges') == base['risk']['solvency_exponential']['training_ranges']
    assert risk == base['risk']
    assert model['application_curves'] == app.read(t.CURVES/'formal5_curves.json')
    assert model['training_round'] == 4 and model['application_round'] == 5
    assert len(model['model_inventory']) == len(model['application_actions']) == 29
    for name, item in model['model_inventory'].items():
        assert item['status'] == base['model_inventory'][name]['status']
        assert (out/item['artifact']).is_file(), name
    checks['all_frozen_parameters_and_29_historical_statuses_preserved'] = True
    p = model['application_parameters']
    for key, value in {'wage':43.5, 'base_rate':.05, 'short_spread':.035,
        'administration':10000., 'material/复合梁':690., 'material/连接件':9.3,
        'machine/复合梁':78., 'machine/连接件':1.1, 'minimum_cash':2000.}.items():
        assert app.math.isclose(p[key]['value'], value, abs_tol=1e-14), key
    assert model['opening_inventory_kunits'] == {'复合梁':0., '连接件':202.4}
    assert model['construction_market_growth'] == {'泰国':.07, '印尼':-.05}
    request = dict(version='t5v0a', market_id=5, phase='formal', round=5)
    rejected = 0
    def rejects(fn):
        nonlocal rejected
        try: fn()
        except (ValueError, KeyError): rejected += 1
        else: raise AssertionError('Invalid input accepted')
    with app.no_training():
        empty = t.apply_request(model, request)
        assert empty['demand']['value'] is None and empty['market_totals']['value'] is None
        assert empty['administration']['cash_delta_kusd'] is None
        assert empty['horizon']['remaining_profit'] is None and empty['horizon']['remaining_rounds'] == 2
        assert not empty['new_tender_available'] and not empty['full_profit_available']
        for r in (3, 4, 6): rejects(lambda: t.apply_request(model, dict(request, round=r)))
        rejects(lambda: t.apply_request(model, dict(request, version='t5v0')))
        rejects(lambda: t.apply_request(model, dict(request, competitors=[])))
        rejects(lambda: t.apply_request(base, request))
        for product in t.PRODUCTS:
            costs = t.material_scenarios(model, product, 10.)
            for form, cost in costs.items():
                parameter = base['materials'][product]['models'][form]['parameter']
                price = p['material/'+product]['value']
                expected = price*(1+parameter) if form == 'proportional' else price+parameter
                assert app.math.isclose(cost['material_cost_kusd'], expected*10, abs_tol=1e-10)
            assert costs['additive']['unit_cost_usd'] != costs['proportional']['unit_cost_usd']
            assert all(v['material_cost_kusd'] == 0 for v in t.material_scenarios(model, product, 0).values())
            for q in (-1, True, float('nan')):
                rejects(lambda: t.material_scenarios(model, product, q))
        for key, c in model['application_curves']['curves'].items():
            ctx = dict(market_id=5, area='PYT', phase='formal', round=5,
                previous_input=c['upstream_condition']['previous_formal4_actual_input']['value'],
                unit='千美元', coordinate_kind='effective_investment_scenario')
            for x in (0, c['x_range'][1]):
                assert t.curve_at(model, key, ctx, x)['multiplier'] > 0
            for context, x in ((dict(ctx, round=4),0), (dict(ctx,previous_input=-1),0),
                               (dict(ctx,unit='美元'),0), (ctx,c['x_range'][1]+1), (ctx,True)):
                rejects(lambda: t.curve_at(model, key, context, x))
        for q in (0,10-1e-7,10+1e-7,20-1e-7,20+1e-7,30):
            plan = dict(capacity_kunits=30., production_kunits=q, previous_workers=200.)
            old = app.labor_cost(model, plan, .2, 33.)
            new = app.labor_cost(model, plan, .2)
            for field in ('payroll','firing'):
                assert app.math.isclose(new[field],old[field]*43.5/33.,abs_tol=1e-8)
        state = dict(equity=50., assets=100., long_debt=40., short_debt=10.)
        rate = app.rate_scenario(model, state)
        assert app.math.isclose(rate['short_rate']-rate['long_rate'], .035, abs_tol=1e-14)
        rejects(lambda: app.rate_scenario(model, state, 'leverage_power'))
        rejects(lambda: app.rate_scenario(model, dict(state,equity=0)))
        growth = {pr:{'泰国': .07, '印尼':-.05} for pr in t.PRODUCTS}
        totals = t.apply_request(model, dict(request, product_growth=growth))['market_totals']
        assert app.math.isclose(totals['totals_kunits']['复合梁']['印尼'],
            .95*model['formal4_market_totals_kunits']['复合梁']['印尼'])
        bad_growth = copy.deepcopy(growth); bad_growth['连接件']['印尼'] = -1.01
        rejects(lambda: t.apply_request(model, dict(request,product_growth=bad_growth)))
        item = dict(product=dict(capacity=412.25, efficiency=10.,
            demand={'泰国':100.,'印尼':150.}, prices={'泰国':27.,'印尼':27.}),
            allocation_pct=0., country_priority=['泰国','印尼'], material_form='published',
            scope='BEFORE_UNVERIFIED_ORDERS')
        inventory = t.apply_request(model, dict(request,connector=item))['connector']
        assert inventory['production_kunits'] == 0
        assert inventory['sales_kunits'] == {'泰国':100.,'印尼':102.4}
        assert inventory['closing_inventory_kunits'] == 0
        reverse = dict(item, country_priority=['印尼','泰国'])
        other = t.apply_request(model, dict(request,connector=reverse))['connector']
        assert other['sales_kunits']['印尼'] == 150.
        for allocation in (-1,101,True):
            rejects(lambda: t.apply_request(model, dict(request,connector=dict(item,allocation_pct=allocation))))
        rejects(lambda: t.apply_request(model, dict(request,connector=dict(item,lifecycle={}))))
        assert t.apply_request(model, request) == app.read(out/'example_result.json')
    try:
        with app.no_training():
            def fit(): pass
            fit()
    except RuntimeError: pass
    else: raise AssertionError('Training guard failed')
    checks.update(published_parameters=True, material_three_scenarios=True,
        formal5_curve_boundaries=True, wage_shift_and_severance_scaling=True,
        risk_spreads_separate=True, inventory_sold_without_new_production=True,
        country_growth_explicit_only=True, unknown_cash_and_horizon_not_zero=True,
        rejected_invalid_requests=rejected, training_guard=True, training_performed=False)
    return dict(status='PASS', version='t5v0a', checks=checks)


if __name__ == '__main__':
    out = Path(sys.argv[1])
    result = verify(out)
    t.app.save(out/'acceptance.json', result)
    print(t.app.json.dumps(result, ensure_ascii=False, indent=2))
