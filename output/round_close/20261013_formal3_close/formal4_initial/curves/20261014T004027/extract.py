"""Extract original chart literals and reuse SVG ordinate checks, without refitting."""
import csv
import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CLOSE = HERE.parents[2]
ROOT = CLOSE.parents[2]
RULE_PATH = CLOSE / 'historical_supplement/audit/verify_historical_supplement.py'
spec = importlib.util.spec_from_file_location('history_curve_rules', RULE_PATH)
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    text = rules.rules.redact_names(json.dumps(data, ensure_ascii=False, indent=2))
    with (HERE / name).open('x', encoding='utf-8') as f:
        f.write(text)


def save_csv(name, records):
    with (HERE / name).open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)


def numeric(v):
    try:
        n = float(str(v).replace('\u00a0', '').replace(' ', ''))
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def check():
    assert numeric('NaN') is None and numeric('1\u00a0000') == 1000
    sample = {'id': 'quality.control.chart', 'data': {'dataset': [{'seriesname': '曲线, 测试', 'data': [{'value': 1 + i / 199} for i in range(200)]}]}}
    path = 'M' + 'L'.join(f'{i},{200 - (1 + i / 199) * 100}' for i in range(200))
    svg = f'<svg><text>需求乘数</text><rect x="0" y="0" width="600" height="200" fill="#eeeeee"/><text x="-1" text-anchor="end">0</text><text x="-1" text-anchor="end">2</text><path d="{path}"/></svg>'
    assert rules.pair_curve_y([sample], [svg])[0]['status'] == 'pass_y_values'
    sample['data']['dataset'][0]['data'][0]['value'] = 10
    assert rules.pair_curve_y([sample], [svg])[0]['status'] == 'fail_y_values'


