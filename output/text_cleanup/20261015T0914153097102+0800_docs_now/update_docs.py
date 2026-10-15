"""Update documented state from saved evidence; preserve historical data and formulas."""
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TRAIN = 'output/t5v0/20261015T085218049188+0800'
CURVE = 'output/t5v0/20261015T090943259882+0800_formal5_curves'
DIAG = 'output/t5_material_diagnosis/20261015T091215236523+0800'

def read(p):
    return (ROOT / p).read_text(encoding='utf-8-sig')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def js(p):
    return json.loads(read(p))

def save_json(name, obj):
    with (OUT / name).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

assert js(TRAIN + '/verification.json')['status'] == 'PASS_WITH_EXPLICIT_TRAINING_GAPS'
assert js(CURVE + '/acceptance.json')['business_validation'] is False
source_checks = []
def check_hashes(mapping, base):
    for p, expected in mapping.items():
        path = base / p
        source_checks.append({'path': path.relative_to(ROOT).as_posix(), 'matches': path.is_file() and sha(path) == expected})

manifest = js(TRAIN + '/manifest_final.json')
check_hashes(manifest['input_hashes'], ROOT)
check_hashes(manifest['output_hashes'], ROOT / TRAIN)
check_hashes(js(CURVE + '/source_hashes.json'), ROOT)
diagnosis = js(DIAG + '/diagnosis.json')
check_hashes(diagnosis['input_hashes'], ROOT)
check_hashes(diagnosis['raw_source_hashes'], ROOT)
save_json('evidence_hash_checks.json', source_checks)
assert all(x['matches'] for x in source_checks), 'Saved evidence hash mismatch; stop before editing'

edits = {}
def replace(path, old, new):
    text = edits.get(path, read(path))
    assert text.count(old) == 1, (path, old[:70], text.count(old))
    edits[path] = text.replace(old, new, 1)

summary = '正式4已处理29类状态：材料两产品100/89条、风险92条及工资条件模型已重拟合；需求缺其他99队最终决策而暂停，效率ρ不可识别，未部署。'
curve_summary = '正式5三曲线600点独立保存，上期研发900/1300、运营750千美元；图形近似不代表经营预测精度，未覆盖正式4训练参数。'
diag_summary = '复合梁材料嵌套市场留出MAE为2.557838千美元，WAPE为0.014242%，100/100残差与显示舍入区间兼容；差额机制及跨基价迁移仍未验证。'

