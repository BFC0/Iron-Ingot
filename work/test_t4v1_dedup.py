"""Check that deduplication preserves every fitted value and demand prediction."""
import ast
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
sys.dont_write_bytecode = True
import numpy as np
import t4v1 as t


def check(source, out):
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    old, new = read(source/'models_full.json'), read(out/'models_full.json')
    inventory = read(out/'model_inventory_final.json')
    expected = json.loads(json.dumps(old))
    for name in ('UNIFIED', 'T2V0'):
        expected['model_inventory'].pop(name)
    expected['interest'].pop('parameters')
    expected['interest']['parameters_source'] = 'risk'
    for item in expected['model_inventory'].values():
        target = out/'models_full.json' if item['artifact'] in ('models.json', 'models_full.json') else source/item['artifact']
        item['artifact'] = Path(os.path.relpath(target, out)).as_posix()
    assert new == expected
    assert inventory['models'] == new['model_inventory'] and inventory['count'] == 29
    assert all((out/item['artifact']).is_file() for item in inventory['models'].values())
    data = read(source/'dataset.json')
    demand_checks = 0
    for product, rows in data['competitive_rows_by_product'].items():
        for name in ('SHARE', 'COUNTRY/泰国', 'COUNTRY/印尼'):
            pool = [r for r in rows if name == 'SHARE' or r['country'] == name.split('/')[1]]
            predictions = []
            for registry in (old, new):
                fitted = registry['demand'][product][name]
                features = t.base.core.features(pool, registry['curves']['rd/'+product]['parameters'], fitted['rho'], fitted['piecewise'])
                predictions.append(t.base.core.predict(pool, features, fitted['beta']))
            assert np.array_equal(*predictions)
            demand_checks += 1
    for form, fitted in old['interest']['parameters'].items():
        assert np.array_equal(t.interest.premium(form, fitted['parameters'], data['risk']),
                              t.interest.premium(form, new[new['interest']['parameters_source']][form]['parameters'], data['risk']))
    # Execute the actual training statements to catch a repeated fit call.
    tree = ast.parse((ROOT/'code/model_v2/t4v1.py').read_text(encoding='utf-8'))
    block = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and n.body
                 and isinstance(n.body[0], ast.Assign) and any(isinstance(v, ast.Name) and v.id == 'fits' for v in n.body[0].targets))
    from types import SimpleNamespace
    for rows in data['materials'].values():
        calls = []
        def fit(records, form):
            calls.append(form)
            return t.material.fit(records, form)
        scope = dict(rows=rows, material=SimpleNamespace(FORMS=t.material.FORMS, fit=fit, evaluate=t.material.evaluate))
        exec(compile(ast.Module(body=block.body[:2], type_ignores=[]), '<material training>', 'exec'), scope)
        assert calls == list(t.material.FORMS)
        for form, fitted in scope['fits'].items():
            original = t.material.fit(rows, form)
            assert fitted == dict(**original, evaluation=t.material.evaluate(original, rows))
    return dict(inventory_count=29, all_other_values_unchanged=True, identical_demand_replays=demand_checks,
                identical_interest_replays=2, material_fit_once_per_form=True)


if __name__ == '__main__':
    print(json.dumps(check(Path(sys.argv[1]), Path(sys.argv[2]))))
