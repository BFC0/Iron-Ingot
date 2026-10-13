"""Small assert checks for evidence gates, period binding and unchanged model structure."""
import copy
import tempfile
from pathlib import Path
import numpy as np
import pipeline as t2


def rejects(call):
    try:
        call()
    except (ValueError, KeyError):
        return
    raise AssertionError('Invalid input was accepted')


def self_check():
    rows = []
    params = [.1, .2, .5, .2]
    for market in range(1, 7):
        for team in range(1, 11):
            rows.append(dict(market_id=market, team_id=f'M{market}:T{team}', team_column=team,
                phase='practice', round=2, context_id=t2.CONTEXT, country=t2.core.COUNTRIES[0],
                kind='actual_result', price=1700 + team * 50, initial_price=2000,
                general=team * 80, designer=(11 - team) * 90, rd=team * 100,
                previous_rd=team * 40, operations=team * 70, previous_operations=team * 50,
                demand=team + 2, rd_curve_id='curve2'))
    curve = dict(curve_id='curve2', parameters=params, parameters_hash=t2.parameter_hash(params), axis_max=1500)
    model = dict(model_id=t2.MODEL_ID, context_id=t2.CONTEXT, country=t2.core.COUNTRIES[0],
                 beta=[1, 0, .4, .5, .6], rho=.5, piecewise=False, curve_id='curve2', migration_gate_passed=True)
    original = copy.deepcopy(model)
    p = t2.bound_prediction(rows, model, curve, 'practice')
    assert np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))
    for ids in t2.core.old.groups(rows).values():
        assert abs(sum(p[ids]) - 1) < 1e-12
    changed_ops = [dict(r, operations=r['operations'] + 1000) for r in rows]
    x = t2.core.features(rows, params)
    assert np.array_equal(x, t2.core.features(changed_ops, params))
    assert not np.array_equal(t2.ops.factors(rows, [.45, .75, 400]), t2.ops.factors(changed_ops, [.45, .75, 400]))
    new_params = [.3, .4, .5, .2]
    changed_x = t2.core.features(rows, new_params)
    assert np.array_equal(x[:, :4], changed_x[:, :4]) and not np.array_equal(x[:, 4], changed_x[:, 4])
    # Change only the upstream curve: its signature changes, downstream beta stays frozen.
    new_curve = dict(curve, curve_id='new', parameters=new_params, parameters_hash=t2.parameter_hash(new_params))
    new_model = dict(model, curve_id='new')
    p2 = t2.bound_prediction([dict(r, rd_curve_id='new') for r in rows], new_model, new_curve, 'practice')
    assert not np.allclose(p, p2) and model == original and new_model['beta'] == model['beta']
    for bad in (rows[:-1], rows + [rows[0]], [dict(r, round=1) for r in rows],
                [dict(r, context_id='other') for r in rows], [dict(r, rd_curve_id='old') for r in rows],
                [dict(r, price=float('nan')) for r in rows], [dict(r, general=-1) for r in rows]):
        rejects(lambda bad=bad: t2.bound_prediction(bad, model, curve, 'practice'))
    rejects(lambda: t2.bound_prediction(rows, dict(model, country=t2.core.COUNTRIES[1]), curve, 'practice'))
    rejects(lambda: t2.bound_prediction(rows, dict(model, migration_gate_passed=False), curve, 'practice'))
    rejects(lambda: t2.bound_prediction(rows, model, dict(curve, parameters=new_params), 'practice'))
    rejects(lambda: t2.bound_prediction(rows, model, curve, 'formal'))
    formal = [dict(r, phase='formal', kind='forecast_scenario') for r in rows]
    assert np.allclose(p, t2.bound_prediction(formal, model, curve, 'formal'))
    folds = list(t2.um.grouped_folds(rows))
    for held, train, test in folds:
        assert not {r['market_id'] for r in train} & {r['market_id'] for r in test}
        for inner_held, inner_train, inner_test in t2.um.grouped_folds(train):
            assert set(inner_held).isdisjoint(held)
            assert not {r['market_id'] for r in inner_train} & {r['market_id'] for r in inner_test}
    assert t2.same_value(dict(value=1.234, unit='u'), dict(value=1.234, unit='u'))
    assert not t2.same_value(dict(value=1.234, unit='u'), dict(value=1.235, unit='u'))
    assert t2.same_value(dict(value=1.23, unit='u', resolution=.01), dict(value=1.234, unit='u'))
    assert not t2.same_value(dict(value=1, unit='u'), dict(value=1, unit='different'))
    rejects(lambda: t2.same_value(dict(value=float('nan'), unit='u'), dict(value=1, unit='u')))
    gate, _ = t2.compare()
    assert not gate['passed'] and all(r['status'] == '证据不足' for r in gate['rows'])
    # Source-backed synthetic dossier exercises both the passing and failing gate, without live data.
    with tempfile.TemporaryDirectory(dir=t2.ROOT / 'work', prefix='t2_gate_') as folder:
        path = Path(folder) / 'synthetic.json'
        values = {key: 'synthetic' for key in t2.required_items()}
        doc = dict(phase='practice', round=2, market_id=5, selection_verified=True, captured_at='synthetic', values=values)
        t2.write(path, doc)
        ref = dict(file=path.relative_to(t2.ROOT).as_posix(), sha256=t2.core.digest(path))
        bundle = dict(identity=ref, items={key: dict(value=value, unit=t2.required_items()[key]['unit'],
            phase='practice', round=2, coverage='ALL_VISIBLE_GIVEN_PARAMETERS_REVIEWED',
            reference=dict(ref, pointer='/values/' + key.replace('~', '~0').replace('/', '~1'))) for key, value in values.items()})
        formal_path = Path(folder) / 'formal.json'
        t2.write(formal_path, dict(doc, phase='formal'))
        formal_ref = dict(file=formal_path.relative_to(t2.ROOT).as_posix(), sha256=t2.core.digest(formal_path))
        formal_bundle = dict(identity=formal_ref, items={key: dict(item, phase='formal',
            reference=dict(formal_ref, pointer=item['reference']['pointer'])) for key, item in bundle['items'].items()})
        evidence = dict(practice=bundle, formal=formal_bundle)
        assert t2.compare(evidence)[0]['passed']
        incomplete = copy.deepcopy(evidence)
        del incomplete['formal']['items']['curve/rd']
        assert not t2.compare(incomplete)[0]['passed']
        forged = copy.deepcopy(evidence)
        forged['formal']['items']['curve/rd']['value'] = 'invented'
        assert not t2.compare(forged)[0]['passed']
        wrong_round = Path(folder) / 'wrong_round.json'
        t2.write(wrong_round, dict(doc, phase='formal', round=1))
        rejects(lambda: t2.period_identity(dict(file=wrong_round.relative_to(t2.ROOT).as_posix(), sha256=t2.core.digest(wrong_round)), 'formal'))
        rejects(lambda: t2.reference(dict(ref, sha256='wrong')))
        rejects(lambda: t2.reference(dict(file='../outside.json', sha256='wrong')))
    return dict(evidence_gate_missing_rejects=True, source_bound_complete_gate_accepts=True,
        forged_and_incomplete_evidence_rejects=True, source_hash_and_period_rejects=True,
        curve_and_row_binding_rejects=True, wrong_country_context_period_rejects=True,
        duplicate_and_incomplete_competitors_rejects=True, shares_sum_to_one=True,
        upstream_curve_changes_features_without_changing_downstream_beta=True,
        operations_affects_efficiency_only=True, nested_market_splits_disjoint=True,
        nonfinite_and_negative_inputs_rejects=True, displayed_rounding_only_when_declared=True)


if __name__ == '__main__':
    print(self_check())
