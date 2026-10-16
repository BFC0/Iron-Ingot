"""Recompute three-candidate sensitivity with explicit domains and core-scenario cash checks."""
import copy,csv,hashlib,json,re,shutil,sys
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2')]
import numpy as np
import t5v1
OUT=ROOT/(ROOT/'work/t5v1_active_run.txt').read_text(encoding='utf-8-sig').strip()
CHANGE=OUT/'sensitivity_rewrite'/datetime.now().strftime('%Y%m%dT%H%M%S')
CHANGE.mkdir(parents=True)
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
(CHANGE/'work_log.md').write_text('# 敏感性重写\n\n修复缺少中性候选、参考情景不清、仅单情景可行性标记及配比扰动与文字不一致。冻结原三候选与模型，统一扰动、按全部核心情景复核现金。旧敏感性证据保留；t5v0b仅只读哈希核验。\n',encoding='utf-8')
reg=read(OUT/'models_full.json');result=read(OUT/'full_result.json');cfgs=result['configs']
m=t5v1.ApplicationModel();m.__dict__.update(t5v1.decode(reg['application_state']));m.r={'risk':reg['risk']}
m.current={int(k):v for k,v in m.current.items()}
ROWS=[9,10,13,14,18,19,21,22,25,26,29,30,51,52,49,46,47,42,43,54]
ORDER=[65,66,58,59,68,69,61,62,72,73,46,47,41,42,43,76,77,51,52,49,9,18,25,13,21,29,10,19,26,14,22,30,11,27,15,31,34,35,37,38,54,79]
old=read(OUT/'decisions.json');fields={r['row']:r for r in old if r['plan']=='稳健利润候选'}
plans=[next(p for p in result['comparisons'] if p['name']==n) for n in ['中性利润候选','COUNTRY利润候选','稳健利润候选']]
references=[0,1,0];baselines={};records=[]
fmt=lambda v:f'{v:,.4f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)

def snapshot(x,cfg,overrides=None):return m.evaluate(x,cfg,True,overrides=overrides)
def predicted(row,e,cfg):
    p=e['periods'][0]
    if row in [58,59,61,62]:return p['demand'][0 if row in [58,59] else 1][0 if row in [58,61] else 1]
    if row in [76,77]:return p['efficiency'][0 if row==76 else 1]
    if row==79:return p['rate']*100
    if row in [65,68]:return 7.
    if row in [66,69]:return -5.
    if row in [72,73]:return (cfg['future_growth'][0 if row==72 else 1]-1)*100
    raise AssertionError(row)

