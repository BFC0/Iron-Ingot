"""Read-only formal 3 audit; run against captured raw directory, never platform."""
import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
OLD = ROOT / 'output/round_close/20261012T221044.031+0800/audit/verify_archive.py'
spec = importlib.util.spec_from_file_location('historical_archive_rules', OLD)
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)
PANELS = rules.PANELS


def full_html(text, expected=None):
    return bool(text) and '[Truncated]' not in text and bool(re.search(r'</html>\s*$', text, re.I)) and (expected is None or len(text.encode('utf-16-le')) // 2 == expected)


def selected(doc):
    return [s['selected'] if isinstance(s.get('selected'), str) else o['text']
            for s in doc.get('selects', []) for o in ([{}] if isinstance(s.get('selected'), str)
                else [o for o in s.get('options', []) if o.get('selected')])]


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(rules.redact_names(json.dumps(value, ensure_ascii=False, indent=2)))


def rows_for(doc, source):
    tables, basis = rules.get_tables(doc)
    records, reviews = [], []
    for ti, table in enumerate(tables):
        if isinstance(table, dict):
            table = table.get('rows', [])
        headers, context, semantic = [], [], ''
        for ri, row in enumerate(table):
            cells = [rules.redact_names(str(c)) for c in row]
            label = cells[0] if cells else ''
            if cells and not label.strip() and len(cells) > 2:
                headers = cells[1:]
                if len(headers) != 10 or len(set(headers)) != 10:
                    reviews.append(dict(source=source['source'], table_index=ti, row_index=ri,
                                        check='team_header_count_or_duplicates', cells=cells))
            elif len(cells) == 1 and label.strip() and len(label) < 100:
                context.append(label)
                if re.search(r'销售|需求|预测|预算|价格|份额|订单|库存', label):
                    semantic = label
            numeric = [rules.num(c) for c in cells[1:]]
            mapped = bool(headers and len(headers) == 10 and len(cells) == 11 and len(set(headers)) == 10)
            if headers and len(cells) > 2 and not mapped:
                reviews.append(dict(source=source['source'], table_index=ti, row_index=ri,
                                    check='width_mismatch_no_truncation', expected=11, cells=cells))
            category = ('forecast_field_requires_review' if '预测' in label + semantic else
                        'actual_demand' if '需求' in label + semantic else
                        'actual_sales' if '销售, 千单位' in semantic else 'actual_result')
            records.append(dict(source=source['source'], sha256=source['sha256'], market=source['market'],
                                phase='formal', round=3, panel=source['panel'], table_index=ti, row_index=ri,
                                cells=cells, label=label, team_order=headers.copy(), section_path=context.copy(),
                                semantic_section=semantic, category=category, table_basis=basis,
                                unit_context=[c for c in context + [label] if re.search(r'美元|单位|%|kg|kWh|人', c)],
                                team_mapping_valid=mapped,
                                numeric_by_team=[dict(team_column_index=i+1, team=headers[i], display=cells[i+1],
                                                     value=n[0] if n else None, rounding_half_step=n[1] if n else None)
                                                 for i, n in enumerate(numeric)] if mapped else []))
    return records, reviews, basis


def financial_checks(records, valid_keys):
    # Reuse frozen accounting signs and displayed precision; ambiguous rows stay pending.
    equations = {
        'balancesheet': [('assets_equal_liabilities_equity', [('资产 总计', 1), ('负债与所有者权益总计', -1)]),
                        ('fixed_assets_components', [('固定资产总和', 1), ('厂房', -1), ('机器', -1)])],
        'incomestatement': [('gross_profit', [('毛利', 1), ('净销售额', -1), ('可变成本总和', 1)]),
                           ('aftertax_profit', [('本回合利润', 1), ('税前利润', -1), ('直接税', 1)])],
        'cashflow': [('cash_bridge', [('12月31日的流动资产', 1), ('1月1日的流动资产', -1), ('流动资产变化', -1)])]}
    checks = []
    for market, panel in valid_keys:
        for name, terms in equations.get(panel, []):
            paired = []
            for label, sign in terms:
                matches = [r for r in records if r['market'] == market and r['panel'] == panel and
                           rules.label_key(r['label']) == rules.label_key(label) and len(r['cells']) > 2]
                paired.append(matches[0] if len(matches) == 1 and matches[0]['team_mapping_valid'] else None)
            base = dict(market=market, round=3, panel=panel, check=name, terms=terms)
            if any(r is None for r in paired) or any(r['team_order'] != paired[0]['team_order'] for r in paired):
                checks.append(dict(base, status='pending', reason='missing_duplicate_width_or_team_order; no_truncation'))
                continue
            for i in range(10):
                numbers = [r['numeric_by_team'][i] for r in paired]
                if any(n['value'] is None for n in numbers):
                    checks.append(dict(base, team_column_index=i+1, status='pending', reason='non_numeric_not_zero'))
                    continue
                residual = sum(n['value'] * sign for n, (_, sign) in zip(numbers, terms))
                tolerance = sum(n['rounding_half_step'] * abs(sign) for n, (_, sign) in zip(numbers, terms)) + 1e-9
                checks.append(dict(base, team_column_index=i+1, team=paired[0]['team_order'][i],
                                   residual=residual, tolerance=tolerance, status='pass' if abs(residual) <= tolerance else 'fail',
                                   source_rows=[dict(source=r['source'], table_index=r['table_index'], row_index=r['row_index']) for r in paired]))
    return checks


def cumulative_checks(records, prior_rows):
    checks = []
    history_root = OLD.parent.parent
    for market in sorted({r['market'] for r in records if r['panel'] == 'summary'}):
        current = [r for r in records if r['market'] == market and r['panel'] == 'summary'
                   and r['label'] == '累计收益' and r['team_mapping_valid']]
        profit = [r for r in records if r['market'] == market and r['panel'] == 'summary'
                  and r['label'] == '本回合利润' and r['team_mapping_valid']]
        prior = [r for r in prior_rows if r['market'] == market and r['phase'] == 'formal'
                 and r['round'] == 2 and r['panel'] == 'summary' and r['cells'][0] == '累计收益'
                 and len(r['cells']) == 11 and r['identity_status'] == 'verified']
        base = dict(market=market, round=3, panel='summary', check='cumulative_profit_bridge')
        if len(current) != 1 or len(profit) != 1 or len(prior) != 1:
            checks.append(dict(base, status='pending', reason='missing_or_ambiguous_team_mapping'))
            continue
        current, profit, prior = current[0], profit[0], prior[0]
        if current['team_order'] != profit['team_order'] or current['team_order'] != prior['team_order']:
            checks.append(dict(base, status='pending', reason='team_order_conflict'))
            continue
        if rules.sha(history_root / prior['source']) != prior['sha256'] or (prior.get('html_source') and
                rules.sha(history_root / prior['html_source']) != prior['html_sha256']):
            raise RuntimeError('Historical cumulative source hash changed')
        for i, team in enumerate(current['team_order']):
            values = [rules.num(current['cells'][i+1]), rules.num(prior['cells'][i+1]),
                      rules.num(profit['cells'][i+1])]
            if any(value is None for value in values):
                checks.append(dict(base, team=team, status='pending', reason='non_numeric_not_zero'))
                continue
            residual = values[0][0] - values[1][0] - values[2][0]
            tolerance = sum(value[1] for value in values) + 1e-9
            checks.append(dict(base, team=team, residual=residual, tolerance=tolerance,
                               status='pass' if abs(residual) <= tolerance else 'fail',
                               current_source=current['source'], profit_source=profit['source'],
                               previous_source=str((history_root / prior['source']).relative_to(ROOT)),
                               previous_sha256=prior['sha256'],
                               previous_table_index=prior['table_index'], previous_row_index=prior['row_index']))
    return checks


def main():
    assert full_html('<html></html>', 13) and not full_html('<html>[Truncated]')
    assert not full_html('<html></html>', 14)
    assert selected({'selects': [{'selected': '回合3'}]}) == ['回合3']
    assert rules.num('1\u00a0419') == (1419.0, .5) and rules.num('NaN') is None
    fake_source = dict(source='selfcheck', sha256='', market=5, panel='marketdetails')
    fake_headers = [''] + [f'T{i}' for i in range(10)]
    fake_doc = {'tables': [[fake_headers, ['销售, 千单位'], ['泰国'] + ['1.00'] * 10,
                           ['额外列'] + ['2'] * 11]], 'url': '/Results'}
    fake_rows, fake_reviews, _ = rows_for(fake_doc, fake_source)
    assert fake_rows[2]['team_mapping_valid'] and len(fake_rows[2]['numeric_by_team']) == 10
    assert not fake_rows[3]['team_mapping_valid'] and len(fake_rows[3]['cells']) == 12 and len(fake_reviews) == 1
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', type=Path, default=Path(__file__).resolve().parents[1] / 'raw')
    args = parser.parse_args()
    output = Path(__file__).parent / 'validation' / datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S.%f+0800')
    output.mkdir(parents=True, exist_ok=False)
    sources, candidates = [], {}
    for path in sorted(args.raw.glob('*.json')):
        doc = json.loads(path.read_text(encoding='utf-8-sig'))
        match = re.fullmatch(r'market(\d+)_formal3_([a-z]+)(?:_complete)?\.json', path.name)
        panel = match[2] if match else None
        market = int(match[1]) if match else None
        opts = selected(doc)
        html = doc.get('html', '')
        actual_panel = parse_qs(urlparse(doc.get('url', '')).query).get('panel', [None])[0]
        footer_market = bool(match and re.search(rf'市场\s*{market}\s*,', doc.get('text', '')))
        identity = bool(match and f'市场 {market}' in opts and '回合3' in opts and '/Results' in doc.get('url', '') and actual_panel == panel)
        source = dict(source=str(path.relative_to(ROOT)), sha256=rules.sha(path), captured_at=doc.get('captured_at'),
                      market=market, panel=panel, selections=opts, html_length=len(html), declared_html_length=doc.get('html_length'),
                      html_complete=full_html(html, doc.get('html_length')), identity_verified=identity, footer_market_verified=footer_market,
                      extracted_scripts=len(doc.get('scripts', [])), html_script_tags=len(re.findall(r'<script\b', html, re.I)),
                      category='metadata_or_outlook_or_other' if not match else 'formal3_actual_candidate')
        source['valid_page'] = bool(identity and source['html_complete'] and panel in PANELS)
        sources.append(source)
        if source['valid_page']:
            candidates.setdefault((market, panel), []).append((source, doc))
    records, reviews, charts, chosen = [], [], [], {}
    for key, options in candidates.items():
        source, doc = max(options, key=lambda item: item[0].get('captured_at') or '')
        chosen[key] = source
        extracted, structural, basis = rows_for(doc, source)
        records.extend(extracted)
        reviews.extend(structural)
        payloads, errors = rules.charts(doc['html'])
        if not payloads:
            payloads, errors = rules.charts('\n'.join(doc.get('scripts', [])))
        charts.extend(dict(source=source['source'], sha256=source['sha256'], market=key[0], round=3,
                           panel=key[1], chart_index=i, chart=chart) for i, chart in enumerate(payloads))
        numerical_rows = sum(bool(r['numeric_by_team']) and any(c['value'] is not None for c in r['numeric_by_team']) for r in extracted)
        source.update(table_count=len(doc.get('tables', [])), table_basis=basis, chart_count=len(payloads),
                      chart_parse_errors=errors, inline_svg_count=len(re.findall(r'<svg\b', doc['html'], re.I)),
                      numeric_team_rows=numerical_rows,
                      data_grade='table_and_chart' if numerical_rows and payloads else 'tables_only' if numerical_rows else 'chart_only' if payloads else 'no_numeric_data')
    matrix = [dict(market=m, phase='formal', round=3, panel=p, status='verified_complete_capture' if (m,p) in chosen else 'not_collected_or_rejected',
                   source=chosen.get((m,p), {}).get('source'), data_grade=chosen.get((m,p), {}).get('data_grade')) for m in range(1,11) for p in PANELS]
    finance = financial_checks(records, chosen)
    prior_file = OLD.parent / '20261013T170300.748980+0800/rows.json'
    prior_rows = json.loads(prior_file.read_text(encoding='utf-8-sig'))
    cumulative = cumulative_checks(records, prior_rows)
    observed_panels = {parse_qs(urlparse(link.get('url', '')).query).get('panel', [None])[0]
                       for options in candidates.values() for _, doc in options
                       for link in doc.get('links', []) if '/Results?' in link.get('url', '')}
    new_panels = sorted(p for p in observed_panels if p and p not in PANELS)
    changed = [s['source'] for s in sources if rules.sha(ROOT / s['source']) != s['sha256']]
    validation = dict(generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                      status='COMPLETE_CAPTURE_WITH_EXPLICIT_CHECK_RESULTS' if len(chosen)==150 else 'PARTIAL',
                      valid_complete_pages=len(chosen), required_base_pages=150,
                      observed_result_panels=sorted(p for p in observed_panels if p), new_result_panels=new_panels,
                      dynamic_new_panels_require_review=bool(new_panels),
                      raw_hash_changes=changed, row_count=len(records), chart_count=len(charts), structure_reviews=len(reviews),
                      financial_counts=dict(Counter(x['status'] for x in finance)), selfchecks_passed=True,
                      cumulative_counts=dict(Counter(x['status'] for x in cumulative)),
                      prior_rows_sha256=rules.sha(prior_file),
                      budget_used_as_actual=False, decisions_changed=False, tables_and_charts_are_same_source=True)
    for name, value in [('sources',sources), ('coverage',matrix), ('rows',records), ('charts',charts), ('structure_review',reviews), ('financial_checks',finance), ('cumulative_checks',cumulative), ('validation',validation)]:
        write(output / f'{name}.json', value)
    with (output / 'coverage.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(matrix[0]))
        writer.writeheader()
        writer.writerows(matrix)
    with (output / 'report.md').open('x', encoding='utf-8') as stream:
        stream.write(f'# 正式3独立离线验收\n\n完整采集且选择匹配{len(chosen)}/150页。逐市场覆盖见coverage.csv；采集完成不代表完整建模或跨期收益链已完成。保留全部{len(sources)}份来源哈希，metadata、截断件、前景均不计实际页；不同版本保留，择最新完整有效页结构化。新增结果栏目{new_panels}，已按原页导航核对。\n\n全部团队原列顺序与原table/row索引见rows.json；多列或重复表头不强配团队。{len(records)}源行、{len(charts)}图表、{len(reviews)}结构审查。图表来自原HTML/脚本，与数表同源，不是独立样本；保存内联SVG的HTML不等于JSON-SVG配对已验收。\n\n财务仅检查已采三表的一组冻结规则，结果{validation["financial_counts"]}；累计收益衔接{validation["cumulative_counts"]}，保留原显示精度及历史来源哈希。未采栏目不视作无数据。未评分、重训、提交或更新项目入口。不要输出真名，姓名统一用首字母替代。未知人员未全面认证，勿分享原件。\n')
    print(json.dumps(dict(output=str(output), **validation), ensure_ascii=False))


if __name__ == '__main__':
    main()
