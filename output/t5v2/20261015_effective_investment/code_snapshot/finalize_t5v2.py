"""Complete t5v2 metadata and trace coordinates without changing optimized decisions."""
import hashlib,json,re,shutil,sys
from pathlib import Path
sys.dont_write_bytecode=True
import build_t5v2 as b
ROOT,OUT=b.ROOT,b.OUT
runtime=ROOT/'code/model_v2/t5v2.py'
runtime.write_text(b.runtime_source(),encoding='utf-8')
shutil.copy2(runtime,OUT/'code_snapshot/t5v2.py')
shutil.copy2(ROOT/'work/build_t5v2.py',OUT/'code_snapshot/build_t5v2.py')
import t5v2
reg=b.read(OUT/'models_full.json')
reg['application_assumptions']['effective_investment_mapping']='t5v2: RD=.75*current+.5*previous; operations=current+.35*previous; interval-compatible formal5 mapping; prior-state weights and formal6 remain assumptions'
reg['application_assumptions']['curve_normalization']='F(E(current;formal4 input))/F(E(formal4 input;formal4 input)); counterfactual normalization, not identified formal4 effective stock'
reg['training_scope']['t5v2_new_fit']='three interval-compatible spending-to-effective-coordinate models; no historical demand/efficiency coefficient retraining'
for name,item in reg['application_actions'].items():
    item['t5v2_impact']='沿用t5v1冻结参数；研发和运营先经有效投资映射，需求、效率、生产及财务一致重算。正式6与历史归一化为情景。'
b.save('models_full.json',reg)
result=b.read(OUT/'full_result.json')
request=b.read(OUT/'example_request.json')
for p in result['comparisons']:
    for cfg,old in zip(result['configs'],p['evaluations']):
        actual=t5v2.apply_request(reg,dict(request,plan=p['name'],scenario=cfg['name']))
        assert abs(old['profit_5_to_6']-actual['profit_5_to_6'])<1e-8
        old.update(actual)
b.save('full_result.json',result)
b.save('example_result.json',t5v2.apply_request(reg,request))
report=OUT/'report.md';text=report.read_text(encoding='utf-8')
section=['## 各候选的有效投资轨迹','','千美元；正式6沿用权重为假设。下列有效投资实际进入曲线，名义支出仍按决策表计成本。','',
    '| 方案 | 正式5研发：梁／连接件 | 正式5运营 | 正式6研发：梁／连接件 | 正式6运营 |','| --- | ---: | ---: | ---: | ---: |']
for p in result['comparisons']:
    a,c=p['evaluations'][0]['periods']
    vals=lambda q:'／'.join(f'{x:,.2f}' for x in q)
    section.append(f'| {p["name"]} | {vals(a["effective_rd_kusd"])} | {a["effective_operations_kusd"]:,.2f} | {vals(c["effective_rd_kusd"])} | {c["effective_operations_kusd"]:,.2f} |')
text=text.replace('## 全部42字段（按网页子页顺序）','\n'.join(section)+'\n\n## 全部42字段（按网页子页顺序）')
report.write_text(text,encoding='utf-8')
with (OUT/'work_log.md').open('a',encoding='utf-8') as f:
    f.write('\n\n封装更正：索引匹配首次因中英文冒号差异停止，后续补齐；清单生成前的链接验收顺序已修复，未重新搜索或改动候选。新增逐期有效投资轨迹并核对利润不变，补充注册表继承字段的t5v2解释。\n')
shutil.copy2(Path(__file__),OUT/'code_snapshot/finalize_t5v2.py')
manifest=b.read(OUT/'version_manifest.json')
manifest['outputs']={p.relative_to(OUT).as_posix():b.sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='version_manifest.json'}
manifest['runtime']={'code/model_v2/t5v2.py':b.sha(runtime)}
b.save('version_manifest.json',manifest)
print('PASS: effective coordinates traced; optimized decisions and profits unchanged')
