"""Finish the interrupted, unpublished t5v1 package and audit the frozen baseline."""
import json
import re
import shutil
import sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import package_t5v1 as p

ROOT=p.ROOT;OUT=p.OUT
read=p.read;save=p.save;sha=p.sha
m=p.update.MarketingModel()
result=read(OUT/'full_result.json')
registry=read(OUT/'models_full.json')
request=read(OUT/'example_request.json')
assert (ROOT/'code/model_v2/t5v1.py').read_text(encoding='utf-8')==p.runtime_source()
for path in [ROOT/'code/model_v2/t5v1.py',ROOT/'work/package_t5v1.py',Path(__file__)]:
    shutil.copy2(path,OUT/'code_snapshot'/path.name)
# Replay the package's remaining validation steps without re-copying or re-training.
tail=(ROOT/'work/package_t5v1.py').read_text(encoding='utf-8').split("    sys.path.insert(0,str(ROOT/'code/model_v2'));import t5v1",1)[1].split("\n\nif __name__",1)[0]
import textwrap
exec(compile("sys.path.insert(0,str(ROOT/'code/model_v2'));import t5v1\n"+textwrap.dedent(tail),'t5v1_package_validation','exec'),dict(vars(p),m=m,result=result,registry=registry,request=request))

# Reuse the existing field mapping and page order, with updated marketing identification status.
source=(ROOT/'work/report_formal5_full.py').read_text(encoding='utf-8')
body=source.split('    records=[]',1)[1].split('    lines=[',1)[0]
scope=dict(s=p.update.base,m=m,result=result,plans=result['comparisons'],OUT=OUT,ROOT=ROOT,csv=__import__('csv'),fmt=lambda v:f'{v:,.4f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v))
exec(compile('records=[]\n'+textwrap.dedent(body),'t5v1_fields','exec'),scope)
records=scope['records'];sections=scope['sections'];allrows=scope['allrows'];fmt=scope['fmt']
for r in records:
    if r['row'] in [18,19,21,22,25,26,29,30]:
        r.update(status='合计联合求解；细分未识别',reason='正式4公司合计费用代理训练，替换正式5重要性；两类营销合计参与搜索，产品/国别按当前构成分摊，仅为可填展示方案，未识别细分最优')
    elif r['row'] in p.update.base.ROWS:
        r['reason']=r['reason'].replace('20个独立可控量共同搜索','14个可识别数值自由度共同搜索（20项决策表示）')
save(OUT/'decisions.json',records)
import csv
with (OUT/'decisions.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
plans=result['comparisons'];cfgs=result['configs'];robust=plans[2];neutral=plans[1]
rows_by_plan=[{r['row']:r for r in records if r['plan']==q['name']} for q in plans[1:]]
lines=['# t5v1：正式5全项条件决策与敏感性分析','',
    '建议采用下表稳健候选作为预算复核的起点。价格和营销均参与前向响应；机器投资当回合立即生效；研发和运营支出全额映射正式5曲线横轴。原版t5v0b保持不变，64项原清单哈希全部匹配，未执行还原。',
    '',
    '最新本人42项输入于2026-10-15 17:04（北京时间）只读复核，与前次归档逐项相同；正式5市场5、PYT，截止当日22:00。两国销售图使用本次已读正式5数据，其他公布条件与三曲线复用最近核验档案。未填写、保存或提交平台决策。',
    '',
    '**范围与限制：覆盖42个字段，20项数值决策表示折合14个可识别自由度，另推导2个物流排序。8项营销分配只有2个合计可识别，同合计重新分配在主模型内等价，细分最优未求解。4项无新招标输入不适用、分包机制不可用；13项预估随方案重算或按外生情景列出。下列是条件候选，不是全参数全局最优。**',
    '', '## 全部字段建议（按决策子页及类别顺序）','',
    '金额为千美元、数量为千单位，售价为美元/单位，比例按表中单位。中性候选最大化中性正式5—6税后利润；稳健候选最大化三核心情景最低利润，两者均要求这些情景采样现金至少3000（官方2000＋分析缓冲1000）。']
for title,rr in sections:
    lines+=['',f'### {title}','','| 项目 | 单位 | 当前 | 中性候选 | 稳健候选（建议） | 状态及依据 |','| --- | --- | ---: | ---: | ---: | --- |']
    for row in rr:
        a,b=[d[row] for d in rows_by_plan]
        label='／'.join(str(v) for v in [b['section'],b['product'],b['label']] if v)
        lines.append(f'| {label} | {b["unit"]} | {fmt(b["current"])} | {fmt(a["suggested"])} | {fmt(b["suggested"])} | {b["status"]}：{b["reason"]} |')
lines+=['','[逐字段CSV](decisions.csv) · [逐字段JSON](decisions.json)。营销展示分摊按当前构成及最大余数取整，不得将展示比例当成国别因果最优。',
    '', '## 同基准、同期限方案比较','',
    '以下利润和现金均为千美元，期限正式5—6；正式4以前收益为共同常数。不加入正式7收益、终局资产出售或债务清偿收益。情景不是概率分布。',
    '', '| 方案 | 中性利润 | 相对当前增量 | COUNTRY利润 | 联合不利利润 | 不利采样最低现金 | 正式5贷款变化 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for q in plans:
    e=q['evaluations']
    lines.append(f'| {q["name"]} | {e[0]["profit_5_to_6"]:,.2f} | {e[0]["profit_5_to_6"]-plans[0]["evaluations"][0]["profit_5_to_6"]:,.2f} | {e[1]["profit_5_to_6"]:,.2f} | {e[2]["profit_5_to_6"]:,.2f} | {e[2]["sampled_minimum_cash"]:,.2f} | {100*q["x"][19]:,.0f} |')
lines+=['',f'稳健候选相对中性候选牺牲中性利润{neutral["evaluations"][0]["profit_5_to_6"]-robust["evaluations"][0]["profit_5_to_6"]:,.2f}，减少联合不利损失{robust["evaluations"][2]["profit_5_to_6"]-neutral["evaluations"][2]["profit_5_to_6"]:,.2f}；仍存在亏损风险。连接件机器400千单位达到分析上界，价值同时来自本期更低班次工资及正式6容量；研发2600与一般营销合计2700也达到支持范围边界。不得未经新增证据向外推。',
    '', '| 方案（中性） | 正式5利润 | 正式6利润 | 梁产量5 | 连接件产量5 | 连接件期末库存5 | 连接件未满足需求5 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for q in plans:
    a,b=q['evaluations'][0]['periods']
    lines.append(f'| {q["name"]} | {a["profit"]:,.2f} | {b["profit"]:,.2f} | {a["production"][0]:.4f} | {a["production"][1]:.4f} | {a["closing_inventory"][1]:.4f} | {sum(a["demand"][1])-sum(a["sales"][1]):.4f} |')
lines+=['','## 正式4训练及正式5需求重要性替换','',
    '使用正式4初值（正式3实际）至正式4终值实际变化；376条继承候选配对，剔除研发曲线支持域外112条，264条可训练：复合梁144条（72队×两国）、连接件120条（60队×两国），不是264支队伍。没有用玩家需求预估作真实标签。',
    '',
    '保持已知正式3价格和研发响应作为偏置项，仅重估一般营销和设计师营销系数，非负岭回归并按市场留出诊断。竞争者真实产品/国别营销缺失，解释变量为公司合计实际营销费用代理。主模型因此只识别两类总额，推断细分响应另列压力，不虚构已知的竞争决策。',
    '',
    '图中横轴为相对重要性（价格3最高），纵轴为相对竞争位置，可为负。按分析映射`β5=β4/重要性4×重要性5`只替换一次，负纵轴没有作为需求乘数。此映射是明确推断，尚未核实为平台公式；价格和研发亦按对应因子的横轴重要性比例调整。',
    '',
    '复合梁泰国重要性：一般营销0.22045993→0.20424331（倍率0.92644187），设计师0.33289345→0.31733280（0.95325636），研发0.56186181→0.84970972（1.51231085）；其余本次读取因子4→5相同，价格均为3。需求份额重新归一化后乘正式5行业总量，行业增长不会重复相乘。',
    '', '| 产品/模型 | 训练行 | 一般营销β4 | 设计师β4 | 旧系数留出RMSE | 新训练留出RMSE |','| --- | ---: | ---: | ---: | ---: | ---: |']
models=read(OUT/'marketing_models_formal4.json')
for product,items in models.items():
    for name,v in items.items():
        lines.append(f'| {product}／{name} | {v["n"]} | {v["beta_general"]:.8f} | {v["beta_designer"]:.8f} | {v["old_nested_market_mean_rmse"]:.6f} | {v["nested_market_mean_rmse"]:.6f} |')
lines+=['', 'SHARE复合梁嵌套留出条件对数需求变化RMSE为0.094164→0.101299（变差）；连接件0.341629→0.334263（略改善）。不能声称整体精度提高，也不等同独立事前数量预测误差。完整逐国诊断、λ及来源见[训练模型](marketing_models_formal4.json)、[训练验收](training_validation.json)、[配对](training_pairs.json)、[排除](training_exclusions.json)、[重要性4→5](sales_importance_4_5.json)、[实际应用系数](applied_marketing_coefficients.json)。',
    '',
    '本次修正独立工作求解器的COUNTRY价格列索引：每个国家读取自身价格系数，印尼不再误读泰国价格列。本版重新搜索和敏感性结果取代此前候选；历史结果及t5v0b文件完整保留。',
    '', '## 42字段逐项敏感性','',
    '以稳健候选为中心，一次改变一个字段。表中为中性正式5—6利润变化（千美元），其他策略固定；价格±10%，投入±10%且至少50，配比±5个百分点，投资/贷款按可选档位，边界处截断。预估字段属于误差冲击，改填预估不等于改变真实需求。营销逐项扰动改变公司合计；不能据此比较同合计下国别投放优劣。',
    '', '| 字段 | 减少/另一选项→利润变化 | 增加/另一选项→利润变化 | 类别 |','| --- | --- | --- | --- |']
sens=read(OUT/'sensitivity_all_fields.json')
for row in allrows:
    field=next(f for f in m.fields if f['row']==row)
    tests=[z for z in sens if z['plan']==robust['name'] and z['row']==row]
    cells=['N/A' if z['delta_profit_5_to_6'] is None else f'{fmt(z["test"])} → {z["delta_profit_5_to_6"]:+,.2f}'+('（现金约束失效）' if not z.get('feasible',True) else '') for z in tests]
    cells+=['—']*(2-len(cells))
    label='／'.join(str(v) for v in [field['section'],field['product_or_location'],field['label']] if v)
    lines.append(f'| {label} | {cells[0]} | {cells[1]} | {tests[0]["category"]} |')
lines+=['','两候选完整敏感性：[CSV](sensitivity_all_fields.csv)、[JSON](sensitivity_all_fields.json)。投资、融资全档固定其余控制量扫描：[稳健](robust_discrete_frontier.json)、[中性](neutral_discrete_frontier.json)，不是每档重新联合优化。',
    '', '## 全局假设压力','', '| 情景 | 当前利润 | 中性候选 | 稳健候选 | 稳健采样最低现金 |','| --- | ---: | ---: | ---: | ---: |']
for i,c in enumerate(cfgs):
    e=[q['evaluations'][i] for q in plans]
    lines.append(f'| {c["name"]} | {e[0]["profit_5_to_6"]:,.2f} | {e[1]["profit_5_to_6"]:,.2f} | {e[2]["profit_5_to_6"]:,.2f} | {e[2]["sampled_minimum_cash"]:,.2f} |')
lines+=['','## 生产与财务假设','',
    '- 正式5三曲线各200点，600点原件精确一致；研发0—2600、运营0—1620范围内使用，支出直接作横轴，不重复加入历史存量。效率按正式4实际产量/人员锚定，乘运营曲线相对750的比值。',
    '- 当前容量41.67/412.25，新增机器立即增加容量；正式6乘0.85。班次工资1/1.65/2.56，基本工资43.5，人员合计自然离职10%、额外解聘35%成本，分产品解聘另压力。库存0/202.40，库存账面0/3516；连接件自由生产，销量受需求与供给双约束。',
    '- 物流按售价减运输费排序，复合梁两国运费30/120、连接件0.5/2，均用本次最新条件。零招标交付；分包无已核可用输入。材料主情景继承比例迁移，公布价/固定加价另压力；库存主情景按当期生产成本，加权平均另压力。',
    '- 期初现金12202，应收3361，应付1867，机器7367，厂房12724，长贷10200，权益27102；资产显示舍入差−1保留。应收/应付30天，厂房资本支出800、折旧7%，机器折旧15%，现金利息平均余额1%，税29%且不补造税亏。',
    '- 长贷基准5%加继承风险模型，按财务状态推断；主情景平均长债计息，旧债/期末债另压力。偿还本金只影响现金与负债。现金只检查年末及回合初投资融资后，不保证任意时点现金，也不虚构自动短贷。',
    '- 正式6同价格、同名义营销/研发/运营，无新机器/贷款；市场中性持平，延用正式5曲线为显式情景。生产可观察需求后调整，继续固定配比另压力。仅优化正式5当期控制，不声称完整正式6策略最优。',
    '- 价格采用正式4实际正价支持范围；一般营销合计≤2700、设计师≤3840是分析范围，不是官方上限。机器梁0—20、连接件0—400（步长20），贷款−10200至10000（步长100），生产配比0—100%。',
    '- 两目标各种子11/29，折叠6个不可识别营销分配方向后联合搜索、显示精度取整、逐坐标检查及离散扫描；收敛不证明全局最优。原草稿预算回放只作财务一致性检验，不作候选平台预算或真实预测验收。',
    '', '## 版本、复现与验收','',
    '[独立运行说明](../../../code/model_v2/t5v1_README.md) · [完整结果](full_result.json) · [冻结注册表](models_full.json) · [运行示例](example_result.json) · [验证](validation.json) · [原版保护核验](t5v0b_preservation_audit.json) · [版本哈希](version_manifest.json)。',
    '',
    '独立t5v1入口仅加载冻结参数，不训练、不写平台。三方案×15情景回放、数量与财务恒等式、两模型各国价格方向、非法请求拒绝均通过；原版清单64项复核通过，恢复文件数0。竞争者响应及跨期预测未独立验证，营销细分配置仍未识别。']
(OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
save(OUT/'field_coverage.json',dict(fields=42,records=84,decision_vector=20,identified_numeric_degrees=14,marketing_totals=2,marketing_allocation_rows=8,allocation_identified=False,sensitivity_fields_per_candidate=42))

# Back up current shared indexes, preserving pre-existing local changes.
backup=OUT/'documents_before';backup.mkdir(exist_ok=True)
docs={}
for rel in ['README.md','code/model_v2/README.md']:
    path=ROOT/rel;old=path.read_text(encoding='utf-8');target=backup/rel;target.parent.mkdir(parents=True,exist_ok=True)
    assert not target.exists();shutil.copy2(path,target);docs[rel]={'before':sha(path),'backup':str(target.relative_to(ROOT))}
    if rel=='README.md':
        old=old.replace('决策基准读取于2026-10-15 16:13','决策基准读取于2026-10-15 17:04')
        marker='| 最新独立应用情景 | **t5v0b**'
        row='| 最新条件优化版本 | **t5v1**：[完整建议与42项敏感性]('+str(OUT.relative_to(ROOT)).replace('\\','/')+'/report.md)、[运行说明](code/model_v2/t5v1_README.md) | 正式4营销合计费用代理重估，替换正式5重要性；价格/营销联合响应，细分营销未识别。t5v0b原版64项哈希不变，未提交平台。 |\n'
        old=old.replace(marker,row+'| 冻结应用基线 | **t5v0b**')
        start=old.index('正式5最新决策分析：');end=old.index('\n',start)
        old=old[:start]+'正式5最新决策分析：[t5v1全字段建议、正式4营销训练及正式5重要性替换]('+OUT.relative_to(ROOT).as_posix()+'/report.md)。价格营销保留前向响应，机器本期生效，研发运营直接映射横轴；营销细分配置未识别，全部利润为正式5—6条件情景。此前候选已被本版重新计算结果取代，历史文件及t5v0b原版保持不变。'+old[end:]
    else:old=old.replace('## 当前工作入口\n','## 当前工作入口\n\n- [t5v1条件优化](t5v1_README.md)：正式4营销代理训练与正式5重要性，完整字段及敏感性；t5v0b只读保留。\n')
    path.write_text(old,encoding='utf-8');docs[rel]['after']=sha(path)
readme=ROOT/'code/model_v2/t5v1_README.md'
assert not readme.exists()
readme.write_text('# t5v1独立冻结应用\n\n正式4初终值营销费用代理训练＋正式5已知重要性；其余组件继承t5v0b，原版不变。\n\n[完整建议与敏感性](../../'+OUT.relative_to(ROOT).as_posix()+'/report.md) · [注册表](../../'+OUT.relative_to(ROOT).as_posix()+'/models_full.json) · [验证](../../'+OUT.relative_to(ROOT).as_posix()+'/validation.json)。\n\n运行：\n\n```powershell\npython code/model_v2/t5v1.py --bundle '+OUT.relative_to(ROOT).as_posix()+'\n```\n\n依赖项目NumPy（与原运行环境一致），可用`--request`传入示例同结构JSON。入口不训练、不改平台；三方案15情景已回放。营销细分真实响应未知，只识别两类合计；正式5—6利润是条件情景，非全参数最优或独立前向预测。\n',encoding='utf-8')
save(OUT/'document_changes.json',docs)
(OUT/'work_log.md').write_text('# t5v1版本工作记录\n\n2026-10-15：按用户要求另存t5v1，t5v0b全程只读。原任务日志见training_work_log.md。独立入口封装时补入曲线纯函数，重新执行全部冻结回放验证；没有修改旧版源代码。共享索引按当前磁盘备份并记录改前/改后哈希。42字段与两候选敏感性分别交付，营销细分未识别。\n',encoding='utf-8')
links=[]
for path in [OUT/'report.md',readme,ROOT/'README.md',ROOT/'code/model_v2/README.md']:
    for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        if target=='version_manifest.json':continue
        dest=(path.parent/target.split('#')[0]).resolve()
        assert dest.exists(),(path,target)
        links.append(dict(source=str(path.relative_to(ROOT)),target=target))
save(OUT/'link_validation.json',dict(status='PASS',checked=len(links),links=links))
audit=read(OUT/'t5v0b_preservation_audit.json')
for item in audit['checks']:assert sha(ROOT/item['path'])==item['sha256']
validation=read(OUT/'validation.json');validation.update(report_fields=42,decision_records=84,links_checked=len(links),t5v0b_final_hashes_match=True)
save(OUT/'validation.json',validation)
save(OUT/'version_manifest.json',dict(version='t5v1',base_version='t5v0b',outputs={str(f.relative_to(OUT)):sha(f) for f in OUT.rglob('*') if f.is_file() and f.name!='version_manifest.json'},source_code={'code/model_v2/t5v1.py':sha(ROOT/'code/model_v2/t5v1.py')},documents={k:sha(ROOT/k) for k in [*docs,'code/model_v2/t5v1_README.md']},t5v0b_preserved=audit['checked']))
print('FINAL',OUT,'BASELINE',audit['checked'],'LINKS',len(links))
