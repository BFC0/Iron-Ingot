"""Rebuild grouped archive indexes and verify this session; no browser writes."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from archive_and_report import table_rows, write_json

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'raw'


def load(name):
    return json.loads((RAW / (name + '.json')).read_text(encoding='utf-8'))


def cells(name):
    return [r['cells'] for r in table_rows(load(name)['snapshot']) if r['cells']]


def classify(name):
    phase, round_no = 'shared', None
    for token, label, number in [('initial0', 'initial', 0),
                                 ('practice1', 'practice', 1),
                                 ('practice2', 'practice', 2),
                                 ('round1', 'formal', 1)]:
        if token in name:
            phase, round_no = label, number
            break
    if 'native_25' in name:
        phase, round_no, kind = 'formal', 1, 'validated_saved_input'
    elif 'modeltest' in name:
        phase, round_no = 'formal', 1
        kind = 'invalid_probe' if 'modeltest_C_' in name or 'modeltest_D_' in name else 'decision_and_budget_mixed'
    elif 'user_probe_B' in name:
        phase, round_no = 'formal', 1
        kind = 'validated_budget_probe'
    elif 'probe_' in name:
        phase, round_no = 'formal', 1
        kind = 'invalid_probe' if 'probe_B' in name else 'platform_budget_baseline'
    elif '_svg' in name:
        phase, round_no, kind = 'formal', 1, 'rendered_chart_geometry'
    elif 'help' in name or 'manual' in name or 'case' in name or 'tutorial' in name:
        kind = 'rules'
    elif 'outlook' in name:
        kind = 'scenario_parameters'
    elif 'budget_' in name:
        kind = 'platform_budget'
    elif 'printable' in name or 'summary' in name:
        kind = 'actual_result'
    elif phase != 'shared':
        kind = 'decision_and_budget_mixed'
    else:
        kind = 'course_context'
    return phase, round_no, kind


def main():
    now = datetime.now(timezone.utc).isoformat()
    # Ignore focus markers and the ticking deadline; compare every table cell.
    before = cells('20261011_round1_checklist')
    after = cells('20261011_round1_checklist_restored')
    tooltip = ['进入决策区域制定决策或浏览。登录时，你自己的决策区域为默认区域。']
    assert [r for r in before if r != tooltip] == [r for r in after if r != tooltip]
    assert cells('20261011_round1_demand_baseline') == cells('20261011_demand_restored')
    practice = cells('20261011_practice1_outlook')
    formal = cells('20261011_round1_outlook')
    assert practice == formal, 'Visible practice1/formal1 scenario mismatch'
    assert len(formal) > 30
    assert cells('20261011_probe_A_budget')[:30] == cells('20261011_probe_B_budget')[:30]
    assert '11.57 1.00' in load('20261011_probe_B_input')['snapshot']
    assert '11.57 5.00' in load('20261011_probe_B_server_readback')['snapshot']
    for name in ['initial0_printable', 'practice1_printable', 'practice2_printable']:
        profit = [r for r in cells(name) if r[0] == '本回合利润, 千 美元']
        assert len(profit) == 1 and len(profit[0]) == 11

    def current(name, label):
        matches = [r for r in cells(name) if r[0] == label]
        assert len(matches) == 1, (name, label)
        return float(matches[0][1].replace(' ', '').replace('\u00a0', ''))

    valid_probe = (RAW / '20261011_user_probe_B_budget_income.json').is_file()
    if valid_probe:
        assert '泰国 10.00 4.32 2.31 1.00' in load('20261011_user_probe_B_demand')['snapshot']
        assert '泰国 10.00 4.32 2.31 1.00' in load('20261011_user_probe_B_demand_readback')['snapshot']
        assert ['泰国', '5.00', '5.00', '5.00', '5.00', '1.00'] in cells('20261011_user_probe_B_checklist')
        user_cells = cells('20261011_user_probe_B_checklist')
        assert len(user_cells) == len(after)
        changed = [(a, b) for a, b in zip(after, user_cells) if a != b]
        assert len(changed) == 3
        assert {a[0] for a, b in changed} == {'利润, 千 美元', '销售变化%', '泰国'}
        assert all(a[:-1] == b[:-1] for a, b in changed), 'Only personal column may differ'
        assert ['运往 泰国', '1.00', '4.32'] in cells('20261011_user_probe_B_logistics')
        assert ['运往 印尼', '2.40', '11.68'] in cells('20261011_user_probe_B_logistics')
        labels = ['净销售额', '运输', '利息收入', '本回合利润']
        deltas = {label: current('20261011_user_probe_B_budget_income', label)
                  - current('20261011_probe_A_budget', label) for label in labels}
        assert deltas == {'净销售额': -2400, '运输': 216, '利息收入': -12, '本回合利润': -2628}
        assert deltas['本回合利润'] == deltas['净销售额'] - deltas['运输'] + deltas['利息收入']
        write_json(ROOT / '有效预估试验_B核验.json', dict(
            actor='user', phase='formal', round=1, data_kind='validated_budget_probe',
            current_personal_thailand_demand_kunits=1, current_group_thailand_demand_kunits=5,
            preserved_user_change=True, platform_revenue_kusd=7800,
            revenue_formula='1*3000+2.4*2000', transport_kusd=318,
            transport_formula='1*30+2.4*120', profit_kusd=-5291,
            deltas=deltas, profit_delta_formula='-2400-216-12=-2628',
            precision='Displayed rounded financial rows; not an unrounded interest formula',
            conclusion='给定需求预测和供给下的预算分配/收入/运输验证；非真实需求样本'))

    native_saved = (RAW / '20261011_native_25_readback.json').is_file()
    if native_saved:
        for name in ['20261011_native_25_input', '20261011_native_25_readback']:
            assert ['泰国', '10.00', '4.32', '5.78', '2.50'] in cells(name)
        assert ['泰国', '5.00', '5.00', '5.00', '5.00', '2.50'] in cells('20261011_native_25_checklist')
        assert classify('20261011_native_25_readback') == ('formal', 1, 'validated_saved_input')
        write_json(ROOT / '原生键盘保存核验.json', dict(
            result='PASS', source='raw/20261011_native_25_readback.json',
            captured_at=load('20261011_native_25_readback')['captured_at'],
            field='泰国需求预测', unit='千单位', personal_value=2.5, group_value=5,
            derived_share_percent=5.78, input_method='native keyboard, separate calls',
            checks=['派生更新', '个人列核对', '重新进入原页回读'],
            full_budget_archived=False, actual_demand_label=False))

    index, output_rows = [], []
    for path in sorted(RAW.glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        phase, round_no, kind = classify(path.stem)
        snapshot = data.get('snapshot', '')
        item = dict(file=path.relative_to(ROOT).as_posix(), phase=phase, round=round_no,
                    data_kind=kind, captured_at=data.get('captured_at'),
                    source_url=data.get('source_url'), market=data.get('market', 5),
                    usable_for_demand_fit=kind == 'actual_result' and phase == 'practice',
                    usage='练习实际作为训练候选；正式实际作为外部检验；预算不作需求标签',
                    representation=data.get('representation', 'DOM snapshot'),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if kind == 'actual_result' and phase == 'initial':
            item['usage'] = '初始基准状态；不是独立策略实验'
        if kind == 'invalid_probe':
            item['usage'] = '客户端输入未保存、派生份额未变；禁止用于参数校准'
        if kind == 'validated_budget_probe':
            item['usage'] = '用户输入已生效；需求页/个人决策/物流/预算交叉验证；仅校准预算机制'
        if kind == 'validated_saved_input':
            item['usage'] = '原生键盘保存核验；玩家需求预测及派生预算，未采集完整财务表；非实际需求'
        if kind == 'decision_and_budget_mixed':
            item['usage'] = '含决策和手填预测及预算；逐字段配对已执行的小组策略，不能整页作实际结果'
        if 'help' in path.stem:
            item['usage'] = '帮助原文有效；底层页面可能同时含预算，不作实际需求标签'
        index.append(item)
        for row in table_rows(snapshot):
            output_rows.append([item['file'], phase, round_no, kind, data.get('captured_at'),
                                row['line'], row['row_text'],
                                json.dumps(row['cells'], ensure_ascii=False)])
    write_json(ROOT / '数据分组索引.json', index)
    with (ROOT / '分组表格行索引.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['来源文件', '阶段', '回合', '数据类型', '采集时间UTC',
                         '快照行号', '完整行文本', '单元格JSON数组'])
        writer.writerows(output_rows)

    checks = dict(generated_at=now, result='PASS', json_files=len(index),
                  indexed_rows=len(output_rows), scenario_comparison_rows=len(formal),
                  practice1_formal1_visible_scenario_equal=True,
                  previous_agent_batch_decision_cells_equal_baseline=True,
                  previous_agent_batch_demand_restored=True,
                  valid_perturbation_samples=int(valid_probe), group_submission_performed=False,
                  current_personal_user_change_preserved=valid_probe or native_saved,
                  current_personal_thailand_demand_kunits=2.5 if native_saved else (1 if valid_probe else 5),
                  current_group_thailand_demand_kunits=5,
                  native_keyboard_save_verified=native_saved,
                  latest_state_source='raw/20261011_native_25_readback.json' if native_saved else 'raw/20261011_user_probe_B_checklist.json',
                  latest_state_captured_at=load('20261011_native_25_readback')['captured_at'] if native_saved else None,
                  current_state_is_live=False,
                  hidden_demand_function_equal='UNDETERMINED',
                  limitations=['原生键盘已在需求字段验证；其他字段及此前失败原因尚待核对',
                               '正式回合实际结果未发生', 'SVG仅为可见绘图几何，非内部公式',
                               '风险溢价、厂房自动支出机制、原材料差额及精确曲线仍未校准'])
    write_json(ROOT / '增量归档核验.json', checks)
    conditional = dict(status='CONDITIONAL_CALCULATION_NOT_OBSERVED',
                       quantities_kunits=dict(A_th=3.4, A_in=0, B_th=1, B_in=2.4),
                       prices_usd=dict(th=3000, indonesia=2000, C_th=3100),
                       A_revenue_kusd=3.4 * 3000,
                       B_revenue_kusd=1 * 3000 + 2.4 * 2000,
                       A_transport_kusd=3.4 * 30,
                       B_transport_kusd=1 * 30 + 2.4 * 120,
                       C_revenue_delta_kusd=3.4 * (3100 - 3000),
                       assumptions='预算供给仍3.4、泰国优先、印尼需求足够；非需求模型',
                       formulas=['R=sum(q_i*p_i)', 'T=sum(q_i*t_i)', 'delta_R=q_th*(p_new-p_old)'])
    assert conditional['B_revenue_kusd'] == 7800
    assert conditional['B_transport_kusd'] == 318
    assert conditional['C_revenue_delta_kusd'] == 340
    write_json(ROOT / '预估试验_条件计算.json', conditional)
    coverage = json.loads((ROOT / '归档覆盖与待办.json').read_text(encoding='utf-8'))
    coverage.update(status='ARCHIVE_UPDATED_VALIDATION_LIMITED', generated_at=now,
                    archival_complete=False, decision_modified=valid_probe or native_saved,
                    agent_persisted_decision_modified=native_saved,
                    decision_probe_attempted=True, decision_probe_persisted=valid_probe or native_saved,
                    user_personal_decision_changed=valid_probe,
                    scope='市场5；旧快照保留，新增案例、教程、日程、教师答复、练习历史决策/前景、图形/提示及正式1预算',
                    completed_additions=['案例全文', '快速教程', '阅读材料索引（本轮无教师上传）',
                                         '完整日程和主页教师答复', '练习1/2历史决策及前景',
                                         '生产与两国销售图形PNG/SVG', '生产/研发/运营/营销/需求/负债/税费帮助',
                                         '正式1最新决策与四类预算', '数据类型与回合分组索引'],
                    pending=['其他字段原生输入与单变量预算试验（需求字段已验证）',
                             '图形精确点与字段边界校准', '厂房自动支出、原材料差额与风险溢价机制核对',
                             '正式实际结果归档与练习拟合模型外部检验',
                             '模型拟合、回算与情景优化', '推荐值及个人区域填写回读；小组提交另行协调'])
    coverage['files'] = index
    write_json(ROOT / '归档覆盖与待办.json', coverage)
    manifest = [dict(file=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size,
                     sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                for p in sorted(ROOT.rglob('*'))
                if p.is_file() and p.name != 'SHA256_manifest.json' and '__pycache__' not in p.parts and '.git' not in p.parts]
    write_json(ROOT / 'SHA256_manifest.json', manifest)
    assert all(hashlib.sha256((ROOT / m['file']).read_bytes()).hexdigest() == m['sha256'] for m in manifest)
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    main()
