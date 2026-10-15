"""Audit captured formal4 print/selection evidence; incomplete HTML never passes."""
import argparse
import importlib.util
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('formal', ROOT / 'output/round_close/20261013_formal3_close/archive_audit/verify_formal3_close.py')
formal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formal)
rules = formal.rules


def read(path):
    doc = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=rules.unique_object)
    if isinstance(doc, dict) and doc.get('html_parts'):
        assert all(isinstance(part,str) for part in doc['html_parts'])
        doc['html'] = ''.join(doc['html_parts'])
    return doc


def check_html_tables(doc):
    parser = rules.Tables()
    parser.feed(doc.get('html',''))
    checks = []
    for ti, table in enumerate(doc['tables']):
        for ri, row in enumerate(table):
            if len(row) != 11 or not all(rules.num(v) for v in row[1:]):
                continue
            html_row = parser.tables[ti][ri] if ti<len(parser.tables) and ri<len(parser.tables[ti]) else []
            checks.append(dict(table_index=ti,row_index=ri,
                               status='pass' if len(html_row)==11 and rules.label_key(row[0])==rules.label_key(html_row[0])
                               and all(rules.num(a)==rules.num(b) for a,b in zip(row[1:],html_row[1:])) else 'fail'))
    return checks


def reference(path):
    return dict(source=path.relative_to(ROOT).as_posix(), sha256=rules.sha(path))


