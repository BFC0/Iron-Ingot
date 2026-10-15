"""Offline audit: python audit/verify_archive.py [--final]. Never writes raw files."""
import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

BASE = next(p for p in Path(__file__).resolve().parents if (p / 'raw').is_dir() and (p / 'audit').is_dir())
ROOT = BASE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import redact_names, table_rows

PANELS = ('summary market marketdetails production productiondetails productionenvironmental '
          'productionhr logistics logisticsdetails logisticsemissions incomestatement '
          'balancesheet cashflow ratios societalimpact').split()
PERIODS = [('initial', 0), ('practice', 1), ('practice', 2), ('formal', 1), ('formal', 2)]
PANEL_NAMES = {'summary': '概要', 'market': '市场/图表', 'marketdetails': '市场/明细',
               'production': '生产/图表', 'productiondetails': '生产/明细',
               'productionenvironmental': '生产/环境', 'productionhr': '生产/人力资源',
               'logistics': '物流/图表', 'logisticsdetails': '物流/明细', 'logisticsemissions': '物流/排放',
               'incomestatement': '财务报表/损益表', 'balancesheet': '财务报表/资产负债表',
               'cashflow': '财务报表/现金流量表', 'ratios': '财务指标', 'societalimpact': '价值创造'}


class Tables(HTMLParser):
    """TextContent fallback for hidden-tab captures whose innerText tables are empty."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.row, self.cell, self.skip = [], [], None, None, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'svg'):
            self.skip += 1
        if tag == 'table':
            self.stack.append([])
        if self.stack and tag == 'tr':
            self.row = []
        if self.stack and tag in ('td', 'th'):
            self.cell = []
        if self.cell is not None and tag == 'input' and attrs.get('type') not in ('hidden', 'button', 'submit'):
            self.cell.append(attrs.get('value', ''))
        if self.cell is not None and tag == 'br':
            self.cell.append('\n')

    def handle_data(self, data):
        if self.cell is not None and not self.skip:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'svg'):
            self.skip = max(0, self.skip - 1)
        if tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(re.sub(r'[ \t\r\n]+', ' ', ''.join(self.cell)).strip())
            self.cell = None
        if tag == 'tr' and self.row is not None:
            if self.stack:
                self.stack[-1].append(self.row)
            self.row = None
        if tag == 'table' and self.stack:
            self.tables.append(self.stack.pop())


def get_tables(doc):
    tables = doc.get('tables')
    if doc.get('html') and '/Decisions' in (doc.get('source_url') or doc.get('url') or ''):
        parser = Tables()
        parser.feed(doc['html'])
        return parser.tables, 'html_textcontent_decision_tables_including_hidden_budget'
    if tables and any(str(c).strip() for t in tables if isinstance(t, list) for r in t for c in r):
        return tables, 'captured_tables'
    if doc.get('html'):
        parser = Tables()
        parser.feed(doc['html'])
        return parser.tables, 'html_textcontent_fallback'
    return [[x['cells'] for x in table_rows(doc.get('snapshot', ''))]], 'snapshot_rows'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def save(path, value):
    # Exclusive creation: a rerun gets a new run directory.
    with path.open('x', encoding='utf-8') as stream:
        stream.write(redact_names(json.dumps(value, ensure_ascii=False, indent=2)))


def unique_object(pairs):
    counts = Counter(key for key, value in pairs)
    duplicates = [key for key, count in counts.items() if count > 1]
    if duplicates:
        raise ValueError('duplicate JSON keys: ' + ', '.join(duplicates))
    return dict(pairs)


def charts(text):
    """Decode literal JSON arguments only; do not execute any JavaScript."""
    result, errors = [], []
    decoder = json.JSONDecoder(object_pairs_hook=unique_object)
    for match in re.finditer(r'Chart\.create\s*\(', text):
        pos, args = match.end(), []
        try:
            for _ in range(3):
                pos += len(text[pos:]) - len(text[pos:].lstrip())
                value, end = decoder.raw_decode(text, pos)
                literal = text[pos:end]
                args.append(value)
                pos = end
                if len(args) < 3:
                    pos += len(text[pos:]) - len(text[pos:].lstrip())
                    if text[pos] != ',':
                        raise ValueError('nonliteral chart argument')
                    pos += 1
            result.append({'id': args[0], 'type': args[1], 'data': args[2], 'data_json_literal': literal, 'offset': match.start()})
        except (ValueError, IndexError) as error:
            errors.append({'offset': match.start(), 'error': str(error)})
    return result, errors


def identity(doc):
    selected = doc.get('selected', [])
    market = [x for x in selected if re.fullmatch(r'市场\s*\d+', x.get('label', ''))]
    period = [x for x in selected if re.fullmatch(r'(?:初始|练习)?回合\s*\d+', x.get('label', ''))]
    errors = []
    if len(market) != 1 or len(period) != 1:
        return ['missing_or_ambiguous_selected_identity']
    label = period[0]['label']
    phase = 'initial' if '初始' in label else 'practice' if '练习' in label else 'formal'
    actual = (int(re.search(r'\d+', market[0]['label'])[0]), phase, int(re.search(r'\d+', label)[0]))
    expected = (doc.get('market'), doc.get('phase'), doc.get('round'))
    if actual != expected:
        errors.append('selected_metadata_mismatch')
    for item in market + period:
        matches = [o for o in item.get('options', []) if o.get('value') == item.get('value')]
        if len(matches) != 1 or matches[0].get('label') != item['label']:
            errors.append('selected_option_value_mismatch')
    html = doc.get('html', '')
    if html:
        html_selected = []
        for select in re.findall(r'<select\b.*?</select>', html, re.S):
            if not re.search(r'name="panel:(?:group|round)-select"', select):
                continue
            options = re.findall(r'<option\b([^>]*)>(.*?)</option>', select, re.S)
            picked = [(re.search(r'value="([^"]*)"', attrs)[1], unescape(re.sub('<[^>]+>', '', label)).strip())
                      for attrs, label in options if re.search(r'\bselected(?:=|\s|$)', attrs)]
            html_selected.extend(picked)
        if html_selected != [(x['value'], x['label']) for x in market + period]:
            errors.append('html_selected_disagrees_with_record')
    url_panel = parse_qs(urlparse(doc.get('source_url', '')).query).get('panel', [])
    if url_panel != [doc.get('panel')]:
        errors.append('url_panel_mismatch')
    if doc.get('filename_panel_mismatch'):
        errors.append('filename_panel_mismatch')
    return errors


def normalize(doc, filename):
    doc = dict(doc)
    doc['source_url'] = doc.get('source_url') or doc.get('url')
    doc['panel'] = doc.get('panel') or parse_qs(urlparse(doc.get('source_url') or '').query).get('panel', [None])[0]
    if filename.startswith('round3_'):
        doc.setdefault('market', 5)
        doc.setdefault('phase', 'formal')
        doc.setdefault('round', 3)
    if not doc.get('selected') and doc.get('selectors'):
        doc['selected'] = [{'label': s.get('selected', ''), 'value': s.get('value'),
                            'options': [{'label': o.get('text'), 'value': o.get('value')} for o in s.get('options', [])]}
                           for s in doc['selectors']]
    requested = re.fullmatch(r'market(\d+)_(initial|practice|formal)(\d+)_([a-z]+)\.json', filename)
    if requested:
        for k, v in [('market', int(requested[1])), ('phase', requested[2]), ('round', int(requested[3])), ('panel', requested[4])]:
            doc.setdefault(k, v)
        # Filename is the requested key; selected evidence must independently prove it.
        if doc['panel'] != requested[4]:
            doc['filename_panel_mismatch'] = True
    return doc


def current_identity(doc):
    content = doc.get('html') or doc.get('snapshot', '')
    content = re.sub(r'<(?:script|style)\b.*?</(?:script|style)>', '', content, flags=re.S)
    text = unescape(re.sub(r'<[^>]+>', ' ', content))
    text = re.sub(r'\s+', ' ', text)
    markets = re.findall(r'市场\s*&\s*课程编码:?\s*市场\s*(\d+)', text)
    # Snapshot strings retain quotes around the footer.
    if not markets:
        markets = re.findall(r'市场\s*&\s*课程编码:\s*市场\s*(\d+)', text)
    expected_market = doc.get('market', 5)
    expected_round = doc.get('round', 3)
    issues = []
    if not markets or any(int(m) != expected_market for m in markets):
        issues.append('current_market_footer_missing_or_mismatched')
    if not re.search(r'回合\s*' + str(expected_round) + r'\s*[:：]', text):
        issues.append('current_round_header_missing_or_mismatched')
    return issues


def coverage(valid, panels):
    return [{'market': m, 'phase': p, 'round': r, 'panel': panel, 'panel_name': PANEL_NAMES.get(panel, panel),
             'status': 'verified' if (m, p, r, panel) in valid else 'pending',
             'sources': valid.get((m, p, r, panel), [])}
            for m in range(1, 11) for p, r in PERIODS for panel in sorted(panels)]


def num(text):
    compact = re.sub(r'[\s,%]', '', text).replace('−', '-')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', compact):
        return None
    value = float(compact)
    decimals = len(compact.partition('.')[2])
    return value, .5 * 10 ** (-decimals)


def label_key(text):
    return re.sub(r'\s+', ' ', text).strip().rstrip(' ?').strip()


def paired_row(records, key, label):
    matches = [r for r in records if (r['market'], r['phase'], r['round'], r['panel']) == key
               and r['identity_status'] == 'verified' and r['cells']
               and label_key(r['cells'][0]) == label_key(label) and len(r['cells']) > 2]
    # A wider row contains real extra cells: never truncate it to the ten-team roster.
    return matches[0] if len(matches) == 1 and len(matches[0]['cells']) == 11 and len(matches[0]['team_order']) == 10 else None


def row_reference(rec):
    return {k: rec[k] for k in ('source', 'sha256', 'table_index', 'row_index', 'section_path', 'unit_context', 'team_order', 'html_source', 'html_sha256') if k in rec}


def printable_references():
    refs = {}
    paths = list((ROOT / 'raw/cross_market').glob('market_*.json'))
    paths += list((ROOT / 'output/formal_update/20261011T223000+0800_sources').glob('market_*_formal1.json'))
    for path in paths:
        doc = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)
        if doc.get('kind') != 'actual_result' or not doc.get('selection_verified'):
            continue
        selection = ROOT / doc['selection_file']
        if not selection.is_file():
            continue
        snapshot = json.loads(selection.read_text(encoding='utf-8-sig')).get('snapshot', '')
        if not all(f'option "{doc[field]}" [selected]' in snapshot for field in ('selected_market', 'selected_round')):
            continue
        rows = table_rows(doc.get('snapshot', ''))
        labels = set(r['cells'][0].strip() for r in rows if r['cells'])
        refs[(doc['market_id'], doc['phase'], doc['round'])] = {
            'source': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
            'selection_source': selection.relative_to(ROOT).as_posix(), 'selection_sha256': sha(selection),
            'labels': labels, 'has_literal_chart_json': bool(charts(doc.get('snapshot', ''))[0])}
    return refs


def selfcheck():
    doc = {'market': 5, 'phase': 'formal', 'round': 2, 'panel': 'summary',
           'source_url': 'https://example/Results?panel=summary',
           'selected': [{'label': '市场 5', 'value': '4', 'options': [{'label': '市场 5', 'value': '4'}]},
                        {'label': '回合2', 'value': '4', 'options': [{'label': '回合2', 'value': '4'}]}]}
    assert not identity(doc)
    assert 'selected_metadata_mismatch' in identity(dict(doc, market=4))
    assert 'url_panel_mismatch' in identity(dict(doc, panel='market'))
    misleading = dict(doc, selected=[dict(doc['selected'][0], value='3'), doc['selected'][1]])
    assert 'selected_option_value_mismatch' in identity(misleading)
    chart_duplicate, duplicate_errors = charts('Chart.create("x", "line", {"value":1,"value":2})')
    assert not chart_duplicate and duplicate_errors
    decoded, errors = charts('Chart.create("x", "line", {"dataset":[{"data":[{"value":1.123456789012345}]}]}, "c");')
    assert not errors and decoded[0]['data']['dataset'][0]['data'][0]['value'] == 1.123456789012345
    assert charts('Chart.create("x", "line", window.secret)')[1]
    assert len(coverage({}, ['summary'])) == 50 and all(x['status'] == 'pending' for x in coverage({}, ['summary']))
    try:
        json.loads('{"a":1,"a":2}', object_pairs_hook=unique_object)
        raise AssertionError('duplicate JSON keys accepted')
    except ValueError:
        pass
    assert num('1\u00a0234.50') == (1234.5, .005)
    parsed, basis = get_tables({'html': '<table><tr><td>连接件</td><td><input value="27.5"></td></tr></table>', 'tables': [[['', '']]]})
    assert parsed == [[['连接件', '27.5']]] and basis == 'html_textcontent_fallback'
    assert label_key('直接税\n        \n            ?') == '直接税'
    assert label_key('已收预付款变化(增 + / 减 -)\n ?') == '已收预付款变化(增 + / 减 -)'
    boundary = {'market': 2, 'phase': 'practice', 'round': 1, 'panel': 'balancesheet',
                'identity_status': 'verified', 'cells': ['资产 总计'] + ['29 144'] * 12, 'team_order': list(range(10))}
    assert paired_row([boundary], (2, 'practice', 1, 'balancesheet'), '资产 总计') is None
    narrow = dict(boundary, cells=['资产 总计'] + ['29 144'] * 10)
    assert paired_row([narrow], (2, 'practice', 1, 'balancesheet'), '资产 总计') == narrow
    assert paired_row([narrow, narrow], (2, 'practice', 1, 'balancesheet'), '资产 总计') is None
    assert num('NaN') is None
    return {'selection_mismatch_rejected': True, 'literal_chart_precision': True,
            'nonliteral_js_rejected': True, 'missing_coverage_pending': True,
            'duplicate_keys_detected': True, 'display_tolerance': True, 'hidden_tab_table_fallback': True,
            'help_label_whitespace': True, 'extra_cells_and_duplicate_labels_rejected': True, 'nan_not_zero': True}


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--final', action='store_true')
    opt = args.parse_args()
    if opt.final and not ((BASE / 'round3_complete.json').is_file() and
                          any((BASE / name).is_file() for name in ('history_complete.json', 'history_blocker.json', 'history_paused.json'))):
        raise RuntimeError('final audit requires round3 marker and history complete/blocker marker')
    run = BASE / 'audit' / datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S.%f+0800')
    run.mkdir(parents=True, exist_ok=False)
    with (BASE / 'audit' / 'work_log.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n{now()} START {run.name}; local read-only audit; no decisions/model/latest changes.\n')
    checks = selfcheck()
    sources, records, valid, failures, chart_index, financial, input_index, structural = [], [], {}, [], [], [], [], []
    panels = set(PANELS)
    datasets = {}
    current_root = BASE / 'resume/20261013T_goal/current_2026-10-13T082849281Z/raw'
    for path in sorted(list((BASE / 'raw').rglob('*.json')) + list(current_root.glob('*.json'))):
        fingerprint = sha(path)
        source = path.relative_to(BASE).as_posix()
        try:
            doc = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)
        except (ValueError, OSError) as error:
            failures.append({'source': source, 'error': str(error)})
            continue
        if not isinstance(doc, dict):
            continue
        doc = normalize(doc, path.name)
        html_source, html_fingerprint = source, fingerprint
        supplement = BASE / 'supplements/html' / (path.stem + '_complete_html.json')
        if supplement.is_file():
            extra = json.loads(supplement.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)
            selected = [dict(s, options=s.get('options', old.get('options', []))) for s in extra.get('selected', [])
                        for old in doc.get('selected', []) if (s['label'], s['value']) == (old['label'], old['value'])]
            if (extra.get('source_original') != source or extra.get('kind') != 'html_supplement'
                    or any(extra.get(k) != doc.get(k) for k in ('market', 'phase', 'round', 'panel'))
                    or identity(dict(extra, selected=selected)) or not extra['html'].rstrip().endswith('</html>')
                    or '[Truncated]' in extra['html']
                    or len(extra['html'].encode('utf-16-le')) // 2 != extra.get('html_length')):
                raise ValueError('invalid HTML supplement: ' + supplement.name)
            html_source, html_fingerprint = supplement.relative_to(BASE).as_posix(), sha(supplement)
            content_errors = []
            if doc.get('panel') == 'summary':
                extracted, parse_errors = charts(extra['html'])
                earnings = [c for c in extracted if c['id'] == 'Graphs.Results.Summary.CumulEarnings.TimeSeries.summary']
                if len(earnings) != 1:
                    content_errors.append('summary_earnings_chart_missing_or_ambiguous')
                else:
                    data = earnings[0]['data']
                    periods = [c['label'] for c in data['categories'][0]['category']]
                    slot = periods.index(str(doc['round'])) if str(doc['round']) in periods else None
                    if slot is None or any(num(str(s['data'][slot]['value'])) is None for s in data['dataset']):
                        content_errors.append('selected_round_has_no_earnings_in_chart; stale_content')
            sources.append({'source': html_source, 'sha256': html_fingerprint, 'kind': 'html_supplement',
                            'source_original': source, 'identity_status': 'rejected' if content_errors else 'verified', 'errors': content_errors})
            if content_errors:
                failures.append({'source': html_source, 'errors': content_errors, 'original_retained': source})
                html_source, html_fingerprint = source, fingerprint
            else:
                doc.update(html=extra['html'], tables=extra.get('tables', []))
        tables, table_basis = get_tables(doc)
        doc['tables'] = tables
        actual = doc.get('kind') == 'actual_result' or (doc.get('panel') in PANELS and 'Results' in doc.get('source_url', ''))
        current = (path.name.startswith('round3_') or path.parent == current_root) and not actual
        errors = identity(doc) if actual else current_identity(doc) if current else []
        source_info = {'source': source, 'sha256': fingerprint, 'captured_at': doc.get('captured_at'),
                       'source_url': doc.get('source_url'), 'market': doc.get('market'), 'phase': doc.get('phase'),
                       'round': doc.get('round'), 'panel': doc.get('panel'), 'kind': doc.get('kind'),
                       'identity_status': 'rejected' if errors else 'verified' if actual else 'current_state_verified' if current else 'non_result_identity_pending',
                       'errors': errors, 'html_source': html_source, 'html_sha256': html_fingerprint}
        sources.append(source_info)
        if errors:
            failures.append({'source': source, 'errors': errors})
        if actual and not errors:
            key = (doc['market'], doc['phase'], doc['round'], doc['panel'])
            valid.setdefault(key, []).append(source)
            datasets.setdefault(key, doc)
        # Navigation discovers actual result panels; printable never counts as an independent page.
        if actual:
            links_text = json.dumps(doc.get('links', doc.get('navigation', [])))
            panels.update(p for p in re.findall(r'panel=([a-zA-Z]+)', links_text) if p not in ('printable', 'slides'))
        for ii, item in enumerate(doc.get('inputs', [])):
            input_index.append({**source_info, 'input_index': ii, 'input': item,
                                'category': 'current_input_or_player_forecast; field name retained, never actual result'})
        for ti, table in enumerate(tables):
            if isinstance(table, dict):
                table = table.get('rows', [])
            headers, context = [], []
            column_roles = []
            budget_table = not actual and any(isinstance(r, list) and '今年' in r and '去年' in r for r in table)
            for ri, row in enumerate(table):
                if not isinstance(row, list):
                    continue
                cells = [redact_names(str(c)) for c in row]
                if '今年' in cells and '去年' in cells:
                    column_roles = cells.copy()
                if len(cells) == 11 and not cells[0].strip():
                    headers = cells[1:]
                    if len(set(headers)) != len(headers):
                        structural.append({'source': source, 'table_index': ti, 'row_index': ri, 'check': 'duplicate_team_headers', 'status': 'fail'})
                elif actual and headers and len(cells) > 2 and len(cells) != len(headers) + 1:
                    structural.append({'source': source, 'table_index': ti, 'row_index': ri, 'check': 'row_width_vs_team_order',
                                       'status': 'review', 'width': len(cells), 'expected': len(headers) + 1,
                                       'reason': 'extra_source_cells_preserved; no_truncation', 'sha256': fingerprint})
                    if not cells[0].strip() and cells[1:len(headers) + 1] != headers:
                        structural.append({'source': source, 'table_index': ti, 'row_index': ri,
                                           'check': 'extra_header_prefix_disagrees', 'status': 'fail'})
                        headers = []
                if len(cells) in (1, 2) and cells[0].strip() and len(cells[0]) < 100:
                    context.append(cells[0])
                category = 'actual_result' if actual else 'platform_budget' if budget_table else doc.get('kind', 'unclassified')
                label = cells[0] if cells else ''
                semantic_section = next((label_key(s) for s in reversed(context)
                                         if re.search(r'销售|需求|预测|预算|价格|份额|订单|库存', s)), '')
                if budget_table:
                    category = 'platform_budget_with_prior_actual_columns'
                elif '预测' in label or '预测' in semantic_section:
                    category = 'player_forecast_or_forecast_field_requires_review'
                elif '预算' in label or 'budget' in category:
                    category = 'platform_budget'
                elif '需求' in label or '需求' in semantic_section:
                    category = 'actual_demand' if actual else 'demand_field_not_actual'
                elif '销量' in label or '销售, 千单位' in semantic_section:
                    category = 'actual_sales' if actual else 'sales_field_not_actual'
                records.append({**source_info, 'table_index': ti, 'row_index': ri, 'cells': cells,
                                'table_basis': table_basis,
                                'column_roles': column_roles.copy(),
                                'cell_categories': ['label' if i == 0 else 'prior_actual_context' if i < len(column_roles) and column_roles[i] == '去年'
                                                    else 'displayed_change_or_ratio' if i < len(column_roles) and column_roles[i] in ('Δ %', '%', '收入占比%', '净销售收入占比%')
                                                    else 'platform_budget' if budget_table else category for i in range(len(cells))],
                                'team_order': headers.copy(), 'section_path': context.copy(),
                                'category': category, 'unit_context': [s for s in context + [label] if re.search(r'单位|美元|千|%|kg|kWh|人', s)],
                                'semantic_section': semantic_section,
                                'product_context': [s for s in context + [label] if '复合梁' in s or '连接件' in s]})
        script_text = doc.get('html') or '\n'.join(doc.get('scripts', []))
        extracted, parse_errors = charts(script_text)
        if not extracted and isinstance(doc.get('charts'), list):
            extracted = doc['charts']
        for ci, chart in enumerate(extracted):
            chart_index.append({**source_info, 'chart_index': ci, 'chart': chart,
                                'precision': 'original JSON values; category labels may be rounded; NaN strings retained'})
        if parse_errors:
            failures.append({'source': source, 'chart_parse_errors': parse_errors})
        source_info.update(table_count=len(tables), table_basis=table_basis, chart_count=len(extracted), svg_count=len(doc.get('svg', doc.get('svgs', []))))

    def row(key, label):
        rec = paired_row(records, key, label)
        return rec['cells'][1:] if rec else None

    def equation(key, name, terms):
        paired = [paired_row(records, key, label) for label, sign in terms]
        values = [row(key, label) for label, sign in terms]
        if any(v is None for v in values):
            financial.append({'key': key, 'check': name, 'status': 'pending', 'missing_or_ambiguous_labels':
                              [terms[i][0] for i, v in enumerate(values) if v is None],
                              'reason': 'missing_ambiguous_or_width_mismatch; no_truncation', 'sources': valid.get(key)})
            return
        if any(rec['team_order'] != paired[0]['team_order'] for rec in paired):
            financial.append({'key': key, 'check': name, 'status': 'pending', 'reason': 'team_order_mismatch'})
            return
        for team in range(10):
            parsed = [num(v[team]) for v in values]
            if any(x is None for x in parsed):
                financial.append({'key': key, 'team_column_index': team + 1, 'check': name,
                                  'status': 'pending', 'reason': 'non_numeric_source_not_zero', 'sources': valid.get(key)})
                continue
            residual = sum(x[0] * terms[i][1] for i, x in enumerate(parsed))
            tolerance = sum(x[1] * abs(terms[i][1]) for i, x in enumerate(parsed)) + 1e-9
            financial.append({'key': key, 'team_column_index': team + 1, 'check': name,
                              'residual': residual, 'rounding_tolerance': tolerance,
                              'status': 'pass' if abs(residual) <= tolerance else 'fail',
                              'terms': terms, 'team': paired[0]['team_order'][team], 'unit': '千 美元' if key[-1] in ('balancesheet', 'incomestatement', 'cashflow') else '千单位',
                              'sources': [row_reference(rec) for rec in paired]})

    for key in datasets:
        if key[-1] == 'balancesheet':
            equation(key, 'assets_equal_liabilities_equity', [('资产 总计', 1), ('负债与所有者权益总计', -1)])
            equation(key, 'fixed_assets_components', [('固定资产总和', 1), ('厂房', -1), ('机器', -1)])
            equation(key, 'current_assets_components', [('总流动资产', 1), ('成品库存', -1), ('应收帐款', -1), ('现金及现金等价物', -1)])
            equation(key, 'liabilities_components', [('负债合计', 1), ('长期贷款', -1), ('短期贷款', -1), ('已收预付款', -1), ('应付账款', -1)])
        elif key[-1] == 'incomestatement':
            equation(key, 'gross_profit', [('毛利', 1), ('净销售额', -1), ('可变成本总和', 1)])
            equation(key, 'ebitda', [('税息折旧及摊销前利润（EBITDA）', 1), ('毛利', -1), ('营销和销售成本总和', 1), ('杂费成本总和', 1)])
            equation(key, 'ebit', [('息税前利润（EBIT）', 1), ('税息折旧及摊销前利润（EBITDA）', -1), ('厂房', 1), ('机器', 1)])
            equation(key, 'pretax_profit', [('税前利润', 1), ('息税前利润（EBIT）', -1), ('利息收入', -1), ('长期贷款利息', 1), ('短期贷款利息', 1)])
            equation(key, 'aftertax_profit', [('本回合利润', 1), ('税前利润', -1), ('直接税', 1)])
        elif key[-1] == 'cashflow':
            equation(key, 'working_capital_movements', [('净营运资本总额变化（增加-/减少+）', 1), ('库存变化(增 - / 减 +)', -1), ('应收帐变化(增 - / 减 +)', -1), ('应付账变化(增 + / 减 -)', -1), ('已收预付款变化(增 + / 减 -)', -1)])
            equation(key, 'operating_cashflow', [('经营活动现金流', 1), ('营运资金总计', -1), ('净营运资本总额变化（增加-/减少+）', -1)])
            equation(key, 'prefinancing_cashflow', [('融资前现金流', 1), ('经营活动现金流', -1), ('资本支出总计', -1)])
            equation(key, 'financing_total', [('融资总计', 1), ('长期贷款变化(增加 + / 减少 -)', -1), ('短期贷款变化(增加 + / 减少 -)', -1)])
            equation(key, 'cash_change', [('流动资产变化', 1), ('融资前现金流', -1), ('融资总计', -1)])
            equation(key, 'cash_bridge', [('12月31日的流动资产', 1), ('1月1日的流动资产', -1), ('流动资产变化', -1)])
        elif key[-1] == 'logisticsdetails':
            equation(key, 'production_shipping_bulk', [('来自于生产', 1), ('大客户订单', -1), ('运往 泰国', -1), ('运往 印尼', -1)])
        elif key[-1] == 'summary':
            m, phase, r, panel = key
            if phase == 'initial':
                financial.append({'key': key, 'check': 'cumulative_profit_difference', 'status': 'not_applicable_initial_base'})
                continue
            prev = (m, phase, r - 1, panel) if r > 1 else (m, 'initial', 0, panel)
            current, previous, profit = row(key, '累计收益'), row(prev, '累计收益'), row(key, '本回合利润')
            paired = [paired_row(records, k, label) for k, label in
                      [(key, '累计收益'), (prev, '累计收益'), (key, '本回合利润')]]
            if all(paired) and any(rec['team_order'] != paired[0]['team_order'] for rec in paired):
                financial.append({'key': key, 'check': 'cumulative_profit_difference', 'status': 'pending', 'reason': 'team_order_mismatch'})
                continue
            if current and previous and profit:
                for i in range(10):
                    a, b, c = num(current[i]), num(previous[i]), num(profit[i])
                    if not all((a, b, c)):
                        financial.append({'key': key, 'check': 'cumulative_profit_difference', 'team_column_index': i + 1,
                                          'status': 'pending', 'reason': 'non_numeric_source_not_zero'})
                        continue
                    residual, tolerance = a[0] - b[0] - c[0], a[1] + b[1] + c[1] + 1e-9
                    financial.append({'key': key, 'check': 'cumulative_profit_difference', 'team_column_index': i + 1,
                                      'residual': residual, 'rounding_tolerance': tolerance,
                                      'status': 'pass' if abs(residual) <= tolerance else 'fail',
                                      'previous_key': prev, 'team': paired[0]['team_order'][i], 'unit': '千 美元',
                                      'baseline': 'initial0_including_displayed_initial_earnings' if r == 1 else 'same_phase_previous_round',
                                      'sources': [row_reference(rec) for rec in paired]})
            else:
                financial.append({'key': key, 'check': 'cumulative_profit_difference', 'status': 'pending', 'previous_key': prev})
    quantities = {}
    for rec in records:
        if rec['identity_status'] != 'verified' or len(rec['cells']) != 11 or rec['cells'][0] not in ('泰国', '印尼') or rec['panel'] not in ('marketdetails', 'logisticsdetails'):
            continue
        section = rec['semantic_section']
        metric = 'sales' if section == '销售, 千单位' else 'demand' if section == '需求, 千单位' else 'unmet' if section == '未满足需求, 千单位' else None
        if metric is None:
            continue
        product = next((p for s in reversed(rec['product_context']) for p in ('连接件', '复合梁') if p in s), None)
        qkey = (rec['market'], rec['phase'], rec['round'], product, rec['cells'][0])
        quantities.setdefault(qkey, {}).setdefault(metric, []).append(rec)
    for qkey, metrics in quantities.items():
        if any(len(metrics.get(k, [])) != 1 for k in ('demand', 'sales', 'unmet')):
            financial.append({'key': qkey, 'check': 'demand_sales_unmet', 'status': 'pending',
                              'metric_occurrences': {k: len(v) for k, v in metrics.items()}})
            continue
        paired = [metrics[k][0] for k in ('demand', 'sales', 'unmet')]
        if any(rec['team_order'] != paired[0]['team_order'] for rec in paired):
            financial.append({'key': qkey, 'check': 'demand_sales_unmet', 'status': 'pending', 'reason': 'team_order_mismatch'})
            continue
        for i in range(1, 11):
            a, b, c = [num(rec['cells'][i]) for rec in paired]
            if not all((a, b, c)):
                financial.append({'key': qkey, 'check': 'demand_sales_unmet', 'team_column_index': i,
                                  'status': 'pending', 'reason': 'non_numeric_source_not_zero'})
                continue
            residual, tolerance = a[0] - b[0] - c[0], a[1] + b[1] + c[1] + 1e-9
            financial.append({'key': qkey, 'check': 'demand_sales_unmet', 'team_column_index': i,
                              'residual': residual, 'rounding_tolerance': tolerance,
                              'status': 'pass' if abs(residual) <= tolerance else 'fail',
                              'team': paired[0]['team_order'][i - 1], 'unit': '千单位',
                              'supply_limit': 'sales_supply_censored; demand_and_unmet_retained',
                              'sources': [row_reference(rec) for rec in paired]})
    matrix = coverage(valid, panels)
    print_refs = printable_references()
    supplement = []
    for rec in records:
        if rec['identity_status'] != 'verified' or len(rec['cells']) != 11 or not rec['cells'][0].strip():
            continue
        ref = print_refs.get((rec['market'], rec['phase'], rec['round']))
        if ref and rec['cells'][0].strip() not in ref['labels']:
            supplement.append({'source': rec['source'], 'source_sha256': rec['sha256'], 'panel': rec['panel'],
                               'table_index': rec['table_index'], 'row_index': rec['row_index'], 'label': rec['cells'][0],
                               'printable_source': ref['source'], 'printable_sha256': ref['sha256'],
                               'status': 'exact_label_not_in_paired_printable; aliases_require_review'})
    duplicates = [{'key': k, 'sources': v} for k, v in valid.items() if len(v) > 1]
    team_orders = {}
    for rec in records:
        if rec['identity_status'] == 'verified' and rec['team_order']:
            period_key = (rec['market'], rec['phase'], rec['round'])
            order = team_orders.setdefault(period_key, rec['team_order'])
            if order != rec['team_order']:
                structural.append({'source': rec['source'], 'check': 'team_order_differs_within_period', 'status': 'fail',
                                   'table_index': rec['table_index'], 'row_index': rec['row_index']})
    markers = {name: [p.relative_to(BASE).as_posix() for p in BASE.rglob(name)] for name in
               ['history_complete.json', 'history_blocker.json', 'history_paused.json', 'round3_complete.json']}
    marker_summary = []
    for name, paths in markers.items():
        for marker_path in paths:
            data = json.loads((BASE / marker_path).read_text(encoding='utf-8-sig'))
            marker_summary.append({'source': marker_path, 'sha256': sha(BASE / marker_path), 'type': name,
                                   'status': data.get('status'), 'gaps': data.get('gaps', []),
                                   'reason': data.get('reason') or data.get('error') or data.get('blocker')})
    attempt_index = [{'source': p.relative_to(BASE).as_posix(), 'sha256': sha(p),
                      'record': json.loads(p.read_text(encoding='utf-8-sig'))}
                     for p in sorted(BASE.glob('history_batch*.json'))]
    changed = [s['source'] for s in sources if sha(BASE / s['source']) != s['sha256']]
    baseline_hashes = {}
    for previous_manifest in sorted((BASE / 'audit').glob('20*/sources.json')):
        for old in json.loads(previous_manifest.read_text(encoding='utf-8')):
            baseline_hashes.setdefault(old['source'], old['sha256'])
    historic_changes = [s['source'] for s in sources if s['source'] in baseline_hashes and baseline_hashes[s['source']] != s['sha256']]
    counts = Counter(x['status'] for x in matrix)
    status = 'INCOMPLETE' if counts['pending'] or failures or changed or historic_changes or any(x['status'] == 'fail' for x in financial + structural) else 'VERIFIED'
    data_status = status
    # Pause files are evidence of an earlier run, not instructions for this audit.
    if status == 'VERIFIED' and (any(x['status'] == 'pending' for x in financial) or structural):
        status = 'PAIRING_REVIEW_REQUIRED'
    data_status = status
    validation = {'generated_at': now(), 'status': status, 'data_status': data_status, 'final_requested': opt.final, 'selfchecks': checks,
                  'coverage_counts': dict(counts), 'source_count': len(sources), 'row_count': len(records),
                  'chart_count': len(chart_index), 'duplicate_page_keys': duplicates, 'failures': failures,
                  'paired_printable_periods': len(print_refs), 'exact_label_supplement_rows': len(supplement),
                  'source_hash_changes_during_run': changed, 'markers': markers, 'marker_summary': marker_summary,
                  'source_hash_changes_since_first_audit': historic_changes,
                  'financial_counts': dict(Counter(x['status'] for x in financial)),
                  'structure_counts': dict(Counter(x['status'] for x in structural)),
                  'pending': [f'financial_pending={sum(x["status"] == "pending" for x in financial)}',
                              f'structure_review={sum(x["status"] == "review" for x in structural)}',
                              'rejected evidence remains historical; see failures',
                              'unknown roster members require initials mapping before sharing'],
                  'name_check': {'known_project_roster_redacted': True, 'unknown_people_not_certified': True},
                  'decision_modified': False, 'model_trained': False, 'latest_changed': False}
    save(run / 'sources.json', sources)
    save(run / 'rows.json', records)
    save(run / 'inputs.json', input_index)
    save(run / 'charts.json', chart_index)
    save(run / 'coverage.json', matrix)
    save(run / 'financial_checks.json', financial)
    save(run / 'structure_checks.json', structural)
    save(run / 'capture_attempts.json', attempt_index)
    save(run / 'printable_supplement.json', supplement)
    save(run / 'printable_references.json', [{**{k: v for k, v in ref.items() if k != 'labels'}, 'key': key,
                                            'label_count': len(ref['labels'])} for key, ref in print_refs.items()])
    save(run / 'code_snapshot.json', {'script_sha256': sha(Path(__file__)), 'parser_sha256': sha(ROOT / 'code/archive_and_report.py')})
    with (run / 'verify_archive.py').open('x', encoding='utf-8') as stream:
        stream.write(Path(__file__).read_text(encoding='utf-8'))
    with (run / 'parser_snapshot.py').open('x', encoding='utf-8') as stream:
        stream.write((ROOT / 'code/archive_and_report.py').read_text(encoding='utf-8'))
    with (run / 'coverage.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['market', 'phase', 'round', 'panel', 'panel_name', 'status', 'sources'])
        for x in matrix:
            writer.writerow([x[k] for k in ['market', 'phase', 'round', 'panel', 'panel_name', 'status']] + [';'.join(x['sources'])])
    report = (f'# 本地逐栏核验\n\n状态：{status}。{len(sources)}份来源、{len(records)}表格行、'
              f'{len(chart_index)}条全精度JSON图表初始化记录；覆盖{counts["verified"]}/{len(matrix)}独立页面。\n\n'
              '范围为市场1–10、初始0、练习1/2、正式1/2。URL panel与真实selected市场、历史回合及选项值同时匹配才计入覆盖。'
              '可打印报告不计独立逐栏完成。重复标签按表格/行号保留，单位和产品上下文不删除，连接件与复合梁保留原维度。\n\n'
              '本次新增独立子栏证据包括市场明细、生产明细/环境/人力、物流明细/排放、财务三表及社会影响；'
              '逐页图表保存原始JSON浮点数和NaN字符串，没有执行网页脚本。是否属于打印版没有的具体字段仍须逐项对照，不能仅凭子栏名认定。\n\n'
              f'已配对{len(print_refs)}个市场/历史回合的旧打印原件及独立选择证据；{len(supplement)}行同名标签未出现于配对打印原件，详见printable_supplement.json。'
              '标签别名和单位写法仍需审查，这些差异不能全部算作新字段；本次保存的逐页全精度图表JSON不能由旧打印快照的舍入表格替代。\n\n'
              f'财务检查：{dict(Counter(x["status"] for x in financial))}。残差与各单元格显示精度合计容差保留在financial_checks.json。\n\n'
              '详情：coverage.csv为覆盖矩阵，rows.json保留逐表行、队列、类别、单位和来源SHA256，charts.json为JSON图表索引。'
              '缺失、拒绝、重复键和完成标记见validation.json。未采集不补零；完成标记只表示采集任务结束，缺口仍按原件核验结果保留。\n\n'
              + '\n'.join('采集标记 ' + str(m['source']) + '：' + str(m['status']) + '；缺口：' + '；'.join(map(str, m['gaps'])) for m in marker_summary) + '\n\n'
              '姓名：已按项目既有哈希映射处理四名已知人员，未知人员仍需映射审查；原件未改。'
              '没有评分或重训模型，没有改变latest、README、工作清单或任何平台决策。\n')
    report += '\n身份未通过的来源及原因：\n\n' + '\n'.join('- ' + str(x['source']) + '：' + str(x.get('errors') or x.get('chart_parse_errors') or x.get('error')) for x in failures) + '\n'
    supplement_by_panel = {}
    for item in supplement:
        supplement_by_panel.setdefault(item['panel'], set()).add(item['label'])
    report += '\n打印快照同名字段缺口（逐行来源见printable_supplement.json，别名仍待审查）：\n\n'
    report += '\n'.join('- ' + panel + '：' + '；'.join(sorted(labels)) for panel, labels in sorted(supplement_by_panel.items())) + '\n'
    with (run / 'report.md').open('x', encoding='utf-8') as stream:
        stream.write(redact_names(report))
    generated = [p for p in run.iterdir() if p.suffix in ('.json', '.md', '.py', '.csv')]
    name_failures = [p.name for p in generated if redact_names(p.read_text(encoding='utf-8-sig')) != p.read_text(encoding='utf-8-sig')]
    validation['name_check'].update(generated_files_checked=len(generated), known_roster_failures=name_failures)
    if name_failures:
        validation['status'] = status = 'INCOMPLETE_NAME_REVIEW'
    save(run / 'validation.json', validation)
    if opt.final:
        validation['artifact_run'] = run.relative_to(BASE).as_posix()
        save(BASE / 'audit' / 'validation.json', validation)
        with (BASE / 'audit' / 'report.md').open('x', encoding='utf-8') as stream:
            stream.write(redact_names(report) + f'\n本次完整产物：[核验目录报告]({run.as_posix()}/report.md)。\n')
    with (BASE / 'audit' / 'work_log.md').open('a', encoding='utf-8') as stream:
        stream.write(f'{now()} END {status}; sources={len(sources)}; coverage={counts["verified"]}/{len(matrix)}; output={run.name}.\n')
    print(json.dumps({'run': str(run), 'status': status, 'coverage': dict(counts), 'rows': len(records), 'charts': len(chart_index), 'failures': len(failures)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
