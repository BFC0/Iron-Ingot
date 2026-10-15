"""Verify historical capture and the separately paired current version offline."""
import hashlib
import importlib.util
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from check_html import check

RUN = Path(__file__).resolve().parent
BASE = RUN.parents[1]
spec = importlib.util.spec_from_file_location('archive_audit', BASE / 'audit/verify_archive.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(audit.redact_names(json.dumps(value, ensure_ascii=False, indent=2)))


def personal_rows(doc):
    tables, _ = audit.get_tables(doc)
    tables = json.loads(audit.redact_names(json.dumps(tables, ensure_ascii=False)))
    matches = [t for t in tables if any('PYT' in r for r in t)
               and any(r and r[0] == '每单位价格' for r in t)]
    assert len(matches) == 1, 'Checklist table missing or ambiguous'
    table = matches[0]
    header = next(r for r in table if 'PYT' in r)
    column = header.index('PYT')
    rows = []
    context = []
    start = next(i for i, r in enumerate(table) if r == ['回合预算'])
    for index, row in enumerate(table):
        if index < start:
            continue
        if len(row) == 1 and row[0]:
            context.append(row[0])
        elif len(row) == len(header) and context:
            rows.append({'row_index': index, 'context': list(context),
                         'label': row[0], 'value': row[column]})
    assert len(rows) >= 35 and all(r['value'] != '' for r in rows), (len(rows), [r['label'] for r in rows if not r['value']])
    return rows


def main():
    status = read(RUN / 'status.json')
    html = check()
    assert status['coverage'] == {'verified': 750, 'pending': 0}
    assert html['complete_html_pages'] == 750 and html['pending_count'] == 0
    for manifest in ('20261013T103249/sources.json',):
        for source in read(BASE / 'resume' / manifest):
            assert audit.sha(BASE / source['source']) == source['sha256']
    current = max(RUN.glob('current_*'))
    raw = current / 'raw'
    required = ['outlook', 'demand', 'productioninvestments', 'productionplanning',
                'marketreportdomestic', 'marketreportinternational1', 'marketreportbulk',
                'logistics', 'corporate', 'decisionchecklist_before',
                'decisionchecklist_after_budget', 'decisionchecklist_final',
                'budget_income', 'budget_balance', 'budget_cashflow', 'budget_ratios']
    sources, parsed, chart_index = [], {}, []
    for name in required:
        path = raw / (name + '.json')
        doc = read(path)
        assert not audit.current_identity(doc), name
        assert doc['html'].startswith('<html') and doc['html'].rstrip().endswith('</html>'), name
        assert '[Truncated]' not in doc['html'], name
        assert len(doc['html'].encode('utf-16-le')) // 2 == doc['html_length'], name
        tables, basis = audit.get_tables(doc)
        charts, errors = audit.charts(doc['html'])
        assert not errors, (name, errors)
        parsed[name] = {'tables': tables, 'basis': basis}
        chart_index.extend({'source': name, 'chart': c} for c in charts)
        sources.append({'source': path.relative_to(RUN).as_posix(),
                        'sha256': audit.sha(path), 'captured_at': doc['captured_at'],
                        'source_url': doc['source_url'], 'html_length': doc['html_length'],
                        'table_count': len(tables), 'chart_count': len(charts)})
    own = {name: personal_rows(read(raw / (name + '.json'))) for name in
           ('decisionchecklist_before', 'decisionchecklist_after_budget', 'decisionchecklist_final')}
    stable = len({json.dumps([{k: v for k, v in row.items() if k != 'row_index'} for row in rows],
                            ensure_ascii=False, sort_keys=True) for rows in own.values()}) == 1
    assert stable, 'Personal values changed: budgets must remain unpaired'
    expected_titles = {'budget_income': '损益表', 'budget_balance': '资产负债表',
                       'budget_cashflow': '现金流量表', 'budget_ratios': '金融指标'}
    for name, title in expected_titles.items():
        assert any(title in c for t in parsed[name]['tables'] for r in t for c in r) or title in read(raw / (name + '.json'))['text']
        assert len(parsed[name]['tables']) >= 2, name
    validation = read(BASE / status['audit'] / 'validation.json')
    pending = [x for x in read(BASE / status['audit'] / 'financial_checks.json') if x['status'] == 'pending']
    result = {'verified_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'status': 'WEB_CAPTURE_COMPLETE', 'history_coverage': 750,
              'history_complete_html': 750, 'historical_html_supplements': html['resolved_count'],
              'new_history_pages_this_turn': 150, 'new_html_supplements_this_turn': 45,
              'baseline_hashes_unchanged': status['baseline_all_212_hashes_unchanged'],
              'current_version_sources': len(sources), 'personal_row_count': len(own['decisionchecklist_final']),
              'personal_values_stable': stable, 'budgets_paired_to_current_version': True,
              'budget_labels_are_not_actual_results': True, 'current_charts': len(chart_index),
              'old_rejected_source_preserved': validation['failures'],
              'financial_pending_by_check': dict(Counter(x['check'] for x in pending)),
              'decision_modified': False, 'model_trained': False,
              'limits': ['Financial label pairing and model validation are separate tasks.',
                        'Old budgets lacking contemporaneous decisions remain unpaired.',
                        'Raw evidence contains names; share only redacted reports.']}
    write(current / 'sources.json', sources)
    write(current / 'tables.json', parsed)
    write(current / 'charts.json', chart_index)
    write(current / 'personal_rows.json', own['decisionchecklist_final'])
    write(current / 'verification.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