# Current state and priorities belong in README, with old scenarios labeled historical.
replace('README.md', '更新：2026-10-15（北京时间）。正式4已结算，10市场结果已通过归档验收；平台开放正式5，截止2026-10-15 22:00。', '更新：2026-10-15（北京时间），依据本次本地资料与哈希核验。正式4已结算，10市场结果已通过归档验收；最近归档显示开放正式5、截止2026-10-15 22:00，本次未实时访问平台。')
replace('README.md', '执行细节见[任务要求](Cesim_任务要求与当前情况说明.md)。生产策略/库存、自动短贷暂不作为完整优化范围，股权操作不涉及；已有连接件规则研究单独保留，不能据此扩展完整利润结论。', '执行细节见[任务要求](Cesim_任务要求与当前情况说明.md)。新候选须覆盖当回合全部可控参数并一致重算预估项，按决策子页顺序逐表输出；缺机制或数据的项目标为未求解，不能默认固定后宣称全参数最优。库存、订单、投资时点及自动短贷机制尚未完整验证，已有连接件规则研究不能据此扩展完整利润结论。')
replace('README.md', '| 正式4联合情景（最新） |', '| 正式4历史联合情景（未采用） |')
replace('README.md', '20变量联合搜索、4物流推导，5项投标/分包输入仍未求解；全部新增研发运营响应用正式4曲线。未来政策与财务映射属假设，未解除t4v1a完整利润排名门槛；未实时预算验证或提交', '20变量联合搜索、4物流推导，5项投标/分包输入仍未求解；新增研发运营响应用正式4曲线。实际最终方案未采用两套候选，模型事前评分0项；保留历史条件情景，不能作为正式5推荐或完整利润成绩')
replace('README.md', '| 连接件价格和历史投入 |', f'| 正式4材料误差诊断 | {diag_summary} | [独立诊断]({DIAG}/report.md)；未替换模型，不为压低显示误差增加复杂特征 |\n| 连接件价格和历史投入 |')
replace('README.md', '| 1 | 真实竞争投入口径 | 已恢复100队正式1/2合计营销/运营历史；99队正式3产品/国别营销、分产品研发仍缺。先补齐同竞争集合再比较真实投入与代理 |', '| 1 | 正式4竞争队最终决策 | 本组42项已分类为29项决策与13项玩家预估，4条产品/国家输入与实际需求配对；其他99队最终输入缺失，t5v0需求重训暂停。正式3旧投入代理缺口仍保留，不用结果费用替代真实决策 |')
replace('README.md', '| 1 | 曲线横轴、研发延期与运营存量 | 正式4曲线来源和上期投入已核；自动支出→有效横轴映射未证实。历史候选改善不等于完整存量识别，不能重复叠加历史影响 |', '| 1 | 曲线横轴、研发延期与运营存量 | 正式4训练曲线与正式5应用曲线分开保存，正式5上期实际投入900/1300/750已配对；自动支出→有效横轴映射未证实，t5v0效率ρ不可识别。先补最终投入历史及存量机制，避免重复叠加 |')
replace('README.md', '| 2 | 风险利率与计息状态 | t4v1a禁止杠杆幂函数应用，指数只作范围内显式状态敏感性；正式4已给基准5%，正式3叙述5%/参数4%的冲突及计息时点仍保留 |', '| 2 | 风险利率与计息状态 | t5v0以92条实际状态重拟合两种风险形式，属于条件回溯；正式5公布基准5%、短贷溢价3.50个百分点，计息状态与时点仍缺。t4v1a原应用限制及正式3利率冲突保留 |')
replace('README.md', '| 2 | 投资与产能生效时点 | 当前零投资容量投影不能泛化，旧下期生效/本期零增量假设与页面证据冲突；正式4仅更新机器价格，不排名投资收益 |', '| 2 | 投资与产能生效时点 | 正式5零本人投资情景下，两产品容量与15%衰减相容，仅为条件核验；正式5机器价格78/1.10美元每单位。投资生效、人员及新增产能尚不足以做收益排名 |')
replace('README.md', '| 2 | 订单、税亏及完整财务状态 | 有确认订单规则但缺真实中标/交付/预收余款，税亏及期初/期末/平均计息状态未齐；不能输出完整现金或利润 |', '| 2 | 订单、税亏及完整财务状态 | 正式4→5结转20项中5项已核或条件核验、15项未知；两产品库存数量可配对。真实合同/交付/收付款、期初现金和税亏仍缺，1900源财务等式通过不代表完整前向财务模型通过 |')
replace('README.md', '| 3 | 正式4至6完整经营收益链 | 冻结响应情景已保存；后续前景、完整状态结转及独立实际验证不足。接通需求→效率→生产→财务→下一期状态后再比较剩余收益 |', '| 2 | 材料误差及跨价格适用 | ' + diag_summary + '正式5公布价690/9.30美元每单位，需独立验证加法/比例迁移及实际产量预测，不能仅凭同期误差切换模型 |\n| 3 | 正式5至6完整经营收益链 | 正式5前景及曲线已归档；正式6条件、完整状态结转及独立实际验证不足。接通需求→效率→生产→财务→下一期状态后再比较5至6新增收益 |')
replace('README.md', '20项问题的“1已解决、15部分、4未解决”是2026-10-12历史验收统计，未重审为当前关闭率；不得用局部公式、自检或预算提高替代经营验收。', f'20项问题的“1已解决、15部分、4未解决”仅为2026-10-12历史统计；[t5v0逐项状态]({TRAIN}/report_final.md#20项问题的本次状态)已分别列明暂停、不可识别、部分及本次检查通过，不合并为新的关闭率。局部公式、自检或预算提高不能替代经营验收。')
replace('README.md', '本次文档整理的改前内容、哈希、范围及验收保存在[20261014T203329199980+0800_all_docs](output/text_cleanup/20261014T203329199980+0800_all_docs/work_log.md)。', f'本次文档整理的改前内容、哈希、范围及验收见[整理记录]({OUT.relative_to(ROOT).as_posix()}/work_log.md)；[上次整理](output/text_cleanup/20261014T203329199980+0800_all_docs/work_log.md)保留。')

