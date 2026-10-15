"""Read-only acceptance of historical replacement evidence and market 8 print coverage."""
import csv
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/round_close/20261014_resume_verified'
RAW = BASE / 'raw'
OLD = ROOT / 'output/financial_pairing/20261013T170415.559484+0800'
HISTORY = ROOT / 'output/round_close/20261012T221044.031+0800'
SPEC = importlib.util.spec_from_file_location('formal_rules', ROOT / 'output/round_close/20261013_formal3_close/archive_audit/verify_formal3_close.py')
formal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(formal)
rules = formal.rules


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def ref(row):
    return {k: row[k] for k in ('source', 'sha256', 'table_index', 'row_index', 'unit_context', 'section_path')}


def document(path):
    doc = read(path)
    match = re.match(r'market(\d+)_(initial|practice|formal)(\d+)_([a-z]+)', path.name)
    market, phase, rnd, panel = int(match[1]), match[2], int(match[3]), match[4]
    selects = doc.get('selects', doc.get('selectors', []))
    selected = []
    for s in selects:
        option = next(o for o in s['options'] if o['value'] == s['value'])
        selected.append(dict(label=option['text'], value=s['value'], options=[dict(label=o['text'], value=o['value']) for o in s['options']]))
    doc.update(market=market, phase=phase, round=rnd, panel=panel, source_url=doc['url'], selected=selected)
    assert formal.full_html(doc['html'], doc['html_length']), path.name
    assert not rules.identity(doc), (path.name, rules.identity(doc))
    source = dict(source=path.relative_to(ROOT).as_posix(), sha256=rules.sha(path), market=market, phase=phase,
                  round=rnd, panel=panel, url=doc['url'], captured_at=doc['captured_at'], selected=selected,
                  html_length=doc['html_length'], value_type='direct', category='actual_result')
    records, reviews, basis = formal.rows_for(doc, source)
    for row in records:
        row.update(phase=phase, round=rnd, identity_status='verified')
    parser = rules.Tables()
    parser.feed(doc['html'])
    # Captured visible numbers must also exist in the preserved complete HTML.
    html_rows = [(ti, ri, cells) for ti, table in enumerate(parser.tables) for ri, cells in enumerate(table)]
    for row in records:
        if row['team_mapping_valid'] and all(rules.num(v) is not None for v in row['cells'][1:]):
            matches = [cells for ti, ri, cells in html_rows if ti == row['table_index'] and ri == row['row_index']]
            assert len(matches) == 1 and rules.label_key(matches[0][0]) == rules.label_key(row['label'])
            assert [rules.num(v) for v in matches[0][1:]] == [rules.num(v) for v in row['cells'][1:]], row['row_index']
    parsed_charts, errors = rules.charts(doc['html'])
    assert not errors, (path.name, errors)
    source.update(table_count=len(doc['tables']), chart_count=len(parsed_charts), structure_reviews=len(reviews), table_basis=basis)
    return doc, source, records, reviews, parsed_charts


