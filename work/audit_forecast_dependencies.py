"""Audit saved training provenance and frozen inference without changing platform data."""
import copy
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
import numpy as np
import t5v0
import t5v1


def main():
    out = ROOT/'output/forecast_dependency_audit'/datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True, exist_ok=False)
    sources = {}
    cache = {}

    def read(path):
        path = ROOT/path
        if path not in cache:
            raw = path.read_bytes()
            sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(raw).hexdigest()
            cache[path] = json.loads(raw.decode('utf-8-sig'))
        return cache[path]

    refs = []

    def walk(value):
        if isinstance(value, dict):
            if all(k in value for k in ('source', 'table', 'row', 'column', 'value')):
                refs.append(value)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    for version, stamp in [('t4v1', '20261014T153914569881+0800'), ('t5v0', '20261015T085218049188+0800')]:
        walk(read(f'output/{version}/{stamp}/dataset.json'))
    categories = Counter()
    unique = set()
    for ref in refs:
        key = (ref['source'], ref['table'], ref['row'], ref['column'])
        if key in unique:
            continue
        unique.add(key)
        doc = read(ref['source'])
        if ref.get('sha256'):
            assert sources[Path(ref['source']).as_posix()] == ref['sha256']
        table = doc['tables'][ref['table']]
        cells = (table['rows'] if isinstance(table, dict) else table)[ref['row']]
        cells = [cell['text'] if isinstance(cell, dict) else cell for cell in cells]
        label = str(cells[0])
        assert t5v0.nd.numeric(cells[ref['column']])[0] == ref['value'], key
        assert not any(w in label for w in ('预计', '预测', '预估')), (key, label)
        assert 'budget' not in ref['source'].lower(), key
        category = ref.get('category')
        if category is None:
            assert any(panel in ref['source'] for panel in ('marketdetails', 'incomestatement', 'productiondetails')), ref
            category = 'historical_result_reference_without_category'
        assert category in ('actual_result', 'FORMAL3_GROUP_FINAL_DECISION', 'ROUND_4_GROUP_FINAL_DECISION',
                            'historical_result_reference_without_category'), ref
        categories[category] += 1

    pairs = read('output/formal5_marketing_r4/20261015T165420238/training_pairs.json')
    # Rebuild every closing feature/label from settled results, including excluded pairs.
    for pair in pairs:
        refs4 = pair['closing_refs']
        market = read(refs4['market'])['tables'][0]
        income = read(refs4['income'])['tables'][0]
        j = ['复合梁', '连接件'].index(pair['product'])
        k = ['泰国', '印尼'].index(pair['country'])
        num = lambda v: float(str(v).replace('\xa0', '').replace(' ', ''))
        expected = {'price': num(market[[[3, 4], [6, 7]][j][k]][refs4['market_column']]),
                    'demand': num(market[[[20, 21], [24, 25]][j][k]][refs4['market_column']])}
        for field, label in [('general', '一般营销'), ('designer', '设计师营销'), ('rd', '研发')]:
            expected[field] = num(next(r for r in income if r and r[0] == label)[refs4['income_column']])
        assert expected == pair['closing']
        assert pair['initial_round'] == 3 and pair['closing_round'] == 4

    fields = read('output/round_close/20261014_formal4_close/decision_history/20261014T233043761904+0800/group_final_42.json')
    assert Counter(r['category'] for r in fields) == {'ROUND_4_GROUP_FINAL_DECISION': 29, 'ROUND_4_GROUP_FINAL_PLAYER_ESTIMATE': 13}
    guard = t5v0.self_check()
    rejected = 0
    for row in fields:
        if row['category'].endswith('PLAYER_ESTIMATE'):
            try:
                t5v0.final_field(fields, row['section'], row['product_or_location'], row['label'])
            except ValueError:
                rejected += 1
            else:
                raise AssertionError('Player estimate accepted')
    assert rejected == 13

    registry = read('output/t5v1/20261015T171355804/models_full.json')
    model = t5v1.ApplicationModel()
    model.__dict__.update(t5v1.decode(copy.deepcopy(registry['application_state'])))
    model.r = {'risk': registry['risk']}
    model.current = {int(k): v for k, v in model.current.items()}
    x = np.array(registry['saved_plans'][0]['x'], float)
    cfg = registry['scenario_configs'][0]
    base = model.evaluate(x, cfg, details=True)
    budget_base = model.evaluate(x, cfg, details=True, budget=True)
    original_current = copy.deepcopy(model.current)
    forecast_rows = [58, 59, 61, 62, 65, 66, 68, 69, 72, 73, 76, 77, 79]
    for row in forecast_rows:
        model.current[row] = model.current[row]*1.7 + .123
    assert model.evaluate(x, cfg, details=True) == base
    assert model.evaluate(x, cfg, details=True, budget=True) != budget_base
    model.current = original_current
    changes = []
    for index, field in [(0, 'demand'), (4, 'demand'), (12, 'demand'), (14, 'efficiency'), (15, 'capacity'), (19, 'rate')]:
        changed = x.copy()
        changed[index] = changed[index]*.9 if index in (0, 4, 12, 14) else changed[index]+1
        result = model.evaluate(changed, cfg, details=True)
        before, after = base['periods'][0][field], result['periods'][0][field]
        assert not np.allclose(before, after, rtol=1e-10, atol=1e-12), (index, field)
        changes.append(dict(decision_index=index, output=field, before=before, after=after))
    checks = dict(status='PASS', unique_training_source_cells=len(unique), source_categories=dict(categories),
                  marketing_pairs_rebuilt=len(pairs), marketing_fit_pairs=sum(p['fit_eligible'] for p in pairs),
                  player_estimate_fields_rejected=rejected, forecast_current_mutation_ignored_in_forward=True,
                  forecast_current_mutation_changes_budget_replay=True,
                  decision_dependency_checks=changes, final_decision_selfcheck=guard,
                  scope='t4v1/t5v0 saved datasets, t5v1 marketing training pairs and frozen forward inference; not all historical versions or live UI')
    for path in [Path(__file__), ROOT/'code/model_v2/t5v0.py', ROOT/'code/model_v2/t4v1.py',
                 ROOT/'code/model_v2/t5v1.py', ROOT/'work/train_formal4_marketing.py', ROOT/'work/solve_formal5_full.py']:
        sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name, data in [('checks.json', checks), ('source_hashes.json', sources)]:
        (out/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(dict(output=str(out), **{k:v for k,v in checks.items() if k not in ('decision_dependency_checks', 'final_decision_selfcheck')}), ensure_ascii=False))


if __name__ == '__main__':
    main()