def compare(a, b):
    na, nb = rules.num(a), rules.num(b)
    return bool(na and nb and abs(na[0] - nb[0]) <= na[1] + nb[1] + 1e-9)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', type=int, required=True)
    parser.add_argument('--print-file', type=Path)
    parser.add_argument('--summary-file', type=Path)
    args = parser.parse_args()
    m = args.market
    assert 1 <= m <= 10
    pp = args.print_file or BASE / f'raw/market{m}_formal4_print.json'
    complete_print = pp.with_name(pp.stem + '_complete.json')
    if not args.print_file and complete_print.is_file():
        pp = complete_print
    sp = args.summary_file or BASE / f'raw/market{m}_formal4_summary.json'
    complete_summary = sp.with_name(sp.stem + '_complete.json')
    if not args.summary_file and complete_summary.is_file():
        sp = complete_summary
    p, s = read(pp), read(sp)
    oldp = ROOT / 'output/round_close/20261014_resume_verified/raw/market8_formal3_printable.json'
    old = read(oldp)['tables'][0]
    t = p['tables'][0]
    html_complete = formal.full_html(p.get('html', ''), p.get('html_length'))
    summary_complete = formal.full_html(s.get('html', ''), s.get('html_length'))
    opts = formal.selected(s)
    selected_valid = f'市场 {m}' in opts and '回合4' in opts
    header = t[1][1:]
    pairing = []
    for print_row, summary_row in [(2, 4), (3, 9), (4, 13), (5, 17), (6, 21)]:
        sr = s['tables'][0][summary_row]
        pairing.append(dict(print_row=print_row, summary_row=summary_row,
                            status='pass' if len(sr) == 11 and all(compare(a,b) for a,b in zip(t[print_row][1:],sr[1:])) else 'fail'))
    header_matches = s['tables'][0][3][1:] == header and len(set(header)) == len(header) == 10
    header_matches = header_matches and all(row[1:]==header for row in t if len(row)==11 and not row[0].strip() and any(v.strip() for v in row[1:]) and not all(rules.num(v) for v in row[1:]))
    layout_matches = len(t) >= 253 and all(len(t[i]) == len(old[i]) and rules.label_key(t[i][0]) == rules.label_key(old[i][0]) for i in range(253))
    selected_valid = selected_valid and '/Results' in urlparse(s['url']).path and parse_qs(urlparse(s['url']).query).get('panel')==['summary']
    print_html_checks = check_html_tables(p) if html_complete else []
    summary_html_checks = check_html_tables(s) if summary_complete else []
    html_tables_valid = bool(print_html_checks and summary_html_checks and all(x['status']=='pass' for x in print_html_checks+summary_html_checks))
    accepted = html_complete and summary_complete and html_tables_valid and selected_valid and header_matches and layout_matches and all(x['status'] == 'pass' for x in pairing)
    finance = []
    # Frozen positions are used only after all 253 field labels/widths match the accepted layout.
    equations = {
        'assets_equal_liabilities_equity': [(182,1),(200,-1)],
        'assets_components': [(182,1),(177,-1),(179,-1),(180,-1),(181,-1)],
        'fixed_assets_components': [(177,1),(175,-1),(176,-1)],
        'liabilities_components': [(199,1),(194,-1),(196,-1),(197,-1),(198,-1)],
        'equity_components': [(190,1),(186,-1),(187,-1),(188,-1),(189,-1)],
        'gross_profit': [(141,1),(128,-1),(140,1)],
        'ebitda': [(156,1),(141,-1),(147,1),(155,1)],
        'ebit': [(161,1),(156,-1),(159,1),(160,1)],
        'pretax_profit': [(167,1),(161,-1),(164,-1),(165,1),(166,1)],
        'aftertax_profit': [(169,1),(167,-1),(168,1)],
        'working_capital_movements': [(215,1),(211,-1),(212,-1),(213,-1),(214,-1)],
        'operating_cashflow': [(216,1),(209,-1),(215,-1)],
        'capital_expenditure_components': [(221,1),(219,-1),(220,-1)],
        'prefinancing_cashflow_print_positive_capex': [(222,1),(216,-1),(221,1)],
        'financing_total': [(226,1),(224,-1),(225,-1)],
        'cash_change': [(227,1),(222,-1),(226,-1)],
        'cash_bridge': [(229,1),(228,-1),(227,-1)],
        'cash_balancesheet_crosscheck': [(229,1),(181,-1)],
        'profit_summary_crosscheck': [(169,1),(5,-1)],
    }
    if layout_matches:
        for name, terms in equations.items():
            for col in range(1,11):
                numbers = [rules.num(t[row][col]) for row, sign in terms]
                assert all(n is not None for n in numbers)
                residual = sum(n[0]*sign for n, (_,sign) in zip(numbers, terms))
                tolerance = sum(n[1]*abs(sign) for n,(_,sign) in zip(numbers, terms)) + 1e-9
                finance.append(dict(market=m,phase='formal',round=4,check=name, team_id=f'M{m:02d}T{col:02d}', column=col,
                                    residual=residual, tolerance=tolerance,
                                    numerical_status='pass' if abs(residual)<=tolerance else 'fail',
                                    source_status='verified' if accepted else 'unverified_incomplete_capture',
                                    inputs=[dict(reference(pp),table_index=0,row_index=row,column_index=col,display=t[row][col],sign=sign) for row,sign in terms]))
    prior_path = ROOT / f'output/round_close/20261014_resume_verified/raw/market{m}_formal3_summary.json'
    complete_prior = prior_path.with_name(prior_path.stem + '_complete.json')
    if complete_prior.is_file():
        prior_path = complete_prior
    prior = read(prior_path)
    prior_t = prior['tables'][0]
    prior_header = prior_t[20][1:]
    prior_cum = prior_t[21]
    cumulative = []
    assert formal.full_html(prior['html']) and len(set(prior_header)) == 10
    assert f'市场 {m}' in formal.selected(prior) and '回合3' in formal.selected(prior)
    for col, team in enumerate(header,1):
        prior_col = prior_header.index(team)+1
        vals = [rules.num(t[6][col]), rules.num(prior_cum[prior_col]), rules.num(t[5][col])]
        assert all(v is not None for v in vals)
        residual = vals[0][0]-vals[1][0]-vals[2][0]
        tolerance = sum(v[1] for v in vals)+1e-9
        cumulative.append(dict(market=m,phase='formal',round=4,team_id=f'M{m:02d}T{col:02d}', residual=residual,tolerance=tolerance,
                               numerical_status='pass' if abs(residual)<=tolerance else 'fail',
                               source_status='verified' if accepted else 'unverified_incomplete_capture',
                               prior=dict(reference(prior_path), table_index=0,row_index=21,column_index=prior_col),
                               print_source=reference(pp), current_cumulative_row=6,current_profit_row=5,column_index=col))
    requirements = read(BASE / 'validation/field_requirements_template.json')
    gaps = [dict(x, market=m, phase='formal', round=4,
                 formal4_status=('print_direct_verified' if accepted else 'print_position_available_needs_complete_source') if x['prior_verified_status']=='print_direct_crosschecked' else 'calculate_or_targeted_web_supplement_required') for x in requirements]
    for field in gaps:
        if not accepted:
            continue
        if field['formal4_status']=='print_direct_verified':
            field['formal4_print_sources'] = [dict(reference(pp),table_index=r['table_index'],row_index=r['row_index']) for r in field['prior_print_references']]
            field['formal4_values'] = [dict(team_id=f'M{m:02d}T{col:02d}', column_index=col,
                                           display=t[field['prior_print_references'][0]['row_index']][col],
                                           value=rules.num(t[field['prior_print_references'][0]['row_index']][col])[0],
                                           semantic_web_value=field['print_to_web_display_sign']*rules.num(t[field['prior_print_references'][0]['row_index']][col])[0]) for col in range(1,11)]
        if field['panel']=='summary':
            ri = field['prior_web_reference']['row_index']
            sr = s['tables'][0][ri]
            if rules.label_key(sr[0])==rules.label_key(field['label']) and len(sr)==11 and all(rules.num(v) for v in sr[1:]):
                field['formal4_status']='web_supplement_direct_verified'
                field['formal4_web_source']=dict(reference(sp),table_index=0,row_index=ri)
                field['formal4_values']=[dict(team_id=f'M{m:02d}T{col:02d}',column_index=col,display=sr[col],value=rules.num(sr[col])[0]) for col in range(1,11)]
    sequence_requirements = read(BASE / 'validation/sequence_requirements_template.json')
    charts, chart_errors = rules.charts(s.get('html',''))
    supplemental_sources, supplemental_rows, supplemental_charts = [], [], []
    for panel in rules.PANELS:
        if panel=='summary':
            continue
        paths = [BASE/f'raw/market{m}_formal4_{panel}.json',BASE/f'raw/market{m}_formal4_{panel}_complete.json']
        existing = [path for path in paths if path.is_file()]
        if not existing:
            continue
        path = existing[-1]
        doc = read(path)
        selections = formal.selected(doc)
        source = dict(reference(path),market=m,panel=panel)
        complete = formal.full_html(doc.get('html',''),doc.get('html_length'))
        identity = f'市场 {m}' in selections and '回合4' in selections and parse_qs(urlparse(doc.get('url','')).query).get('panel')==[panel]
        html_checks = check_html_tables(doc) if complete else []
        valid = complete and identity and html_checks and all(x['status']=='pass' for x in html_checks)
        rows, reviews, _ = formal.rows_for(doc,source)
        valid = bool(valid and not reviews and all(r['team_order']==header for r in rows if r['numeric_by_team']))
        source.update(html_complete=complete,identity_valid=identity,valid=valid,structure_reviews=reviews)
        supplemental_sources.append(source)
        if valid:
            supplemental_rows.extend(rows)
            parsed, errors = rules.charts(doc['html'])
            chart_errors.extend(dict(source=source['source'],**error) for error in errors)
            supplemental_charts.extend(dict(chart,source=reference(path),panel=panel) for chart in parsed)
    for field in gaps:
        if not accepted:
            continue
        prior = field['prior_web_reference']
        matches = [r for r in supplemental_rows if r['panel']==field['panel'] and r['table_index']==prior['table_index']
                   and r['row_index']==prior['row_index'] and rules.label_key(r['label'])==rules.label_key(field['label'])
                   and r['section_path']==field['section_path'] and r['team_mapping_valid'] and all(rules.num(v) for v in r['cells'][1:])]
        if len(matches)==1:
            r=matches[0]
            field.update(formal4_status='web_supplement_direct_verified',
                         formal4_web_source=dict(source=r['source'],sha256=r['sha256'],table_index=r['table_index'],row_index=r['row_index']),
                         formal4_values=[dict(team_id=f'M{m:02d}T{col:02d}',column_index=col,display=r['cells'][col],value=rules.num(r['cells'][col])[0]) for col in range(1,11)])
    sequence_coverage = []
    for item in sequence_requirements:
        found = ([dict(c,source=reference(sp)) for c in charts if c['id']==item['chart_id']] if item['panel']=='summary' and summary_complete else
                 [c for c in supplemental_charts if c['id']==item['chart_id'] and c['panel']==item['panel']])
        sequence_coverage.append(dict(item,market=m,round=4,
                                     formal4_status='web_original_json' if len(found)==1 else 'missing',
                                     source=found[0]['source'] if len(found)==1 else None,
                                     data=found[0]['data'] if len(found)==1 else None,
                                     svg_pairing_status='not_checked'))
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S.%f+0800')
    out = BASE / f'validation/market{m}/{stamp}'
    out.mkdir(parents=True,exist_ok=False)
    summary = dict(status='PRINT_IDENTITY_AND_LAYOUT_VALIDATED' if accepted else 'REJECTED_INCOMPLETE_CAPTURE',
                   market=m,round=4, sources=[reference(pp),reference(sp)],script_sha256=rules.sha(Path(__file__)),
                   printable_html_complete=html_complete, summary_html_complete=summary_complete,
                   printable_actual_html_length=len(p.get('html','')),printable_declared_html_length=p.get('html_length'),
                   summary_actual_html_length=len(s.get('html','')),summary_declared_html_length=s.get('html_length'),
                   selected_valid=selected_valid, selected=opts,team_header_matches=header_matches,
                   html_table_checks=dict(Counter(x['status'] for x in print_html_checks+summary_html_checks)),
                   labels_and_widths_match_253_row_layout=layout_matches,
                   table_rows=len(t),empty_trailing_rows=sum(not r for r in t[253:]),
                   summary_print_pairing=pairing, financial_numerical_counts=dict(Counter(x['numerical_status'] for x in finance)),
                   cumulative_numerical_counts=dict(Counter(x['numerical_status'] for x in cumulative)),
                   field_status_counts=dict(Counter(x['formal4_status'] for x in gaps)),
                   original_sequence_count_required=28, sequence_status_counts=dict(Counter(x['formal4_status'] for x in sequence_coverage)),
                   chart_parse_errors=chart_errors, supplemental_source_count=len(supplemental_sources),
                   all_field_coverage_verified=accepted and all(x['formal4_status'] in ['print_direct_verified','web_supplement_direct_verified'] for x in gaps))
    for name,data in [('validation',summary),('financial_checks',finance),('cumulative_checks',cumulative),('field_gaps',gaps),('sequence_coverage',sequence_coverage),('supplemental_sources',supplemental_sources),('html_table_checks',dict(print=print_html_checks,summary=summary_html_checks))]:
        with (out/f'{name}.json').open('x',encoding='utf-8') as stream:
            stream.write(rules.redact_names(json.dumps(data,ensure_ascii=False,indent=2)))
    with (out/'validate_market.py').open('x',encoding='utf-8') as stream:
        stream.write(Path(__file__).read_text(encoding='utf-8'))
    assert compare('1 419','1419') and not compare('NaN','0')
    print(json.dumps(dict(output=str(out),**summary),ensure_ascii=False))


if __name__=='__main__':
    main()
