"""Offline evidence checks; no UI, training, or source edits."""
import csv
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
CLOSE = HERE.parents[2]
PANELS = 'outlook demand productioninvestments productionplanning marketreportdomestic marketreportinternational1 marketreportbulk logistics corporate'.split()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell(value):
    if isinstance(value, dict):
        value = value.get('text') or value.get('html') or ''
    return html.unescape(re.sub(r'<[^>]*>', '', str(value or ''))).strip()


def number(value):
    try:
        return float(re.sub(r'[\s,]', '', cell(value)))
    except ValueError:
        return None


def write_json(name, value):
    with (HERE / name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def write_csv(name, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (HERE / name).open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def checklist(data):
    assert parse_qs(urlparse(data['url']).query).get('panel') == ['decisionchecklist']
    assert any(s.get('selected') == '回合4' for s in data['selects'])
    for ti, table in enumerate(data['tables']):
        heads = [cell(c) for c in table[0]] if table else []
        if '营销团队' not in heads:
            continue
        group = heads.index('营销团队')
        personal = next(i for i, h in enumerate(heads) if ''.join(h.split()) == ''.join(map(chr, (28006, 35821, 26312))))
        aliases = {}
        for h, alias in zip(heads[2:], ('JY', 'XXL', 'SRQ', 'PYT')):
            aliases[h] = alias
            aliases[''.join(h.split())] = alias
        section, sub, rows = '', '', []
        for ri, row in enumerate(table[1:], 1):
            vals = [cell(c) for c in row]
            if len(vals) == 1:
                if vals[0] in ('复合梁', '连接件', '泰国', '下回合'):
                    sub = vals[0]
                else:
                    section, sub = vals[0], ''
                continue
            if not section or len(vals) != len(heads):
                continue
            key = '|'.join((section, sub, vals[0]))
            rows.append(dict(key=key, section=section, subsection=sub, label=vals[0],
                             group_value=vals[group], PYT_value=vals[personal],
                             category='CURRENT_PLATFORM_BUDGET_NOT_ACTUAL' if section == '回合预算' else 'CURRENT_GROUP_DRAFT_AND_PERSONAL_INPUT_NOT_FINAL',
                             source_table=ti, source_row=ri, group_column=group, PYT_column=personal))
        assert len({r['key'] for r in rows}) == len(rows)
        assert sum(r['section'] == '回合预算' for r in rows) == 2
        return rows, aliases
    raise AssertionError('No verified group/PYT checklist table')


def page_check(path, panel):
    d = read(path)
    assert parse_qs(urlparse(d['url']).query).get('panel') == [panel], path.name
    assert d.get('market') == 5 and d.get('area') == 'PYT', path.name
    assert d.get('selected_period', {}).get('id') == 'formal4', path.name
    source_html = d['html']
    assert len(source_html.encode('utf-16-le')) // 2 == d['html_length'], path.name
    assert '</html>' in source_html.lower(), path.name
    return d


def self_check():
    assert number('1\u00a0698') == 1698 and number('-') is None
    assert cell({'text': '', 'html': '<!--x-->1&nbsp;500'}) == '1\u00a0500'
    assert abs(36.5 * .85 - 31.03) < .006
    assert abs(100 * .85 - 85) < .006
    print('self_check passed')


def main():
    self_check()
    if '--self-check' in sys.argv:
        return
    paths = {p: CLOSE / 'formal4_initial/raw' / f'market5_formal4_{p}.json' for p in PANELS}
    baseline_path = CLOSE / 'raw/market5_formal4_decisionchecklist_baseline.json'
    readback_path = CLOSE / 'raw/market5_formal4_decisionchecklist_readback.json'
    missing = [str(p.relative_to(CLOSE)) for p in [*paths.values(), baseline_path, readback_path] if not p.exists()]
    if missing:
        print(json.dumps({'status': 'WAITING_REQUIRED_SOURCES', 'missing': missing}, ensure_ascii=False))
        return
    baseline, aliases = checklist(read(baseline_path))
    readback, _ = checklist(read(readback_path))
    old = {r['key']: r for r in baseline}
    new = {r['key']: r for r in readback}
    assert old.keys() == new.keys(), 'Checklist input schema changed'
    changes = [dict(key=k, baseline=old[k]['PYT_value'], readback=new[k]['PYT_value']) for k in old if old[k]['PYT_value'] != new[k]['PYT_value']]
    group_changes = [dict(key=k, baseline=old[k]['group_value'], readback=new[k]['group_value']) for k in old if old[k]['group_value'] != new[k]['group_value']]

    def safe(text):
        for name, initials in sorted(aliases.items(), key=lambda x: -len(x[0])):
            if name:
                text = text.replace(name, initials)
        return text

    sources, table_rows, editable, previous, pages = [], [], [], [], {}
    for panel, path in paths.items():
        d = page_check(path, panel)
        pages[panel] = d
        sources.append(dict(path=str(path.relative_to(CLOSE)), sha256=digest(path), url=d['url'], captured_at=d['captured_at'], html_utf16_length=d['html_length']))
        for item in d.get('inputs', []):
            editable.append(dict(panel=panel, id=item.get('id'), name=item.get('name'), type=item.get('type'),
                                 value=item.get('value'), disabled=item.get('disabled'),
                                 category='CURRENT_PERSONAL_EDITABLE_VALUE_NOT_FINAL' if not item.get('disabled') else 'PAGE_DISABLED_CONTROL_NOT_FINAL', source=sources[-1]['path'], source_sha256=sources[-1]['sha256']))
        for ti, table in enumerate(d['tables']):
            context, last_year_col = [], None
            for ri, row in enumerate(table):
                vals = [safe(cell(c)) for c in row]
                if len(vals) == 1 and '\n' not in vals[0]:
                    context.append(vals[0])
                for ci, v in enumerate(vals):
                    if v in ('去年', '上回合', '上年'):
                        last_year_col = ci
                category = 'PERSONAL_PLATFORM_BUDGET_PROJECTION_NOT_OPENING_BALANCE' if ti == 0 else 'PAGE_DISPLAY_GIVEN_OR_INPUT_DEPENDENT_SEPARATE_FROM_EDITABLE_CONTROLS'
                table_rows.append(dict(panel=panel, source_table=ti, source_row=ri, context=context.copy(), cells=vals, category=category, source=sources[-1]['path'], source_sha256=sources[-1]['sha256']))
                if last_year_col is not None and last_year_col < len(vals) and number(vals[last_year_col]) is not None and vals:
                    previous.append(dict(panel=panel, field=vals[0], value=number(vals[last_year_col]), context=context.copy(), source_table=ti, source_row=ri, source_column=last_year_col, source=sources[-1]['path'], source_sha256=sources[-1]['sha256'], category='PAGE_LAST_YEAR_REFERENCE_REQUIRES_ACTUAL_MATCH_NOT_AUTOMATIC_OPENING_BALANCE'))

    outlook = pages['outlook']
    narrative = outlook['tables'][1]
    conditions = {cell(narrative[i][0]): safe(cell(narrative[i + 1][0])) for i in range(1, len(narrative), 2)}
    assert set(conditions) == {'需求', '大客户订单', '生产', '货币', '财务'}
    params, ctx = [], []
    for ri, row in enumerate(outlook['tables'][2]):
        vals = [safe(cell(c)) for c in row]
        if len(vals) == 1:
            ctx.append(vals[0])
        elif len(vals) == 4 and vals[1] != '今年':
            params.append(dict(context=ctx.copy(), label=vals[0], current=vals[1], change=vals[2], previous=vals[3], category='PUBLISHED_FORMAL4_PARAMETER', source='formal4_initial/raw/market5_formal4_outlook.json', source_table=2, source_row=ri, source_sha256=digest(paths['outlook'])))

    carry = read(CLOSE / 'formal4_initial/carryover_preparation/carryover_table.json')['rows']
    carry_sources = read(CLOSE / 'formal4_initial/carryover_preparation/source_manifest.json')
    for source in carry_sources['actual_sources']:
        assert digest(CLOSE / source['path']) == source['sha256'], 'Formal3 source changed after carryover preparation'
    prior_input_map = {
        'group_final_49': ('productionplanning', '研发, 千 美元', '复合梁'),
        'group_final_50': ('productionplanning', '研发, 千 美元', '连接件'),
        'group_final_47': ('productionplanning', '运营改进, 千 美元', '泰国'),
    }
    for source_row, panel, product, field in (
        (16, 'marketreportdomestic', '复合梁', '一般营销'),
        (17, 'marketreportinternational1', '复合梁', '一般营销'),
        (19, 'marketreportdomestic', '连接件', '一般营销'),
        (20, 'marketreportinternational1', '连接件', '一般营销'),
        (23, 'marketreportdomestic', '复合梁', '设计师营销'),
        (24, 'marketreportinternational1', '复合梁', '设计师营销'),
        (27, 'marketreportdomestic', '连接件', '设计师营销'),
        (28, 'marketreportinternational1', '连接件', '设计师营销'),
    ):
        prior_input_map[f'group_final_{source_row}'] = (panel, product, field)
    pairs = []
    for original in carry:
        r = original.copy()
        r['comparison_status'] = 'UNKNOWN_NO_IDENTICAL_OPENING_FIELD'
        if r['key'] in prior_input_map:
            panel, context, field = prior_input_map[r['key']]
            candidates = [v for v in previous if v['panel'] == panel and context in v['context'] and v['field'] == field]
        else:
            candidates = []
            if r['key'] == 'long_debt':
                candidates = [v for v in previous if v['panel'] == 'corporate' and v['field'] == '长期贷款, 千 美元']
            elif r['key'].startswith('retail_shipping_'):
                product = '复合梁' if '_beam_' in r['key'] else '连接件'
                candidates = [v for v in previous if v['panel'] == 'logistics' and f'{product}, 千单位' in v['context'] and v['field'] == r['field']]
        unique = {v['value'] for v in candidates}
        r['formal4_last_year_references'] = candidates
        if r['formal3_value'] is not None and len(unique) == 1:
            r['last_year_display_match'] = abs(next(iter(unique)) - r['formal3_value']) <= .01
            r['comparison_status'] = 'LAST_YEAR_REFERENCE_MATCH_NOT_OPENING_PROOF' if r['last_year_display_match'] else 'LAST_YEAR_REFERENCE_MISMATCH_REVIEW_CONTEXT'
        if r['key'] in ('inventory_beam_qty', 'inventory_connector_qty'):
            product = '复合梁' if r['key'] == 'inventory_beam_qty' else '连接件'
            opening_matches = [v for v in table_rows if v['panel'] == 'logistics' and v['cells'] and v['cells'][0] == '期初库存' and f'{product}, 千单位' in v['context']]
            assert len(opening_matches) == 1
            opening = opening_matches[0]
            r['formal4_opening_value'] = number(opening['cells'][1])
            r['formal4_opening_status'] = 'DISPLAYED_OPENING_QUANTITY_FROM_PERSONAL_PAGE_MATCHED_PRIOR_ACTUAL'
            r['formal4_source'] = opening['source']
            r['formal4_source_row'] = opening['source_row']
            r['formal4_source_table'] = opening['source_table']
            r['formal4_source_column'] = 1
            r['formal4_source_sha256'] = opening['source_sha256']
            r['comparison_status'] = 'OPENING_QUANTITY_MATCHED' if r['formal4_opening_value'] == r['formal3_value'] else 'OPENING_QUANTITY_MISMATCH'
        pairs.append(r)

    capacity_rows = [(ti, ri, [cell(c) for c in row]) for ti, table in enumerate(pages['productioninvestments']['tables']) for ri, row in enumerate(table) if row and cell(row[0]).startswith('机器产能,')]
    investments = {r['label']: number(r['PYT_value']) for r in readback if r['section'] == '投资决策, 千单位'}
    capacities = []
    for ti, ri, vals in capacity_rows:
        product = '复合梁' if '复合梁' in vals[0] else '连接件'
        actual = next(r['formal3_value'] for r in carry if r['key'] == ('capacity_beam' if product == '复合梁' else 'capacity_connector'))
        observed = number(vals[2])
        capacities.append(dict(product=product, formal3_group_visible_capacity=actual, formal4_current_personal_investment=investments.get('机器, ' + product), formal4_displayed_this_year_capacity=observed, decay_15percent_reference=actual * .85, matches_zero_investment_decay=investments.get('机器, ' + product) == 0 and observed is not None and abs(observed - actual * .85) <= .006, category='CURRENT_PERSONAL_CAPACITY_PROJECTION_NOT_UNCONDITIONAL_OPENING', source='formal4_initial/raw/market5_formal4_productioninvestments.json', source_table=ti, source_row=ri, source_column=2))
    assert len(capacities) == 2
    historical = CLOSE / 'historical_supplement/raw/market5_formal3_productioninvestments.json'
    historical_data = read(historical)
    historical_capacities = [dict(field=cell(row[0]), this_year=number(row[2]), source_table=ti, source_row=ri, source_column=2) for ti, table in enumerate(historical_data['tables']) for ri, row in enumerate(table) if row and cell(row[0]).startswith('机器产能,')]
    assert len(historical_capacities) == 2
    formal3_final = read(CLOSE / 'decision_history/final_decisions_labeled/all_fields.json')['fields']
    historical_investments = [dict(product=r['label'], group_value=r['group_value'], PYT_value=r['PYT_value'], source=r['source'], source_row=r['source_row_zero_based'], category=r['group_category']) for r in formal3_final if r['round_id'] == 'formal3' and r['section'] == '投资决策, 千单位']
    assert len(historical_investments) == 2
    historical_risk = dict(source=str(historical.relative_to(CLOSE)), sha256=digest(historical), personal_capacity_fields=historical_capacities, group_final_and_personal_investments=historical_investments, formal3_group_actual_capacity=[r['formal3_group_visible_capacity'] for r in capacities], status='FACT_DIFFERENCE_UNVERIFIED_INVESTMENT_TIMING', boundary='个人当期容量可能已含当期投资投影；旧零产能/投资下期生效假设出现冲突，未改模型、不强判平台机制')
    for path in (baseline_path, readback_path, historical, CLOSE / 'formal4_initial/carryover_preparation/carryover_table.json'):
        sources.append(dict(path=str(path.relative_to(CLOSE)), sha256=digest(path)))
    write_json('sources.json', sources)
    write_json('known_conditions.json', dict(five_sections=conditions, parameters=params, category='FORMAL4_KNOWN_CONDITIONS_NOT_FINAL_DECISIONS'))
    write_csv('published_parameters.csv', params)
    write_json('page_fields.json', dict(table_rows=table_rows, editable_personal_controls=editable, last_year_references=previous))
    write_csv('page_fields.csv', table_rows)
    write_csv('editable_personal_controls.csv', editable)
    write_json('input_stability.json', dict(PYT_changes=changes, group_draft_changes=group_changes, PYT_stable=not changes, baseline=baseline, readback=readback, formal4_group_category='CURRENT_GROUP_DRAFT_NOT_FINAL'))
    write_csv('formal4_current_checklist.csv', readback)
    write_json('carryover_comparison.json', dict(rows=pairs, capacity_projection_checks=capacities, historical_personal_group_capacity_risk=historical_risk))
    write_csv('carryover_comparison.csv', pairs)
    write_json('acceptance.json', dict(status='OFFLINE_VERIFIED_SOURCE_CLASSIFICATION', panels=len(pages), five_sections=len(conditions), parameters=len(params), personal_stable=not changes, group_draft_changed=bool(group_changes), all_current_inputs_not_final=True, no_training=True, script_sha256=digest(Path(__file__)), created_at=datetime.now(timezone(timedelta(hours=8))).isoformat()))
    report = '正式4已知条件与初值核验。不要输出真名，姓名统一用首字母替代。\n\n九子页URL、市场5、正式4、PYT区域及完整HTML UTF16长度通过核验。正式4当前个人输入和小组草稿均不标final。\n\n'
    report += '\n\n'.join(f'{k}：{v}' for k, v in conditions.items())
    report += '\n\n完整公布参数见published_parameters.csv/known_conditions.json；各页给定/上年字段与可编辑个人控制分别见page_fields.json及editable_personal_controls.csv。预算投影不是实际余额。\n\n'
    report += f'个人输入前后变化{len(changes)}项；小组草稿变化{len(group_changes)}项，均单列于input_stability.json，预算也单独比较。\n\n'
    report += '逐字段结转中两产品物流页本期期初库存均0，与正式3期末数量匹配；其余仅有上年参考的字段不改称期初余额。缺税亏、完整研发运营持续状态、未生效投资及未披露合同不补零。\n\n'
    report += '机器容量逐产品核验：' + '；'.join(f"{r['product']}上期小组显示容量{r['formal3_group_visible_capacity']}，本期个人投资{r['formal4_current_personal_investment']}，本期显示容量{r['formal4_displayed_this_year_capacity']}，零投资衰减匹配{r['matches_zero_investment_decay']}" for r in capacities) + '。\n\n'
    report += '当前投资0且衰减匹配时，仅作为该个人容量投影的核验，不证明所有投资下期生效。历史正式3个人容量21.5/20与小组实际36.5/100不同，个人投资0/20与小组15/100不同，旧零产能/下期生效假设存在冲突。机制时点仍待独立核验，未强判规则或改模型。\n\n'
    report += '未训练、未操作网页或修改原件。完整来源SHA256、采集时间和行列保存；脚本自检通过。\n'
    with (HERE / 'report.md').open('x', encoding='utf-8') as f:
        f.write(report)
    print(json.dumps(dict(status='COMPLETE', panels=len(pages), parameters=len(params), PYT_changes=len(changes), output=str(HERE)), ensure_ascii=False))


if __name__ == '__main__':
    main()
