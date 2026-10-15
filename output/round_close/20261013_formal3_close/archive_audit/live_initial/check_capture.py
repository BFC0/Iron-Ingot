"""Offline capture integrity and selected team extraction; exclusive outputs only."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path


def complete_html(value):
    return bool(value) and '[Truncated]' not in value and bool(re.search(r'</html>\s*$', value, re.I))


def numeric(value):
    cleaned = re.sub(r'\s+', '', value).replace(',', '')
    return float(cleaned) if re.fullmatch(r'-?\d+(?:\.\d+)?', cleaned) else None


def inspect(path):
    raw = path.read_bytes()
    doc = json.loads(raw.decode('utf-8-sig'))
    markup = doc.get('html', '')
    text = doc.get('text', '')
    selections = [{'id': s['id'], 'value': s['value'],
                   'selected': [o for o in s['options'] if o.get('selected')]}
                  for s in doc.get('selects', [])]
    options = [o['text'] for s in selections for o in s['selected']]
    is_actual = '/Results' in doc.get('url', '')
    # shortcut: identity is market 5 formal 3/4 only, extend before auditing another market or period.
    verified = ('市场 5' in options and '回合3' in options) if is_actual else (
        '市场 5,' in text and '回合4: 2026-10-14 22:00' in text)
    scripts = doc.get('scripts', [])
    result = dict(source=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                  bytes=len(raw), captured_at=doc.get('captured_at'), url=doc.get('url'),
                  category='actual_result' if is_actual else 'next_round_outlook',
                  market=5, round=3 if is_actual else 4,
                  selection_verified=verified, selections=selections,
                  html_characters=len(markup), html_complete=complete_html(markup),
                  truncation_marker=('[Truncated]' in markup),
                  html_ends_with_closing_tag=bool(re.search(r'</html>\s*$', markup, re.I)),
                  extracted_script_blocks=len(scripts), html_script_tags=len(re.findall(r'<script\b', markup, re.I)),
                  chart_calls=sum(s.count('Chart.create(') for s in scripts),
                  script_truncation_marker=any('[Truncated]' in s for s in scripts),
                  svg_count=len(doc.get('svgs', [])), table_count=len(doc.get('tables', [])),
                  team='营销团队', team_rows=[], team_chart_points=[], outlook_sections={}, parameters=[])
    for ti, table in enumerate(doc.get('tables', [])):
        team_column = None
        context = ''
        for ri, row in enumerate(table):
            if '营销团队' in row:
                team_column = row.index('营销团队')
            elif team_column is not None and len(row) > team_column:
                value = numeric(row[team_column])
                if value is not None:
                    result['team_rows'].append(dict(table_index=ti, row_index=ri, section=context,
                                                    label=row[0], display=row[team_column], value=value))
            elif len(row) == 1 and len(row[0]) < 80:
                context = row[0]
        if not is_actual:
            context = ''
            parameter_context = []
            narrative_table = bool(table and table[0] == ['市场前景'])
            for ri, row in enumerate(table):
                if narrative_table and len(row) == 1 and row[0] in ['需求', '大客户订单', '生产', '货币', '财务']:
                    context = row[0]
                elif narrative_table and len(row) == 1 and context:
                    result['outlook_sections'][context] = row[0]
                    context = ''
                elif len(row) == 4 and numeric(row[1]) is not None and numeric(row[3]) is not None:
                    result['parameters'].append(dict(table_index=ti, row_index=ri, label=row[0],
                                                     preceding_headings=parameter_context[-3:],
                                                     current=numeric(row[1]), displayed_change=row[2],
                                                     previous=numeric(row[3]), changed=numeric(row[1]) != numeric(row[3])))
                elif len(row) == 1 and row[0].strip():
                    parameter_context.append(row[0])
    decoder = json.JSONDecoder()
    for script in scripts:
        for match in re.finditer(r'Chart\.create\("([^"]+)",\s*"([^"]+)",\s*', script):
            try:
                chart, _ = decoder.raw_decode(script[match.end():])
            except ValueError:
                result.setdefault('chart_parse_errors', []).append(match[1])
                continue
            for series in chart.get('dataset', []):
                if series.get('seriesname') == '营销团队':
                    result['team_chart_points'].append(dict(chart_id=match[1], chart_type=match[2],
                        categories=chart.get('categories', []), points=series.get('data', [])))
    result['final_source_hash_unchanged'] = hashlib.sha256(path.read_bytes()).hexdigest() == result['sha256']
    return result


def main():
    assert complete_html('<html><body></body></html>')
    assert not complete_html('<html>[Truncated]')
    assert not complete_html('<html><body>')
    assert numeric('17\u00a0698') == 17698 and numeric('-') is None
    parser = argparse.ArgumentParser()
    parser.add_argument('sources', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    checks = [inspect(path) for path in args.sources]
    report = dict(generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  status='COMPLETE' if all(c['selection_verified'] and c['html_complete'] and
                         c['final_source_hash_unchanged'] for c in checks) else 'INCOMPLETE',
                  selfcheck_passed=True, raw_modified=False, financial_balances_checked=False,
                  sources=checks)
    with (args.output / 'checks.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'], 'output': str(args.output),
                      'checks': [{'source': c['source'], 'html_complete': c['html_complete'],
                                  'selection_verified': c['selection_verified']} for c in checks]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
