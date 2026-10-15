"""One-off documentation consolidation; preserve pre-existing edits in a full backup."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import shutil
import os

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output/text_cleanup' / (STAMP + '_all_docs')
OUT.mkdir(parents=True, exist_ok=False)
files = sorted(set(ROOT.glob('*.md')) | set((ROOT/'模型说明').glob('*.md')) | set((ROOT/'code').rglob('*.md')))
before = {}
for p in files + [ROOT/'预测模型与变量说明.docx']:
    rel = p.relative_to(ROOT)
    backup = OUT/'before'/rel
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, backup)
    before[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'work_log.md').write_text(f'# 全部现行说明文档整理\n\n开始：{STAMP}（北京时间）。\n\n用户授权更新所有说明并分类汇总。范围为根目录、模型说明、code下的现行Markdown及根目录Word说明；output/history/raw/sources/quarantine中的历史证据和报告保留。已有未提交修改按当前磁盘内容完整备份。核对本地正式3归档、t4v1去重、t4v1a及研究诊断，不访问平台、不训练或提交决策。\n\n姓名统一用首字母替代。\n', encoding='utf-8')
(OUT/'before_hashes.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')

TRAIN = 'output/t4v1/20261014T153914569881+0800'
DEDUP = 'output/t4v1_deduplicated/20261014T162452595723+0800'
APP = 'output/t4v1a/20261014T175143627079+0800'
CON = 'output/t4v1_connector_optimization/20261014T162353579815+0800'
ABS = 'output/t4v1_abs_nested/20261014T170607791200+0800'
OWN = 'output/own_efficiency_scenarios/20261014T170508965934+0800'
RHO = 'output/efficiency_rho_local_reference/20261014T171500629011+0800'
ARCH = 'output/round_close/20261014_resume_verified/acceptance/20261014T152737.694032+0800'
registry = json.loads((ROOT/DEDUP/'models_full.json').read_text(encoding='utf-8'))
acceptance = json.loads((ROOT/APP/'acceptance.json').read_text(encoding='utf-8'))
assert registry['deployment_enabled'] is False
assert acceptance['frozen_demand_replay_records'] == 752
assert acceptance['bundle_hashes'] and acceptance['unchanged_fitted_parameters']

def link(p, target, label):
    return f'[{label}]({Path(os.path.relpath(ROOT/target, p.parent)).as_posix()})'

def write(p, text):
    p.write_text(text.strip()+'\n', encoding='utf-8')

def split_intro(text):
    lines = text.strip().splitlines()
    match = re.search(r'^## ', text, re.M)
    if match:
        return lines[0], text[len(lines[0]):match.start()].strip(), text[match.start():].strip()
    return lines[0], text[len(lines[0]):].strip(), ''

def scope(p):
    return ('更新：2026-10-14（北京时间）。本文按所列版本维护专题内容；项目当前状态与最新证据统一见'
            + link(p, 'README.md', '项目总览')
            + '。最新实际训练为t4v1（正式3完整10市场、100队），去重清单29类；t4v1a为非重训应用情景版。历史公式、参数和误差保留各自范围，未部署，完整剩余回合收益未验证。')

readme = f'''# Cesim 项目总览

更新：2026-10-14（北京时间），依据本地已保存资料核对。本文集中维护当前状态、版本入口、问题和下一步；历史过程与精确参数分别查阅对应归档。操作平台前仍须重新确认开放回合、身份、截止时间和本人输入。

## 项目目标与执行边界

目标是比较正式六回合的累计税后利润及不利情景。正式第t回合只比较t至6的新增收益，已实现收益作为共同基准；未知未来利润不补零，不宣称完整最优。

- 沿用只读采集与可恢复个人预算试验授权；推荐值填写仍待恢复，小组提交由用户协调，个人草稿与小组生效方案分开。
- 预算依赖所填需求预估，销量口径为`min{{需求预估数量，产量}}`，具体物流/供给/订单约束另核；预算、玩家预估、预测与实际标签分开。
- 正式1以初始0为基准，不继承练习2资金、债务及税亏。编号市场独立与同期参数共享属于用户分析假设，未证明为平台规则。
- 快速教程复用现有归档。结果按“打印版→可推导缺项计算→网页定向补采”采集；计算值保留公式、输入和舍入限制。
- 新报告默认Markdown，指定Word/PDF等格式则按指定格式交付；不再新增HTML报告或副本，历史HTML及网页证据保留。
- 姓名统一使用大写首字母。原始资料及历史截图可能含姓名，分享只选已脱敏交付，不能整包原件目录。

执行细节见[任务要求](Cesim_任务要求与当前情况说明.md)。生产策略/库存、自动短贷暂不作为完整优化范围，股权操作不涉及；已有连接件规则研究单独保留，不能据此扩展完整利润结论。

## 数据归档与当前回合

| 类别 | 已核状态 | 证据与边界 |
| --- | --- | --- |
| 初始0、练习1/2、正式1/2结果 | 历史750/750页及完整HTML已归档 | [历史完成验收](output/round_close/20261012T221044.031+0800/resume/20261013T_goal/completion.md)；统计范围截至正式2 |
| 正式3实际结果 | 10市场、100队、150/150网页；500项财务等式和100项累计衔接通过 | [正式3完整验收](output/round_close/20261013_formal3_close/archive_audit/validation/20261014T142929.104834+0800/report.md)；t4v0的90页只是历史训练子集 |
| 历史财务与结构补证 | 原6条财务待核展开为60项，全部通过；26条结构审查的新来源均为10队列 | [补证验收]({ARCH}/report.md)；旧附加列归属仍未知，旧额外列、冲突/拒绝原件保留 |
| 市场8正式3打印结构 | 1打印页与15网页独立计数；200字段行中150直接配对、50网页补充，另存28个图表JSON | [字段覆盖]({ARCH}/market8_field_coverage.json)；本批计算值0条，不虚算打印页为15网页 |
| 本组历史小组方案 | 市场5练习1/2、正式1/2/3小组列已保存，历史子页45/45核验 | [最终决策标签](output/round_close/20261013_formal3_close/decision_history/final_decisions_labeled/report.md)；个人、预算和实际分列 |
| 正式4已知条件 | 已归档前景、42项参数、初值及三条曲线600点，上期投入1000/400/600已配对 | [初值](output/round_close/20261013_formal3_close/formal4_initial/verification/20261014T002441/report.md)、[结转分类](output/round_close/20261013_formal3_close/formal4_initial/carryover_classification/20261014T005023/addendum_report.md)、[曲线]({TRAIN}/formal4_curves/README.md)；最近快照截止2026-10-14 22:00，非实时状态 |

新采集按字段/所需序列覆盖验收，旧750页与正式3的15栏统计保持原定义。结构或产品变化时先完整网页对照一次，旧缺口不会因切换路径自动关闭。[归档工作清单](每回合结束后工作清单.md)

## 模型训练与应用版本

| 角色 | 版本和入口 | 已完成及限制 |
| --- | --- | --- |
| 最新实际训练 | **t4v1**：[训练报告]({TRAIN}/report_final.md)、[运行说明](code/model_v2/t4v1_README.md) | 正式3双产品实际训练，复合梁200条、连接件176条有效需求；原31类包含拟合、规则及门槛状态，不等于31个独立拟合模型 |
| 当前训练参数查阅 | **t4v1去重版**：[29类注册表]({DEDUP}/models_full.json)、[清单]({DEDUP}/model_inventory_final.json)、[清理验收]({DEDUP}/report.md) | 删除UNIFIED/T2V0重复登记，利率引用风险参数；未重训，原训练参数与验证保留。外部旧调用须按`interest.parameters_source`取参数 |
| 最新独立应用情景 | **t4v1a**：[报告]({APP}/report.md)、[模型]({APP}/models_full.json)、[验收]({APP}/acceptance.json)、[运行说明](code/model_v2/t4v1a_README.md) | 训练回合3、应用情景回合4，冻结参数不重训；更新正式4公布参数及行业情景，752条冻结需求预测复算通过。不是正式4实际成绩或完整经营推荐 |
| 历史实际训练子集 | **t4v0**：[说明](模型说明/T4V0_正式3实际训练.md) | 正式3的6市场60队90页，需求120/110条；31类历史状态。已被t4v1完整数据版本扩展，原档保留 |
| 历史假设及统一版本 | **t3v1/t3v0**：[同曲线与联合分配](模型说明/T3V1_同曲线假设与联合分配.md)、[正式2训练](模型说明/T3V0_正式2重训及正式3附加曲线.md) | t3v1连接件实际标签0条只限该版本；不能用于描述t4v1。t3v0正式2训练、正式3曲线另存 |
| 更早研究组合 | **unified-market/t2v0-um**：[模型索引](模型说明/README.md) | 正式1同期共享假设与练习2组件，整体迁移和完整经营预测仍有门槛；去重删除登记不删除历史功能及文件 |

训练、研究诊断与应用情景分别保存。公司合计营销/研发仍为产品/国别代理，留出使用已实现竞争输入；同期条件误差不能当事前跨回合精度。全项目参数档案计数273/6283等只对应2026-10-12历史扫描，本次不重新统计为当前总数。[版本统计](模型版本重新统计.md)

## 研究诊断与条件比较

| 专题 | 结果 | 使用边界 |
| --- | --- | --- |
| 连接件价格和历史投入 | 需求份额MAE 2.602759→2.520797个百分点，改善3.15%；营销历史代理未增益 | [报告]({CON}/report.md)；99队真实产品/国别分配仍缺，未替换主预测或部署 |
| 更早运营历史 | 加入正式1投入后，连接件逐队MAPE 0.953284%→0.194342%，复合梁0.863225%→0.191008% | 同上；`O3+ρO2+ρ²O1`是已观测历史前缀，未知更早状态仍缺，异常队残差仍超舍入区间 |
| ABS与SHARE数量对照 | ABS数量MAE为复合梁1.109495、连接件44.421894千单位；SHARE×实际总量为0.760673、36.983275 | [嵌套验证]({ABS}/report.md)；SHARE享有实际总量条件，ABS保留诊断，不默认平均或替换 |
| 本组效率情景 | 10组单公司ρ/θ情景可精确回算q/n；其他9市场拟合后回放本组 | [报告]({OWN}/report.md)；单观测不能识别ρ，保存情景补充原输出覆盖问题，不作效率调整依据 |
| 效率ρ局部细化 | 仅其他9市场选参、市场5留出回放，训练目标改善极小 | [参考]({RHO}/report.md)；精细小数不代表估计精度或泛化提升，未改注册表 |
| 连接件自由生产与订单生命周期 | 数量结转、确认订单优先、10%预收/余款规则有独立自检 | [V1](模型说明/CONNECTOR_连接件独立自由生产路径.md)、[V2](模型说明/CONNECTOR_V2_库存订单及影响路径.md)；机会不是中标，真实库存/订单跨期财务未验证 |

## 当前问题与修复顺序

| 优先级 | 缺口 | 已完成与下一步 |
| --- | --- | --- |
| 1 | 真实竞争投入口径 | 已恢复100队正式1/2合计营销/运营历史；99队正式3产品/国别营销、分产品研发仍缺。先补齐同竞争集合再比较真实投入与代理 |
| 1 | 曲线横轴、研发延期与运营存量 | 正式4曲线来源和上期投入已核；自动支出→有效横轴映射未证实。历史候选改善不等于完整存量识别，不能重复叠加历史影响 |
| 2 | 风险利率与计息状态 | t4v1a禁止杠杆幂函数应用，指数只作范围内显式状态敏感性；正式4已给基准5%，正式3叙述5%/参数4%的冲突及计息时点仍保留 |
| 2 | 投资与产能生效时点 | 当前零投资容量投影不能泛化，旧下期生效/本期零增量假设与页面证据冲突；正式4仅更新机器价格，不排名投资收益 |
| 2 | 订单、税亏及完整财务状态 | 有确认订单规则但缺真实中标/交付/预收余款，税亏及期初/期末/平均计息状态未齐；不能输出完整现金或利润 |
| 3 | 正式4至6完整经营收益链 | 冻结响应情景已保存；后续前景、完整状态结转及独立实际验证不足。接通需求→效率→生产→财务→下一期状态后再比较剩余收益 |
| 3 | 事前评分与历史列归属 | 原176份预测/模型已冻结，但本组实际方案未采用候选，不能计为候选事前成绩；旧附加列归属未知，拒绝/冲突原件保留 |

20项问题的“1已解决、15部分、4未解决”是2026-10-12历史验收统计，未重审为当前关闭率；不得用局部公式、自检或预算提高替代经营验收。

## 下一步执行与文档导航

1. 实时确认回合、本人基准及小组草稿，复用已核归档，按缺口定点补证。
2. 核对冻结预测与实际生效方案；不匹配的方案仅作条件回溯，不补造事前预测。
3. 补齐输入与状态后做独立跨回合验证；研究候选通过适用范围及稳定性门槛后再决定版本切换。
4. 正式4结算后按[回合清单](每回合结束后工作清单.md)归档、评分、复盘、更新与结转；正式6走终局分支。

| 阅读目的 | 专题入口 |
| --- | --- |
| 要求、授权、日志、脱敏和交付 | [任务说明](Cesim_任务要求与当前情况说明.md)、[AGENTS](AGENTS.md) |
| 参数、期限与模型验收 | [六回合要求](参数细化与六回合期限要求.md)、[重审与验收](建模重审与验收要求.md) |
| 平台采集及个人保存 | [图表读取](网页图表原始数据读取.md)、[操作标准](原生键盘标准操作.md) |
| 模型公式、输入与参数 | [模型目录](模型说明/README.md)、[流程图](模型说明/完整计算流程图.md)、[变量说明](预测模型与变量说明.md)、[Word说明](预测模型与变量说明.docx)、[参数汇总](预测模型与训练参数汇总.md) |
| 版本明细 | [统计](模型版本重新统计.md)、[技术清单](训练拟合模型与版本清单.md)、[文字清单](训练拟合模型与版本清单_文字说明版.md) |
| 目录职责与脚本运行 | [项目结构](项目结构.md)、[代码入口](code/README.md)、[model-v2](code/model_v2/README.md) |
| 历史研究报告 | [初版需求](需求拟合报告.md)、[正式1分步](正式1分步建模报告.md)、[初版回算](建模与回算报告.md)、[迁移方法](模型迁移与预估验证.md)、[练习/正式差异](练习与正式_已知数据差异.md) |

本次文档整理的改前内容、哈希、范围及验收保存在[{OUT.name}](output/text_cleanup/{OUT.name}/work_log.md)。原件、旧模型、冻结预测与历史报告保留，不以文档更新表示平台状态或模型训练改变。
'''
write(ROOT/'README.md', readme)

# Remove stacked global status bulletins from topical intros; preserve unique history below.
for p in files:
    if p.name in {'README.md','AGENTS.md'} or p == ROOT/'模型版本重新统计.md':
        continue
    text = p.read_text(encoding='utf-8-sig')
    title, intro, body = split_intro(text)
    paragraphs = re.split(r'\n\s*\n', intro)
    keep, version_notes = [], []
    for para in paragraphs:
        if any(marker in para for marker in ['2026-10-14 t4v1去重更新', '2026-10-14最新实际训练版本', '2026-10-14定时状态核对', '2026-10-14新增 **t4v0', 't4v0更新（2026-10-14']):
            continue
        if para.startswith('2026-10-13新增') or para.startswith('2026-10-14已复制'):
            version_notes.append(para)
        else:
            keep.append(para)
    intro = '\n\n'.join(keep).strip()
    intro = intro.replace('已有Word未同步本次整理。', '').replace('Word版尚未同步本次口径更新。', '')
    intro = intro.replace('本次定时整理核实正式3新归档与t4v0交付', '本次整理核实正式3完整归档、t4v1去重及t4v1a独立应用情景')
    intro = intro.replace('整理：2026-10-13（北京时间）', '整理：2026-10-14（北京时间）')
    intro = intro.replace('核对日期：2026-10-12（北京时间）', '历史参数核对日期：2026-10-12（北京时间）')
    if not body:
        body = '## 版本内容与运行边界\n\n'+intro
        intro = ''
    text = title+'\n\n'+scope(p)+'\n\n'+intro+'\n\n'+body
    if version_notes:
        text += '\n\n## 相关版本归档\n\n'+'\n\n'.join(version_notes)
    # Standard formula pages put applicability before details, and historical tables last.
    if p.parent.name == '模型说明' and '## 公式\n' in text:
        segments = re.split(r'(?=^## )', text, flags=re.M)
        preamble, sections = segments[0], segments[1:]
        order = ['适用版本与限制','公式','输入变量','输出变量','参数定义','实现与原始参数来源']
        def key(s):
            heading = s.splitlines()[0][3:]
            return next((i for i,h in enumerate(order) if heading.startswith(h)), len(order))
        text = preamble+''.join(sorted(sections, key=key))
    write(p, text)

# Current protocol corrections, preserving original numerical/history detail.
p = ROOT/'建模重审与验收要求.md'
t = p.read_text(encoding='utf-8')
t = t.replace('## HTML报告与一致性验收','## 报告交付与一致性验收')
t = t.replace('- 交付中文本地HTML及Markdown结论、JSON明细、CSV。优先原生HTML/CSS/JavaScript与已安装Matplotlib，图表、数据、样式随报告保存，不依赖外部CDN。', '- 新报告默认交付中文Markdown结论、JSON明细和CSV；指定Word/PDF等非HTML格式时按指定格式交付，不生成HTML报告副本。使用已安装绘图工具保存独立图表，历史HTML报告和网页证据保留。')
t = t.replace('函数、计算链、搜索和HTML中一致','函数、计算链、搜索、报告及导出中一致')
write(p,t)
p = ROOT/'每回合结束后工作清单.md'
t = p.read_text(encoding='utf-8').replace('每项计算结果在Markdown/HTML/表格中','每项计算结果在Markdown、指定的非HTML文档及表格中')
t = t.replace('同期HTML内容冲突与财务待核仍单列。最新依据见', '正式3已齐10市场100队150页；历史6条财务待核的60项新配对已通过，26条结构审查新来源已补齐；旧附加列归属与拒绝/冲突原件继续保留。最新依据见')
write(p,t)
p = ROOT/'code/model_v2/新增数据价值验证.md'
write(p,p.read_text(encoding='utf-8').replace('中文Markdown/HTML和核验哈希','中文Markdown和核验哈希（历史HTML输出不再作为新交付要求）'))

# Historical catalogs retain identifiers and all complete-precision rows; current entries stand apart.
for name in ['训练拟合模型与版本清单.md','训练拟合模型与版本清单_文字说明版.md','预测模型与训练参数汇总.md']:
    p = ROOT/name
    t = p.read_text(encoding='utf-8')
    t = t.replace('## 当前最新独立训练与正式报告版本','## 2026-10-12历史训练与报告版本')
    t = t.replace('## 最新版本示例','## 2026-10-12历史版本示例')
    t = t.replace('## 每个模型的全部保存参数版本','## 历史扫描范围内的保存参数版本')
    t = t.replace('## 全部主版本的文字说明','## 历史扫描范围内的主版本说明')
    t = t.replace('最新组件训练为 t2v0-um', '该历史扫描时的最新组件训练为 t2v0-um')
    t = t.replace('最新整套假设训练仍为 unified-market', '该历史扫描时的最新整套假设训练为 unified-market')
    title, intro, body = split_intro(t)
    newest = f'''## 当前版本与统计范围

| 分类 | 当前证据 | 口径 |
| --- | --- | --- |
| 实际训练 | [t4v1完整训练]({TRAIN}/report_final.md) | 正式3：10市场100队；双产品有效需求200/176条；原31类状态含确定规则和门槛 |
| 参数查阅 | [去重注册表]({DEDUP}/models_full.json)、[29类清单]({DEDUP}/model_inventory_final.json) | 不重训；原参数不变，利率风险参数由引用定位 |
| 独立应用 | [t4v1a]({APP}/report.md)、[冻结参数]({APP}/models_full.json) | 回合3训练/回合4应用情景，非完整预测，未部署 |
| 新诊断 | [ABS嵌套留出]({ABS}/report.md)、[连接件候选]({CON}/report.md)、[效率情景]({OWN}/report.md)、[ρ细化]({RHO}/report.md) | 研究证据并列，不增加或替换主模型类别，不当事前成绩 |
| 历史参数普查 | 78档案、6283位置、6371说明行、273非副本主版本 | 仅2026-10-12保存范围；不同统计单位不可相加，本次未重跑全项目普查 |

下文旧ID、精确参数、副本关系和误差维持当时记录；新增版本通过上表固定JSON与专题说明查阅，不将后来的参数冒配到旧ID。
'''
    write(p,title+'\n\n'+intro+'\n\n'+newest+'\n'+body)

p = ROOT/'模型版本重新统计.md'
original = (OUT/'before/模型版本重新统计.md').read_text(encoding='utf-8-sig')
historical = original[original.index('核对时间：20261012'):]
historical = historical.replace('最新组件训练：','该历史扫描时的组件训练：').replace('最新整套假设训练：','该历史扫描时的整套假设训练：')
write(p, '# 模型版本与统计口径\n\n'+scope(p)+f'''

## 当前版本分类

| 项目 | 版本 | 统计单位与限制 |
| --- | --- | --- |
| 最新实际训练 | [t4v1]({TRAIN}/report_final.md) | 原31类状态登记，200/176条有效需求，10市场100队；不等于31个自由参数模型 |
| 当前去重清单 | [t4v1去重]({DEDUP}/model_inventory_final.json) | 29类；移除UNIFIED/T2V0重复入口，未删除历史版本或独立功能 |
| 非重训应用情景 | [t4v1a]({APP}/report.md) | 保留29类及冻结候选，正式4情景应用；不作为新增训练版本 |
| 研究候选与诊断 | [连接件]({CON}/report.md)、[ABS]({ABS}/report.md)、[效率]({OWN}/report.md)、[ρ细化]({RHO}/report.md) | 单独保存，不并入主注册表类型计数或部署清单 |
| 历史训练 | t4v0、t3v1、t3v0、unified-market、t2v0-um | 按各自范围读取，t4v0的6市场及t3v1连接件零标签不能描述当前训练 |

## 数量的含义

“模型类型”包含训练、确定公式、组合与门槛；“参数位置”是JSON字段路径；“版本说明行”可能展开同一位置的多个估计向量；“评分条数”记录选参成绩。四者不是同一个统计单位，副本也不能算新增独立训练。

## 2026-10-12历史普查结果

'''+historical)

# Central model navigation, grouped by business purpose.
p = ROOT/'模型说明/README.md'
groups = {
    '需求与行业规模': ['ABS','SHARE','COUNTRY','TOTAL','BASELINE','GROWTH'],
    '投入响应与生产成本': ['RD','OPS','EFF','CAPACITY','LABOR','MATERIAL','MATERIAL_PROP'],
    '经营财务与期限评价': ['OPERATING','FINANCE','INTEREST','RISK_POWER','RISK_EXP','HORIZON','METRICS'],
    '连接件与联合分配': ['CONNECTOR','CONNECTOR_V2','T3V1'],
    '训练版本与历史组合': ['T4V1','T4V0','T3V0','UNIFIED','T2V0'],
}
catalog = '# 模型说明分类索引\n\n'+scope(p)+'\n\n## 当前模型和应用入口\n\n'
catalog += f'''[t4v1完整训练](T4V1_正式3完整数据训练.md)维护训练范围与复现；[t4v1a应用情景](T4V1A_正式4非重训应用情景.md)说明冻结参数应用与缺口。当前参数查阅使用{link(p,DEDUP+'/models_full.json','去重29类注册表')}，原训练和应用参数分别冻结保存。

历史UNIFIED/T2V0页面仍解释各自组合；从当前清单删除重复入口不删除历史功能。目录中的公式、参数与留出误差均按来源版本使用。

## 按业务主题查阅

'''
for group, prefixes in groups.items():
    catalog += '### '+group+'\n\n| 类型 | 说明文档 |\n| --- | --- |\n'
    for prefix in prefixes:
        matching = next((x for x in (ROOT/'模型说明').glob(prefix+'_*.md')),None)
        assert matching, prefix
        catalog += f'| {prefix} | [{matching.stem}]({matching.name}) |\n'
    catalog += '\n'
catalog += '''## 参数和流程的职责

[计算流程图](完整计算流程图.md)区分当前冻结应用和历史条件链；[变量说明](../预测模型与变量说明.md)维护符号与通用公式；[参数汇总](../预测模型与训练参数汇总.md)维护输入、参数、训练配置和误差分类；[版本统计](../模型版本重新统计.md)解释数量口径；[完整历史清单](../训练拟合模型与版本清单.md)保留参数ID及副本关系。

## 研究诊断与应用限制

'''
for target,label in [(CON,'连接件价格和运营历史候选'),(ABS,'ABS与SHARE嵌套对照'),(OWN,'本组效率情景'),(RHO,'其他9市场ρ细化参考')]:
    catalog += '- '+link(p,target+'/report.md',label)+'。\n'
catalog += '\n研究候选未部署，99队真实产品/国别投入、前向曲线横轴映射、订单实际状态及完整财务/剩余收益链仍缺。确定规则自检、曲线近似与同期留出不能代替独立后续回合成绩。\n'
write(p,catalog)

# Replace outdated code intro stacks with a work-oriented current index, retain legacy script table.
p = ROOT/'code/README.md'
old = (OUT/'before/code/README.md').read_text(encoding='utf-8-sig')
body = old[old.index('## 按工作选择入口'):]
header = '# 代码入口与运行边界\n\n'+scope(p)+f'''

## 当前训练、应用与诊断

| 工作 | 维护入口 | 输出与限制 |
| --- | --- | --- |
| 正式3完整训练 | [t4v1](model_v2/t4v1_README.md) | `output/t4v1/`新目录；当前查阅{link(p,DEDUP+'/models_full.json','去重参数')}，重跑训练会产生原31类登记，去重交付另列 |
| 正式4冻结应用情景 | [t4v1a](model_v2/t4v1a_README.md) | 不训练或选参；缺状态返回缺口，禁止完整利润/期限排名 |
| 连接件历史/价格研究 | [optimize_t4v1_connector.py](model_v2/optimize_t4v1_connector.py) | 新目录保存；`--self-check`最小合成检查，`work/accept_connector_optimization.py`对应验收 |
| 本组效率诊断 | [diagnose_own_efficiency.py](model_v2/diagnose_own_efficiency.py) | 单公司ρ不可识别；独立保存情景及其他9市场留出结果 |
| ρ局部参考 | [refine_efficiency_rho_reference.py](../work/refine_efficiency_rho_reference.py) | 仅其他9市场训练，不改主注册表 |
| ABS嵌套数量对照 | [validate_t4v1_abs_nested.py](../work/validate_t4v1_abs_nested.py) | 复用冻结代码、保存同集合外折；SHARE数量基线使用实际总量 |

## 历史版本与专项脚本

[t4v0](model_v2/t4v0_README.md)仅正式3的6市场子集；[t3v1](model_v2/t3v1_README.md)为连接件同曲线假设及联合分配；[t3v0](model_v2/t3v0_README.md)为正式2统一训练。这些运行和报告保持原版本范围，不作为正式4完整预测入口。

历史脚本可能仍生成HTML报告；新任务应使用Markdown交付，不为本次文档整理运行历史生成器或改写旧报告。`code/要求说明_模板.md`只供早期归档生成器使用，不能覆盖当前任务要求。

'''
write(p,header+body)
p = ROOT/'code/model_v2/README.md'
old = (OUT/'before/code/model_v2/README.md').read_text(encoding='utf-8-sig')
body = old[old.index('## 运行与输出'):].replace('## 运行与输出','## 历史情境重审入口与输出').replace('## 适用范围与验收状态','## 历史重审版本的范围与门槛')
write(p,'# model-v2 运行与版本选择\n\n'+scope(p)+'''

## 当前工作入口

- [t4v1训练](t4v1_README.md)：正式3完整双产品实际训练；训练与去重交付分别定位。
- [t4v1a应用](t4v1a_README.md)：冻结参数的正式4情景，不重训、不选参。
- [代码总目录](../README.md)：连接件优化、ABS嵌套、本组效率与ρ参考分别运行和验收。
- [新增数据价值验证](新增数据价值验证.md)：独立审计、增量比较和门槛训练；不自动部署。

以下`run.py --stage`是早期情境重审流程，其门槛结论仅属于该版本；不代表t4v1未训练，也不代表t4v1a完整经营预测已通过。复现使用项目Python与对应NumPy/SciPy版本，不假定系统Python兼容。

'''+body)

# Targeted current evidence attached to each relevant model, while keeping historical coefficient rows.
notes = {
 'ABS': f'最新双产品ABS嵌套整市场验证见{{abs}}。数量MAE：复合梁1.109495、连接件44.421894千单位；SHARE乘实际总量对照为0.760673、36.983275。两产品均有9/10市场ABS数量误差较大；保留独立数量/规模诊断，不默认平均或替换SHARE，不能据同期对照判断事前优劣。',
 'SHARE': 't4v1双产品SHARE正式3整市场嵌套份额MAE为复合梁0.793234、连接件2.602759个百分点（见{abs}复算）。连接件线性价格候选为2.520797个百分点，营销历史代理未增益；见{con}。主参数保持原版，99队真实产品/国别分配仍缺，不将同期条件成绩当事前定价依据。',
 'COUNTRY': 't4v1按产品保留泰国/印尼COUNTRY分支；t4v1a与SHARE并列情景比较，不默认平均。公司合计营销/研发仍是代理，不能当国别因果投入。完整当期竞争输入缺失时拒绝预测，不自行删队重归一化。',
 'EFF': 't4v1基线为O3+ρO2。独立历史候选使用O3+ρO2+ρ²O1，连接件留出逐队MAPE从0.953284%降至0.194342%，复合梁从0.863225%降至0.191008%；见{con}。本组10情景已单独恢复，见{own}；单观测不能识别ρ。{rho}仅其他9市场数值细化，不更新注册表。正式4成本比较保持正式3效率响应，不等于前向效率预测。',
 'OPS': '正式3训练曲线与正式4应用曲线独立保存，各回合来源/历史条件必须匹配。正式4三条曲线共600点已冻结，上期投入1000/400/600已核；当期支出到有效横轴的自动映射仍未证实，只开放显式有效坐标求值，不叠加未经核实历史存量。',
 'RD': '正式4曲线来源和上期投入1000/400/600已核，曲线参数冻结保存；自动支出→有效横轴映射和完整研发存量仍未知。t4v1a跳过自动研发预测，不把本组曲线推广为99队的产品投入响应。',
 'INTEREST': '当前去重注册表不再保存interest.parameters副本；按`registry[registry["interest"]["parameters_source"]][registry["interest"]["selected"]]`读取对应risk函数。t4v1a禁止杠杆幂函数，指数函数仅允许范围内显式状态敏感性；正式4基准5%与正式3历史4%差异单列，计息时点未识别。',
 'RISK_POWER': '历史训练与参数保留；t4v1a因稳定性/外推风险禁止杠杆幂函数应用，不作为正式4贷款或完整财务推荐。原训练误差不能解除该保护。',
 'RISK_EXP': 't4v1a只允许范围内显式资产/权益状态敏感性，不自动识别期初、期末或平均计息状态。正式4基准利率5%；长债整期不变的固定状态对照仅为税前利息敏感性，未验证现金终值。',
 'MATERIAL': 't4v1已按双产品真实成本训练加法与比例形式；固定基价下等价，跨基价含义不同，去重仍保留两者。t4v1a更新正式4材料公布价1053/14.20美元每单位，但无新基价实际标签，仅作冻结参数敏感性。',
 'MATERIAL_PROP': '与材料加法形式在当次固定基价下等价，跨基价解释不同，不能因此删去独立业务含义。t4v1按产品训练；正式4新价应用仅固定参数敏感性，跨基价迁移待实际标签验证。',
 'LABOR': '正式4工资33千美元/人已纳入t4v1a。固定产量和正式3效率保持下可比较人员、班次工资与解聘费用；历史效率候选单列，不作为正式4实际效率或完整利润预测。',
 'CAPACITY': '投资生效时点与旧假设存在证据冲突。正式4已知零投资容量投影可保留，不能泛化为任意投资规则；t4v1a仅更新机器价格58/1美元每单位，不排名投资收益。',
 'FINANCE': 't4v1a保留范围内利率和局部税前成本敏感性；计息状态/时点、税亏和完整现金链未齐，缺项明确返回，不能输出完整经营利润或现金终值。',
 'OPERATING': '正式3双产品成本标签已训练；正式4公布工资、材料与机器价格可用于显式条件对照。历史效率保持、供给与订单状态未知时，局部成本不升级为完整经营利润。',
 'TOTAL': 't4v1a以正式3各国各产品实际需求总量为基准，复合梁−15%/−17.5%/−20%、连接件+5%分别缩放；这些是前景情景，不是已实现正式4行业总量或独立训练的规模预测。',
 'BASELINE': 'SHARE乘同期实际总量只是条件数量基线。ABS不使用实际总量并不保证市场合计守恒；两种诊断按数量和份额分别报告，不能直接认定未知行业总量的事前胜负。',
 'GROWTH': '正式4行业变化按产品和国家分别计算，不能把不同产品千单位合并增长；保持正式3策略/响应的外部缩放仅情景传播，不等于完整未来需求预测。',
 'HORIZON': 't4v1a明确跳过正式4→5→6剩余利润排名；后续前景、完整经营链及结转状态不足，未知利润不能补零。正式6保留终局状态，不创建正式7或擅加终值。',
 'METRICS': '新指标分开报告：SHARE份额百分点、ABS数量千单位、效率逐队MAPE百分比及策略加权MAE。两个产品量级不同，不合并数量误差排名；冻结预测复算、同期嵌套留出与独立后续回合成绩分开。',
 'CONNECTOR': 't4v1已取得连接件真实需求/效率/材料/工资标签，旧V1的零标签只属于t3v1历史范围。数量结转和超产规则自检保留；实际库存计价与完整跨期备货收益未验证。',
 'CONNECTOR_V2': '当前V2继续按确认订单处理优先交付、10%预收和交付余款；投标机会不等于中标。t4v1a只保留已有规则和自检，缺真实中标、交付和收款状态，不能输出完整利润或最优备货。',
 'T2V0': '本文为练习2组件及正式2迁移历史版本。UNIFIED/T2V0从当前29类清单移除的是重复组合登记，历史代码、参数和解释仍保留；不作为最新训练或正式4整体应用入口。',
 'UNIFIED': '本文为正式1同期共享假设组合历史版本。去重只移除当前清单中的重复组合登记，不删除历史功能或参数；同期共享尚是用户分析假设，不能扩展为跨回合稳定规则。',
}
for prefix, note in notes.items():
    p = next((ROOT/'模型说明').glob(prefix+'_*.md'))
    t = p.read_text(encoding='utf-8')
    title, intro, body = split_intro(t)
    note = note.replace('{abs}',link(p,ABS+'/report.md','ABS嵌套对照')).replace('{con}',link(p,CON+'/report.md','连接件候选报告')).replace('{own}',link(p,OWN+'/report.md','本组效率情景')).replace('{rho}',link(p,RHO+'/report.md','ρ局部参考'))
    write(p,title+'\n\n'+intro+'\n\n## 当前证据与使用边界\n\n'+note+'\n\n'+body)

# Explicit sections for version runbooks, including new application documentation.
for p in [ROOT/'code/model_v2/t4v1_README.md',ROOT/'模型说明/T4V1_正式3完整数据训练.md']:
    write(p,'# t4v1 正式3完整数据训练\n\n'+scope(p)+f'''

## 训练数据与标签

正式3完整10市场100队150网页；有效需求复合梁200条、连接件176条。正式2实际期末形成期初，正式3需求/成本为真实标签；三条正式3曲线600点对应训练，正式4曲线单独保存，不混入训练。预算及玩家预估不作实际标签。

## 参数和交付版本

原训练保存31类状态：{link(p,TRAIN+'/models_full.json','原注册表')}、{link(p,TRAIN+'/report_final.md','训练报告')}。当前查阅{link(p,DEDUP+'/models_full.json','去重注册表')}和{link(p,DEDUP+'/model_inventory_final.json','29类清单')}；去重不重新训练，利率参数引用risk、材料同次拟合复用。UNIFIED/T2V0历史入口保留，删除的是重复登记。

正式4三条曲线原样复制在{link(p,TRAIN+'/formal4_curves/README.md','曲线副本目录')}，来源哈希一致；{link(p,APP+'/report.md','t4v1a')}为独立非重训应用情景，不替换正式3训练成绩。

## 运行与核验

从项目根目录按顺序使用匹配NumPy/SciPy的Python：

1. `python code/model_v2/t4v1.py`；最小自检加`--self-check`。
2. `python work/verify_t4v1.py <新目录>`。
3. `python work/finalize_t4v1.py <新目录>`。
4. `python work/accept_t4v1.py <新目录>`，再用验证脚本`--check-only`核对最终哈希。

各运行创建独立目录，不覆盖历史。该历史训练流程可能仍写HTML；新任务交付以Markdown为准，本次未运行生成器或重新训练。

## 应用限制

公司合计营销/研发仍为代理，缺产品/国别分配不伪造。零价零需求范围外记录保留，不补零。留出为同期条件研究，风险利率稳定性、自动曲线横轴、投资生效、税亏、订单库存及跨期经营链仍有缺口；未部署，不能据此推荐完整正式4决策或宣称六回合最优。
''')

for p in [ROOT/'code/model_v2/t4v1a_README.md',ROOT/'模型说明/T4V1A_正式4非重训应用情景.md']:
    write(p,'# t4v1a 正式4非重训应用情景\n\n'+scope(p)+f'''

## 版本职责与交付

t4v1a保留29类模型及冻结候选，训练回合3、应用情景回合4；未重训、未选参、未修改平台。独立{link(p,APP+'/report.md','报告')}、{link(p,APP+'/models_full.json','注册表')}、{link(p,APP+'/acceptance.json','验收')}与{link(p,APP+'/example_request.json','示例请求')}随包保存。

## 已应用条件

- 正式4公布参数：基准利率5%、短贷溢价3个百分点、工资33千美元/人；复合梁/连接件机器58/1、材料1053/14.20美元每单位。
- 行业情景：复合梁−15%/−17.5%/−20%、连接件+5%，按国家分别缩放正式3实际总量；需求保持正式3策略/响应，不称正式4已实现需求。
- 主份额仍用SHARE，COUNTRY与连接件线性价格候选分列，ABS仅诊断，不默认平均。
- 正式4三曲线冻结保存且上期投入1000/400/600已核；仅允许显式有效横轴求值，自动支出映射跳过。
- 运营历史候选在正式3效率响应保持、固定产量和当期工资下比较人员/工资/解聘及材料成本，不能称正式4效率预测或利润。
- 杠杆幂函数禁止应用；指数仅限范围内显式状态敏感性，计息时点与完整现金不自动推定。

## 使用与检查

进入交付目录`{APP}`，使用Python 3.12和包中版本锁对应的依赖：

```powershell
python code/model_v2/t4v1a.py --bundle . --self-check
python code/model_v2/t4v1a.py --bundle . --request example_request.json
python code/model_v2/verify_t4v1a.py .
```

以上是交付包内相对路径，根目录维护代码见{link(p,'code/model_v2/t4v1a.py','t4v1a.py')}与{link(p,'code/model_v2/verify_t4v1a.py','verify_t4v1a.py')}。已保存本地导入闭包和依赖锁，不复制原始人员表头；示例是条件请求，不是本人当前推荐。

752条冻结需求训练预测、保存的留出指标、效率/风险参数、曲线条件与范围、份额守恒、订单既有规则、缺输入拒绝、未知期限不排名及包哈希均有验收。复算不构成新增正式4实际成绩。

## 缺口与不支持范围

缺99队产品/国别投入、完整研发运营存量、曲线自动支出映射、投资生效时点、真实订单状态、计息时点、税亏及完整现金链；缺正式4→5→6后续前景和状态。接口返回具体缺口，非法数值/情境拒绝，不计算完整利润或剩余收益排名，不部署或填写平台。
''')

# Project directory/report table now resolves current acceptance instead of the superseded subset.
p = ROOT/'项目结构.md'
t = p.read_text(encoding='utf-8')
t = t.replace('output/round_close/20261013_formal3_close/archive_audit/validation/20261014T091756.838292+0800/report.md','output/round_close/20261013_formal3_close/archive_audit/validation/20261014T142929.104834+0800/report.md')
t = t.replace('6市场60队，90/150页，市场3/6/7/8尚未纳入','完整10市场100队150/150页；旧90页只属于t4v0历史训练范围')
t = t.replace('| t4v0正式3实际更新 |',f'| t4v1完整训练与去重 | [完整训练]({TRAIN}/report_final.md)、[当前29类参数]({DEDUP}/models_full.json)；正式3双产品实际训练，未部署 |\n| t4v1a冻结应用 | [独立应用]({APP}/report.md)、[验收]({APP}/acceptance.json)；回合4情景，未重训、无完整利润排名 |\n| 历史t4v0正式3子集 |')
write(p,t)

# Old generator template keeps placeholders and original numbers, but is explicitly historical.
p = ROOT/'code/要求说明_模板.md'
t = p.read_text(encoding='utf-8')
t = t.replace('| 2 | 快速教程归档 | 保存全部流程说明并与用户最初给出的步骤对照 |','| 2 | 快速教程归档复用 | 已有归档直接复用；仅明确要求、归档缺失/损坏或内容更新时补采并记录原因 |')
t = t.replace('## 8. 当前进展与本次交付','## 8. 早期归档批次进展与交付').replace('## 9. 暂停后的待办清单','## 9. 早期暂停记录与历史待办')
t = t.replace('## 4. 当前正式回合1数据','## 4. 早期正式回合1快照')
title, intro, body = split_intro(t)
write(p,title+'\n\n'+intro+'\n\n## 模板用途与覆盖限制\n\n本模板属于早期`archive_and_report.py`固定路径生成器；以下带占位符的数值与暂停状态只用于复现当时归档，不能作为当前状态或覆盖现行任务说明。现行规则维护在项目根目录专题文档；新报告默认Markdown，教程复用已有归档。\n\n'+body)

# Formula overview labels historical chains and adds latest evidence without changing native equations.
p = ROOT/'预测模型与变量说明.md'
t = p.read_text(encoding='utf-8')
t = re.sub(r'（当前，A/B）','（历史A/B）',t)
t = t.replace('（当前条件模型）','（历史条件模型）').replace('（当前及备选）','（历史及备选）').replace('（当前情景传播）','（条件情景传播）').replace('（当前）','（通用或历史公式）')
title,intro,body = split_intro(t)
new = f'''## 当前模型与公式适用范围

最新实际训练为t4v1，正式3完整10市场100队双产品有效需求200/176条；[29类去重注册表]({DEDUP}/models_full.json)保留原训练参数。t4v1a是独立非重训的正式4应用情景，不能用历史公式直接拼成完整经营预测。

需求主分支保持SHARE，COUNTRY并列，ABS仅数量/规模诊断；[ABS嵌套对照]({ABS}/report.md)不能替代事前验证。效率历史候选为O3+ρO2+ρ²O1，见[历史候选]({CON}/report.md)；它保留未知更早存量，未更新主参数。

[正式4应用情景]({APP}/report.md)更新公布参数，但自动研发/运营支出横轴映射、投资生效及完整计息/现金链仍缺。下文公式用于解释已列历史版本及范围内确定计算，所有参数必须按回合、产品和来源配对；不能把旧A/B数值当正式4当前值。

Word说明同步本次版本边界与分类，保留可编辑Office公式；各模型详细公式和当前证据见[模型目录](模型说明/README.md)。
'''
write(p,title+'\n\n'+intro+'\n\n'+new+'\n'+body)

# Current flow placed first; historical Mermaid graphs and source-specific labels retained.
p = ROOT/'模型说明/完整计算流程图.md'
t = p.read_text(encoding='utf-8')
t = t.replace('当前研究版本为 **t3v0**','该历史流程的研究版本为 **t3v0**')
title,intro,body = split_intro(t)
diagram = '''## 当前训练与冻结应用流程

```mermaid
flowchart TD
  A[正式3已核10市场100队实际与对应曲线] --> B[t4v1双产品训练及同期条件留出]
  B --> C[原31类登记 保留训练证据]
  C --> D[不重训去重 29类与风险参数引用]
  D --> E[t4v1a冻结参数应用情景]
  F[正式4公布参数 行业情景 三条曲线] --> E
  E --> G[SHARE主分支 COUNTRY并列 ABS诊断]
  E --> H[显式效率与风险状态下局部成本敏感性]
  E --> I[缺横轴映射 投资时点 订单 税亏或现金链]
  I --> J[返回缺口 不输出完整利润或剩余收益排名]
  D --> K[连接件价格与历史候选 ABS嵌套 效率诊断]
  K --> L[独立研究归档 不替换主参数]
```

训练、诊断与应用分开。当前冻结应用图不意味着完整财务链已经实现或跨回合验证通过；下文t3v0/t3v1图保留历史接口与假设，其中连接件零标签只属于旧版本。
'''
write(p,title+'\n\n'+scope(p)+'\n\n'+diagram+'\n## 历史流程范围\n\n'+intro.replace(scope(p),'').strip()+'\n\n'+body)

# Minimal project instructions link to one current navigation source, avoiding repeated status.
p = ROOT/'AGENTS.md'
t = p.read_text(encoding='utf-8-sig')
write(p,t+'\n\n## 文档维护\n\n当前状态集中在`README.md`，执行要求在`Cesim_任务要求与当前情况说明.md`，公式、参数和历史误差按专题及版本分类维护。新增进展更新所属主题，不继续在各文档开头叠加重复日志；历史证据与冻结结果保留。说明更新需备份当前磁盘内容、保存改前/改后哈希并核验链接，已有未提交修改不回退。\n')

# Put a compact topic TOC in lengthy documents without changing existing anchor names.
all_files = sorted(set(files) | {ROOT/'code/model_v2/t4v1a_README.md',ROOT/'模型说明/T4V1A_正式4非重训应用情景.md'})
def anchor(heading):
    return re.sub(r'[^\w\- ]','',heading.lower()).replace(' ','-')
for p in all_files:
    t = p.read_text(encoding='utf-8')
    t = re.sub(r'\n{3,}','\n\n',t)
    if p.name != 'AGENTS.md' and len(t.splitlines()) > 100:
        headings = re.findall(r'^## (.+)$',t,re.M)
        if headings:
            toc = '**主题导航：** '+' · '.join(f'[{h}](#{anchor(h)})' for h in headings)+'\n\n'
            first = re.search(r'^## ',t,re.M)
            t = t[:first.start()]+toc+t[first.start():]
    write(p,t)

# Record changes only; Word is handled separately and appended to the final validation.
after = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in all_files}
changes = [{'path':k,'before':before.get(k),'after':v} for k,v in after.items() if before.get(k)!=v]
(OUT/'document_changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'work/document_refresh_active.txt').write_text(OUT.relative_to(ROOT).as_posix(),encoding='utf-8')
assert len(changes) >= 50, len(changes)
assert '{{time}}' in (ROOT/'code/要求说明_模板.md').read_text(encoding='utf-8')
print(json.dumps({'output':str(OUT),'markdown_changed':len(changes),'backed_up':len(before)},ensure_ascii=False))