for plan,ref in zip(plans,references):
    x=np.array(plan['x'],float);base=[snapshot(x,c) for c in cfgs[:3]];own=base[ref]
    for expected,actual in zip(plan['evaluations'][:3],base):assert abs(expected['profit_5_to_6']-actual['profit_5_to_6'])<1e-8
    baselines[plan['name']]=dict(reference=cfgs[ref]['name'],profit=own['profit_5_to_6'],worst_core_profit=min(e['profit_5_to_6'] for e in base),core_minimum_cash=min(e['sampled_minimum_cash'] for e in base))
    for row in ORDER:
        f=fields[row];common=dict(plan=plan['name'],reference_scenario=cfgs[ref]['name'],row=row,key=f['key'],unit=f['unit'],baseline_profit=own['profit_5_to_6'],baseline_worst_core_profit=min(e['profit_5_to_6'] for e in base))
        if row in [11,15,27,31,41]:
            records.append(dict(common,category='不可用／机制未解',direction='不适用',baseline_value=f['suggested'],test_value=None,delta_profit=None,delta_worst_core_profit=None,core_minimum_cash=None,core_feasible=None,status='无新招标或无可用分包机制，未求解'))
            continue
        for sign in [-1,1]:
            z=x.copy();overrides=[{} for _ in base];clipped=False;unchanged=False
            if row in ROWS:
                category='可控数值决策';j=ROWS.index(row);v=float(x[j]);scale=20 if row==47 else 100 if row==54 else 1
                display=v*scale
                if row in [9,10,13,14]:step=abs(display)*.1
                elif row in [18,19,21,22,25,26,29,30,51,52,49]:step=max(abs(display)*.1,50.)
                elif row in [42,43]:step=5.
                elif row==46:step=max(1.,round(abs(display)*.1))
                elif row==47:step=max(20.,round(abs(display)*.1/20)*20)
                elif row==54:step=max(1000.,round(abs(display)*.1/100)*100)
                else:raise AssertionError(row)
                requested=display+sign*step
                if row in [9,10,18,19,21,22,25,26,29,30,51,52,49]:requested=round(requested)
                elif row in [13,14,42,43]:requested=round(requested,1)
                lo,hi=[float(v)*scale for v in m.bounds[j]]
                if row in [18,19,21,22]:hi=min(hi,2700-(sum(x[4:8])-x[j]))
                if row in [25,26,29,30]:hi=min(hi,3840-(sum(x[8:12])-x[j]))
                test=float(np.clip(requested,lo,hi));clipped=abs(test-requested)>1e-8;unchanged=abs(test-display)<1e-8
                z[j]=test/scale
                assert all(lo-1e-8<=val<=hi+1e-8 for val,(lo,hi) in zip(z,m.bounds))
                assert sum(z[4:8])<=2700+1e-8 and sum(z[8:12])<=3840+1e-8
                v=display
            elif row in [34,35,37,38]:
                if sign==1:continue
                category='物流排序（两国联动）';j=0 if row in [34,35] else 1;k=0 if row in [34,37] else 1
                v='第一' if own['periods'][0]['priority'][j]==k else '第二';test='第二' if v=='第一' else '第一'
                overrides=[{row:test} for _ in base]
            else:
                category='预估误差／外生压力';v=predicted(row,own,cfgs[ref])
                if row in [58,59,61,62,76,77]:
                    test=v*(1+sign*.1)
                    overrides=[{row:predicted(row,e,c)*(1+sign*.1)} for e,c in zip(base,cfgs)]
                elif row==79:
                    test=v+sign
                    overrides=[{row:predicted(row,e,c)+sign} for e,c in zip(base,cfgs)]
                else:
                    test=v+sign*5
                    overrides=[{row:predicted(row,e,c)+sign*5} for e,c in zip(base,cfgs)]
            evaluated=[snapshot(z,c,o) for c,o in zip(cfgs[:3],overrides)]
            current=evaluated[ref];minimum=min(e['sampled_minimum_cash'] for e in evaluated)
            assert all(e['balance_error_max']<1e-7 and e['quantity_error_max']<1e-8 for e in evaluated)
            status='边界截断，无实际扰动' if unchanged else '边界截断，按实际幅度计算' if clipped else '已计算'
            if not all(e['feasible'] for e in evaluated):status+='；三核心情景约束失效'
            records.append(dict(common,category=category,direction='减少／切换' if sign<0 else '增加',baseline_value=v,test_value=test,actual_change=(test-v if isinstance(v,(int,float)) else None),boundary_clipped=clipped,no_actual_change=unchanged,delta_profit=current['profit_5_to_6']-own['profit_5_to_6'],delta_worst_core_profit=min(e['profit_5_to_6'] for e in evaluated)-min(e['profit_5_to_6'] for e in base),core_minimum_cash=minimum,core_feasible=all(e['feasible'] for e in evaluated),status=status,core_results=[dict(scenario=c['name'],profit=e['profit_5_to_6'],minimum_cash=e['sampled_minimum_cash'],feasible=e['feasible']) for c,e in zip(cfgs,evaluated)]))
for p in plans:assert {r['row'] for r in records if r['plan']==p['name']}==set(ORDER)
# Regression checks: 5 percentage points, core cash checking, and aggregate marketing bounds.
for r in records:
    if r['row'] in [42,43]:assert abs(abs(r['actual_change'])-5)<1e-8
    if r.get('core_results'):assert r['core_feasible']==all(v['feasible'] for v in r['core_results'])
loan=next(r for r in records if r['plan']=='稳健利润候选' and r['row']==54 and r['direction']=='减少／切换')
assert loan['test_value']==-6200 and not loan['core_feasible'] and loan['core_minimum_cash']<3000
for r in records:
    if r['row'] in [18,19,21,22] and r['direction']=='增加':assert r['no_actual_change']
