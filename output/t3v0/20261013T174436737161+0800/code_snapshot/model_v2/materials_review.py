"""Independent archived material-cost review; append-only output, no model changes."""
import csv
import hashlib
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import number, table_rows


def interval(quantity, expense, quantity_half_width=.005, expense_half_width=.5):
    assert quantity > quantity_half_width >= 0 and expense >= expense_half_width >= 0
    return ((expense-expense_half_width)/(quantity+quantity_half_width),
            (expense+expense_half_width)/(quantity-quantity_half_width))


def main():
    assert interval(10, 9000, 0, 0) == (900, 900)
    low, high = interval(10, 9000)
    assert low < 900 < high
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out = ROOT / 'output/model_v2/materials_review' / stamp
    out.mkdir(parents=True, exist_ok=False)
    paths = ['结构化模型输入.json', '分步模型拟合与验证.json',
             'raw/practice1_printable.json', 'raw/practice2_printable.json',
             'raw/20261011_practice1_outlook.json', 'raw/20261011_practice2_outlook.json',
             'raw/20261011_model_v2_round1_outlook.json']
    hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    docs = {p: json.loads((ROOT/p).read_text(encoding='utf-8')) for p in paths}
    tables = {p: table_rows(d['snapshot']) for p, d in docs.items() if 'snapshot' in d}
    parameters = {}
    for name in paths[-3:]:
        row, = [r for r in tables[name] if len(r['cells']) == 4 and r['cells'][0] == '复合梁']
        parameters[name] = dict(value=number(row['cells'][1]), line=row['line'], cells=row['cells'])
    assert parameters[paths[-3]]['value'] == parameters[paths[-1]]['value'] == 900
    assert parameters[paths[-2]]['value'] == 1053
    uplift = docs['分步模型拟合与验证.json']['finance']['materials']['uplift_usd_per_unit']
    records = []
    for h in docs['结构化模型输入.json']['history']:
        if h['round'] not in [1, 2]:
            continue
        s = h['fields']['production']
        rows = tables[s['file']]
        qrow, = [r for r in rows if r['line'] == s['line']]
        q = number(qrow['cells'][s['column']])
        assert q == s['value'] and qrow['cells'][0] == '生产规模, 千单位'
        mrow, = [r for r in rows if r['cells'] and r['cells'][0] == '原材料购买']
        m = number(mrow['cells'][s['column']])
        base = parameters[paths[-3] if h['round'] == 1 else paths[-2]]['value']
        lo, hi = interval(q, m)
        envelope = .005*base+.5
        records.append(dict(market=5, phase=h['phase'], round=h['round'], team=h['team'],
            production_kunits=q, materials_kusd=m, official_usd_per_unit=base,
            raw_residual_kusd=m-q*base, rounding_envelope_kusd=envelope,
            base_compatible=lo <= base <= hi, effective_cost_low=lo, effective_cost_high=hi,
            uplift_low=lo-base, uplift_high=hi-base,
            calibrated_residual_kusd=m-q*(base+uplift), calibrated_compatible=lo <= base+uplift <= hi,
            source_file=s['file'], production_line=s['line'], materials_line=mrow['line'], column=s['column']))
    assert len(records) == 20 and len({(r['round'],r['team']) for r in records}) == 20
    summaries = []
    for rnd in [1, 2]:
        rr = [r for r in records if r['round'] == rnd]
        lo, hi = max(r['uplift_low'] for r in rr), min(r['uplift_high'] for r in rr)
        summaries.append(dict(round=rnd, n=len(rr), official_usd_per_unit=rr[0]['official_usd_per_unit'],
            base_compatible_count=sum(r['base_compatible'] for r in rr),
            calibrated_compatible_count=sum(r['calibrated_compatible'] for r in rr),
            common_uplift_low=lo, common_uplift_high=hi, common_uplift_exists=lo <= hi,
            median_display_implied_uplift=statistics.median(r['materials_kusd']/r['production_kunits']-r['official_usd_per_unit'] for r in rr)))
    lo, hi = max(r['uplift_low'] for r in records), min(r['uplift_high'] for r in records)
    result = dict(run_id=stamp, input_hashes=hashes, code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        parameters=parameters, empirical_uplift_usd_per_unit=uplift, summaries=summaries, records=records,
        pooled_uplift_interval=dict(low=lo, high=hi, exists=lo <= hi),
        rounding_assumption='假定产量按0.01千单位、费用按1千美元四舍五入；端点按闭区间保守诊断，非已核平台规则',
        interval_formula='[(费用-0.5)/(产量+0.005), (费用+0.5)/(产量-0.005)] 美元/单位',
        limits=['只覆盖市场5练习1/2；跨回合为不同情境，合并区间仅诊断共同经验差额',
                '兼容显示舍入不证明真实机制；不兼容也不能直接归因隐藏加价',
                '没有独立高精度生产量或可恢复预算试验，不修改正式1官方单价或经验项'])
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == v for p,v in hashes.items())
    (out/'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    with (out/'records.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    lines = ['# 原材料成本独立重审', '', '官方单价：市场5练习1及正式1为900，练习2为1053美元/单位。未来涨幅叙述不叠加到当期参数。', '',
             '| 回合 | 样本 | 官方价与舍入兼容 | 经验价与舍入兼容 | 共同差额区间（美元/单位） |',
             '| --- | ---: | ---: | ---: | --- |']
    for s in summaries:
        lines.append(f"| 练习{s['round']} | {s['n']} | {s['base_compatible_count']} | {s['calibrated_compatible_count']} | [{s['common_uplift_low']:.6f}, {s['common_uplift_high']:.6f}]，{'非空' if s['common_uplift_exists'] else '空集'} |")
    lines += ['', f'旧经验差额为{uplift:.6f}美元/单位。两回合共同差额区间为[{lo:.6f}, {hi:.6f}]，'+('非空。' if lo <= hi else '空集。'), '',
              '产量半格0.005千单位产生4.5或5.265千美元费用误差，加费用半格0.5后包络为5或5.765千美元。旧“约5美元”说明需更正。', '',
              '数据直接从产量原单元格和实际材料费读取，没有从模型预测反推产量。每条来源文件、行、列见records.csv。', '',
              result['rounding_assumption'], '', *result['limits']]
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(out)
    print(json.dumps(summaries, ensure_ascii=False))


if __name__ == '__main__':
    main()
