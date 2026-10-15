"""Source-linked formal round 1 closing states, carried unchanged into round 2."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from archive_and_report import table_rows, number


FIELDS = {
    'capacity': ('生产能力, 千单位', 0), 'workers': ('生产线人工数量', 0),
    'efficiency': ('生产效率, 千单位/人', 0), 'inventory': ('复合梁', 0),
    'inventory_book': ('成品库存', 0), 'cash': ('现金及现金等价物', 1),
    'ar': ('应收帐款', 0), 'ap': ('应付账款', 0),
    'machine_book': ('机器', 1), 'building_book': ('厂房', 1),
    'long_debt': ('长期贷款', 0), 'short_debt': ('短期贷款', 1),
    'equity': ('股东权益合计', 0), 'assets': ('资产总计', 0),
    'advance_receipts': ('已收预付款', 0),
    'previous_rd': ('研发', 1), 'previous_operations': ('运营改进', 0),
    'profit': ('本回合利润, 千 美元', 0),
    'cumulative_profit': ('累计收益, 千 美元', 0),
    'pretax': ('税前利润', 0), 'tax_paid': ('直接税', 0),
    'current_bulk_quantity': ('本回合复合梁', 0),
    'next_bulk_quantity': ('下一回合复合梁', 0),
}
UNKNOWN = ['tax_loss', 'rd_stock', 'operations_stock', 'pending_machine_capacity',
           'pending_building_capacity']
ROOT = Path(__file__).resolve().parents[1]


def verify_selection(snapshot, market, teams):
    selected = re.findall(r'- option "([^"]+)" \[selected\]', snapshot)
    if selected != [f'市场 {market}', '回合1']:
        raise ValueError(f'Actual selector mismatch: {selected}')
    if not any(r['cells'] == teams for r in table_rows(snapshot)):
        raise ValueError('Selection/report team order mismatch')
    return selected


def parse_state(path):
    doc = json.loads(path.read_text(encoding='utf-8'))
    market = doc.get('market_id')
    if not (isinstance(market, int) and not isinstance(market, bool) and 1 <= market <= 10
            and doc.get('phase') == 'formal' and doc.get('round') == 1
            and doc.get('kind') == 'actual_result' and doc.get('selection_verified') is True
            and doc.get('selected_round') == '回合1'
            and doc.get('selected_market') == f'市场 {market}'
            and doc.get('title') == f'Results for 市场 {market}, 回合1'):
        raise ValueError(f'Unverified formal actual identity: {path}')
    rows = table_rows(doc['snapshot'])
    selection_path = ROOT / doc['selection_file']
    selection = json.loads(selection_path.read_text(encoding='utf-8'))
    def numeric(value):
        try:
            number(value)
            return True
        except ValueError:
            return False
    headers = [r['cells'] for r in rows if len(r['cells']) == 10
               and not any(numeric(c) for c in r['cells'])]
    if not headers or any(h != headers[0] for h in headers) or len(set(headers[0])) != 10:
        raise ValueError(f'Expected consistent ten-team headers: {path}')
    selected = verify_selection(selection['snapshot'], market, headers[0])
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    output = []
    for column, team in enumerate(headers[0], 1):
        refs = {}
        state = {}
        for key, (label, occurrence) in FIELDS.items():
            found = [r for r in rows if r['cells'] and r['cells'][0] == label
                     and len(r['cells']) == 11]
            if len(found) <= occurrence:
                state[key] = None
                refs[key] = dict(value=None, status='NOT_DISCLOSED_OR_ROW_MISSING',
                                 label=label, occurrence=occurrence)
                continue
            row = found[occurrence]
            value = number(row['cells'][column])
            if not math.isfinite(value):
                raise ValueError(f'Non-finite state: {path}/{team}/{key}')
            if key not in ['equity', 'profit', 'cumulative_profit', 'pretax'] and value < 0:
                raise ValueError(f'Negative nonnegative state: {path}/{team}/{key}')
            state[key] = value
            refs[key] = dict(value=value, file=str(path), sha256=sha, line=row['line'],
                             column=column, label=label, occurrence=occurrence)
        state.update({key: None for key in UNKNOWN})
        # shortcut: report exposes order quantities only; add prices/terms when a verified order source exists.
        state['orders'] = [dict(delivery_round=2, quantity=state['next_bulk_quantity'],
                                price=None, terms=None,
                                source=refs['next_bulk_quantity'])]
        output.append(dict(market_id=market, team=team, team_column=column,
            source_phase='formal', source_round=1, decision_start_round=2,
            formal1_end_state=state, formal2_initial_state=dict(state), fields=refs,
            history=[dict(phase='formal', round=1, rd=state['previous_rd'],
                          operations=state['previous_operations'],
                          source_rd=refs['previous_rd'], source_operations=refs['previous_operations'])],
            unknown_fields=UNKNOWN + [key for key in FIELDS if state[key] is None],
            carry_status='OBSERVED_FORMAL1_CLOSE_NOT_ADJUSTED_FOR_FORMAL2_DECISIONS',
            prediction_complete=False))
        output[-1]['observed_fields_complete'] = all(state[key] is not None for key in FIELDS)
        output[-1]['missing_required_fields'] = [key for key in FIELDS if state[key] is None]
        output[-1]['projection_gate'] = dict(eligible=False,
            reason='Unknown tax loss and accumulated technology stocks; observed state alone is not a complete forecast')
        output[-1]['selection_source'] = dict(file=str(selection_path),
            sha256=hashlib.sha256(selection_path.read_bytes()).hexdigest(),
            selected_options=selected, team_order_verified=True)
    return output


def build(source_dir):
    files = sorted(source_dir.glob('market_*_formal1.json'))
    if not files:
        raise ValueError('No formal actual source files')
    states = [row for path in files for row in parse_state(path)]
    markets = sorted({r['market_id'] for r in states})
    if len(states) != len(markets) * 10:
        raise ValueError('Duplicate market sources')
    return dict(schema='FORMAL2_INITIAL_STATE_V1', states=states, markets=markets,
        missing_markets=sorted(set(range(1, 11)) - set(markets)),
        all_markets_complete=markets == list(range(1, 11)),
        observed_state_complete=all(r['observed_fields_complete'] for r in states),
        source_directory=str(source_dir), remaining_formal_rounds=[2, 3, 4, 5, 6],
        units=dict(finance='千美元', quantity='千单位', capacity='千单位',
                   efficiency='千单位/人', workers='人'),
        consumption_audit=dict(
            legacy_state_entry='code/stepwise_model.py:current_state (initial0 fixed)',
            legacy_consumers=['stepwise_model.accounts_from_state', 'stepwise_model.risk_linked_accounts',
                'model_v2.finance.accounts', 'model_v2.audit', 'model_v2.live_review',
                'model_v2.current_trial_review', 'model_v2.rounding_review', 'model_v2.supplement',
                'model_v2.report'],
            status='Old frozen runs retain initial0; new formal report must consume this artifact explicitly',
            finance_limits='Existing accounts assumes zero inventory/short debt; unknown tax loss blocks complete projection'),
        limitations=['税损余额未披露，不用单期亏损代替；研发运营存量未披露，保留已观察单期投入',
                    '正式1期末资产为正式2决策之前起点；不预扣折旧、不提前加入投资',
                    '已接受订单数量保留，价格条款未知；零数量不证明未来没有新订单',
                    '期末库存账面值与数量分别保存，不强行换算'])


def self_check(source_dir):
    result = build(source_dir)
    for row in result['states']:
        assert row['formal1_end_state'] == row['formal2_initial_state']
        assert row['formal2_initial_state']['tax_loss'] is None
        assert row['formal2_initial_state']['orders'][0]['delivery_round'] == 2
        s = row['formal2_initial_state']
        balance_keys = ['assets', 'equity', 'long_debt', 'short_debt', 'ap', 'advance_receipts']
        if all(s[key] is not None for key in balance_keys):
            assert abs(s['assets'] - sum(s[key] for key in balance_keys[1:])) <= 3
    if 5 in result['markets']:
        ours = next(r for r in result['states'] if r['market_id'] == 5 and r['team'] == '营销团队')
        assert ours['formal2_initial_state']['cash'] == 16372
        assert ours['formal2_initial_state']['previous_rd'] == 650
        assert ours['formal2_initial_state']['previous_operations'] == 760
    path = next(source_dir.glob('market_*_formal1.json'))
    doc = json.loads(path.read_text(encoding='utf-8'))
    selection = json.loads((ROOT / doc['selection_file']).read_text(encoding='utf-8'))
    altered = selection['snapshot'].replace('option "回合1" [selected]',
                                            'option "练习回合1" [selected]')
    teams = [r['team'] for r in parse_state(path)]
    for snapshot, order in [(altered, teams), (selection['snapshot'], teams[::-1])]:
        try:
            verify_selection(snapshot, doc['market_id'], order)
        except ValueError:
            pass
        else:
            raise AssertionError('Trusted metadata instead of actual selected round/team order')
    return dict(teams_checked=len(result['states']), closing_state_preserved=True,
                missing_state_not_zero=True, formal1_only=True, selector_mismatch_rejected=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.sources)
    result['self_check'] = self_check(args.sources)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"{len(result['states'])} states; markets={result['markets']}; missing={result['missing_markets']}")


if __name__ == '__main__':
    main()