save(CHANGE/'sensitivity_all_candidates.json',records);save(CHANGE/'baselines.json',baselines)
with (CHANGE/'sensitivity_all_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
    cols=[k for k in records[0] if k!='core_results'];cols=list(dict.fromkeys(k for r in records for k in r if k!='core_results'))
    w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(records)
rel=CHANGE.relative_to(OUT).as_posix()
lines=['## 敏感性分析：三类候选完整对照','',
    '本节重新计算并补齐中性、COUNTRY、稳健三套候选。原表遗漏中性候选，且将单一情景现金可行误作整体可行；本节及下列新导出取代旧敏感性表，历史原件保留。候选决策、训练系数及利润基准均未修改。',
    '', '### 基准与读表口径','',
    '| 候选 | 单项利润变化的参考情景 | 基准5—6税后利润 | 三核心情景最低利润 | 三核心情景采样最低现金 |','| --- | --- | ---: | ---: | ---: |']
for p in plans:
    b=baselines[p['name']];lines.append(f'| {p["name"]} | {b["reference"]} | {b["profit"]:,.2f} | {b["worst_core_profit"]:,.2f} | {b["core_minimum_cash"]:,.2f} |')
lines+=['',
    '金额均为千美元，期限正式5—6；每次只改变一个字段，其他决策保持原方案，不做重新优化。三核心情景是中性SHARE、国别COUNTRY和联合不利。每格显示“基准→测试值；Δ利=参考情景利润变化；Δ底=三核心最低利润变化；现=扰动后三核心采样最低现金”。▲表示任一核心情景违反模型约束，通常是现金低于3000。正的Δ利不代表符合稳健目标。各列参考情景不同，跨方案直接比较请使用后面的同情景压力表。',
    '',
    '同一字段在各列使用相同扰动规则，各自围绕自身建议值。触及分析范围或营销总预算上限时截断；“边界无扰动”表示本次没有改变输入，不能据零变化认定该参数不敏感。所有数值决策扰动按原页面展示精度取整；投资和贷款保持分析档位。',
    '', '| 类型 | 扰动规则 | 作用范围 |','| --- | --- | --- |',
    '| 售价 | ±10%，梁取整数、连接件一位小数 | 正式5及沿用价格的正式6，需求前向重算 |',
    '| 一般/设计师营销、研发、运营 | ±10%且至少50千美元，取整数 | 正式5及沿用投入的正式6，前向重算；营销不突破合计2700/3840 |',
    '| 产能分配 | ±5个百分点 | 正式5；正式6仍按既定需求后调整政策 |',
    '| 机器投资 | 梁±10%且至少1千单位；连接件±10%且至少20千单位，按档位取整 | 正式5立即生效并影响正式6衰减后容量、工资、折旧和现金 |',
    '| 贷款变化 | ±10%且至少1000千美元，按100档位取整 | 正式5融资并结转正式6，重算利率、利息、税与现金 |',
    '| 物流 | 切换两国优先顺序 | 两国排序联动；两行表示同一个选择，不能重复累计 |',
    '| 当期市场增长、下回合增长 | 各情景原增长率±5个百分点 | 当期国别增长作用5—6；下回合产品增长仅作用6 |',
    '| 需求、效率、利率预估 | 各情景自身基准需求/效率±10%；利率±1个百分点 | 需求误差仅正式5；效率/利率误差作用5—6，不是可操作的真实控制 |',
    '| 招标及分包 | N/A | 无新招标/未识别可用分包机制，仍列出但不虚构敏感性 |',
    '',
    '预估/外生冲击在每个核心情景各自基准上施加相同百分比或百分点变化，保留联合不利情景原有冲击，不用中性绝对预估覆盖不利需求。营销单项增减改变公司合计；固定合计的国别/产品重新分配在主模型内等价，仍不能识别局部投放优劣。',
    '', '### 全部42字段（三套候选各42项）','',
    '| 字段（单位） | 中性候选：减少／增加 | COUNTRY候选：减少／增加 | 稳健候选：减少／增加 | 类别 |','| --- | --- | --- | --- | --- |']
def cell(v):
    if v['delta_profit'] is None:return 'N/A：无可用机制'
    if v.get('no_actual_change'):return f'{fmt(v["baseline_value"])}→{fmt(v["test_value"])}：边界无扰动'
    return f'{fmt(v["baseline_value"])}→{fmt(v["test_value"])}；Δ利{v["delta_profit"]:+,.2f}；Δ底{v["delta_worst_core_profit"]:+,.2f}；现{v["core_minimum_cash"]:,.2f}'+('▲' if not v['core_feasible'] else '')+('（截断）' if v.get('boundary_clipped') else '')
for row in ORDER:
    f=fields[row];label='／'.join(str(v) for v in [f['section'],f['product'],f['label']] if v)+f'（{f["unit"]}）';cells=[]
    for p in plans:
        tests=[r for r in records if r['row']==row and r['plan']==p['name']]
        cells.append('；增加：'.join(cell(r) for r in tests))
    lines.append('| '+label+' | '+' | '.join(cells)+' | '+tests[0]['category']+' |')
lines+=['','完整数值及逐核心情景明细：[CSV]('+rel+'/sensitivity_all_candidates.csv)、[JSON]('+rel+'/sensitivity_all_candidates.json)、[三套基准]('+rel+'/baselines.json)。表内舍入到两位，模型用完整精度。',
    '', '### 敏感性结论','',
    '稳健候选的贷款减少额从−5200进一步降至−6200，参考中性利润虽然增加，但三个核心情景最低现金跌破3000；旧表仅检查中性情景，遗漏了这一约束。此次以▲标明，不能视为可采用的改进。',
    '',
    '一般营销合计已到2700，单项增加会突破同一个合计约束，因此本次增加方向截断为原值；降低方向仍可测。研发或投资达到上界也只提供单侧证据。固定其余输入扫描不等于放宽边界后重新求解，不能把边界零变化当成无边际价值。',
    '',
    '可用控制共24行（20个数值表示＋4行联动物流），预估/外生项13行，不可用/机制未解5行，总计42行；每套方案均覆盖。8项营销实际只识别2个合计，自由度仍为14个数值加2个物流选择。',
    '', '### 全局假设压力：统一情景比较','',
    '下表每一行让三套方案面对完全相同的情景，便于横向比较。每格为“5—6税后利润／该情景采样最低现金”；▲为该情景违反模型约束。基准行与压力行均为条件结果，没有概率权重。',
    '', '| 情景 | 中性候选：利润／现金 | COUNTRY候选：利润／现金 | 稳健候选：利润／现金 |','| --- | ---: | ---: | ---: |']
for i,c in enumerate(cfgs):
    vals=[]
    for p in plans:
        e=p['evaluations'][i];vals.append(f'{e["profit_5_to_6"]:,.2f}／{e["sampled_minimum_cash"]:,.2f}'+('▲' if not e['feasible'] else ''))
    lines.append('| '+c['name']+' | '+' | '.join(vals)+' |')
lines+=['','15个情景逐一比较不等于所有压力同时发生；“联合不利”本身已经叠加多种冲击。上述单项测试与全局情景不是独立可加的利润分解，不能将各行损益简单求和。独立跨回合预测尚未验证。',
    '', '[重写验收]('+rel+'/validation.json) · [变更与备份哈希]('+rel+'/document_changes.json)。','']
report=OUT/'report.md';text=report.read_text(encoding='utf-8');start=text.index('## 42字段逐项敏感性');end=text.index('## 生产与财务假设',start)
updated=text[:start]+'\n'.join(lines)+'\n'+text[end:]
backup=CHANGE/'before';backup.mkdir()
hashes={}
for name in ['report.md','validation.json','version_manifest.json']:
    shutil.copy2(OUT/name,backup/name);hashes[name]={'before':sha(OUT/name),'backup':str((backup/name).relative_to(ROOT))}
report.write_text(updated,encoding='utf-8')
validation=read(OUT/'validation.json');validation.update(sensitivity_candidates=3,sensitivity_field_coverage_per_candidate=42,sensitivity_primary_artifact=rel+'/sensitivity_all_candidates.json',sensitivity_core_feasibility_checked=True)
save(OUT/'validation.json',validation)
save(CHANGE/'validation.json',dict(status='PENDING_FINAL_CHECKS'))
save(CHANGE/'document_changes.json',hashes)
links=[]
for target in re.findall(r'\]\(([^)]+)\)',updated):
    if '://' in target or target.startswith('#'):continue
    assert (OUT/target.split('#')[0]).resolve().exists(),target
    links.append(target)
width=None
for line in updated.splitlines():
    if line.startswith('|'):
        now=len(line.split('|'));assert width is None or width==now,(width,now,line);width=now
    else:width=None
audit=read(OUT/'t5v0b_preservation_audit.json')
for item in audit['checks']:assert sha(ROOT/item['path'])==item['sha256']
assert read(OUT/'full_result.json')==result and read(OUT/'models_full.json')==reg
save(CHANGE/'validation.json',dict(status='PASS',candidate_count=3,field_count_each=42,candidate_field_pairs=126,test_records=len(records),all_core_scenarios_recomputed=True,allocation_step_percentage_points=5,aggregate_marketing_caps_enforced=True,robust_loan_cash_regression_passed=True,quantity_balance_identities_passed=True,original_candidates_and_coefficients_unchanged=True,t5v0b_preserved_files=64,markdown_table_widths_pass=True,report_links_checked=len(links)))
for name in hashes:
    if name!='version_manifest.json':hashes[name]['after']=sha(OUT/name)
save(CHANGE/'document_changes.json',hashes)
shutil.copy2(Path(__file__),CHANGE/Path(__file__).name)
manifest=read(OUT/'version_manifest.json');manifest['outputs']={str(f.relative_to(OUT)):sha(f) for f in OUT.rglob('*') if f.is_file() and f.name!='version_manifest.json'}
save(OUT/'version_manifest.json',manifest)
for path,digest in manifest['outputs'].items():assert sha(OUT/path)==digest
print('REPORT',report)
print('VALIDATION',json.dumps(read(CHANGE/'validation.json'),ensure_ascii=False))
print('LOAN_REGRESSION',json.dumps(loan,ensure_ascii=False))
