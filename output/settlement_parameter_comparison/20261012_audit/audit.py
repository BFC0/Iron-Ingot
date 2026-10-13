"""Offline comparison of published parameters and settled expenses; no source edits."""
import csv
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import number, table_rows

manifest = {}


def read(relative):
    path = ROOT / relative
    raw = path.read_bytes()
    manifest[relative] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def get(rows, label, column, occurrence=0):
    matches = [r for r in rows if r['cells'] and r['cells'][0] == label and len(r['cells']) == 11]
    assert len(matches) > occurrence, (label, occurrence)
    row = matches[occurrence]
    return number(row['cells'][column]), row['line']


started = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
with (OUT / 'work_log.md').open('a' if (OUT / 'work_log.md').exists() else 'x', encoding='utf-8') as f:
    f.write(f'# 系统参数与结算费用核对\n\n开始：{started}。\n\n'
            '授权范围：只列系统给定参数，不包含玩家预测或预算。只读本地原件。'
            '不要输出真名，姓名统一用首字母替代。复用项目表格解析器；新增独立报告，不改模型、原件或平台决策。\n')

contexts = [
    ('练习1', 'raw/20261011_practice1_outlook.json', 'raw/cross_market', 'practice_1', 900, 3),
    ('练习2', 'raw/20261011_practice2_outlook.json', 'raw/cross_market', 'practice_2', 1053, 2.5),
    ('正式1', 'raw/20261011_round1_outlook.json', 'output/formal_update/20261011T223000+0800_sources', 'formal1', 900, 3),
]
records = []
parameters = []
for phase, outlook, directory, suffix, base, rate in contexts:
    published = table_rows(read(outlook)['snapshot'])
    parameters.extend(dict(phase=phase, label=r['cells'][0], start=r['cells'][1], previous=r['cells'][3],
                           source=outlook, line=r['line'])
                      for r in published if len(r['cells']) == 4)
    assert any(r['cells'][0] == '复合梁' and number(r['cells'][1]) == base for r in published if len(r['cells']) == 4)
    assert any(r['cells'][0] == '基准利率' and number(r['cells'][1]) == rate for r in published if len(r['cells']) == 4)
    paths = sorted((ROOT / directory).glob(f'market_*_{suffix}.json'))
    if phase.startswith('练习'):
        assert len(paths) == 9
        paths.append(ROOT / f'raw/practice{2 if phase == "练习2" else 1}_printable.json')
    assert len(paths) == 10
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        doc = read(relative)
        if path.name.startswith('practice'):
            summary_file = f'raw/practice{2 if phase == "练习2" else 1}_summary.json'
            selection = read(summary_file)['snapshot']
            assert 'option "市场 5" [selected]' in selection
            assert f'option "练习回合{2 if phase == "练习2" else 1}" [selected]' in selection
            doc['market_id'] = 5
        else:
            assert doc['selection_verified'] is True and doc['kind'] == 'actual_result'
            assert doc['round'] == (2 if phase == '练习2' else 1)
            assert doc['phase'] == ('formal' if phase == '正式1' else 'practice')
        rows = table_rows(doc['snapshot'])
        headers = [r['cells'] for r in rows if len(r['cells']) == 10 and
                   all(c and not re.fullmatch(r'[\d\s.,%+?−-]+', c) for c in r['cells'])]
        assert headers and all(h == headers[0] for h in headers)
        if path.name.startswith('practice'):
            summary_rows = table_rows(selection)
            assert any(r['cells'] == headers[0] for r in summary_rows)
            for col in range(1, 11):
                assert get(rows, '本回合利润, 千 美元', col)[0] == get(summary_rows, '本回合利润', col)[0]
        for col, team in enumerate(headers[0], 1):
            q, q_line = get(rows, '生产规模, 千单位', col)
            cost, cost_line = get(rows, '原材料购买', col)
            actual_rate, rate_line = get(rows, '长期贷款利率，%', col)
            assert q > .005
            low, high = (cost - .5) / (q + .005), (cost + .5) / (q - .005)
            records.append(dict(phase=phase, market=doc['market_id'], team=team, column=col,
                published_material=base, production=q, material_cost=cost,
                implied_material=cost/q, material_difference=cost/q-base,
                implied_low=low, implied_high=high, material_difference_exceeds_rounding=low > base or high < base,
                base_rate=rate, actual_long_rate=actual_rate, rate_difference_pp=actual_rate-rate,
                source=relative, production_line=q_line, material_line=cost_line, rate_line=rate_line))

assert len(records) == 300 and len({(r['phase'], r['market'], r['column']) for r in records}) == 300
ours = next(r for r in records if r['phase'] == '正式1' and r['market'] == 5 and r['team'] == '营销团队')
assert ours['production'] == 16.45 and ours['material_cost'] == 14824 and ours['actual_long_rate'] == 3.07
assert abs(ours['implied_material'] - 901.1550151975684) < 1e-9

# A next-round historical column corroborates the same prior round; its current column does not.
historical_checks = []
for phase, next_file in [('练习1', 'raw/20261011_practice2_outlook.json'),
                         ('正式1', 'output/formal_update/20261011T223000+0800_sources/formal2_outlook.json')]:
    next_rows = [r for r in table_rows(read(next_file)['snapshot']) if len(r['cells']) == 4]
    prior = [r for r in parameters if r['phase'] == phase]
    assert len(prior) == len(next_rows)
    for before, after in zip(prior, next_rows):
        assert before['label'] == after['cells'][0]
        historical_checks.append(dict(phase=phase, label=before['label'], start=before['start'],
            next_round_previous=after['cells'][3], equal=before['start'] == after['cells'][3],
            start_source=before['source'], start_line=before['line'], next_source=next_file, next_line=after['line']))

