"""No-fit checks for country demand transmission and stable machine costing."""
import copy
import sys
from pathlib import Path

import t5v0b as t
from verify_t5v0a import verify as verify_prior


def verify(out):
    app = t.app
    registry = app.read(out/'models_full.json')
    old = app.read(t.BASE/'models_full.json')
    assert verify_prior(t.BASE)['status'] == 'PASS'
    for key in ('curves','application_curves','risk','materials','labor','demand','efficiency',
                'interest','application_parameters','formal4_market_totals_kunits'):
        assert registry[key] == old[key],key
    for path,digest in registry['source_sha256'].items():
        assert app.sha(t.ROOT/path) == digest,path
    assert len(registry['application_actions']) == len(registry['model_inventory']) == 29
    for name,item in registry['model_inventory'].items():
        assert item['status'] == old['model_inventory'][name]['status']
        assert (out/item['artifact']).is_file()
        assert registry['application_actions'][name]['t5v0b_impact']
    request = dict(version='t5v0b',market_id=5,phase='formal',round=5)
    rejects = 0
    def reject(fn):
        nonlocal rejects
        try: fn()
        except (ValueError,KeyError): rejects += 1
        else: raise AssertionError('Invalid input accepted')
    with app.no_training():
        result = t.apply_request(registry,request)
        assert result == app.read(out/'example_result.json')
        totals = result['market_totals']['totals_kunits']
        for p in t.PRODUCTS:
            for c in t.COUNTRIES:
                assert app.math.isclose(totals[p][c],old['formal4_market_totals_kunits'][p][c]*(1+t.GROWTH[c]),abs_tol=1e-10)
                assert app.math.isclose(result['equal_share_baseline_kunits'][p][c]*10,totals[p][c],abs_tol=1e-10)
        assert result['demand']['value'] is None
        assert result['machines']['unit_prices_usd'] == {'复合梁':78.,'连接件':1.1}
        assert result['machines']['future_round6_unit_prices'] is None
        assert result['machines']['cash_payment_kusd'] is None
        assert result['machines']['incremental_capacity_kunits'] is None
        assert result['horizon']['remaining_rounds'] == 2 and result['horizon']['remaining_profit'] is None
        plans = dict(复合梁=10.,连接件=100.)
        capex = t.apply_request(registry,dict(request,investments_kunits=plans))['machines']
        for p,amount in {'复合梁':780.,'连接件':110.}.items():
            assert app.math.isclose(capex['investment_purchase_amount_kusd'][p],amount,abs_tol=1e-10)
        assert app.math.isclose(capex['total_purchase_amount_kusd'],890.)
        zero = t.apply_request(registry,dict(request,investments_kunits=dict.fromkeys(t.PRODUCTS,0)))
        assert zero['machines']['total_purchase_amount_kusd'] == 0
        for invalid in (-1,True,float('nan'),float('inf')):
            reject(lambda: t.apply_request(registry,dict(request,investments_kunits=dict(plans,复合梁=invalid))))
        reject(lambda: t.apply_request(registry,dict(request,investments_kunits={'复合梁':1})))
        reject(lambda: t.apply_request(registry,dict(request,product_growth={})))
        reject(lambda: t.apply_request(registry,dict(request,demand_basis='FORECAST_VERIFIED')))
        for key,value in [('version','t5v0a'),('round',6),('market_id',1)]:
            reject(lambda: t.apply_request(registry,dict(request,**{key:value})))
        reject(lambda: t.apply_request(old,request))
        held = t.apply_request(registry,dict(request,demand_basis='FORMAL4_OWN_SHARE_HELD'))
        for p in t.PRODUCTS:
            for c in t.COUNTRIES:
                assert app.math.isclose(held['demand']['demand_kunits'][p][c],
                    registry['formal4_own_demand_kunits'][p][c]*(1+t.GROWTH[c]),abs_tol=1e-12)
        item = dict(product=dict(capacity=412.25,efficiency=10.,prices={'泰国':27.,'印尼':27.}),
            allocation_pct=0,country_priority=['泰国','印尼'],material_form='published',scope='BEFORE_UNVERIFIED_ORDERS')
        combined = t.apply_request(registry,dict(request,demand_basis='FORMAL4_OWN_SHARE_HELD',connector=item))
        flow = combined['connector']
        assert app.math.isclose(sum(flow['sales_kunits'].values())+flow['closing_inventory_kunits'],202.4,abs_tol=1e-10)
        assert all(flow['sales_kunits'][c] <= held['demand']['demand_kunits']['连接件'][c] for c in t.COUNTRIES)
        wrong = copy.deepcopy(item); wrong['product']['demand'] = dict.fromkeys(t.COUNTRIES,0.)
        reject(lambda: t.apply_request(registry,dict(request,demand_basis='FORMAL4_OWN_SHARE_HELD',connector=wrong)))
        # Inherited modules must give exactly the prior result for identical explicit inputs.
        direct = dict(version='t5v0a',market_id=5,phase='formal',round=5,
            product_growth={p:dict(t.GROWTH) for p in t.PRODUCTS},
            production={'复合梁':dict(capacity_kunits=30.,production_kunits=10.,previous_workers=100.,
                efficiency_kunits_per_person=.2,efficiency_basis='EXPLICIT_SCENARIO')},
            financial_state=dict(equity=50.,assets=100.,long_debt=40.,short_debt=10.))
        inherited = t.prior.apply_request(old,direct)
        new = t.apply_request(registry,dict(direct,version='t5v0b'))
        for field in ('materials','labor','finance','curves','administration','spending_to_curve','existing_orders'):
            assert new[field] == inherited[field],field
    return dict(status='PASS',version='t5v0b',training_performed=False,
        checks=dict(prior_acceptance=True,all_frozen_parameters_unchanged=True,
            modules_reviewed=29,sources_unchanged=len(registry['source_sha256']),
            country_product_demand_ratios=True,equal_share_conservation=True,
            stable_published_machine_costs=True,zero_investment_cost=True,
            inherited_cost_finance_curves_consistent=True,inventory_demand_transmission=True,
            no_double_growth_or_future_assumptions=True,invalid_inputs_rejected=rejects))


if __name__ == '__main__':
    out = Path(sys.argv[1])
    result = verify(out)
    t.app.save(out/'acceptance.json',result)
    print(t.app.json.dumps(result,ensure_ascii=False,indent=2))