def main():
    check()
    current_path = CLOSE / 'formal4_initial/raw/market5_formal4_productionplanning.json'
    prior_path = CLOSE / 'historical_supplement/raw/market5_formal3_productionplanning.json'
    current, prior = read(current_path), read(prior_path)
    assert current['market'] == 5 and current['area'] == 'PYT' and current['selected_period']['id'] == 'formal4'
    assert prior['selected_period']['id'] == 'formal3'
    assert rules.full_html(current)[0] and rules.full_html(prior)[0]
    charts, errors = rules.rules.charts(current['html'])
    old_charts, old_errors = rules.rules.charts(prior['html'])
    assert not errors and not old_errors
    svgs = re.findall(r'<svg\b[\s\S]*?</svg>', current['html'], re.I)
    pairings = rules.pair_curve_y(charts, svgs)
    assert len(pairings) == 3 and all(p['status'] == 'pass_y_values' and p['points'] == 200 for p in pairings)
    conditions = {}
    for ti, table in enumerate(current['tables']):
        if not table or not table[0]:
            continue
        title = table[0][0]
        if title not in ('研发, 千 美元', '运营改进, 千 美元'):
            continue
        assert table[1] == ['\u00a0', '今年', '去年']
        for ri, row in enumerate(table[2:], 2):
            if len(row) == 3 and row[0] in ('复合梁', '连接件', '泰国'):
                conditions[(title, row[0])] = dict(input_category='PREVIOUS_GROUP_ACTUAL_INPUT_FROM_FORMAL4_LAST_YEAR_COLUMN', previous_value=numeric(row[2]), unit='千美元', source_table=ti, source_row=ri, source_column=2, source=str(current_path.relative_to(ROOT)), source_sha256=sha(current_path))
    labels_path = CLOSE / 'decision_history/final_decisions_labeled/all_fields.json'
    final3 = read(labels_path)['fields']
    for (section, label), condition in conditions.items():
        match = [r for r in final3 if r['round_id'] == 'formal3' and r['section'] == section and r['label'] == label and r['group_category'] == 'ROUND_K_GROUP_FINAL_DECISION']
        assert len(match) == 1 and numeric(match[0]['group_value']) == condition['previous_value']
        condition['matched_final3_group_source'] = match[0]['source']
        condition['matched_final3_group_row'] = match[0]['source_row_zero_based']
        condition['matched_final3_group_column'] = match[0]['group_column_zero_based']
    assert sorted(c['previous_value'] for c in conditions.values()) == [400, 600, 1000]
    records, summaries, diffs = [], [], []
    old_series = {(c['id'], s['seriesname']): (c, s) for c in old_charts for s in c['data'].get('dataset', []) if s.get('seriesname', '').startswith('曲线')}
    for chart in charts:
        categories = chart['data'].get('categories', [])
        for series in chart['data'].get('dataset', []):
            if not series.get('seriesname', '').startswith('曲线'):
                continue
            key = (chart['id'], series['seriesname'])
            product = series['seriesname'].split(', ')[1]
            section = '研发, 千 美元' if 'quality.control' in chart['id'] else '运营改进, 千 美元'
            condition = conditions[(section, product)]
            labels = [p['label'] for p in categories[0]['category']]
            ys = [p['value'] for p in series['data']]
            assert len(labels) == len(ys) == 200 and all(numeric(y) is not None for y in ys)
            old_chart, old = old_series[key]
            old_labels = [p['label'] for p in old_chart['data']['categories'][0]['category']]
            old_ys = [p['value'] for p in old['data']]
            assert len(old_labels) == len(old_ys) == 200
            pairing = next(p for p in pairings if (p['chart_id'], p['series']) == key)
            slug = 'rd_beam' if product == '复合梁' else 'rd_connector' if product == '连接件' else 'operations_thailand'
            curve = dict(valid_period='formal4', market=5, chart_id=chart['id'], series=series['seriesname'], source=str(current_path.relative_to(ROOT)), source_sha256=sha(current_path), upstream_condition=condition, x_axis='本回合有效投资，千美元', x_precision='原始类别标签已舍入，不能称精确投入横坐标', x_labels=labels, original_y_values=ys, pairing=pairing, points=200, independent_samples=200, svg_additional_samples=0)
            save(slug + '.json', curve)
            summaries.append(dict(series=series['seriesname'], chart_id=chart['id'], file=slug+'.json', points=200, x_label_min=min(map(numeric, labels)), x_label_max=max(map(numeric, labels)), y_min=min(map(numeric, ys)), y_max=max(map(numeric, ys)), previous_group_actual_input=condition['previous_value'], previous_input_source_table=condition['source_table'], previous_input_source_row=condition['source_row'], previous_input_source_column=2, max_svg_y_delta=pairing['max_y_difference'], svg_index=pairing['svg_index']))
            delta = []
            for i, (x, y, ox, oy) in enumerate(zip(labels, ys, old_labels, old_ys)):
                difference = numeric(y) - numeric(oy)
                delta.append(abs(difference))
                diffs.append(dict(series=series['seriesname'], index=i, formal4_rounded_x_label=x, formal3_rounded_x_label=ox, displayed_x_labels_equal=x == ox, formal4_y=y, formal3_y=oy, y_delta_index_aligned=difference, scope='按200点序号对比，两期x范围不同；不是同一精确投入x处差异'))
                records.append(dict(series=series['seriesname'], index=i, rounded_x_label=x, original_y=y, valid_period='formal4'))
            summaries[-1]['index_aligned_max_absolute_y_delta_vs_formal3'] = max(delta)
            summaries[-1]['formal3_rounded_x_range'] = [min(map(numeric, old_labels)), max(map(numeric, old_labels))]
    assert len(summaries) == 3 and len(records) == len(diffs) == 600
    save('all_charts_original.json', dict(source=str(current_path.relative_to(ROOT)), charts=charts, original_nan_preserved=True, series_ranges=rules.chart_ranges(charts)))
    for index in sorted({p['svg_index'] for p in pairings}):
        with (HERE / f'source_svg_{index}.svg').open('x', encoding='utf-8') as f:
            f.write(svgs[index])
    save('curve_index.json', summaries)
    save_csv('curve_points.csv', records)
    save_csv('formal3_formal4_index_comparison.csv', diffs)
    save('pairing_checks.json', pairings)
    comparison_path = CLOSE / 'formal4_initial/verification/20261014T002441/carryover_comparison.json'
    carry = read(comparison_path)['rows']
    missing_review = []
    for row in carry:
        if row['comparison_status'] != 'UNKNOWN_NO_IDENTICAL_OPENING_FIELD':
            continue
        kind = row['formal3_category']
        reason = 'Formal4已采页面没有可独立配对的同口径期初余额/状态；非缺少全部页面'
        if kind == 'UNKNOWN_NOT_REPORTED_OR_TIMING_UNVERIFIED':
            reason = '真实持续存量、税亏、待生效时点或产品独立价值未披露，不用上期投入/模型rho补造'
        elif kind in ('FORMAL3_ACTUAL_FLOW_NOT_OPENING_INPUT', 'FORMAL3_CASH_CONTEXT', 'CUMULATIVE_COMMON_BASELINE', 'FORMAL3_ACTUAL_EXPENSE_NOT_CONTINUING_STATE'):
            reason = '上期发生额/历史基准/费用不是本期期初存量，不适用机械原值结转；相关余额或持续状态另核'
        elif kind == 'FORMAL3_VISIBLE_CAPACITY':
            reason = '已在capacity_projection_checks中验证零个人投资衰减；页面容量仍是当前个人投影，不升级无条件组期初'
        elif row['key'].startswith('group_final_'):
            reason = '上期已生效投入或投资不是本期期初存量；待生效时点不能靠再加一次投资推断'
        elif kind == 'FORMAL3_REPORTED_NEXT_ROUND_ORDER':
            reason = '上期下期订单已显示0；正式4已获得订单栏本期为空，不能将招标数或空白当确认承诺0'
        missing_review.append(dict(key=row['key'], field=row['field'], formal3_category=kind, formal3_known_value=row['formal3_value'], formal4_same_scope_status='UNKNOWN_OR_NOT_APPLICABLE_NO_ZERO_FILL', reason=reason, original_boundary=row['boundary']))
    assert len(missing_review) == 46
    save('carryover_unknown_review.json', dict(reviewed_fields=46, nine_pages_complete=True, thirteen_sources_have_hashes=True, source_index_is_not_missing_value_count=True, rows=missing_review))
    sources = [current_path, prior_path, RULE_PATH, Path(rules.rules.__file__), labels_path, comparison_path, CLOSE / 'formal4_initial/verification/20261014T002441/sources.json']
    save('version_index.json', dict(valid_period='formal4', sources=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for p in sources], formal4_curves=summaries, formal4_known_conditions_version='formal4_initial/verification/20261014T002441/known_conditions.json', formal4_published_parameters_version='formal4_initial/verification/20261014T002441/published_parameters.csv', upstream_group_inputs=[dict(section=k[0], field=k[1], **v) for k, v in conditions.items()], applied_model='未重训、未更新、未部署', formal3_curve_comparison_source=str(prior_path.relative_to(ROOT))))
    assert all(sha(p) == s['sha256'] for p, s in zip(sources, read(HERE / 'version_index.json')['sources']))
    save('acceptance.json', dict(status='THREE_FORMAL4_CURVES_FROZEN_AND_Y_PAIRED', curves=3, points_per_curve=200, total_curve_points=600, all_curve_y_finite=True, all_svg_y_pairings_pass=True, raw_nan_and_round_effect_series_preserved=True, x_precision='rounded', no_refit=True, no_model_update=True, sources_unchanged=True, self_check_passed=True, script_sha256=sha(Path(__file__))))
    with (HERE / 'report.md').open('x', encoding='utf-8') as f:
        f.write('# 正式4曲线封存与版本索引\n\n不要输出真名，姓名统一用首字母替代。复用历史核验charts解码及pair_curve_y，只读原文件，不执行网页脚本、不重训或改模型。\n\n')
        for r in summaries:
            f.write(f"{r['series']}：200点，原显示x范围{r['x_label_min']}至{r['x_label_max']}千美元；上期小组实际投入{r['previous_group_actual_input']}千美元，原页table {r['previous_input_source_table']}/row {r['previous_input_source_row']}/column 2证实。JSON与SVG纵坐标最大差{r['max_svg_y_delta']:.3g}。正式3显示x范围{r['formal3_rounded_x_range']}，按序号对齐y最大绝对差{r['index_aligned_max_absolute_y_delta_vs_formal3']:.8g}。\n\n")
        f.write('三条曲线共600点，SVG同源不增加独立样本。横坐标标签已舍入，两期横轴范围不同；逐点CSV仅按序号比较，不能读作同一精确投入x处差异。回合效果系列的原NaN全部保留在all_charts_original.json，不清零。原SVG按源索引独立保存。\n\n')
        f.write('关键条件版本与上期小组投入对应证据见version_index.json。13项sources是9个子页加开始/结束列表、历史投资页和结转表，并不是13个未知字段；此前46项结转unknown逐项复核见carryover_unknown_review.json。部分为上期费用/发生额不适合结转，部分真实余额/持续状态未在本次同口径页面披露，两个容量投影已另行条件验证。保持未知，不为凑全补零。\n\n')
        f.write('正式3比较使用已验证历史个人生产计划原件中的对应情境曲线，不覆盖旧冻结预测或模型。正式4当前输入仍不是截止小组final。\n')
    print(json.dumps(dict(output=str(HERE), curves=len(summaries), points=len(records), pairing_max_delta=max(p['max_y_difference'] for p in pairings), unknown_review=len(missing_review)), ensure_ascii=False))


if __name__ == '__main__':
    main()