summary = []
for phase, *_ in contexts:
    rr = [r for r in records if r['phase'] == phase]
    summary.append(dict(phase=phase, n=len(rr), material_base=rr[0]['published_material'],
        implied_material_min=min(r['implied_material'] for r in rr),
        implied_material_max=max(r['implied_material'] for r in rr),
        median_material_difference=median(r['material_difference'] for r in rr),
        material_beyond_rounding_n=sum(r['material_difference_exceeds_rounding'] for r in rr),
        base_rate=rr[0]['base_rate'], actual_long_rate_min=min(r['actual_long_rate'] for r in rr),
        actual_long_rate_max=max(r['actual_long_rate'] for r in rr)))

for name, data in [('逐队对照.csv', records), ('期初参数.csv', parameters), ('同回合参数历史核对.csv', historical_checks)]:
    with (OUT / name).open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)

lines = ['# 系统给定参数与回合结算对照', '',
    '范围：本地归档的练习1、练习2、正式1，10市场各100队。正式1全部及练习其他9市场有选择核验元数据；练习市场5使用旧打印结果及其回合标签，缺独立选择快照。只比较系统参数；不含需求/效率预测或预算。市场前景原件来自市场5，其他市场的期初参数未独立逐市场采集，因此跨市场范围仅为同一市场5基准的对照，不证明各市场参数完全相同。', '',
    '**未发现已证实的“系统基础参数结算时被改值”。结算费用与公布基础参数存在以下两类数值差额。**', '',
    '| 回合 | 原料公布价（美元/单位） | 按结算反算单价范围 | 排除显示舍入后仍不同的队数 | 基准利率 | 实际长期利率范围 |',
    '| --- | ---: | ---: | ---: | ---: | ---: |']
for s in summary:
    lines.append(f"| {s['phase']} | {s['material_base']} | {s['implied_material_min']:.4f}–{s['implied_material_max']:.4f} | {s['material_beyond_rounding_n']}/100 | {s['base_rate']:.2f}% | {s['actual_long_rate_min']:.2f}%–{s['actual_long_rate_max']:.2f}% |")
lines.extend(['', '1. **原材料单位费用**：原材料购买额（千美元）÷生产规模（千单位）。这是费用反算值，不是系统直接公布的结算单价。金额整数按±0.5千美元、产量两位小数按±0.005千单位核对；舍入模式尚未核实。稳定差额的组成未知，不能据此宣称平台改了基础原料价格。',
    '2. **公司长期贷款利率**：结果直接披露实际利率，高于前景基准。指南第19页明确公司债务风险决定公司利率；这是公司风险定价，并不证明基准利率改变。短期利率=公司长期利率+当期短期附加利率；结算没有直接披露实际短期利率，不将推算值写成观察到的参数变化。', '',
    f"市场5营销团队正式1：原料900 → {ours['implied_material']:.4f}美元/单位（14824÷16.45），反算差额+{ours['material_difference']:.4f}；长期利率基准3.00% → 实际3.07%，差额+0.07个百分点。", '',
    f"市场前景参数共{len(parameters)//3}行/回合；练习1与正式1各{len(historical_checks)//2}行期初值均与下一回合‘去年’列一致。该历史列是参数一致性的佐证，不等于逐项实付费用验证。练习2缺下一回合历史参数，不能作相同核验。", '',
    '未纳入差异：正式2今年原料1053、基准2.50%、短期附加2.00%是下一回合的新参数。工资基准28与实际人均工资因班次不同、总单位可变成本与原料基础价、税额与税率、现金余额与最低现金要求，均不是同一口径，不能直接相减认定改参。', '',
    '未能逐项独立核实：汇率、环境强度、库存持有费（须非零库存与计费时点）、短期附加利率（须计息余额及时间）、人员自然流失/解雇费（须期初人数和触发条件）等基础参数。没有对照证据不记作零差异。', '',
    '完整逐队数据见逐队对照.csv；所有系统参数与定位见期初参数.csv；历史参数核对另表保存。来源哈希见verification.json。'])
(OUT / 'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
verification = dict(started=started, completed=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
    records=len(records), summary=summary, historical_parameter_checks=len(historical_checks),
    historical_parameter_mismatches=[r for r in historical_checks if not r['equal']],
    parameter_rows_per_round=len(parameters)//3, our_formal1_example=ours, source_sha256=manifest,
    source_hashes_unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == sha for p, sha in manifest.items()),
    limitations=['期初前景只独立核验市场5', '材料反算单价不等于平台基础参数', '未读取当前网页', '练习2缺下一回合历史参数'])
assert verification['source_hashes_unchanged']
with (OUT / 'verification.json').open('x', encoding='utf-8') as f:
    json.dump(verification, f, ensure_ascii=False, indent=2)
with (OUT / 'work_log.md').open('a', encoding='utf-8') as f:
    f.write(f"\n完成：{verification['completed']}。300队记录唯一性、来源身份、示例计算和原件哈希检查通过；历史参数核对{len(historical_checks)}行。未改任何原件或决策。\n")
print(json.dumps(dict(summary=summary, historical_mismatches=verification['historical_parameter_mismatches'],
                     parameter_rows_per_round=verification['parameter_rows_per_round']), ensure_ascii=False, indent=2))