# Requirements are normative; remove duplicate old progress preambles, preserve new rules.
req = 'Cesim_任务要求与当前情况说明.md'
text = read(req)
start = text.index('更新：')
end = text.index('## 关键边界')
replace(req, text[start:end], '更新：2026-10-15（北京时间）。本文维护执行要求，当前状态、版本和待解决问题统一见[项目总览](README.md)；公式、参数和历史误差按专题及来源版本保存。包含2026-10-15确认的全参数优化及方案输出要求，文档整理不代表平台填写或提交。\n\n')

new_train_row = f'| 正式4实际训练（有缺口） | [t5v0报告]({TRAIN}/report_final.md)、[注册表]({TRAIN}/models_full.json)、[29类状态]({TRAIN}/model_inventory_final.json) | {summary} |\n'
new_curve_row = f'| 正式5曲线（独立保存） | [报告]({CURVE}/report.md)、[参数]({CURVE}/formal5_curves.json)、[验收]({CURVE}/acceptance.json) | {curve_summary} |\n'
new_diag_row = f'| 正式4材料诊断 | [报告]({DIAG}/report.md)、[明细]({DIAG}/diagnosis.json) | {diag_summary} |\n'
replace('预测模型与训练参数汇总.md', '| 实际训练 |', new_train_row + new_curve_row + new_diag_row + '| 正式3需求基线 |')
for p in ['训练拟合模型与版本清单.md', '训练拟合模型与版本清单_文字说明版.md']:
    replace(p, '| 新诊断 |', new_diag_row + '| 其他诊断 |')
replace('模型版本重新统计.md', '| 当前去重清单 |', new_curve_row + new_diag_row + '| 正式3去重清单 |')

replace('预测模型与变量说明.md', '最新实际训练为t4v1，正式3完整10市场100队双产品有效需求200/176条；', f'最新实际训练为[t5v0]({TRAIN}/report_final.md)，{summary}正式5曲线[独立保存]({CURVE}/report.md)。t4v1保留为正式3需求基线，10市场100队双产品有效需求200/176条；')
replace('预测模型与变量说明.md', 'Word说明同步本次版本边界与分类，保留可编辑Office公式；', 'Word说明保留此前版本及可编辑Office公式，尚未同步本次t5v0及正式5文档更新；')

replace('code/README.md', '| 正式3完整训练 |', '| 正式4可估计项及状态核验 | [t5v0](model_v2/t5v0_README.md) | 独立训练目录，29类状态包含暂停和不可识别项，不代表完整预测通过 |\n| 正式5曲线 | [fit_formal5_curves.py](model_v2/fit_formal5_curves.py) | 三曲线600点，独立于正式4注册表保存 |\n| 材料误差诊断 | [diagnose_t5_materials.py](../work/diagnose_t5_materials.py) | 复现既有材料留出及舍入兼容性，独立诊断，不替换模型 |\n| 正式3完整训练 |')
replace('code/model_v2/README.md', '- [t4v1训练]', '- [t5v0训练与核验](t5v0_README.md)：正式4可估计项、29类状态和数据缺口；含正式5曲线独立产物入口。\n- [t4v1训练]')
replace('模型说明/README.md', '| T4V1 |', '| T5V0 | [T5V0_正式4训练与缺口](T5V0_正式4训练与缺口.md)；含正式5独立曲线入口 |\n| T4V1 |')
replace('模型说明/README.md', '- [连接件价格和运营历史候选]', f'- [正式4材料误差与舍入诊断](../{DIAG}/report.md)。\n- [连接件价格和运营历史候选]')

