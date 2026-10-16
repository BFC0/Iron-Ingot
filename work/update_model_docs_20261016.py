"""Update version documentation from saved evidence; preserve disk baselines."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import shutil
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output' / 'model_documentation' / stamp
OUT.mkdir(parents=True, exist_ok=False)
(OUT / 'work_log.md').write_text('# 模型说明补齐与项目文档更新\n\n状态：进行中。用户要求更新项目文档，并参照旧模型补齐新增模型说明。仅修改Markdown，保留磁盘未提交内容和历史结果。\n', encoding='utf-8')

# version, title, bundle, method, limits
versions = [
 ('t5v0a', '正式5非重训应用', 't5v0a/20261015T131507850861+0800',
  '冻结t5v0正式4训练系数，接入正式5的42项公布参数与独立三曲线。材料保留公布价、固定加价、比例修正三种情景；支持工资、班次、解聘、利率分解、显式曲线坐标及订单前库存数量计算。训练曲线与application_curves分开保存。',
  '有效投入映射、完整需求、订单现金与投资时序仍缺，缺输入跳过；正式5—6完整收益不排名。'),
 ('t5v0b', '国别需求与机器稳定价', 't5v0b/20261015T153107587428+0800',
  '继承t5v0a且不重训。两产品按用户假设以正式4国别实际总量×(1＋增长率)生成正式5总量，泰国+7%、印尼−5%。机器采购按正式5公布78/1.10美元每单位计算，投资输入为千单位；只有显式选择本组份额保持假设才计算对应公司需求。29类逐项记录影响。',
  '采购金额不等于付款现金或生效产能；不把国别总量变化重复乘到ABS数量。不是全参数优化或完整利润排名。'),
 ('t5v1', '营销代理训练与条件优化', 't5v1/20261015T171355804',
  '以t5v0b为基线，用正式4公司合计一般营销、设计师营销实际费用代理重估营销响应，接入正式5已知重要性；其余组件继承。价格与营销联合响应，重新求解三套候选，保存15情景回放及42项字段敏感性。',
  '只识别营销合计，产品/国别细分响应未知。正式5—6收益为条件情景，不能称整套模型重新训练或全参数最优。'),
 ('t5v2', '有效投资映射与条件优化', 't5v2/20261015_effective_investment',
  '继承t5v1，采用正式5网页区间试验的投入映射：研发有效投入=0.75×当期＋0.50×上期，运营有效投入=当期＋0.35×上期，金额为千美元。映射接入需求、效率、生产和财务链，重新求解三候选并重算42字段敏感性。',
  '该映射仅由正式5试验支持；历史截距、更早存量和正式6迁移仍是假设。营销细分、投标、分包未完全求解。'),
 ('t5v3', '统一对手默认价格情景', 't5v3/20261015_common_default_prices',
  '冻结t5v2系数，历史假设其他九队统一采用本组正式5期初默认价：复合梁泰国1860/印尼2180、连接件36/32美元每单位。以各队正式4价格及需求份额为锚点重估吸引力，在十队内归一化；本组需求=市场总量×本组份额。输出正式5需求与份额，不重新优化。',
  '这是历史统一同价情景；后续竞争输入已另存为各队沿用各自上回合实际价格，不能把两者混用。正式6默认拒绝外推，旧t5v2建议和利润不属于t5v3结果。'),
 ('t6v0', '正式5实际训练与筛选', 't6v0/20261015T235330003362+0800',
  '正式5的10市场100队实际结果与三曲线600点训练，正式4期末仅作结转参照。价格、需求为真实值，营销与研发为公司合计实际费用代理。SHARE为softmax份额，COUNTRY国别独立；价格对数线性、正则0.001、rho固定0.5，研发代理为当期公司合计＋0.5×上期合计。训练折内3IQR筛极端输入，低残差须同时具备供给证据才标疑似供给偏离；测试市场全量评分。ABS独立选择正则并作整市场留出。',
  '费用代理不是细分真实决策，供给归因与跨市场共享曲线是假设。效率rho仍不可识别，材料/工资/风险使用实际状态条件回溯；29类状态不等于29个独立模型全部通过。未部署，未证明正式6前向精度。'),
 ('t6v1', '正式6终局条件应用', 't6v1/20261016T001633520',
  '冻结t6v0国别需求、材料、风险及效率锚点，另拟合正式6三条投入曲线。菲律宾迁移印尼，十队以1600/23美元共同锚定，总量5/105千单位。28维决策含六价格、十二营销、两研发、一运营、四机器档、两产能分配、一贷款档，物流枚举。泰国机器当期生效，印尼本期产量0，印尼投资现金与0%/15%折旧分情景；仅评价正式6新增收益。',
  '56字段中39项经营字段包括28项搜索、6项物流枚举及4投标/1分包未求解；17项预估/派生重算或终局停用。15项独立期初状态缺口、公司费用细分和全期现金时序仍缺，无第7回合收益。'),
 ('t6v1n', '自上而下总量与竞争份额', 't6v1n/20261016T130746833',
  '继承t6v1，把需求明确拆为Q=T×s：T为产品/国家市场总量（千单位），s为十队归一化竞争份额（0—1），Q为本公司需求（千单位）。泰国/印尼T取正式5市场5实际总量×1.04/1.05，菲律宾取前景5/105千单位；菲律宾仍迁移印尼。份额随方案价格、营销合计、研发重算，供给约束后进入生产物流财务。',
  '总量为外生预估，不包含本公司价格引起的市场扩张。初版仅27次回归，随后前景优化另存两候选及56字段；拆分接口本身不代表精度提高。细分营销、投标、分包及期初财务仍缺。'),
 ('t6v1n1', '菲律宾泰国迁移与份额优化', 't6v1n1/20261016T174823123',
  '继承t6v1n的Q=T×s框架，菲律宾改迁移冻结t6v0泰国国别beta及对手非价格代理，按team_id对齐，并以菲律宾指导价重新归一化十队份额，不直接继承泰国份额。总量5/105千单位、运费170/2.2美元每单位。五候选为中性、稳健及菲律宾两产品10%/20%/30%中性交付份额目标，统一13情景比较；份额约束使用实际可交付销量/市场总量。',
  '泰国相似性由用户指定，未新增菲律宾实际标签，不代表精度提高。份额目标不保证压力下达标；公司费用细分、投标、分包和独立期初财务仍未求解。'),
 ('t6v1n2', '研发口径修复与定价压力', 't6v1n2/20261016_final',
  '继承t6v1n1，研发需求特征统一为当期公司研发合计＋0.5×上期公司合计，以冻结正式5训练曲线为代理尺度，撤去单产品0.75/0.50映射对公司合计特征的替换。价格系数不重训。增加旧市场价格敏感度+20%/+50%、营销/研发新增收益失效及联合压力；五候选统一18情景90次回放，稳健核心为包内九情景。',
  '失效比例只取消相对历史特征的正增量，负增量保留，不是零投入保留旧需求的保证。细分营销/研发仍不可识别；投标、分包及15项独立期初核验缺口保留，压力下仍可能亏损。'),
]
changes = {}
for version, title, bundle, method, limits in versions:
    path = f'模型说明/{version.upper()}_{title}.md'
    evidence = 'report.md'
    if version == 't6v1n':
        evidence = 'report.md'
    assert (ROOT / 'output' / bundle / evidence).exists(), bundle
    text = f'''# {version} {title}

更新：2026-10-16（北京时间）。当前项目状态见[项目总览](../README.md)；本页按冻结版本解释，不覆盖旧模型和历史成绩。

## 版本职责与计算方法

{method}

## 输入、输出与参数来源

[版本报告](../output/{bundle}/{evidence})、[运行说明](../code/model_v2/{version}_README.md)与[维护代码](../code/model_v2/{version}.py)保存输入结构、参数来源和复现入口。参数数值以对应包及报告为准，不跨版本拼接；金额、数量和份额按字段单位使用。

输出及假设随该版本保存，实际、玩家预估、预算、模型预测与压力情景分开；公司费用代理不冒充产品/国别真实投入。

## 运行与核验

在项目根目录使用匹配项目NumPy/SciPy的Python，按[运行说明](../code/model_v2/{version}_README.md)执行。已保存验收属于实现、回算或条件情景检查，不能当独立跨回合预测精度。复现需要项目归档，不能只移动说明页或应用包。新增运行采用新目录并保留日志、源哈希和旧结果。

## 应用限制

{limits} 未填写或提交平台，不宣称全参数最优。
'''
    if version == 't6v0':
        text += '''
## 保存的留出误差

| 模型 | 复合梁 | 连接件 | 单位及边界 |
| --- | ---: | ---: | --- |
| SHARE全量测试市场MAE | 0.831231 | 1.745256 | 份额百分点；训练保留193/200、170/180条，测试不筛除 |
| ABS外层留出MAE | 1.072472 | 33.383889 | 千单位；不使用实际行业总量换算预测数量 |

[独立复核](../output/t6v0/20261015T235330003362+0800/verification.json)与[筛选记录](../output/t6v0/20261015T235330003362+0800/demand_screening.json)保留来源、参数及每折评分；SHARE和COUNTRY是替代规格，样本不可相加。
'''
    if version == 't6v1n':
        text += '\n[后续前景优化](../output/t6v1n_optimization/20261016T173718998/report.md)重新求解中性和稳健两候选，56项按页面顺序输出；与初版接口回归分别归档。\n'
    if version == 't6v1n2':
        text += '''
## 菲律宾30/310千单位假设分支

[独立重算报告](../output/t6v1n2/20261016_ph30_310/report.md)将菲律宾市场总量改为复合梁30、连接件310千单位，缩量压力为21/217，五候选重新求解并作18情景90次回放。它来自用户历史提示，未独立核实，原前景5/105千单位及旧方案保留；两套总量不是同一基准，不能直接比较原分数。

该分支稳健候选中性利润223.80千美元、18情景最低利润−4741.73千美元；仅供进一步审核，不是安全盈利保证。基准5/105分支稳健印尼梁价2332.5美元不能标为30/310分支推荐价。
'''
    changes[path] = text

names = {v: f'{v.upper()}_{title}.md' for v, title, *_ in versions}
summaries = {v: method.split('。')[0] for v, _, _, method, _ in versions}
def load(path):
    return changes.get(path, (ROOT / path).read_text(encoding='utf-8-sig'))
def replace(path, old, new):
    content = load(path)
    assert old in content, (path, old[:70])
    changes[path] = content.replace(old, new, 1)

index = '模型说明/README.md'
content = load(index)
start, end = content.index('## 当前模型和应用入口'), content.index('## 按业务主题查阅')
rows = '\n'.join(f'| {v} | [{title}]({names[v]}) | {summaries[v]}；详见版本边界。 |' for v, title, *_ in reversed(versions))
changes[index] = content[:start] + '''## 当前模型和应用入口

正式6最新应用为t6v1n2，最新实际训练为t6v0；t5系列按正式5历史用途查阅。训练、冻结应用、用户假设及独立诊断分开，版本说明不计作新增训练。

| 版本 | 独立说明 | 职责与边界 |
| --- | --- | --- |
''' + rows + '''

菲律宾30/310千单位是t6v1n2用户假设分支，原前景5/105千单位保留，见该版本说明。正式6已有条件适配，细分投入、投标、分包、期初状态及前向精度仍缺；旧42项建议不能直接作为当前56项方案。

[t5v0正式4训练与缺口](T5V0_正式4训练与缺口.md)保留29类状态及正式5独立曲线；[t4v1完整训练](T4V1_正式3完整数据训练.md)与[t4v1a应用](T4V1A_正式4非重训应用情景.md)分别保存。历史公式及误差仅属于对应版本。

''' + content[end:]
replace(index, '更新：2026-10-15', '更新：2026-10-16')

new_rows = '\n'.join(f'| {v} | [独立说明](模型说明/{names[v]}) | {summaries[v]}；冻结参数、假设与缺口详见说明。 |' for v, *_ in reversed(versions) if v.startswith('t6')) + '\n'
for path in ['模型版本重新统计.md', '预测模型与训练参数汇总.md', '训练拟合模型与版本清单.md', '训练拟合模型与版本清单_文字说明版.md']:
    content = load(path)
    match = re.search(r'\|[^\n]*\n\|[ :|\-]+\|\n', content)
    assert match, path
    changes[path] = content[:match.end()] + new_rows + content[match.end():]
    if '更新：2026-10-15' in changes[path]:
        replace(path, '更新：2026-10-15', '更新：2026-10-16')

replace('README.md', '更新：2026-10-15', '更新：2026-10-16')
replace('README.md', '## 模型训练与应用版本\n', '## 模型训练与应用版本\n\n[模型说明分类索引](模型说明/README.md)已补齐t5v0a—t5v3、t6v0—t6v1n2十个独立版本说明，包含继承关系、计算方法、来源、复现与限制；后续新增版本沿用同一结构。\n')
replace('code/model_v2/README.md', '更新：2026-10-15', '更新：2026-10-16')
replace('code/model_v2/README.md', '## 当前工作入口\n', '## 当前工作入口\n\n业务解释、公式和版本边界见[模型说明索引](../../模型说明/README.md)，本目录README维护运行接口。\n')
replace('预测模型与变量说明.md', '更新：2026-10-15', '更新：2026-10-16')
replace('预测模型与变量说明.md', '## 当前模型与公式适用范围\n', '''## 当前模型与公式适用范围

最新实际训练为[t6v0](模型说明/T6V0_正式5实际训练与筛选.md)：正式5实际价格/需求与公司费用代理，整市场留出；同期条件误差不等于正式6前向精度。正式6应用由t6v1→t6v1n→t6v1n1→[t6v1n2](模型说明/T6V1N2_研发口径修复与定价压力.md)独立保存，需求按市场总量×竞争份额计算，菲律宾现迁移泰国。t6v1n2研发统一公司合计＋0.5×上期合计代理，不沿用t5v2的单产品0.75/0.50映射替换公司特征；菲律宾5/105前景与30/310千单位用户假设分支分开。仅评价第6回合，56字段中的未求解项保留，不能称全参数最优。

以下t5及更早版本属于历史公式与应用边界，不代表当前训练暂停或正式6尚未条件适配。
''')
replace('预测模型与变量说明.md', '尚未同步本次t5v1—t5v3及正式6适用边界更新', '尚未同步t5v1—t6v1n2版本及本次适用边界更新')
replace('项目结构.md', '更新：2026-10-15', '更新：2026-10-16')
replace('项目结构.md', '| 正式5结算与正式6初值 |', '| 正式6模型与独立说明 | [模型说明索引](模型说明/README.md)、[t6v0训练](模型说明/T6V0_正式5实际训练与筛选.md)、[t6v1n2应用及总量分支](模型说明/T6V1N2_研发口径修复与定价压力.md)；条件适配完成，未验证前向精度及全参数最优 |\n| 正式5结算与正式6初值 |')
replace('项目结构.md', '| `project_structure/` |', '| `t6v0/`、`t6v1/`、`t6v1n/`、`t6v1n1/`、`t6v1n2/`、`t6v1n_optimization/`、`formal6_curves/` | 正式5训练、正式6条件应用、各假设分支、优化及曲线，按版本分别保存 |\n| `model_documentation/` | 说明维护的磁盘改前备份、改前/改后SHA256、链接与版本覆盖核验 |\n| `project_structure/` |')
replace('code/README.md', '更新：2026-10-15', '更新：2026-10-16')
replace('code/README.md', '| 正式5统一对手价格情景 |', '| 正式5实际训练及正式6应用 | [t6v0](model_v2/t6v0_README.md)、[t6v1](model_v2/t6v1_README.md)、[t6v1n](model_v2/t6v1n_README.md)、[t6v1n1](model_v2/t6v1n1_README.md)、[t6v1n2](model_v2/t6v1n2_README.md) | 独立训练与条件应用；业务解释见[模型说明](../模型说明/README.md)，部分优化、未部署 |\n| 正式6独立曲线 | [fit_formal6_curves.py](model_v2/fit_formal6_curves.py) | 600点图形近似，非经营精度 |\n| 正式5统一对手价格情景 |')
flow = '模型说明/完整计算流程图.md'
replace(flow, '更新：2026-10-15', '更新：2026-10-16')
replace(flow, '  R6[正式6已归档56字段 48参数 600点曲线] --> GAP6[菲律宾需求 印尼投资 15项独立期初状态待核]\n  GAP6 --> END6[仅评价正式6新增收益 按终局处理 不创建正式7预测]', '''  R5ACT --> T6[t6v0 实际价格需求与公司费用代理重训]
  T6 --> APP6[t6v1 正式6终局条件应用]
  R6[正式6已归档56字段 48参数 600点曲线] --> APP6
  APP6 --> N6[t6v1n 市场总量乘竞争份额]
  N6 --> N61[t6v1n1 菲律宾迁移泰国及份额候选]
  N61 --> N62[t6v1n2 研发公司口径修复及18情景]
  N62 --> PH6[菲律宾5和105前景 或30和310用户假设 独立求解]
  PH6 --> GAP6[细分投入 投标 分包及15项独立期初核验仍缺]
  GAP6 --> END6[仅评价正式6新增收益 部分优化 不创建正式7预测]''')
replace(flow, 't5v1—t5v3接口与边界见', 't5v1—t6v1n2接口与边界见')

req = 'Cesim_任务要求与当前情况说明.md'
replace(req, '更新：2026-10-15', '更新：2026-10-16')
replace(req, '## 2. 建模、验证与候选比较', '''## 模型说明与文档维护

新增模型或独立应用版本时，在`模型说明/`参照旧版本建立独立Markdown说明，至少写明版本职责与继承关系、训练/应用回合、输入输出及单位、核心计算方法与参数来源、假设、运行与核验入口、误差类型和未解决限制。训练、冻结应用与用户假设分支分别标记，同版本不同情景不得冒充新增训练。

同步更新模型说明索引、README当前入口及相关版本/参数专题；运行参数和请求结构仍由`code/model_v2/`版本README维护，说明页链接到对应冻结报告和参数，避免手工复制完整注册表。当前状态集中在README，专题文件不叠加重复进度日志。改前备份当前磁盘内容并记录SHA256，改后保存SHA256及链接核验，保留已有未提交修改和历史结果。默认Markdown，不新增HTML报告副本。

## 2. 建模、验证与候选比较''')

before = {}
for path in changes:
    source = ROOT / path
    before[path] = hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None
    if source.exists():
        dest = OUT / 'before' / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
(OUT / 'before_manifest.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
for path, content in changes.items():
    prior = (OUT / 'before' / path).read_bytes() if before[path] else b''
    newline = '\r\n' if b'\r\n' in prior else '\n'
    encoding = 'utf-8-sig' if prior.startswith(b'\xef\xbb\xbf') else 'utf-8'
    (ROOT / path).write_bytes(content.replace('\n', newline).encode(encoding))

links = []
for path, content in changes.items():
    old = (OUT / 'before' / path).read_text(encoding='utf-8-sig') if before[path] else ''
    old_targets = set(re.findall(r'\]\(([^)]+)\)', old))
    for target in re.findall(r'\]\(([^)]+)\)', content):
        if target.startswith(('http:', 'https:', '#', 'codex:')):
            continue
        raw = re.sub(r':\d+$', '', unquote(target.split('#')[0].strip('<>')))
        resolved = Path(raw) if re.match(r'^[A-Za-z]:[/\\]', raw) else (ROOT / path).parent / raw
        links.append({'document': path, 'target': target, 'exists': resolved.exists(), 'new_target': target not in old_targets})
failures = [item for item in links if not item['exists'] and item['new_target']]
after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in changes}
coverage = {v: (ROOT / '模型说明' / names[v]).exists() and names[v] in changes[index] for v, *_ in versions}
result = {'modified_existing': sum(v is not None for v in before.values()), 'new_documents': sum(v is None for v in before.values()), 'version_coverage': coverage, 'links_checked': len(links), 'new_broken_links': failures, 'preexisting_broken_links': [i for i in links if not i['exists'] and not i['new_target']], 'before_sha256': before, 'after_sha256': after}
(OUT / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'link_checks.json').write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding='utf-8')
assert all(coverage.values()) and not failures, failures
assert all(hashlib.sha256((OUT / 'before' / p).read_bytes()).hexdigest() == h for p, h in before.items() if h)
(OUT / 'work_log.md').write_text(f'# 模型说明补齐与项目文档更新\n\n状态：完成。北京时间目录：{stamp}。\n\n新增10个独立说明，更新{result["modified_existing"]}份既有Markdown与后续新增版本维护规则。改前备份直接来自当前磁盘，未回退已有修改。版本覆盖10/10；核验{len(links)}条本地链接，新增失效链接0，历史失效项见verification.json。改前/改后SHA256与链接明细同目录保存。\n\n未重训、未重算方案、未更新历史Word/HTML、未操作平台；模型有效性仍以各版本独立证据及限制为准。\n', encoding='utf-8')
print(json.dumps({'output': str(OUT), 'documents': len(changes), 'coverage': coverage, 'links_checked': len(links), 'new_broken_links': failures, 'preexisting_broken_link_count': len(result['preexisting_broken_links'])}, ensure_ascii=False))
