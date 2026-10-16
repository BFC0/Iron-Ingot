"""Add an independently optimized COUNTRY column without changing prior candidates."""
import copy,csv,inspect,json,re,shutil,sys
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'work')]
import numpy as np
import t5v1
import solve_formal5_full as base
from scipy.optimize import differential_evolution

OUT=ROOT/(ROOT/'work/t5v1_active_run.txt').read_text(encoding='utf-8-sig').strip()
CHANGE=OUT/'country_update'/datetime.now().strftime('%Y%m%dT%H%M%S')
CHANGE.mkdir(parents=True)
(CHANGE/'work_log.md').write_text('# COUNTRY新增列\n\n按用户要求，复用冻结t5v1，独立最大化COUNTRY正式5—6利润；保留原三核心情景现金约束与全部范围。原候选不改，t5v0b只读。新增42字段、需求预估和逐项敏感性及15情景比较；修改前备份报告、注册表和对应导出。\n',encoding='utf-8')
read=base.read
save=lambda name,v:(CHANGE/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
registry=read(OUT/'models_full.json');result=read(OUT/'full_result.json');cfgs=result['configs']
m=t5v1.ApplicationModel();m.__dict__.update(t5v1.decode(registry['application_state']))
m.r={'risk':registry['risk']};m.current={int(k):v for k,v in m.current.items()}
oldrows=read(OUT/'decisions.json');seedrows=[r for r in oldrows if r['plan']=='稳健利润候选']
m.fields=[dict(row=r['row'],key=r['key'],section=r['section'],product_or_location=r['product'],label=r['label'],unit=r['unit']) for r in seedrows]
actual_bounds=copy.deepcopy(m.bounds);actual_baseline=m.baseline.copy()
m.baseline[4:8]=[m.general_total,0,0,0];m.baseline[8:12]=[m.designer_total,0,0,0]
for i in [5,6,7,9,10,11]:m.bounds[i]=[0,0]
base.OUT=CHANGE
source=inspect.getsource(base.search).replace("for objective in ['中性','稳健']:","for objective in ['COUNTRY']:").replace("active=cfgs[:1] if objective=='中性' else cfgs[:3]","active=cfgs[1:2]")
ns=dict(vars(base));exec(compile(source,'country_search','exec'),ns)
x=ns['search'](m,cfgs)[0]
m.baseline=actual_baseline;m.bounds=actual_bounds
def distribute(total,weights):
    raw=total*weights/weights.sum();values=np.floor(raw).astype(int)
    for i in np.argsort(-(raw-values))[:int(round(total-values.sum()))]:values[i]+=1
    assert sum(values)==total
    return values
raw=x.copy()
x[4:8]=distribute(int(round(sum(x[4:8]))),m.local_general.ravel())
x[8:12]=distribute(int(round(sum(x[8:12]))),m.local_designer.ravel())
evaluations=[dict(name=c['name'],**m.evaluate(x,c,True)) for c in cfgs]
assert all(e['feasible'] for e in evaluations[:3])
assert all(e['balance_error_max']<1e-7 and e['quantity_error_max']<1e-8 for e in evaluations)
assert all(abs(m.evaluate(raw,c)[0][0]-m.evaluate(x,c)[0][0])<1e-7 for c in cfgs[:3])
plan=dict(name='COUNTRY利润候选',objective='国别COUNTRY',x=x.tolist(),evaluations=evaluations,raw_search_allocation=raw.tolist())
save('country_result.json',plan)
# Base sensitivity code uses the first scenario as its reference.
base.sensitivity(m,[result['comparisons'][0],plan],[cfgs[1],cfgs[0],*cfgs[2:]])
sens=read(CHANGE/'sensitivity_all_fields.json');assert len({s['key'] for s in sens})==42
p5=evaluations[1]['periods'][0]
values={row:x[j]*(20 if row==47 else 100 if row==54 else 1) for j,row in enumerate(base.ROWS)}
values.update({65:7.,66:-5.,68:7.,69:-5.,72:0.,73:0.,76:round(p5['efficiency'][0],6),77:round(p5['efficiency'][1],6),79:round(p5['rate']*100,2)})
for j,rr in enumerate([[58,59],[61,62]]):
    for k,row in enumerate(rr):values[row]=round(p5['demand'][j][k],2)
for j,rr in enumerate([[34,35],[37,38]]):
    for k,row in enumerate(rr):values[row]='第一' if p5['priority'][j]==k else '第二'
countryrows=[]
for r in seedrows:
    z=copy.deepcopy(r);v=values.get(r['row'],m.current[r['row']]);v=v.item() if isinstance(v,np.generic) else v;z.update(plan=plan['name'],suggested=v,changed=bool(v!=m.current[r['row']]))
    if r['row'] in base.ROWS:z['reason']='COUNTRY利润目标独立联合搜索；原三核心情景采样现金≥3000；'+r['reason']
    elif r['row'] in [58,59,61,62,76,77,79]:z['reason']='按COUNTRY候选及COUNTRY需求情景一致重算；'+r['reason']
    countryrows.append(z)
assert len(countryrows)==42
save('decisions_country.json',countryrows)

# Back up all modified existing artifacts before the first mutation.
changed=['report.md','decisions.json','decisions.csv','full_result.json','models_full.json','field_coverage.json','validation.json','version_manifest.json']
backups=CHANGE/'before';backups.mkdir()
hashes={}
for name in changed:
    shutil.copy2(OUT/name,backups/name);hashes[name]={'before':base.sha(OUT/name)}
registry['saved_plans'].append(dict(name=plan['name'],x=plan['x']))
for cfg,expected in zip(cfgs,evaluations):
    actual=t5v1.apply_request(registry,dict(version='t5v1',market_id=5,phase='formal',round=5,plan=plan['name'],scenario=cfg['name']))
    assert abs(actual['profit_5_to_6']-expected['profit_5_to_6'])<1e-8
result['comparisons'].append(plan)
def write(name,v):(OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
write('models_full.json',registry);write('full_result.json',result);write('decisions.json',oldrows+countryrows)
with (OUT/'decisions.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(oldrows[0]));w.writeheader();w.writerows(oldrows+countryrows)
fmt=lambda v:f'{v:,.4f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)
country_byrow={r['row']:r for r in countryrows}
text=(OUT/'report.md').read_text(encoding='utf-8')
text=text.replace('中性候选 | 稳健候选（建议） |','中性候选 | COUNTRY候选 | 稳健候选（建议） |')
text=text.replace('| --- | --- | ---: | ---: | ---: | --- |','| --- | --- | ---: | ---: | ---: | ---: | --- |')
order=[65,66,58,59,68,69,61,62,72,73,46,47,41,42,43,76,77,51,52,49,9,18,25,13,21,29,10,19,26,14,22,30,11,27,15,31,34,35,37,38,54,79]
first_end=text.index('[逐字段CSV]')
head=text[:first_end];tail=text[first_end:];counter=0;rebuilt=[]
for line in head.splitlines():
    if line.startswith('| ') and not line.startswith('| 项目 |') and not line.startswith('| ---'):
        row=order[counter];r=country_byrow[row];counter+=1;cells=line.split('|')
        assert cells[2].strip()==r['unit'] and cells[3].strip()==fmt(r['current']),(row,line)
        cells[1]=' '+'／'.join(str(v) for v in [r['section'],r['product'],r['label']] if v)+' '
        cells.insert(5,' '+fmt(r['suggested'])+' ');line='|'.join(cells)
    rebuilt.append(line)
assert counter==42
text='\n'.join(rebuilt)+'\n'+tail
intro='\n\nCOUNTRY列为新增独立候选：最大化国别COUNTRY模型的正式5—6税后利润，同时保留与原两方案完全相同的三核心情景采样现金≥3000约束、支持范围、期限和未来政策。需求等预估字段按COUNTRY模型重算，不是把原决策重复展示。营销细分仍按当前构成分摊，未识别细分最优。'
text=text.replace('## 全部字段建议（按决策子页及类别顺序）',intro+'\n\n## 全部字段建议（按决策子页及类别顺序）',1)
e=evaluations
line=f'| {plan["name"]} | {e[0]["profit_5_to_6"]:,.2f} | {e[0]["profit_5_to_6"]-result["comparisons"][0]["evaluations"][0]["profit_5_to_6"]:,.2f} | {e[1]["profit_5_to_6"]:,.2f} | {e[2]["profit_5_to_6"]:,.2f} | {e[2]["sampled_minimum_cash"]:,.2f} | {100*x[19]:,.0f} |'
marker=next(l for l in text.splitlines() if l.startswith('| 稳健利润候选 |'))
text=text.replace(marker,marker+'\n'+line,1)
# Add the candidate to the existing common SHARE production comparison.
a,b=e[0]['periods'];line=f'| {plan["name"]} | {a["profit"]:,.2f} | {b["profit"]:,.2f} | {a["production"][0]:.4f} | {a["production"][1]:.4f} | {a["closing_inventory"][1]:.4f} | {sum(a["demand"][1])-sum(a["sales"][1]):.4f} |'
start=text.index('| 方案（中性）');end=text.index('\n\n',start)
text=text[:end]+'\n'+line+text[end:]
# Add comparable data columns, all from the same COUNTRY scenario.
metric=['','## COUNTRY同情景经营与财务数据','',
    '以下每列均代入COUNTRY情景；与上表“中性”数据口径分开。金额千美元、数量千单位，利率为%。',
    '', '| 数据 | 中性候选 | COUNTRY候选 | 稳健候选 |','| --- | ---: | ---: | ---: |']
compare=[result['comparisons'][1],plan,result['comparisons'][2]]
def metricrow(label,fn):metric.append('| '+label+' | '+' | '.join(fmt(fn(q['evaluations'][1])) for q in compare)+' |')
metricrow('正式5—6税后利润',lambda v:v['profit_5_to_6'])
metricrow('两期采样最低现金',lambda v:v['sampled_minimum_cash'])
for t in range(2):
    for name,key in [('税后利润','profit'),('期末现金','cash'),('长期贷款余额','long_debt'),('贷款利息','long_interest'),('收入','revenue')]:metricrow(f'正式{5+t} {name}',lambda v,t=t,key=key:v['periods'][t][key])
    metricrow(f'正式{5+t} 贷款利率',lambda v,t=t:v['periods'][t]['rate']*100)
    for j,product in enumerate(base.P):
        metricrow(f'正式{5+t} {product}产量',lambda v,t=t,j=j:v['periods'][t]['production'][j])
        metricrow(f'正式{5+t} {product}期末库存',lambda v,t=t,j=j:v['periods'][t]['closing_inventory'][j])
        for k,country in enumerate(base.C):
            for name,key in [('需求','demand'),('销量','sales')]:metricrow(f'正式{5+t} {product}/{country}{name}',lambda v,t=t,j=j,k=k,key=key:v['periods'][t][key][j][k])
text=text.replace('## 正式4训练及正式5需求重要性替换','\n'.join(metric)+'\n\n## 正式4训练及正式5需求重要性替换',1)
# Add COUNTRY sensitivity beside existing robust sensitivity without mixing reference models.
start=text.index('## 42字段逐项敏感性');end=text.index('## 全局假设压力',start)
part=text[start:end].replace('| 类别 |','| COUNTRY候选减少/另一选项 | COUNTRY候选增加/另一选项 | 类别 |').replace('| --- | --- | --- | --- |','| --- | --- | --- | --- | --- | --- |')
for r in seedrows:
    prefix='| '+'／'.join(str(v) for v in [r['section'],r['product'],r['label']] if v)+' |'
    match=[l for l in part.splitlines() if l.startswith(prefix)];assert len(match)==1
    tests=[v for v in sens if v['row']==r['row']]
    cells=['N/A' if v['delta_profit_5_to_6'] is None else f'{fmt(v["test"])} → {v["delta_profit_5_to_6"]:+,.2f}'+('（现金约束失效）' if not v.get('feasible',True) else '') for v in tests]
    cells+=['—']*(2-len(cells));parts=match[0].split('|');parts[4:4]=[' '+v+' ' for v in cells];part=part.replace(match[0],'|'.join(parts))
part=part.replace('以稳健候选为中心','原两列以稳健候选/中性SHARE为中心，新增两列以COUNTRY候选/国别COUNTRY为中心（各自相对自身基准，不能混读）。以稳健候选为中心',1)
rel=CHANGE.relative_to(OUT).as_posix()
part+='\n[COUNTRY逐项敏感性CSV]('+rel+'/sensitivity_all_fields.csv) · [COUNTRY离散扫描]('+rel+'/neutral_discrete_frontier.json)。\n\n'
text=text[:start]+part+text[end:]
start=text.index('## 全局假设压力');end=text.index('## 生产与财务假设',start)
part=text[start:end].replace('| 稳健采样最低现金 |','| COUNTRY候选利润 | COUNTRY候选最低现金 | 稳健采样最低现金 |').replace('| --- | ---: | ---: | ---: | ---: |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
for cfg,v in zip(cfgs,e):
    line=next(l for l in part.splitlines() if l.startswith('| '+cfg['name']+' |'))
    cells=line.split('|');cells[5:5]=[f' {v["profit_5_to_6"]:,.2f} ',f' {v["sampled_minimum_cash"]:,.2f} '];part=part.replace(line,'|'.join(cells))
text=text[:start]+part+text[end:]
text=text.replace('三方案×15情景回放','四方案×15情景回放')
text+='\n\nCOUNTRY新增依据：[求解结果]('+rel+'/country_result.json)、[搜索记录]('+rel+'/searches.json)、[更新验收]('+rel+'/validation.json)。两目标既有候选保持原值。COUNTRY按自身模型表现选择，不能据其较高得分推断预测更准确；总体仍优先稳健候选，除非接受更大的模型选择与不利情景风险。\n'
(OUT/'report.md').write_text(text,encoding='utf-8')
coverage=read(OUT/'field_coverage.json');coverage.update(records=126,candidates=3,country_sensitivity_fields=42);write('field_coverage.json',coverage)
validation=read(OUT/'validation.json');validation.update(decision_records=126,country_candidate_fields=42,country_candidate_scenarios_replayed=15);write('validation.json',validation)
audit=read(OUT/'t5v0b_preservation_audit.json')
for item in audit['checks']:assert base.sha(ROOT/item['path'])==item['sha256']
save('validation.json',dict(status='PENDING_FINAL_LINK_AND_HASH_CHECKS'))
links=[]
for target in re.findall(r'\]\(([^)]+)\)',text):
    if '://' in target or target.startswith('#'):continue
    assert (OUT/target.split('#')[0]).resolve().exists(),target
    links.append(target)
for name in changed:
    if name!='version_manifest.json':hashes[name]['after']=base.sha(OUT/name)
save('document_changes.json',hashes)
save('validation.json',dict(status='PASS',country_fields=42,total_records=126,all_15_scenarios_replayed=True,core_cash_feasible=True,quantity_and_balance_identities=True,marketing_total_allocation_equivalent=True,existing_candidates_unchanged=result['comparisons'][:3]==read(backups/'full_result.json')['comparisons'],t5v0b_original_hashes_match=64,report_links_checked=len(links)))
shutil.copy2(Path(__file__),CHANGE/Path(__file__).name)
manifest=read(OUT/'version_manifest.json');manifest['outputs']={str(f.relative_to(OUT)):base.sha(f) for f in OUT.rglob('*') if f.is_file() and f.name!='version_manifest.json'}
write('version_manifest.json',manifest)
for rel,digest in manifest['outputs'].items():assert base.sha(OUT/rel)==digest
print('COUNTRY_UPDATE',CHANGE,flush=True)
print(json.dumps(dict(x=plan['x'],core=[(v['name'],v['profit_5_to_6'],v['sampled_minimum_cash']) for v in evaluations[:3]]),ensure_ascii=False),flush=True)
