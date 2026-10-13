"""Fit three payroll branches; validate only on reserved live budget samples."""
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import table_rows, number
from build_model_inputs import production_and_delivery

OUT = Path(__file__).resolve().parent
SPECS = [
    ('train_a20_budget.txt', 'train', 20),
    ('train_a50_budget_valid.txt', 'train', 50),
    ('train_a80_budget.txt', 'train', 80),
    ('validation_a33_4_budget.txt', 'validation', 33.4),
    ('validation_a66_7_budget.txt', 'validation', 66.7),
    ('validation_a100_restored_budget.txt', 'validation', 100),
]
state_path = ROOT / 'output/formal_update/20261011T224300+0800_state/formal2_initial_states.json'
state = next(s for s in json.loads(state_path.read_text(encoding='utf-8'))['states']
             if s['market_id'] == 5 and s['team'] == '营销团队')
previous_workers = state['formal2_initial_state']['workers']
data = []
for filename, split, allocation in SPECS:
    path = OUT / filename
    snapshot = path.read_text(encoding='utf-8')
    assert 'generic: 回合2' in snapshot and '市场 5' in snapshot
    rows = table_rows(snapshot)
    def get(label):
        matches = [r for r in rows if r['cells'] and r['cells'][0] == label]
        assert len(matches) == 1, (filename, label)
        return number(matches[0]['cells'][1])
    assert get('产能分配, %') == allocation
    assert get('生产效率, 千单位/人') == .17
    cap = get('产能, 千单位')
    q = cap * allocation / 100  # demand 18 exceeds capacity throughout these trials
    n = q / .17
    bands = [min(q, cap/3), min(max(q-cap/3, 0), cap/3), max(q-2*cap/3, 0)]
    data.append(dict(file=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        captured_at=datetime.fromtimestamp(path.stat().st_mtime, timezone(timedelta(hours=8))).isoformat(),
        split=split, allocation=allocation, capacity=cap, efficiency=.17, q=q, n=n,
        band_workers=[x/.17 for x in bands], observed_q=get('生产, 千单位'),
        observed_n=get('生产线人工数量'), payroll=get('工厂员工成本'), firing=get('解聘费'),
        profit=get('本回合利润'), category='platform_budget_not_actual_result'))

train = [r for r in data if r['split'] == 'train']
# Triangular design: training samples progressively enter the first, second, third band.
rates = []
for i, row in enumerate(train):
    rates.append((row['payroll'] - sum(a*b for a,b in zip(row['band_workers'], rates)))
                 / row['band_workers'][i])
xbar, ybar = mean(r['n'] for r in train), mean(r['firing'] for r in train)
slope = sum((r['n']-xbar)*(r['firing']-ybar) for r in train) / sum((r['n']-xbar)**2 for r in train)
intercept = ybar - slope*xbar
fitted = dict(wage=rates[0], second_shift=rates[1]/rates[0], third_shift=rates[2]/rates[0],
              severance=-slope/rates[0], retained_workers=intercept/-slope,
              attrition=1-(intercept/-slope)/previous_workers)
for row in data:
    row['fitted_payroll'] = sum(a*b for a,b in zip(row['band_workers'], rates))
    row['fitted_firing'] = max(intercept+slope*row['n'], 0)
    official = production_and_delivery(row['capacity'], row['allocation'], .17, [4.5,13.5],
        [0,1], 28, 1.65, 2.56, previous_workers, .1, .35)
    row['official_payroll'] = official['payroll']
    row['official_firing'] = official['firing']
    # Half a displayed monetary unit; previous headcount has +/- .005 display uncertainty.
    row['checks'] = dict(production=abs(row['q']-row['observed_q']) <= .005+1e-9,
        workers=abs(row['n']-row['observed_n']) <= .05+1e-9,
        published_payroll=abs(row['official_payroll']-row['payroll']) <= .5+1e-9,
        published_firing=abs(row['official_firing']-row['firing']) <= .5+.005*.9*28*.35+1e-9,
        fitted_payroll=abs(row['fitted_payroll']-row['payroll']) <= .5+1e-9,
        fitted_firing=abs(row['fitted_firing']-row['firing']) <= .5+1e-9)
    assert all(row['checks'].values()), row
