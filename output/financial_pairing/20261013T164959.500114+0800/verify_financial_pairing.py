"""Offline acceptance report; run the shared archive audit first. Exclusive outputs only."""
import argparse
import importlib.util
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/round_close/20261012T221044.031+0800'
spec = importlib.util.spec_from_file_location('archive_audit', BASE / 'audit/verify_archive.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(audit.redact_names(json.dumps(value, ensure_ascii=False, indent=2)))


def ref(rec):
    # Team identifiers are column numbers, so even unknown roster names stay out of deliverables.
    return {k: rec[k] for k in ('source', 'sha256', 'html_source', 'html_sha256', 'table_index', 'row_index') if k in rec}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    generated = datetime.now(timezone(timedelta(hours=8)))
    out = args.output or ROOT / 'output/financial_pairing' / generated.strftime('%Y%m%dT%H%M%S.%f+0800')
    out.mkdir(parents=True, exist_ok=bool(args.output))
    with (out / 'work_log.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n{generated.isoformat()} START acceptance; offline; originals unchanged; no decisions or training.\n')
    run = args.audit.resolve()
    rows, financial, charts = [read(run / name) for name in ('rows.json', 'financial_checks.json', 'charts.json')]
    validation = read(run / 'validation.json')
    old = BASE / 'audit/20261013T160101.677658+0800'
    old_checks = read(old / 'financial_checks.json')
    sources = read(run / 'sources.json')
    assert validation['coverage_counts'] == {'verified': 750}
    assert not validation['source_hash_changes_during_run'] and not validation['source_hash_changes_since_first_audit']
    assert not any(x['status'] == 'fail' for x in financial)
    for s in sources:
        assert audit.sha(BASE / s['source']) == s['sha256'], s['source']
    for s in read(old / 'sources.json'):
        assert audit.sha(BASE / s['source']) == s['sha256'], s['source']
    current = BASE / 'resume/20261013T_goal/current_2026-10-13T082849281Z'
    for s in read(current / 'sources.json'):
        assert audit.sha(current.parent / s['source']) == s['sha256'], s['source']
    assert read(current / 'verification.json')['personal_values_stable']

    remaining = []
    for item in financial:
        if item['status'] != 'pending':
            continue
        key = tuple(item['key'])
        evidence = [r for r in rows if (r['market'], r['phase'], r['round'], r['panel']) == key
                    and r['cells'] and audit.label_key(r['cells'][0]) in item.get('missing_or_ambiguous_labels', [])]
        remaining.append({**{k: item[k] for k in ('key', 'check', 'status', 'missing_or_ambiguous_labels')},
                          'reason': '原件有11或12个值，而已核团队队列为10；不能截列或猜测附加列归属。',
                          'evidence': [{**ref(r), 'label': audit.label_key(r['cells'][0]),
                                        'width': len(r['cells']), 'expected_width': 11,
                                        'display_values_in_original_order': r['cells'][1:]} for r in evidence]})
        assert evidence and all(len(r['cells']) > 11 for r in evidence)
    structure = []
    for s in read(run / 'structure_checks.json'):
        r = next(r for r in rows if r['source'] == s['source'] and r['table_index'] == s['table_index'] and r['row_index'] == s['row_index'])
        structure.append({**s, 'sha256': r['sha256'], 'label': audit.label_key(r['cells'][0]),
                          'reason': 'HTML及采集表均保存额外列；部分额外表头为Name11，团队身份未证明。保留整行，不截列。'})

    mapping = []
    for x in financial:
        if x['status'] != 'pass':
            continue
        index = x['team_column_index']
        for s in x.get('sources', []):
            if not isinstance(s, dict):
                continue
            r = next(r for r in rows if r['source'] == s['source'] and r['table_index'] == s['table_index'] and r['row_index'] == s['row_index'])
            display = r['cells'][index]
            value, tolerance = audit.num(display)
            mapping.append({'check': x['check'], 'market': r['market'], 'phase': r['phase'], 'round': r['round'],
                            'panel': r['panel'], 'team_id': f"M{r['market']:02d}T{index:02d}",
                            'label_original': r['cells'][0], 'label_key': audit.label_key(r['cells'][0]),
                            'section': [s for s in r['section_path'] if len(s) < 60 and 'Export As' not in s],
                            'country': x['key'][-1] if x['check'] == 'demand_sales_unmet' else None,
                            'product': x['key'][-2] if x['check'] == 'demand_sales_unmet' else None,
                            'unit': x['unit'], 'display': display, 'value': value, 'display_half_step': tolerance,
                            'category': 'actual_result', **ref(r)})
    # Repeated references participate in different checks; export each check/field once.
    mapping = list({(m['check'], m['source'], m['table_index'], m['row_index'], m['team_id']): m for m in mapping}.values())
    per_item = [{**{k: v for k, v in x.items() if k not in ('team', 'sources')},
                 'team_id': f"M{x['key'][0]:02d}T{x['team_column_index']:02d}" if 'team_column_index' in x else None,
                 'sources': [ref(s) if isinstance(s, dict) else s for s in x.get('sources', [])]} for x in financial]

    # A same-page chart is another representation of one observation, not an independent sample.
    exact_profits, chart_by_key = {}, {}
    crosschecks = []
    nan_count = 0
    for c in charts:
        if c.get('panel') != 'summary' or c['identity_status'] != 'verified':
            continue
        key = (c['market'], c['phase'], c['round'], 'summary')
        chart_by_key.setdefault(key, {})[c['chart']['id']] = c
    for key, group in chart_by_key.items():
        rec = audit.paired_row(rows, key, '本回合利润')
        chart = group['Graphs.Summary.Profitability']
        data = chart['chart']['data']
        teams = [c['label'] for c in data['categories'][0]['category']]
        assert rec and teams == rec['team_order']
        series = [s for d in data['dataset'] for s in d['dataset'] if s['seriesname'] == '利润']
        assert len(series) == 1 and len(series[0]['data']) == 10
        exact_profits[key] = [p['value'] for p in series[0]['data']]
        for i, value in enumerate(exact_profits[key], 1):
            shown, tol = audit.num(rec['cells'][i])
            crosschecks.append({'key': key, 'team_id': f'M{key[0]:02d}T{i:02d}', 'check': 'profit_exact_chart_vs_display',
                                'display': shown, 'chart_value': value, 'residual': value - shown, 'tolerance': tol + 1e-9,
                                'status': 'pass' if abs(value - shown) <= tol + 1e-9 else 'fail',
                                'chart_id': chart['chart']['id'], 'chart_source': chart['html_source'],
                                'chart_sha256': chart['html_sha256'], 'row': ref(rec), 'independent_sample': False})
    for key, group in chart_by_key.items():
        m, phase, round_no, panel = key
        rec = audit.paired_row(rows, key, '累计收益')
        assert rec
        chart = group['Graphs.Results.Summary.CumulEarnings.TimeSeries.summary']
        data = chart['chart']['data']
        slots = [p['label'] for p in data['categories'][0]['category']]
        slot = slots.index(str(round_no))
        assert [s['seriesname'] for s in data['dataset']] == rec['team_order']
        nan_count += sum(p['value'] == 'NaN' for s in data['dataset'] for p in s['data'])
        periods = [(m, 'initial', 0, panel)] + [(m, phase, r, panel) for r in range(1, round_no + 1)]
        for i in range(1, 11):
            shown, tol = audit.num(rec['cells'][i])
            total = sum(exact_profits[k][i - 1] for k in periods)
            rounded_chart = data['dataset'][i - 1]['data'][slot]['value']
            assert audit.num(str(rounded_chart)) is not None
            crosschecks.append({'key': key, 'team_id': f'M{m:02d}T{i:02d}', 'check': 'cumulative_exact_profit_sum_vs_display',
                                'display': shown, 'exact_profit_sum': total, 'rounded_cumulative_chart': rounded_chart,
                                'residual': total - shown, 'tolerance': tol + 1e-9,
                                'status': 'pass' if abs(total - shown) <= tol + 1e-9 and rounded_chart == shown else 'fail',
                                'contributing_periods': periods, 'chart_id': chart['chart']['id'],
                                'chart_source': chart['html_source'], 'chart_sha256': chart['html_sha256'],
                                'row': ref(rec), 'independent_sample': False})
    assert len(exact_profits) == 50 and len(crosschecks) == 1000
    chart_counts = dict(Counter(x['status'] for x in crosschecks))

    old_pending = [x for x in old_checks if x['status'] == 'pending']
    transition = []
    for x in old_pending:
        paired = [y for y in financial if y['key'] == x['key'] and y['check'] == x['check']]
        transition.append({'key': x['key'], 'check': x['check'], 'old_status': 'pending',
                           'new_counts': dict(Counter(y['status'] for y in paired)),
                           'reason': '额外列归属未证明' if any(y['status'] == 'pending' for y in paired)
                           else '供需分区重置并保留国家/产品' if x['check'] == 'demand_sales_unmet'
                           else '完整补件与原件核对，累计基准按同阶段历史图验证' if x['check'] == 'cumulative_profit_difference'
                           else '规范化换行帮助符号；保留原标签、数值及舍入容差'})
        assert paired
    summary = {'generated_at': generated.isoformat(), 'status': 'COMPLETE_WITH_EXPLICIT_REVIEW_ITEMS',
               'archive_audit': run.relative_to(ROOT).as_posix(), 'history_page_coverage': 750,
               'financial_counts': dict(Counter(x['status'] for x in financial)),
               'old_pending_records': len(old_pending), 'old_pending_resolved': sum('pending' not in t['new_counts'] for t in transition),
               'remaining_pending': len(remaining), 'structure_review': len(structure),
               'same_source_chart_crosschecks': chart_counts, 'future_nan_preserved_in_cumulative_charts': nan_count,
               'rejected_sources': validation['failures'], 'original_and_old_audit_source_hashes_unchanged': True,
               'current16_sources_hashes_unchanged': True, 'current_budgets_remain_paired_to_current_decisions': True,
               'old_budgets_without_contemporaneous_decisions_remain_unpaired': True,
               'decision_modified': False, 'model_trained': False, 'personal_names_in_delivery': False,
               'limits': ['6 wider financial rows require team-column evidence; never truncated.',
                          '26 structural reviews remain open.', 'One stale HTML supplement remains rejected; original tables remain usable.',
                          'Budget values are conditional forecasts, never actual training labels.']}
    for name, value in [('acceptance.json', summary), ('label_mapping.json', mapping), ('financial_checks.json', per_item),
                        ('remaining.json', remaining), ('structure_review.json', structure), ('chart_crosschecks.json', crosschecks),
                        ('old_pending_transition.json', transition), ('source_hashes.json', sources)]:
        write(out / name, value)
    command = '"<LOCAL_USER_DIR>\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe"'
    report = f'''# 财务标签配对验收

时间：{generated.isoformat()}（北京时间）。不要输出真名，姓名统一用首字母替代；交付表仅使用市场/团队列编号。

财务审计9340项通过、0项数值失败、6项待核、10项初始基准不适用。旧235个pending记录中229个已配对，6个保留；记录数随按团队展开增加，不能将235与新增通过条数直接相减。历史页覆盖仍为750/750。26项结构review未关闭。

根因：换行帮助符号不能用rstrip精确去除；市场份额分区未重置导致需求重复；7个累计待核记录需要完整HTML补件；部分HTML本身有额外列。规范化仅去空白与末尾帮助问号，不改数字、单位或标签含义。重复标签和多列继续拒绝。所有等式均核对队列；供需只配市场明细需求/销售与物流明细未满足需求，保持国家、产品、千单位及供给截断含义。缺失/NaN不补零。

累计收益：指南第6页说明练习结束后回到初始状态。50个时期的概要表与同页CumulEarnings/Profitability图表逐队配对；初始0显示收益约1293千美元，不是零。正式1与练习1各自回到初始0基准，正式2接正式1，练习2接练习1，不能继承练习2到正式1。累计表与初始利润加同阶段各期利润的全精度和交叉核验结果为{chart_counts}（共1000项利润/累计检查）；图表与表格同源，不是独立样本。CumulRevenue图是收入序列，不能当累计收益；CumulEarnings时间序列本身已舍入，保留其NaN及显示精度。

发现新证据冲突：市场2练习1完整HTML补件选择器虽为练习1，利润/累计图第1年却为NaN且表仍为初始值。补件被拒绝；原件所保存的练习1数表与原件脚本、练习2历史图一致，因此继续使用原件，不用旧值或补零替代。旧“完整HTML750页”是结构验收，本次内容配对只有46/47补件获接纳；该页完整且同期的HTML仍待补证。旧round3_productionplanning身份拒绝亦保留。两个拒绝项使完整档案审计仍标INCOMPLETE，不能称全部证据通过。

正式3新版本16份来源哈希已核；三次个人列稳定及四类预算绑定沿用同期验收。新productionplanning独立存在且通过当前身份核验，未替换旧拒绝原件。旧两份预算各留版本，缺同期决策的旧预算未配对；预算不作为实际标签。

## 剩余待核

|市场/阶段/回合|检查|原因|
|---|---|---|
'''
    for x in remaining:
        report += f"|{x['key'][0]}/{x['key'][1]}/{x['key'][2]}|{x['check']}|{x['reason']}|\n"
    report += f'''
逐项来源、原列数和数值见[剩余证据](remaining.json)；26项见[结构审查](structure_review.json)。不能截去Name11或第12值，也不凭会计平衡猜测团队归属。

交付：[标签映射](label_mapping.json)、[逐项核验](financial_checks.json)、[旧待核迁移](old_pending_transition.json)、[同源图表交叉检查](chart_crosschecks.json)、[来源哈希](source_hashes.json)、[验收JSON](acceptance.json)。映射保存源行列、规范化前后标签、分区、单位、国家/产品、数值及显示半步容差。原始证据和旧结论未覆盖。

复现：在项目根目录先运行 `{command} output/round_close/20261012T221044.031+0800/audit/verify_archive.py`，再运行 `{command} work/verify_financial_pairing.py --audit <新审计目录>`。第二条默认排他创建新报告目录；不要重用--output覆盖旧交付。新审计包含完整代码快照；本目录另附验收脚本快照。离线复现不访问平台。

未训练模型、未改平台决策、未提交小组方案、未评价六回合最优。额外列和同期HTML冲突尚未解决；原件及审计中未知队名未全面认证，只分享本目录脱敏交付文件，勿打包raw或旧审计目录。
'''
    with (out / 'report.md').open('x', encoding='utf-8') as stream:
        stream.write(audit.redact_names(report))
    with (out / 'verify_financial_pairing.py').open('x', encoding='utf-8') as stream:
        stream.write(Path(__file__).read_text(encoding='utf-8'))
    with (out / 'work_log.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n{audit.now()} END; counts={summary["financial_counts"]}; charts={chart_counts}; remaining={len(remaining)}; structure={len(structure)}; no decisions/training.\n')
    print(json.dumps({'output': str(out), 'financial': summary['financial_counts'], 'charts': chart_counts}, ensure_ascii=False))


if __name__ == '__main__':
    main()
