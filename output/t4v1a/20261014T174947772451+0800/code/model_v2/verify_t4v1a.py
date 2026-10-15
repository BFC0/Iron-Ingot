"""Read-only bundle verification, API boundary checks and frozen-value comparison."""
import copy
import csv
import json
import math
import sys
from pathlib import Path
import t4v1a as app


def verify(bundle):
    bundle=Path(bundle).resolve()
    manifest=app.read(bundle/'manifest.json')
    for name,digest in manifest['output_hashes'].items():
        assert app.sha(bundle/name)==digest, name
    registry=app.read(bundle/'models_full.json')
    original=app.read(bundle/'baseline_models_full.json')
    for key in original:
        if key not in ('version','model_inventory'):
            assert registry[key]==original[key], key
    inventory=app.read(bundle/'model_inventory.json')
    assert len(registry['model_inventory'])==inventory['count']==29
    assert all((bundle/v['artifact']).is_file() for v in registry['model_inventory'].values())
    curves=app.read(bundle/'formal4_curves.json')
    assert registry['formal4_curves']==curves
    request=app.read(bundle/'example_request.json')
    with app.no_training():
        checks=app.self_check(registry)
        result=app.apply_request(registry,request)
        assert result==app.read(bundle/'scenario_0.175.json')
        assert result['complete_profit'] is None and not result['full_profit_available']
        assert result['horizon']['remaining_profit'] is None
        for field in ('growth','competitors','market_totals_kunits'):
            probe=copy.deepcopy(request);probe.pop(field)
            assert app.apply_request(registry,probe)['demand']['status']=='SKIPPED_MISSING_EVIDENCE'
        probe=copy.deepcopy(request)
        probe['production']={'复合梁':{'efficiency_basis':'EXPLICIT_SCENARIO'}}
        probe['financial']={'state':{}}
        probe['curve_coordinates']={'rd_beam':{}}
        result=app.apply_request(registry,probe)
        assert result['labor']['复合梁']['value'] is None
        assert result['finance']['value'] is None and result['curves']['rd_beam']['value'] is None
        for bad in (True,float('nan'),-1):
            probe=copy.deepcopy(request);probe['competitors'][0]['price']=bad
            try: app.apply_request(registry,probe)
            except ValueError: pass
            else: raise AssertionError('Bad demand input accepted')
        probe=copy.deepcopy(request);probe['competitors'].append(probe['competitors'][0])
        assert app.apply_request(registry,probe)['demand']['status']=='INCOMPLETE_COMPETITION'
        probe=copy.deepcopy(request);probe['financial']['form']='leverage_power'
        try: app.apply_request(registry,probe)
        except ValueError: pass
        else: raise AssertionError('Power risk deployed')
        try: app.core.fit([],[],0)
        except RuntimeError: pass
        else: raise AssertionError('Actual training call escaped guard')
        # Labels cannot influence prospective reference prediction.
        rows=copy.deepcopy(request['competitors'])
        for r in rows: r.update(demand=1e20,sales=0)
        clean=app.demand_reference(registry,request['competitors'],request['market_totals_kunits'],request['growth'])
        assert clean==app.demand_reference(registry,rows,request['market_totals_kunits'],request['growth'])
    comparison=app.read(bundle/'comparison.json')
    for name,records in [('comparison',comparison['demand']),('efficiency_cost_comparison',comparison['efficiency_cost']),
                         ('price_response',comparison['price_response']),('material_sensitivity',comparison['material_sensitivity'])]:
        with (bundle/(name+'.csv')).open(encoding='utf-8-sig',newline='') as f:
            csvrows=list(csv.DictReader(f))
        assert len(csvrows)==len(records)
        for csvrow,record in zip(csvrows,records):
            for k,v in record.items():
                if isinstance(v,(int,float)) and not isinstance(v,bool):
                    assert math.isclose(float(csvrow[k]),v,rel_tol=1e-14,abs_tol=1e-12)
    for product in app.PRODUCTS:
        for country in app.COUNTRIES:
            for linear in ((False,True) if product=='连接件' else (False,)):
                prices=[r for r in comparison['price_response'] if (r['product'],r['country'],r['linear_candidate'])==(product,country,linear)]
                assert prices[0]['share']<=prices[1]['share']<=prices[2]['share']
    checks.update(bundle_hashes=True,full_registry_artifacts_resolve=True,frozen_registry_values_unchanged=True,
        saved_request_exact_replay=True,missing_fields_return_gaps=True,demand_invalid_and_duplicate_inputs=True,
        demand_labels_not_read=True,actual_training_function_intercepted=True,csv_json_numeric_agreement=True,
        independent_country_product_price_direction=True)
    print(json.dumps(checks,ensure_ascii=False))
    return checks


if __name__=='__main__':
    verify(sys.argv[1])
