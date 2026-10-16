"""Independent saved-bundle acceptance; never retrains or changes platform state."""
import argparse
import hashlib
import itertools
import json
import re
from pathlib import Path
from urllib.parse import unquote
import t6v1 as app
import numpy as np


def verify(bundle):
    bundle = Path(bundle).resolve()
    manifest = app.read(bundle/'manifest.json')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    for rel, expected in manifest['source_hashes'].items():
        assert sha(app.ROOT/rel) == expected, rel
    for rel, expected in manifest['output_hashes'].items():
        assert sha(bundle/rel) == expected, rel
    for rel, rec in manifest['documents'].items():
        assert sha(app.ROOT/rel) == rec['after_sha256']
        assert sha(bundle/'documents_before'/rel) == rec['before_sha256'] == rec['backup_sha256']
    m = app.ApplicationModel(bundle)
    results = app.read(bundle/'result.json')
    fields = app.read(bundle/'field_coverage.json')
    assert results['start_round'] == results['end_round'] == 6
    assert len(fields) == len({f['key'] for f in fields}) == 56
    assert sum(f['status'] == '未求解' for f in fields) == 5
    assert sum(f['status'] == '合计求解；细分未识别' for f in fields) == 12
    old_fields = app.read(bundle/'current_fields.json')
    assert {f['key'] for f in old_fields} == {f['key'] for f in fields}
    assert all(f['current'] == next(q['value'] for q in old_fields if q['key'] == f['key']) for f in fields)
    for plan in results['candidates']:
        x = m.validate(plan['x'])
        fixed = [app.ORDERS.index(tuple(o)) for o in plan['evaluations'][0]['priorities']]
        for scenario, saved in zip(m.r['scenarios'], plan['evaluations']):
            ev = m.evaluate(x, scenario, True, priorities=fixed)
            for key in ['profit', 'cash', 'short_debt', 'revenue', 'rate', 'machine_depreciation', 'balance_error']:
                assert abs(ev[key]-saved[key]) < 1e-8, (plan['name'], scenario['name'], key)
            assert abs(ev['balance_error']) < 1e-7
            assert ev['production_indonesia'] == [0., 0.] and ev['round'] == 6
            assert np.allclose(np.array(ev['opening_inventory'])+ev['production'], np.array(ev['sales']).sum(axis=1)+ev['closing_inventory'])
        # Check fixed priorities against all alternatives under every saved scenario.
        for scenario, saved in zip(m.r['scenarios'], plan['evaluations']):
            values = [m.evaluate(x, scenario, True, priorities=o)['profit'] for o in itertools.product(range(6), repeat=2)]
            assert max(values) <= saved['profit']+1e-7
        # A redistribution with identical company totals cannot create a marketing gain.
        trial = x.copy()
        for start in [6, 12]:
            trial[start:start+6] = x[start:start+6].sum()/6
        assert np.allclose(m.demand(x, {})[0], m.demand(trial, {})[0])
    trials = app.read(bundle/'indonesia_investment_checks.json')
    assert len(trials) == 252
    assert all(q['production_indonesia'] == [0., 0.] for q in trials)
    for plan in results['candidates']:
        for variable in ['machine/印尼/复合梁', 'machine/印尼/连接件']:
            for dep in [0., .15]:
                rows = sorted([q for q in trials if q['plan'] == plan['name'] and q['variable'] == variable and q['depreciation_fraction'] == dep], key=lambda q: q['step'])
                assert [q['step'] for q in rows] == list(range(21))
                assert rows[0]['profit'] >= max(q['profit'] for q in rows)-1e-7
    # Validate all changed documents' local links; retain, but distinguish, pre-existing gaps.
    link_count = 0
    existing_gaps = []
    paths = [bundle/'report.md', bundle/'input_review.md', app.ROOT/'code/model_v2/t6v1_README.md']
    paths += [app.ROOT/p for p in manifest['documents']]
    for path in paths:
        backup = bundle/'documents_before'/path.relative_to(app.ROOT) if path.is_relative_to(app.ROOT) else None
        before = backup.read_text(encoding='utf-8-sig') if backup and backup.exists() else ''
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8-sig')):
            target = target.strip('<>')
            if '://' in target or target.startswith('#'):
                continue
            resolved = path.parent/unquote(target.split('#')[0])
            link_count += 1
            if not resolved.exists():
                assert ']('+target+')' in before, (str(path), target)
                existing_gaps.append(dict(document=str(path.relative_to(app.ROOT)), target=target))
    request = app.read(bundle/'example_request.json')
    ev = m.evaluate(m.validate(request['decision_vector']), m.r['scenarios'][0], True)
    assert abs(ev['profit']-results['candidates'][1]['evaluations'][0]['profit']) < 1e-8
    return dict(status='PASS_SAVED_BUNDLE_REPLAY', source_hashes=len(manifest['source_hashes']),
        output_hashes=len(manifest['output_hashes']), fields=56, candidate_scenarios=18,
        fixed_logistics_scenario_pairs=18*36, investment_trials=len(trials), checked_links=link_count,
        preexisting_link_gaps=existing_gaps, training_performed=False, platform_verified=False,
        independent_forward_validation=False, full_global_optimum=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle), ensure_ascii=False, indent=2))