assert len(train) == 3 and len(data)-len(train) == 3
assert {r['file'] for r in train}.isdisjoint(r['file'] for r in data if r['split']=='validation')
restored_rows = table_rows((OUT/'restored_checklist.txt').read_text(encoding='utf-8'))
baseline = {
    '泰国, 美元': ['1 800.0'], '印尼, 美元': ['2 000.0'],
    '大客户订单, 美元': ['0.0'], '大客户订单': ['0.0'],
    '泰国': ['100', '100', '第一', '760', '4.50', '-1.00'],
    '印尼': ['200', '100', '第二', '13.50', '3.50'],
    '复合梁': ['100.0', '650', '1.00', '0.17'],
    '分包制造': ['FALSE'], '机器, 复合梁': ['0'],
    '长期贷款变化(增加 + / 减少 -), 千 美元': ['0'], '长期贷款利率, %': ['3.00'],
    '利润, 千 美元': ['-530'],
}
for label, expected in baseline.items():
    actual = [r['cells'][-1] for r in restored_rows if len(r['cells'])==6 and r['cells'][0]==label]
    assert actual == expected, (label, actual, expected)
result = dict(market=5, phase='formal', round=2, personal_area='PYT',
    published=dict(wage=28, second_shift=1.65, third_shift=2.56, attrition=.1, severance=.35),
    previous_workers=previous_workers, previous_state_source=str(state_path),
    previous_state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),
    fitted=fitted, samples=data, all_checks_passed=True, restoration_checked=True,
    exclusions=['train_a50_budget.txt','train_a50_budget_saved.txt','validation_eta25_plan.txt'],
    limits=['One capacity, efficiency, opening workforce and current context only.',
            'Budget outputs are not realized results or operating-efficiency training labels.',
            'Boundary points only cover the upper side of each nominal threshold.',
            'Firing fit identifies a conditional line and zero floor, not unique event timing.',
            'No machine investment or multi-round labor dynamics tested.'])
(OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
lines = ['# 人力成本网页预算：训练与验证', '',
    '市场5、正式2、PYT个人区。采集训练样本3条、留出验证样本3条。网页原始损益预算和生产页独立保存；未更新预算的输入排除。', '',
    '只用20%、50%、80%产能训练，33.4%、66.7%及100%用于验证；100%是试验前基准并在恢复后重采。', '',
    '| 分组 | 产能分配% | 产量千单位（模型精确值） | 人数（模型精确值） | 网页工资千美元 | 网页裁员费千美元 |',
    '|---|---:|---:|---:|---:|---:|']
for r in data:
    lines.append(f"| {r['split']} | {r['allocation']} | {r['q']:.5f} | {r['n']:.3f} | {r['payroll']:.0f} | {r['firing']:.0f} |")
lines += ['', '训练结果：', '', f"- 基础工资 {fitted['wage']:.6f} 千美元/人，第二班倍数 {fitted['second_shift']:.6f}，第三班倍数 {fitted['third_shift']:.6f}。",
    f"- 条件裁员线 F=max({intercept:.6f}−{-slope:.6f}×N,0)，补偿比例估计 {fitted['severance']:.6%}，自然离职比例估计 {fitted['attrition']:.6%}。",
    '- 后两项依据固定期初人数96.09和线性结构估计，不能据此唯一识别平台的事件顺序。', '',
    '公布参数28、1.65、2.56、10%、35%代入原有共享函数后，6条预算的工资和裁员费均与显示舍入区间兼容；拟合参数对3条留出样本也全部通过。人数和产量同样通过显示精度核验。', '',
    '裁员费核验纳入期初人数两位小数的±0.005不确定性；网页财务金额显示整数。50%样本的公式中心值406.5138与显示406的0.5138差额，在上述联合显示误差范围内，未放宽为任意经验容差。', '',
    '结论：本次支持三个等分产能班次、连续人数计算、分班工资和裁员费的当期预算表达式；不等于证明隐藏算法唯一，也不等于验证真实效率预测或跨回合迁移。', '',
    '未采得有效0.25效率样本；未试机器投资、其他期初人数、边界下侧、库存/大客户分支和多回合动态。未训练运营投入—实际效率函数，未替换既有模型。', '',
    '恢复：产能100%、效率0.17、研发650、运营760，重入生产页回读一致；工资4376、裁员费0、利润−530与初始预算一致。完整个人列表恢复检查另见restored_checklist.txt。', '',
    '复现：运行本目录analyze.py；样本原文、哈希、输入、输出、拟合及逐项断言见validation.json。']
(OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(fitted=fitted, checks='all passed', train=3, validation=3),ensure_ascii=False))