for p, prefix in [('模型说明/T5V0_正式4训练与缺口.md', '../'), ('code/model_v2/t5v0_README.md', '../../')]:
    text = edits.get(p, read(p))
    addition = f'\n## 正式4材料误差诊断\n\n{diag_summary} [诊断报告]({prefix}{DIAG}/report.md)给出市场等权与逐队等权差别、最大残差和显示精度边界。加法与比例在同基价下等价，正式5降价后的适用性仍需独立验证；诊断未替换注册表。\n'
    assert '## 正式4材料误差诊断' not in text
    edits[p] = text + addition

mat = '模型说明/MATERIAL_PROP_原材料单位费用比例模型.md'
text = read(mat)
start = text.index('## 当前证据与使用边界')
end = text.index('## 适用版本与限制')
replace(mat, text[start:end], f'## 当前证据与使用边界\n\n[t5v0正式4训练](../{TRAIN}/report_final.md)按双产品100/89条材料样本比较公布价、加法与比例形式，使用已实现产量作条件回溯。材料嵌套市场留出MAE为2.557838/0.266364千美元；连接件逐队等权MAE为0.265988，不能混用两种加权口径。\n\n{diag_summary} [独立诊断](../{DIAG}/report.md)说明显示产量半格可放大为数千美元残差，但兼容不证明真实成因。单一基价下加法与比例等价，尚不能识别正式5公布价690/9.30美元每单位时的迁移方式；未因本诊断修改模型。\n\nt4v1与t4v1a保留各自正式3训练及正式4冻结情景；下文练习/正式1历史参数不改写为t5v0参数。\n\n')
replace(mat, '两版独立保留，正式2实际验证未取得。', '两版独立保留；该历史训练记录未包含正式2实际验证，不据此判断当前归档是否已有正式2结果。')

flow = '模型说明/完整计算流程图.md'
replace(flow, '```mermaid\nflowchart TD', '```mermaid\nflowchart TD\n  R4[正式4已核实际及本组最终决策] --> T5[t5v0 29类逐项状态]\n  T5 --> COST[材料 工资 风险条件模型及正式4曲线]\n  T5 --> GAP[缺99队最终决策 需求暂停 效率rho不可识别]\n  R5[正式5公布条件及600点曲线] --> C5[独立曲线拟合 不覆盖正式4注册表]\n  COST --> LIMIT[完整正式5至6财务及状态链未通过]\n  GAP --> LIMIT\n  C5 --> LIMIT')
replace(flow, '训练、诊断与应用分开。当前冻结应用图', 't5v0及正式5曲线的来源与状态见[专题说明](T5V0_正式4训练与缺口.md)。训练、诊断与应用分开；图中t4v1→t4v1a保留正式3训练到正式4历史冻结应用路径。该冻结应用路径')

replace('项目结构.md', '| 正式3实际归档 |', f'| 正式4归档与正式5初值 | [正式4验收](output/round_close/20261014_formal4_close/final_validation/report.md)、[正式5初值](output/round_close/20261014_formal4_close/formal5_initial/report.md)；草稿、实际及未知状态分别保存 |\n| t5v0及正式5独立曲线 | [版本说明](模型说明/T5V0_正式4训练与缺口.md)；正式4可估计项训练与正式5曲线不混用，需求暂停 |\n| 正式4材料误差诊断 | [报告]({DIAG}/report.md)；条件误差、费用比例与舍入兼容性，不替换模型 |\n| 正式3实际归档 |')
replace('项目结构.md', '| `project_structure/` |', '| `t5v0/`、`t5_material_diagnosis/`、`decision_rules/` | 正式4训练及正式5独立曲线、材料误差诊断、全参数方案输出要求的修改前备份与验收 |\n| `project_structure/` |')

for p in list(edits):
    edits[p] = edits[p].replace('更新：2026-10-14（北京时间）', '更新：2026-10-15（北京时间）', 1)
    if p == '项目结构.md':
        edits[p] = edits[p].replace('整理日期：2026-10-14', '整理日期：2026-10-15', 1)

before = {}
for p in edits:
    target = ROOT / p
    backup = OUT / 'before' / p
    backup.parent.mkdir(parents=True, exist_ok=True)
    assert not backup.exists()
    shutil.copy2(target, backup)
    before[p] = sha(target)
    assert sha(backup) == before[p]
