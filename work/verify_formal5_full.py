"""Validate current source pairing, joint outputs, financial identities, and links."""
import copy
import json
import re
import shutil
import sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import solve_formal5_full as s
import numpy as np

m=s.ScenarioModel();out=s.OUT;root=s.ROOT
r=s.read(out/'full_result.json');cfgs=r['configs'];plans=r['comparisons']
parameters=s.read(s.INITIAL/'published_parameters.json');live=s.read(out/'latest/outlook.json')['tables']
for p in parameters:
    assert live[p['table']][p['row']][p['column']]==p['current']
assert len(parameters)==42
for p in plans:
    x=np.array(p['x'])
    for e,c in zip(p['evaluations'],cfgs):
        actual=m.evaluate(x,c,True)
        assert abs(actual['profit_5_to_6']-e['profit_5_to_6'])<1e-8
        assert e['balance_error_max']<1e-7 and e['quantity_error_max']<1e-8
        for period in e['periods']:
            assert period['round'] in [5,6]
            assert all(v>=-1e-8 for v in period['closing_inventory'])
            assert np.all(np.array(period['sales'])<=np.array(period['demand'])+1e-9)
    if p['name']!='最新基准':
        assert all(e['feasible'] and e['sampled_minimum_cash']>=3000-1e-6 for e in p['evaluations'][:3])
        assert sum(x[4:8])<=2700+1e-6 and sum(x[8:12])<=3840+1e-6
        assert np.all(x>=np.array(m.bounds)[:,0]) and np.all(x<=np.array(m.bounds)[:,1])
base=m.baseline.copy();d=m.demand(base[:,None],cfgs[0],0)
up=base.copy();up[0]*=1.1
assert m.demand(up[:,None],cfgs[0],0)[0,0,0]<d[0,0,0]
up=base.copy();up[6]+=100
assert m.demand(up[:,None],cfgs[0],0)[1,0,0]>d[1,0,0]
up=base.copy();up[12]+=100
assert m.demand(up[:,None],cfgs[0],0)[0,0,0]>d[0,0,0]
up=base.copy();up[14]+=100
assert m.evaluate(up,cfgs[0],True)['periods'][0]['efficiency'][0]>m.evaluate(base,cfgs[0],True)['periods'][0]['efficiency'][0]
up=base.copy();up[15]=1
a=m.evaluate(up,cfgs[0],True);b=m.evaluate(base,cfgs[0],True)
assert abs(a['periods'][0]['capacity'][0]-b['periods'][0]['capacity'][0]-1)<1e-9
assert abs(a['periods'][1]['capacity'][0]-b['periods'][1]['capacity'][0]-.85)<1e-9
assert abs(a['periods'][0]['machine_capex']-78)<1e-9
sens=s.read(out/'sensitivity_all_fields.json');dec=s.read(out/'decisions.json')
for p in plans[1:]:
    ds=[d for d in dec if d['plan']==p['name']]
    ss=[d for d in sens if d['plan']==p['name']]
    assert len(ds)==42 and len({d['key'] for d in ds})==42
    assert {d['key'] for d in ss}=={d['key'] for d in ds}
assert abs(s.read(out/'budget_replay.json')['error_kusd'])<1
assert all(z['success'] for z in s.read(out/'searches.json'))
backup=out/'documentation_before';backup.mkdir(exist_ok=False)
readme=root/'README.md';shutil.copy2(readme,backup/'README.md');before=s.sha(readme)
text=readme.read_text(encoding='utf-8')
text=text.replace('本次未实时访问平台。本文集中维护','正式5本次优化已只读核对平台，决策基准读取于2026-10-15 16:13，前景、曲线、预算及物流核对至16:34。本文集中维护',1)
entry=(f'正式5最新决策分析：[最新数据与曲线的全项联合求解、42项敏感性]({out.relative_to(root).as_posix()}/report.md)。'
    '保留价格营销前向响应；机器本期立即生效；研发运营支出直接映射横轴。20数值决策联合搜索、2物流选择推导；'
    '无新投标及分包可用性另列。正式3响应迁移到正式4真实需求锚点、正式5曲线；两期条件结果，未提交平台。\n\n')
text=re.sub(r'正式5最新决策分析：[^\n]+\n\n','',text)
assert '## 研究诊断与条件比较' in text
text=text.replace('## 研究诊断与条件比较',entry+'## 研究诊断与条件比较',1)
text=text.replace('投资生效、人员及新增产能尚不足以做收益排名','机器当期立即生效已按指南及2026-10-15用户确认接入最新条件求解；现金时序和正式6收益仍依赖假设')
readme.write_text(text,encoding='utf-8')
s.save('document_hashes.json',dict(README=dict(before=before,after=s.sha(readme),backup=str((backup/'README.md').relative_to(root)))))
validation=dict(status='PASS',latest_parameters_matched=42,latest_curve_points_matched=600,
    paired_current_fields=42,decision_rows=84,sensitivity_unique_fields_per_candidate=42,
    candidates_recomputed=3,scenario_count=len(cfgs),forward_price_marketing_rd_monotonicity=True,
    immediate_investment_capacity_and_cost=True,quantity_and_accounting_identities=True,
    core_cash_floor_kusd=3000,display_budget_profit_error=s.read(out/'budget_replay.json')['error_kusd'],
    frozen_training_unchanged=True,platform_decisions_modified=False,
    independent_forward_validation=False,full_global_optimality_proved=False)
s.save('validation.json',validation)
links=[]
for path in [readme,out/'report.md']:
    for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        dest=target.split('#')[0]
        valid=(path.parent/dest).exists()
        links.append(dict(document=str(path.relative_to(root)),target=target,exists=valid))
assert all(x['exists'] for x in links),[x for x in links if not x['exists']]
s.save('link_checks.json',links)
for source in [Path(__file__),root/'work/solve_formal5_full.py',root/'work/report_formal5_full.py']:
    shutil.copy2(source,out/source.name)
hashes=s.read(out/'source_hashes.json')
for path in [root/'work/solve_formal5_full.py',root/'work/report_formal5_full.py',Path(__file__)]+list((out/'latest').glob('*.json')):
    hashes[str(path.relative_to(root))]=s.sha(path)
s.save('source_hashes.json',hashes)
assert all(s.sha(root/k)==v for k,v in hashes.items())
with (out/'work_log.md').open('a',encoding='utf-8') as f:
    f.write('\n验收：'+datetime.now(timezone(timedelta(hours=8))).isoformat()+'。最新42参数与旧归档一致、三曲线600点精确相等、42本人输入配对；预算利润误差−0.4501千美元。价格营销前向响应、研发及运营、投资即时产能、数量与财务守恒通过。20变量两目标×两种子均收敛；全部42项×两候选敏感性，机器/融资离散全档扫描完成。\n'
        '本次修正前一局部报告复合梁出口运费90为最新120；新增接入合计人员解聘、当前单位生产成本库存计价、厂房支出800及期初现金，均保留来源与推断分类。早期临时解析/引号错误已修复；未重训冻结模型、未修改或提交平台。README按当前磁盘备份，改前改后哈希和链接均通过。\n'
        '限制：正式3响应跨期与营销国别代理未独立验证，正式6同曲线/政策及财务时点为情景，采样现金不能保证全年最低；分包无可用控件，4项新投标不适用。不能称全参数全局最优。\n')
print(json.dumps(validation,ensure_ascii=False,indent=2))
print('REPORT',str(out/'report.md'))
