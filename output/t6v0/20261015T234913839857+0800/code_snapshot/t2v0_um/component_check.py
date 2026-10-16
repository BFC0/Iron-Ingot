"""Practice-only source/holdout checks and a synthetic financial-feedback test."""
import copy
import json
import numpy as np
import pipeline as t2
import calibrated as c


def rejected(call):
    try:
        call()
    except (ValueError, KeyError):
        return
    raise AssertionError('Unsupported input accepted')


def check(components, rows, validation, changes, gate):
    assert len(rows) == 100
    assert {(r['phase'], r['round']) for r in rows} == {('practice', 2)}
    assert len({(r['market_id'], r['team_column']) for r in rows}) == 100
    for r in rows:
        for ref in r['sources'].values():
            p = t2.ROOT / ref['file']
            value = t2.formal.field(p, ref['label'], ref['column'], ref['occurrence'])['value']
            assert value == ref['value']
        expected = c.interest.ratios(r['state'])
        assert expected['equity_ratio'] == r['equity_ratio'] and expected['leverage'] == r['leverage']
        assert abs(r['premium'] - r['rate_percent'] / 100 + .025) < 1e-12
    for name in ('interest_rate', 'material_unit_cost'):
        model = components[name]
        assert model['training_n'] == 100
        assert model['training_phase'] == 'practice' and model['training_round'] == 2
        assert {tuple(k) for k in model['training_keys']} == {(r['market_id'], 'practice', 2, r['team_column']) for r in rows}
    errors = []
    for fold in validation['interest_nested_market_holdouts']:
        held = fold['held_market']
        assert set(fold['training_markets']) == set(range(1, 11)) - {held}
        test = [r for r in rows if r['market_id'] == held]
        predicted = c.interest.premium(fold['form'], fold['parameters'], test)
        for r, pred, saved in zip(test, predicted, fold['records']):
            assert (saved['market_id'], saved['team_column']) == (held, r['team_column'])
            assert abs(saved['predicted_rate_percent'] - (2.5 + pred * 100)) < 1e-10
            errors.append(saved['error_bp'])
    assert len(errors) == 100
    assert abs(np.mean(abs(np.array(errors))) - components['interest_rate']['nested_market_holdout_mae_basis_points']) < 1e-10
    for fold in validation['material_market_holdouts']:
        held = fold['held_market']
        train = [r for r in rows if r['market_id'] != held]
        test = [r for r in rows if r['market_id'] == held]
        assert set(fold['training_markets']) == set(range(1, 11)) - {held}
        assert fold['fitted'] == c.material.fit(train, 'proportional')
        assert fold['evaluation'] == c.material.evaluate(fold['fitted'], test)
    original = copy.deepcopy(components)
    c.check_component_period(components, 'practice', 2)
    rejected(lambda: c.check_component_period(components, 'practice', 1))
    if not gate['passed']:
        rejected(lambda: c.check_component_period(components, 'formal', 2))
    bad = copy.deepcopy(components)
    bad['interest_rate']['training_phase'] = 'formal'
    rejected(lambda: c.check_component_period(bad, 'practice', 2))
    state = dict(inventory=0, short_debt=0, tax_loss=0, equity=10000, capacity=20, workers=100,
                 cash=30000, long_debt=40000, ar=0, ap=0, machine_book=10000, building_book=10000)
    decision = dict(prices=[3000, 3000], allocation=50, priority=[0, 1], general=[200, 200],
        designer=[200, 200], rd=500, operations=700, machine_investment=0, long_change=0)
    assumptions = dict(building_capex=0, building_depreciation=.07, ar_days=30, ap_days=30)
    result = c.conditional_accounts(components, state, decision, [20, 10], .2, assumptions, phase='practice', round_number=2)
    assert abs(result['balance_error']) < 1e-6
    assert abs(result['materials'] - result['production']['production'] * components['material_unit_cost']['unit_cost_usd']) < 1e-8
    closing = {key: result[key] for key in ('equity', 'assets', 'long_debt')}
    closing['short_debt'] = 0
    expected_rate = c.interest.predict(components['interest_rate'], closing, 2.5, 2)['long_rate_percent'] / 100
    assert abs(result['long_rate'] - expected_rate) < 1e-10
    altered = copy.deepcopy(components)
    altered['material_unit_cost']['parameter'] += .01
    new = c.conditional_accounts(altered, state, decision, [20, 10], .2, assumptions, phase='practice', round_number=2)
    assert new['materials'] > result['materials'] and new['profit'] < result['profit'] and new['cash'] < result['cash']
    assert new['long_rate'] > result['long_rate']
    assert components == original
    rejected(lambda: c.conditional_accounts(components, state, decision, [20, 10], .2, {}, phase='practice', round_number=2))
    rejected(lambda: c.conditional_accounts(components, dict(state, tax_loss=None), decision, [20, 10], .2, assumptions, phase='practice', round_number=2))
    rejected(lambda: c.conditional_accounts(components, dict(state, short_debt=1), decision, [20, 10], .2, assumptions, phase='practice', round_number=2))
    rejected(lambda: c.conditional_accounts(components, dict(state, orders=[dict(quantity=1)]), decision, [20, 10], .2, assumptions, phase='practice', round_number=2))
    if not gate['passed']:
        assert changes['demand_coefficients']['status'].startswith('NOT_RETRAINED')
    return dict(practice2_only_100_unique_labels=True, source_fields_replayed=True,
        components_training_periods_bound=True, source_rate_units_correct=True,
        whole_market_holdouts_disjoint=True, holdout_predictions_replayed=True,
        formal2_closed_gate_rejects=True, financial_feedback_converges=True,
        material_adjustment_counted_once=True, financial_balance_verified=True,
        cost_changes_profit_cash_equity_and_risk_rate=True,
        missing_tax_loss_assumptions_short_debt_bulk_rejects=True, models_not_mutated=True)


if __name__ == '__main__':
    import sys
    folder = t2.Path(sys.argv[1])
    load = lambda name: json.loads((folder / name).read_text(encoding='utf-8'))
    print(check(load('components.json'), load('component_dataset.json'), load('component_validation.json'),
                load('parameter_changes.json'), load('comparison.json')))