def main():
    stamp = datetime.now(timezone(timedelta(hours=8)))
    out = BASE / 'acceptance' / stamp.strftime('%Y%m%dT%H%M%S.%f+0800')
    out.mkdir(parents=True)
    (out / 'work_log.md').write_text(stamp.isoformat() + ' START:只读验收；不要输出真名，姓名统一用首字母替代。原件保留；不改决策、不训练模型。\n', encoding='utf-8')
    fingerprints = {p.relative_to(ROOT).as_posix(): rules.sha(p) for p in RAW.glob('*.json')}
    paths = sorted(RAW.glob('*history_recheck.json'))
    assert len(paths) == 13
    sources, rows, reviews, by_key, chart_map = [], [], [], {}, {}
    for path in paths:
        doc, source, records, checks, parsed_charts = document(path)
        key = (source['market'], source['phase'], source['round'], source['panel'])
        sources.append(source)
        rows.extend(records)
        reviews.extend(checks)
        by_key[key] = records
        chart_map[key] = parsed_charts
    assert not reviews, reviews

    terms_by_check = {
        'aftertax_profit': [('本回合利润', 1), ('税前利润', -1), ('直接税', 1)],
        'assets_equal_liabilities_equity': [('资产 总计', 1), ('负债与所有者权益总计', -1)],
        'working_capital_movements': [('净营运资本总额变化（增加-/减少+）', 1), ('库存变化(增 - / 减 +)', -1), ('应收帐变化(增 - / 减 +)', -1), ('应付账变化(增 + / 减 -)', -1), ('已收预付款变化(增 + / 减 -)', -1)],
        'gross_profit': [('毛利', 1), ('净销售额', -1), ('可变成本总和', 1)],
        'fixed_assets_components': [('固定资产总和', 1), ('厂房', -1), ('机器', -1)],
        'current_assets_components': [('总流动资产', 1), ('成品库存', -1), ('应收帐款', -1), ('现金及现金等价物', -1)],
    }
    financial = []
    for item in read(OLD / 'remaining.json'):
        key, terms = tuple(item['key']), terms_by_check[item['check']]
        paired = [rules.paired_row(rows, key, label) for label, sign in terms]
        assert all(paired) and all(r['team_order'] == paired[0]['team_order'] for r in paired)
        for i in range(1, 11):
            values = [rules.num(r['cells'][i]) for r in paired]
            assert all(v is not None for v in values)
            residual = sum(v[0] * sign for v, (_, sign) in zip(values, terms))
            tolerance = sum(v[1] * abs(sign) for v, (_, sign) in zip(values, terms)) + 1e-9
            financial.append(dict(key=key, check=item['check'], team_id=f'M{key[0]:02d}T{i:02d}', team_column_index=i,
                                  terms=terms, inputs=[dict(ref(r), column_index=i, display=r['cells'][i], value=v[0]) for r, v in zip(paired, values)],
                                  unit='千 美元', residual=residual, tolerance=tolerance,
                                  status='pass' if abs(residual) <= tolerance else 'fail'))
    assert len(financial) == 60 and all(x['status'] == 'pass' for x in financial)

    structures = []
    for item in read(OLD / 'structure_review.json'):
        old_path = HISTORY / item['source']
        assert rules.sha(old_path) == item['sha256']
        m = re.match(r'raw/market(\d+)_(initial|practice|formal)(\d+)_([a-z]+)', item['source'])
        key = (int(m[1]), m[2], int(m[3]), m[4])
        candidates = [r for r in by_key[key] if r['table_index'] == item['table_index'] and r['row_index'] == item['row_index']]
        assert len(candidates) == 1
        row = candidates[0]
        assert rules.label_key(row['label']) == rules.label_key(item['label']) and row['team_mapping_valid']
        structures.append(dict(old_source=old_path.relative_to(ROOT).as_posix(), old_sha256=item['sha256'], old_row_index=item['row_index'],
                               label=item['label'], new_source=ref(row), width=len(row['cells']), team_columns=list(range(1, 11)),
                               status='new_source_valid_old_extra_columns_unassigned',
                               old_evidence_disposition='preserved; not truncated, not mapped, not used as accepted replacement'))
    assert len(structures) == 26

    key = (2, 'practice', 1, 'summary')
    cumulative = rules.paired_row(rows, key, '累计收益')
    profit = rules.paired_row(rows, key, '本回合利润')
    cs = {c['id']: c for c in chart_map[key]}
    earnings = cs['Graphs.Results.Summary.CumulEarnings.TimeSeries.summary']['data']
    profits = cs['Graphs.Results.Summary.Profits.TimeSeries.summary']['data']
    profitability = cs['Graphs.Summary.Profitability']['data']
    exact = [s for d in profitability['dataset'] for s in d['dataset'] if s['seriesname'] == '利润']
    assert len(exact) == 1
    chart_checks = []
    for data, rec, chart_id in [(earnings, cumulative, 'Graphs.Results.Summary.CumulEarnings.TimeSeries.summary'), (profits, profit, 'Graphs.Results.Summary.Profits.TimeSeries.summary')]:
        slot = [p['label'] for p in data['categories'][0]['category']].index('1')
        assert [s['seriesname'] for s in data['dataset']] == rec['team_order']
        for i, series in enumerate(data['dataset'], 1):
            value = series['data'][slot]['value']
            shown, tolerance = rules.num(rec['cells'][i])
            assert value != 'NaN' and abs(float(value) - shown) <= tolerance + 1e-9
            chart_checks.append(dict(team_id=f'M02T{i:02d}', chart_id=chart_id, period=1, value=value, display=shown, tolerance=tolerance,
                                     status='pass', independent_sample=False, row=ref(rec), source_column_index=i))
    assert [c['label'] for c in profitability['categories'][0]['category']] == profit['team_order']
    for i, point in enumerate(exact[0]['data'], 1):
        shown, tolerance = rules.num(profit['cells'][i])
        assert abs(point['value'] - shown) <= tolerance + 1e-9
        chart_checks.append(dict(team_id=f'M02T{i:02d}', chart_id='Graphs.Summary.Profitability', value=point['value'], display=shown,
                                 status='pass', independent_sample=False, row=ref(profit), source_column_index=i))

    # Each web field is retained as direct evidence; conservative print matching never infers a missing value.
    print_path = RAW / 'market8_formal3_printable.json'
    printed = read(print_path)
    assert formal.full_html(printed['html'], printed['html_length'])
    print_sha = rules.sha(print_path)
    print_fields, context = [], []
    for ti, table in enumerate(printed['tables']):
        for ri, cells in enumerate(table):
            label = cells[0].strip() if cells else ''
            numeric = len(cells) == 11 and all(rules.num(v) is not None for v in cells[1:])
            if label and not numeric:
                context.append(label)
            if numeric and label:
                print_fields.append(dict(source=print_path.relative_to(ROOT).as_posix(), sha256=print_sha, table_index=ti, row_index=ri,
                                         label=label, section_path=context.copy(), cells=cells, value_type='direct_print', team_columns=list(range(1, 11))))
    aliases = {'营业收入净额, 千 美元': '营业收入净额', '本回合利润, 千 美元': '本回合利润', '累计收益, 千 美元': '累计收益',
               '销货成本, 千 美元': '销货成本', '资产总计': '资产 总计', '销售额总计, 千单位 - 复合梁': '销售额总计 - 复合梁',
               '销售额总计, 千单位 - 连接件': '销售额总计 - 连接件', '各市场总销售，千单位': '销售额总计',
               '本回合复合梁': '本回合 复合梁', '本回合连接件': '本回合 连接件', '下一回合复合梁': '下一回合 复合梁', '下一回合连接件': '下一回合 连接件'}
    def label(text):
        return rules.label_key(aliases.get(text, text))
    print_source_rows = {p['row_index']: p for p in print_fields}
    section_ranges = {'summary': (0, 33), 'marketdetails': (34, 81), 'productiondetails': (82, 100), 'productionhr': (82, 100),
                      'logisticsdetails': (101, 125), 'incomestatement': (126, 170), 'balancesheet': (171, 202), 'cashflow': (203, 231),
                      'ratios': (232, 243), 'societalimpact': (244, 252)}
    coverage, sequences, web_sources = [], [], []
    for panel in rules.PANELS:
        path = RAW / f'market8_formal3_{panel}.json'
        doc, source, records, checks, charts = document(path)
        assert not checks
        web_sources.append(source)
        for row in records:
            if not row['team_mapping_valid'] or not row['label'] or not all(rules.num(v) is not None for v in row['cells'][1:]):
                continue
            candidates = []
            for p in print_fields:
                bounds = section_ranges.get(panel)
                if bounds and bounds[0] <= p['row_index'] <= bounds[1] and label(p['label']) == label(row['label']):
                    if all(abs(rules.num(a)[0] - rules.num(b)[0]) <= rules.num(a)[1] + rules.num(b)[1] + 1e-9 for a, b in zip(p['cells'][1:], row['cells'][1:])):
                        candidates.append(p)
            coverage.append(dict(panel=panel, label=row['label'], section_path=row['section_path'], units=row['unit_context'],
                                 web=ref(row), market=8, phase='formal', round=3, team_columns=list(range(1, 11)), value_type='direct',
                                 values=[dict(team_id=f'M08T{i:02d}', column_index=i, display=v, value=rules.num(v)[0]) for i, v in enumerate(row['cells'][1:], 1)],
                                 status='print_direct_crosschecked' if len(candidates) == 1 else 'web_supplement_direct',
                                 print_matches=[dict(source=p['source'], sha256=p['sha256'], table_index=p['table_index'], row_index=p['row_index']) for p in candidates],
                                 note='语义分区、标签别名与逐队显示精度共同配对' if len(candidates) == 1 else '直接网页值已保留；不按相同数值猜测打印标签或重复行归属'))
        for chart in charts:
            sequences.append(dict(panel=panel, chart_id=chart['id'], chart_type=chart['type'], source=source['source'], sha256=source['sha256'],
                                  status='web_original_json', independent_sample=False, data=chart['data'],
                                  note='打印页主体数表不替代原始图表精度或历史序列；本次未执行全部JSON/SVG同点配对'))
    # Explicit cross-layout mappings for production cost and company summary fields.
    cross_layout = {}
    for panel, mapping in {
        'summary': {4:2, 9:3, 13:4, 17:5, 21:6, 24:9, 25:10, 27:89, 28:95, 30:15, 31:16, 32:17, 34:20, 35:21, 36:22},
        'marketdetails': {3:38,4:39,6:41,7:42,10:46,11:47,12:52,14:49,15:50,16:53,17:55,20:59,21:60,24:62,25:63,
                          30:66,31:67,34:68,35:69,39:72,40:73,41:74,42:75,44:78,45:79},
        'productiondetails': {4:85,6:9,7:88,8:89,9:90,10:91,11:92,13:10,14:94,15:95,16:96,17:97,18:98},
        'productionhr': {3:86},
        'logisticsdetails': {2:104,3:105,4:106,5:107,7:111,8:112,9:113,10:114,11:115,12:116,15:120,16:121,18:123,19:124},
        'cashflow': {10:206,24:220,25:221},
        'ratios': {11:244},
    }.items():
        cross_layout.update({(panel, row): target for row, target in mapping.items()})
    for entry in coverage:
        target = cross_layout.get((entry['panel'], entry['web']['row_index']))
        if target is None:
            continue
        p = print_source_rows[target]
        row = next(r for r in document(RAW / f"market8_formal3_{entry['panel']}.json")[2] if r['table_index'] == entry['web']['table_index'] and r['row_index'] == entry['web']['row_index'])
        sign = -1 if (entry['panel'], entry['web']['row_index']) in [('cashflow',24),('cashflow',25)] else 1
        assert all(abs(rules.num(a)[0] - sign * rules.num(b)[0]) <= rules.num(a)[1] + rules.num(b)[1] + 1e-9 for a, b in zip(row['cells'][1:], p['cells'][1:]))
        entry.update(status='print_direct_crosschecked', print_matches=[dict(source=p['source'], sha256=p['sha256'], table_index=p['table_index'], row_index=target)],
                     print_to_web_display_sign=sign,
                     note='已核打印分区与网页产品/国家/指标语义及逐队显示精度；机器资本支出和资本支出总计打印为正支付额、网页为负现金流，分别保留' if sign == -1 else '已核打印分区与网页产品/国家/指标语义及逐队显示精度')

    assert all(rules.sha(ROOT / name) == h for name, h in fingerprints.items())
    counts = dict(Counter(x['status'] for x in coverage))
    summary = dict(generated_at=stamp.isoformat(), historical_sources=13, financial_old_records=6, financial_team_checks=60,
                   financial_pass=60, structural_old_records=26, structural_new_sources_valid=26, new_structural_reviews=0,
                   old_extra_columns_still_unassigned=True, market2_practice1_chart_checks_pass=30,
                   market8_print_numeric_fields=len(print_fields), market8_web_field_coverage=counts,
                   market8_original_charts=len(sequences), market8_print_pages=1, market8_web_pages=15,
                   calculated_values=0, raw_hash_changes=0, decisions_changed=False, models_trained=False,
                   all_json_svg_pairs_verified=False, browser_elapsed_note='本次继续请求后的有耗时返回浏览器调用累计297.55秒；中断调用无可靠耗时，前对话未计，不作为同范围速度收益。')

    def write(name, value):
        text = rules.redact_names(json.dumps(value, ensure_ascii=False, indent=2))
        assert rules.redact_names(text) == text
        with (out / name).open('x', encoding='utf-8') as stream:
            stream.write(text)
    for name, value in [('acceptance.json', summary), ('sources.json', sources + web_sources), ('financial_checks.json', financial),
                        ('structural_transition.json', structures), ('market2_chart_checks.json', chart_checks), ('historical_rows.json', rows),
                        ('market8_print_fields.json', print_fields), ('market8_field_coverage.json', coverage), ('market8_sequences.json', sequences),
                        ('raw_hashes.json', fingerprints)]:
        write(name, value)
    for name, data in [('financial_checks.csv', financial), ('market8_field_coverage.csv', coverage)]:
        with (out / name).open('x', encoding='utf-8-sig', newline='') as stream:
            fields = list(data[0])
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in data:
                writer.writerow({k: rules.redact_names(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, tuple)) else str(v)) for k, v in row.items()})
    report = f'''# 历史补证与正式3打印对照验收

时间：{stamp.isoformat()}（北京时间）。不要输出真名，姓名统一用首字母替代。只分享脱敏交付文件；raw原件可能含姓名。

13份历史补证通过市场/阶段/回合、URL、完整HTML长度、数表与HTML一致性核验。本对话新增4页，其余9页复用前对话补证。旧6条待核等式按10队展开为60项，60项通过，0失败；26条旧结构审查在新来源对应行均为10个已核团队列，0项新结构异常。旧附加列归属仍未知，旧证据不截列、不改写、不用于新验收，不能将本次结果称为证明旧额外列身份。

市场2练习1概要：利润及累计图第1年20项与同期显示值匹配，利润图全精度另10项匹配，共30项通过。未来NaN保留；图表与数表是同源表示，不重复计为样本。旧初始0内容冲突补件继续拒绝；新完整同期HTML获接纳。旧正式3生产计划拒绝原件不属于本次范围，历史拒绝结论保留。

正式3固定15栏旧口径：10市场、100队、150/150网页；500项财务等式、100项累计衔接通过，3700源行、280图表，0结构审查、0哈希变化。依据为[正式3验收](../../../20261013_formal3_close/archive_audit/validation/20261014T142929.104834+0800/report.md)。本次验收再核本批raw原件哈希无变化。

## 市场8正式3打印版字段与序列

打印版1页、网页15页分别统计，打印页不虚算15栏。新双产品结构已做一次完整网页对照，不能直接套用市场7清单。打印版保存{len(print_fields)}条数值字段行；网页{len(coverage)}条数值字段行全部有直接来源，其中{counts.get('print_direct_crosschecked', 0)}条以语义分区、标签与逐队数值配对确认打印已有，{counts.get('web_supplement_direct', 0)}条保留网页直接来源。保守匹配未通过的重复/异名字段不按相同数字猜归属，网页证据保证其覆盖；明细见[完整字段对照](market8_field_coverage.json)、[CSV](market8_field_coverage.csv)、[打印字段索引](market8_print_fields.json)。

打印已有：概要利润/累计收益/现金/营销研发；双产品价格、国别需求销量、订单库存；泰国产能、产品人员/班次/产量/效率/工资分摊；物流、损益、资产负债、现金流、主要财务指标与价值创造。资产总计等标签别名以同口径逐队数值核验，不覆盖原标签。

网页补充：历年收入/利润/累计收益原始图表；需求总计及市场份额总计、产品机器产能；人均工资、上/本回合人员、辞职、招聘裁员及比例；生产CO₂/能源/用水、物流排放；产品/订单销售收入拆分、流动资产小计及摘要息税前利润、各类图表独有序列/原始精度。网页已取得直接值，本次计算值0条，无需额外制造计算值。各项单位、业务分区、团队列编号、源行列及哈希在JSON保留。

打印的机器资本支出和资本支出总计为正支付额，网页对应项为负现金流；10队绝对值按舍入精度配对通过，表中保留两种符号、原标签和源行列。不是同符号字段，不用打印正数直接套入网页现金流等式。

{len(sequences)}个市场8网页图表初始化JSON已提取并保留于[序列索引](market8_sequences.json)，同页完整HTML保留SVG；本次未完成全部JSON/SVG同点配对，不能把采集齐全称为全图表配对通过。

## 边界与复现

所有新旧原件保留。未改决策、未提交小组方案、未重复快速教程、未重训。t4v0仍是原6市场/60队/90页训练范围，最新全市场归档不自动扩大模型训练样本。完整跨期状态与六回合最优仍未完成。

财务逐队来源见[核验JSON](financial_checks.json)、[CSV](financial_checks.csv)；结构来源替换见[26项记录](structural_transition.json)；市场2冲突补证见[30项配对](market2_chart_checks.json)。`python work/verify_history_resume.py`复现至新排他时间戳目录，复用既有解析、身份、财务符号和显示舍入容差，不修改共享审计程序。

本对话浏览器耗时以工具返回累加单列，不与前对话或打印优先同范围基准混算，不宣称速度收益。输出仅Markdown、JSON/CSV；历史HTML报告与原始网页证据保留。
'''
    (out / 'report.md').write_text(rules.redact_names(report), encoding='utf-8')
    (out / 'work_log.md').open('a', encoding='utf-8').write(stamp.isoformat() + ' ACCEPTED:13页、60等式、26结构新来源、30图表配对；原件哈希不变。\n')
    print(json.dumps(dict(output=out.relative_to(ROOT).as_posix(), **summary), ensure_ascii=False))


if __name__ == '__main__':
    main()