save_json('before_hashes.json', before)

# Guard already existing edits and immutable evidence before and after the document write.
protected = {x['path']: sha(ROOT / x['path']) for x in source_checks if x['path'] not in edits}
save_json('protected_hashes.json', protected)
for p, text in edits.items():
    assert sha(ROOT / p) == before[p], 'Concurrent edit detected: ' + p
    with (ROOT / p).open('w', encoding='utf-8', newline='') as f:
        f.write(text)

def links(path, text):
    result = []
    for target in re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', text):
        target = unquote(target.strip().strip('<>'))
        if re.match(r'^[a-z]+://', target, re.I):
            continue
        dest, _, anchor = target.partition('#')
        file = (ROOT / path).parent / dest if dest else ROOT / path
        ok = file.exists()
        if ok and anchor and file.suffix.lower() == '.md':
            headings = re.findall(r'^#{1,6}\s+(.+)$', file.read_text(encoding='utf-8-sig'), re.M)
            slugs = [re.sub(r'[^\w\-\s]', '', h.lower()).replace(' ', '-') for h in headings]
            ok = anchor in slugs
        result.append({'document': path, 'target': target, 'ok': ok})
    return result

link_checks = []
for p, text in edits.items():
    link_checks.extend(links(p, text))
old_broken = {(x['document'], x['target']) for p in edits for x in links(p, (OUT / 'before' / p).read_text(encoding='utf-8-sig')) if not x['ok']}
new_broken = [x for x in link_checks if not x['ok'] and (x['document'], x['target']) not in old_broken]
save_json('link_checks.json', {'checked': len(link_checks), 'failures': [x for x in link_checks if not x['ok']], 'new_failures': new_broken})
assert not new_broken, new_broken[:5]
assert all(sha(ROOT / p) == digest for p, digest in protected.items()), 'Protected evidence changed'
assert '最新实际训练为t4v1' not in read('预测模型与变量说明.md')
assert read(req).count('更新：2026-10-15（北京时间）') == 1
assert read(mat).count('## 当前证据与使用边界') == 1
assert '正式4历史联合情景（未采用）' in read('README.md')
assert '全部参数纳入优化' in read(req)
assert (ROOT / '预测模型与变量说明.docx').exists()
after = {p: sha(ROOT / p) for p in edits}
save_json('after_hashes.json', after)
save_json('acceptance.json', {'status': 'PASS', 'documents': list(edits), 'document_count': len(edits), 'backups_verified': True, 'evidence_hash_checks': len(source_checks), 'protected_files_unchanged': len(protected), 'links_checked': len(link_checks), 'new_broken_links': 0, 'existing_link_findings': [x for x in link_checks if not x['ok']], 'no_training_or_platform_operation': True, 'word_updated': False, 'privacy_scope': '新增文本仅使用PYT等既有大写首字母；未复制原始人员表头，未重跑全项目姓名审计。'})
now = datetime.now(timezone(timedelta(hours=8))).isoformat()
with (OUT / 'work_log.md').open('a', encoding='utf-8') as f:
    f.write(f'\n完成：{now}。更新{len(edits)}份Markdown说明。\n\n正式4归档、t5v0部分训练、正式5独立曲线与材料误差诊断已按来源更新；需求暂停、效率不可识别和跨期财务缺口明确保留。旧参数、公式及历史报告未改。\n\n验收：全部备份与改前/改后SHA256已保存；来源及冻结输出哈希核验{len(source_checks)}项，保护{len(protected)}个文件未变化；检查{len(link_checks)}条本地链接，新增失效0条。详见[验收](acceptance.json)、[链接检查](link_checks.json)、[来源检查](evidence_hash_checks.json)。\n\n本次未访问平台、未采集教程、未训练或修改模型参数、未提交决策，未同步Word，未重跑全项目参数计数或姓名审计。平台实时草稿仍须操作前重新确认。\n')
print(json.dumps({'run': OUT.relative_to(ROOT).as_posix(), 'documents': len(edits), 'hash_checks': len(source_checks), 'links': len(link_checks), 'existing_link_findings': len([x for x in link_checks if not x['ok']])}, ensure_ascii=False))
