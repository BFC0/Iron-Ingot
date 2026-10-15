"""一次性整理2026-10-13原文；不可对整理后的文档再次运行。"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.now(timezone(timedelta(hours=8)))
OUT = ROOT / 'output' / 'text_cleanup' / NOW.strftime('%Y%m%dT%H%M%S%f+0800')
OUT.mkdir(parents=True, exist_ok=False)
LOG = OUT / 'work_log.md'
LOG.write_text(f'# 文档整理工作日志\n\n开始：{NOW.isoformat()}（北京时间）。\n\n授权：整理项目文本、合并重复要求、更新工作状态和问题说明。仅编辑维护文档；不访问平台，不训练模型，不提交Git。当前已有改动先备份，不回退。\n\n状态：进行中。\n', encoding='utf-8')

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

protected = {str(p.relative_to(ROOT)): digest(p)
             for folder in ('raw', 'sources', 'quarantine', 'code', 'history')
             for p in (ROOT / folder).rglob('*') if p.is_file()}
(OUT / 'protected_manifest.json').write_text(json.dumps(protected, ensure_ascii=False, indent=2), encoding='utf-8')
status = subprocess.run(['git', 'status', '--short'], cwd=ROOT, capture_output=True, check=True).stdout
(OUT / 'git_status_before.txt').write_bytes(status)
before = {}
texts = {}

def read(name):
    return (ROOT / name).read_text(encoding='utf-8-sig')

def save(name, content):
    path = ROOT / name
    if path.exists() and name not in before:
        copy = OUT / 'before' / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(path.read_bytes())
        before[name] = digest(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + '\n', encoding='utf-8')
    texts[name] = content.strip() + '\n'

def section(text, start, end):
    assert start in text and end in text, (start, end)
    return text.split(start, 1)[1].split(end, 1)[0]

old = read('README.md')
history = '# 项目历史记录（截至2026-10-13整理前）\n\n本文保留旧文档索引、复现说明、对话目录及阶段成果，所有状态均对应原记录时点。最新进展见[项目总览](../README.md)，现行要求见[任务说明](../Cesim_任务要求与当前情况说明.md)。旧“无正式实际”“源未修复”“暂停”等表述不代表现状；旧候选不得直接用作当前决策。\n\n## 文档、数据与代码索引\n' + old.split('## 文档、数据与代码索引', 1)[1]
# 历史索引移入history后，原相对文件链接仍定位项目根目录。
def rebase(m):
    target = m.group(2)
    if ':' in target or target.startswith(('#', '/', '../')):
        return m.group(0)
    return '[' + m.group(1) + '](' + (ROOT / target).as_posix() + ')'
history = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', rebase, history)
save('history/项目记录_整理前_20261013.md', history)

review = '## 建模重审要求与执行顺序' + section(old, '## 建模重审要求与执行顺序', '## 文档、数据与代码索引')
review = review.replace('## 建模重审要求与执行顺序', '# 建模重审与验收要求', 1)
review = review.replace('2026-10-11新增执行要求：', '整理：2026-10-13（北京时间）。沿用2026-10-11的重审要求：', 1)
review = review.replace('### ', '## ')
review = review.replace('以下要求优先于旧文档中的暂停及过时待办，但不授权推荐值填写或小组提交。', '最新状态见[README](README.md)，操作边界见[任务说明](Cesim_任务要求与当前情况说明.md)。生产策略/库存、自动短贷暂不考虑，股权变动不涉及；下表历史编号保留，范围外分支仅标记适用限制，不列当前修复任务。')
review = review.replace('遵守上文', '遵守[任务说明](Cesim_任务要求与当前情况说明.md)')
review = review.replace('兼容性范围按上文交付偏好执行。', '优先桌面宽屏，不额外扩展小屏或多浏览器兼容测试。')
review = review.replace('正式实际需求、完整投入历史、国别营销、非零库存、大客户中标、短贷计息、亏后转盈及未来前景不足项单独列出。', '正式1实际数据已取得；冻结预测是否已评分须另查验收。完整投入历史、国别营销、大客户中标、亏后转盈及未来前景不足项单独列出；库存/短贷按当前简化范围保留限制。')
review += '\n## 问题状态的使用\n\n20项编号用于追溯，不能按表中原始问题描述认定现状。2026-10-12历史验收为1项已解决、15项部分完成、4项未解决；第2项损失与惩罚尺度等价已通过断言，第4/7/17/18项未解决。当前结构缺口与范围以[README问题汇总](README.md#当前问题与修复顺序)为准。规则已经写入文档、局部测试通过和模型机制已经实现分别记录；关闭问题必须附实现及验证证据。\n'
save('建模重审与验收要求.md', review)

save('README.md', '''# Cesim 项目总览

更新：2026-10-13（北京时间）。**目标是尽可能最大化正式6结束时的累计收益；六回合联合优化尚未完成，现有候选不能称为最终最优。**

## 先看这些提醒

- 操作前重新确认市场、开放回合、截止时间及本人区域；归档中的正式1、2.5等旧值不是当前基准。当前资料涉及正式3，本次未核验实时页面。
- 预算依赖手填需求预估，预算销量口径为`min{需求预估数量，产量}`；国别交付、物流及订单约束另核。预算、玩家预测和实际结果分开，预算不能充当实际训练标签。
- 原件、冻结预测及旧模型保留。先评分冻结预测，再重训；条件回算误差不能当事前成绩。缺失值不补零。
- 展示与导出中的姓名统一用大写首字母。原件和历史截图可能含姓名，分享只选已脱敏交付文件。
- 只读补证与可恢复个人试验沿用原授权；推荐值填写仍待恢复，小组提交另行协调。详细边界见[任务说明](Cesim_任务要求与当前情况说明.md)。

## 当前工作状态

| 工作 | 状态与依据 | 下一步或限制 |
| --- | --- | --- |
| 历史结果逐栏补采 | **部分完成：195/750页，剩余555页。** 市场1、2五个历史回合已齐；市场3初始0、练习1已齐。[最新续采报告](output/round_close/20261012T221044.031+0800/resume/20261013T103249/report.md) | 从市场3练习2继续。先切换并核验平台选中回合，再读各栏；仅改URL不能切换回合。三页同回合并发成功，六页读取超时，未保存为有效练习2原件。此进度优先于旧180/750及暂停标记。 |
| 正式1实际与正式2期初 | **已归档并复核：100队、200条国别实际；正式2期初由正式1期末结转。** [更新报告](output/formal_update/20261011T230905+0800_report/report.html) | 数据取得不表示冻结预测评分已完成；整体状态链仍不完整。 |
| 两份旧JSON恢复 | **已解决来源覆盖缺口。** 从Git精确恢复，SHA256与事故前一致。[恢复记录](output/model_v2/20261012T095938104706+0800_git_recovery/recovery.json) | 旧报告“尚未修复”仅为事故当时记录；历史来源和记录保留。 |
| 预算与决策口径 | **已更正文档、数据标签及对应生成器。** [更正说明](output/budget_semantics/20261013T105250646340+0800_sales_min/更正说明.md)、[数据标签](output/data_labels/说明.md) | 正式3两份预算对应用户修改前后方案，分别配对；缺决策快照的版本标“未配对”，不拼接。 |
| 研发/运营图表 | **正式2 JSON与SVG独立拟合、同点核验已完成。** [拟合](output/visible_coefficients/20261012_round2_json/拟合报告.md)、[配对核验](output/visible_coefficients/20261012_round2_joint/联合核验说明.md) | 通用训练仍读冻结曲线；逐回合、历史投入条件选择尚未完整接入。图形拟合通过不代表经营预测通过。 |
| unified-market正式1组合 | **已训练独立版本。** [报告](output/unified-market/20261012T114145124558+0800/report.md) | 按用户同期共享假设合并10市场，两国独立；份额MAE为0.300540/0.183417个百分点，属于同回合条件验证。假设未被证明，旧情境隔离版本保留。 |
| t2v0-um正式2组合 | **两项练习2组件已训练，整体迁移未通过。** [报告](output/t2v0-um/20261012T181028387320+0800/report.md) | 33项前景/给定值一致，15项曲线、销售响应及规则待配对；无整套需求/效率重训及正式2预测，仅适用回合2。 |
| 独立利率与材料模型 | **已训练和条件验证。** [利率](output/interest_rate/20261012T174038098990+0800/report.md)、[材料](output/material_unit_cost/20261012T175213319382+0800/report.md) | 未替换旧财务模型。利率MAE 0.3766基点依赖实际期末状态；材料单位费用=当期公布价×1.001379836576，跨回合比例仍属经验假设，正式2实际验证未完成。 |
| 正式2销售响应试验 | **价格2200保存及重入已确认，四个销售点未变；恢复未完成核验。** [日志](output/sales_response/20261012_manual_formal2/工作日志.md) | 不认定当前仍为2200，也不认定已恢复；下次操作先查最新本人值。四项销售乘数暂按给定值保存，不分别拟合响应函数。 |
| 六回合收益与完整推荐 | **未完成。** 旧联合情景仅比较当期条件利润。[历史研究](output/joint_scenarios/report.md) | 先修计算链，再重训、独立验证及比较至正式6；不得直接沿用历史候选。 |

## 当前问题与修复顺序

当前简化范围：**生产策略与库存机制、自动短贷机制暂不考虑；不涉及股权变动操作。** 这些不列为当前修复任务；遇到相应条件时仍须标明模型范围，不能当完整利润预测。

| 顺序 | 未解决问题 | 影响及下一步 |
| --- | --- | --- |
| 1 | 研发历史条件与延期作用未完整确认 | 已有`R_t+0.5R_(t-1)`及下期情景，不能称为完全无延期；但0.5、同曲线合并和历史映射未验证，`rho=0`且无其他路径会遗漏下期作用。先核曲线条件及当期/下期传递，避免重复计入历史影响。 |
| 1 | 运营累计状态缺失 | `O_t+rho*O_(t-1)`忽略更早投入，单次投入第二个后续回合回到零投入乘数。须建立并核验可更新的历史状态，连接效率、用工、工资和后续利润。 |
| 2 | 大客户订单及预付款跨期链缺失 | 缺中标状态、下期交付/产能占用、合同10%预收、余款收取及合同负债/现金结转；同等吸引力可平分，客户可拒绝全部投标。报价不能当中标。 |
| 2 | 多产品与当期条件未完整接入 | 旧模型主要面向复合梁，正式3新增连接件，工资、管理费和投资单价等已变。按产品、国家、回合及历史条件绑定，不能整套套用旧参数或t2v0-um。 |
| 3 | 跨回合经营收益链未建立 | 当期研发、运营费用已扣除，延期研发与累计运营未接入财务状态更新；六回合函数只求和外部利润。接通需求→效率→生产→财务→下一期状态后，才比较剩余累计收益。 |

依据：[模型结构重审](output/help_review/20261012/模型结构重审.md)、[脉冲与历史状态检查](output/help_review/20261012/structural_checks.json)、[22类模型审查](output/help_review/20261012/model_review.json)。系数重拟合、曲线形状检验和会计平衡不能补足结构缺口。

待补证据集中为四类：①研发/运营曲线族、完整投入历史及国别营销；②行业规模、未知对手策略和四项销售给定值的含义/入模方式；③经验softmax、投入尺度、风险/材料函数、计息时点、税亏清算、厂房与周转机制；④正式3前景年利率5%与参数表基准4%的来源冲突、当期完整输入及未来前景。定性信息不变成精确系数，未知继续保留。[当期部分条件](output/help_review/20261012/current_context.json)

已体现的机制不重复报缺：研发当期及单期滞后代理、运营对效率的作用、零库存零订单下按国别优先级交付、税亏抵扣方向，以及当期研发/运营/营销费用。预算未满足需求是玩家预估与交付之差，不是实际需求标签。

20项历史验收为**1项已解决、15项部分完成、4项未解决**；9组运行检查通过。该计数截至2026-10-12此前验收，未纳入后续结构审查与简化范围，不能作为当前问题关闭率。[逐项报告](output/issues_review/20261012T112446993158+0800/report.md)、[运行核验](output/issues_review/20261012T112446993158+0800/verification.json)

## 按流程继续工作

1. 核对最新身份、回合及本人基准，继续历史逐栏补采；缺口逐项保留。
2. 补齐当期前景、曲线历史条件、完整决策及预算版本配对，建立可追溯输入。
3. 按上表顺序修状态与依赖，再做独立训练、留出、预算回算和压力验收。
4. 评分正式1原冻结档案：[参数](output/cross_market/parameters_20261011T081705179804Z.json)、[预测](output/cross_market/future_predictions_20261011T081705179804Z.json)；缺失信息或最终方案变化单列，不事后补造预测。
5. 比较剩余至正式6的收益，按当回合完整决策清单输出候选；结算后依[回合清单](每回合结束后工作清单.md)复盘、更新及交接。

## 文档入口

| 阅读目的 | 入口 |
| --- | --- |
| 执行要求、授权、日志、姓名与交付 | [任务说明](Cesim_任务要求与当前情况说明.md) |
| 六回合目标、当期前景、曲线/利率及参数研究 | [参数与期限要求](参数细化与六回合期限要求.md) |
| 建模阶段、测试网格、20项追溯及报告验收 | [建模重审与验收要求](建模重审与验收要求.md) |
| 结果归档、冻结评分、结转及终局封存 | [每回合结束清单](每回合结束后工作清单.md) |
| 完整决策读取与个人保存 | [操作标准](原生键盘标准操作.md) |
| JSON/SVG采集、点配对与拟合 | [图表读取](网页图表原始数据读取.md) |
| 每个模型的公式、输入输出、参数及来源 | [模型说明目录](模型说明/README.md)、[计算流程图](模型说明/完整计算流程图.md) |
| 模型版本与训练口径 | [版本统计](模型版本重新统计.md)、[技术清单](训练拟合模型与版本清单.md)、[文字版](训练拟合模型与版本清单_文字说明版.md)、[参数汇总](预测模型与训练参数汇总.md) |
| 文件定位与安全运行 | [项目结构](项目结构.md)、[代码入口](code/README.md) |
| 历史成果、原始索引、旧复现命令及对话记录 | [历史记录](history/项目记录_整理前_20261013.md)、[对话索引](对话索引.json) |

最新状态集中在本文，要求在对应专题维护；历史报告保留当时结论及误差，不冒充当前状态。Markdown是本次维护范围，已有Word/PDF未同步此次整理。
''')

task_old = read('Cesim_任务要求与当前情况说明.md')
budget = section(task_old, '## 预算与决策读取更正（2026-10-13用户确认）', '## 执行要求')
logging = section(old, '## 日志、交付与姓名规则', '## 参数细化与六回合期限')
logging = logging.replace('正式2更新过程见[日志01](output/formal_update/20261011_work_log_01.md)，完成入口见下方版本记录；进度以追加验收为准。', '历史日志见[项目历史记录](history/项目记录_整理前_20261013.md)；当前进度以对应任务的追加验收为准。')
flow = section(old, '## 正式回合流程与技术步骤', '### 建模和个人试验的交付要求')
flow = flow.split('**继承口径：**', 1)[0]
save('Cesim_任务要求与当前情况说明.md', '''# Cesim任务要求与执行流程

更新：2026-10-13（北京时间）。目标、当前进展与问题统一见[README](README.md)；本文维护执行要求，专题文档补充细节。

## 关键边界

**先确认当前回合与本人基准，再采集或操作；不以旧快照覆盖最新值。** 正式1从初始0开始，练习2的资金、债务及亏损不能继承到正式1。个人草稿、最终小组方案和实际结果分别保存。

沿用已授权只读采集及可恢复个人预算试验。推荐值填写仍待用户恢复；不导入或提交小组决策，不覆盖其他成员，不联系其他小组或教师。其他成员在各自个人列的改动不影响本人输入及预算，不单独构成停试或样本失效理由；本人列、所选区域或小组方案变化时重新核验。同编号市场内最终小组决策仍有竞争作用。

当前模型简化范围与修复优先级见README。局部公式通过或预算提高不等于完整预测通过，更不等于六回合最优。

## 1. 确认身份与准备资料

核对课程、市场、阶段、开放回合、团队、本人区域、截止时间及最新输入。先读规则、案例、当期前景五部分和历史实际结果，再拟合、验证及比较。原件保留来源URL、采集时间、单位、源行列、市场/阶段/回合/团队/国家/产品、情境ID、有效期、核验状态及哈希；不可访问、失败或错配项明确记录，错配资料隔离于`quarantine/`。

编号市场间无直接作用及同期unified-market共享均为用户指定分析假设，尚未证明。共享系数不改变本市场内竞争集合；同一期共享不扩大为跨回合不变。旧情境隔离版本保留，研发/运营曲线还须匹配上期实际投入；两国独立，同国家可在独立共享版本中跨市场训练，运营不直接乘需求。

规则来源：[在线指南](raw/online_manual.json)、[PDF逐页文本](sources/决策指南_逐页文本.txt)、[案例](raw/20261011_case.json)。数据按[项目结构](项目结构.md)与[分组索引](数据分组索引.json)定位，逐栏归档要求见[回合清单](每回合结束后工作清单.md)。

## 预算与决策读取更正（2026-10-13用户确认）
''' + budget + '''
## 2. 建模、验证与候选比较

所有预测及财务计算使用Python，保留可复现代码、公式、单位、输入、参数来源、训练方法、适用范围与误差。实际结果、已知条件/历史决策、当前决策输入、玩家预估、平台预算和模型输出分别标记；销量受供给截断，不能代替真实需求，缺失不补零。[统一分类](预测模型与训练参数汇总.md)

用已结束回合的对应输入与真实终值训练，调参限训练内；当前曲线可当回合拟合，历史回算匹配历史曲线。先评分原冻结预测，再纳入新实际重训；训练误差、图形近似、已知对手/总量/期末状态的条件回溯和事前预测分开报告。

比较需求、定价、营销、研发、运营、产能、投资、班次、解聘、物流、融资及最低现金，报告当前方案、候选及不利情景。正式第t回合只评价t至6的新增利润，之前已实现收益为共同基准；状态或期限不完整时不输出完整累计收益排名。

具体执行：[参数与六回合要求](参数细化与六回合期限要求.md)、[建模重审与验收](建模重审与验收要求.md)、[图表读取](网页图表原始数据读取.md)、[迁移验证](模型迁移与预估验证.md)。

## 3. 个人试验与保存

每次只变一个授权字段，固定无关需求、效率及利率预估，保存完整相关预算；须确认输入、本人列及重入回读一致，再用于校准。每个机制至少留一个未校准样本验证。试验后恢复试验前最新基准并回读，用户明确保留的值继续保留；未保存、未恢复样本不参与拟合。恢复失败或回合/本人基准变化时停止扰动并报告。操作细节统一见[保存标准](原生键盘标准操作.md)。

## 4. 交付、协商与结算
''' + flow + '''
## 5. 结算复盘与下一回合

依[每回合结束后工作清单](每回合结束后工作清单.md)确认发布、逐栏归档、核验、评分冻结预测、分析偏差、更新模型和问题、结转状态、核验新前景与曲线，再交付复盘。正式6改为终局核验与封存，不创建正式7预测。

继承状态和持续作用，不原样继承销售、成本等当期发生额。现金、债务、资产、人员、税亏及研发/运营状态按已核规则结转；订单承诺与收付款分别跟踪。当前简化范围外的库存、短贷条件仍须标记限制，未知状态不补零。未来参数用显式情景，不能把上期值当作下期事实。

## 日志、交付与姓名规则
''' + logging + '''
## 验收与历史定位

验收须满足来源可追溯、Python可复现、类别/单位/约束正确、偏差可解释、当前与建议可比较、完整字段无遗漏、网页回读一致，且无误改其他区域。桌面报告的数值、筛选与导出须一致；完整数表留JSON/CSV，同一要求在对应专题完整维护，其余入口用摘要和链接。Word公式可编辑，中文宋体、英文Times New Roman。

2026-10-11保存记录为市场5、营销团队、正式1、PYT个人区，泰国个人需求2.5千单位、小组5；正式1截止为当日22:00。这是历史证据，不是实时状态：[保存核验](原生键盘保存核验.json)、[重入回读](raw/20261011_native_25_readback.json)、[日程](raw/20261011_schedule.json)。早期归档、A/B验证、对话及阶段成果见[历史记录](history/项目记录_整理前_20261013.md)，不再把当时“正式实际待公布”等待办写作当前状态。
''')

# 参数文档保留研究结果，删除跨专题重复定义，按输入→期限→研究排序。
param = read('参数细化与六回合期限要求.md')
finite = '## 有限期限目标\n' + section(param, '## 有限期限目标', '## 当前回合市场前景优先')
finite = re.sub(r'训练与预测的回合口径：.*?\n\n', '', finite, count=1, flags=re.S)
outlook = '## 当期前景与预算反馈\n' + section(param, '## 当前回合市场前景优先（2026-10-12用户新增）', '## 利率参数提示')
outlook = re.sub(r'真实值与预算反馈：.*?\n\n', '历史状态与训练标签取实际值，当期新增条件按决策时可见来源使用；预算口径与版本配对统一见[任务说明](Cesim_任务要求与当前情况说明.md#预算与决策读取更正2026-10-13用户确认)。受控预算试验可研究工资等计算关系，须保留基线、舍入/阈值检查及有效保存恢复证据，并与实际样本分开；结算后再检验适用性。\n\n', outlook, count=1, flags=re.S)
curves = '''## 当期曲线与历史条件

每回合重新采集、拟合并绑定对应版本；历史回算匹配历史曲线，缺失不静默沿用，未来曲线只作显式情景。研发需求乘数与运营效率乘数还依赖上期实际投入；同回合共享须历史条件相同或映射已验证。销售页四项乘数暂按给定值保存，含义与入模方式待核，不分别拟合响应函数。

JSON优先保留完整纵轴，SVG用于校准。同一原始点配对去重、同时分配训练/留出，图形误差与实际经营误差分开。采集格式、点映射、横轴取整和来源规范统一见[图表读取](网页图表原始数据读取.md)。正式2曲线已独立核验，通用训练仍使用冻结曲线，逐回合/历史条件选择未完整接入。
'''
rates = '## 利率参数提示\n' + section(param, '## 利率参数提示（2026-10-12用户新增）', '## 每回合曲线参数规则')
research = '## 待细化参数与机制\n' + param.split('## 待细化参数与机制', 1)[1]
research = research.replace('材料单位差额Δv | 练习1中位数校准；跨情境固定差额不兼容 | 独立预算与舍入区间重审，不自动解释成固定隐藏加价', '材料费用结构 | 旧固定差额跨情境不兼容；新独立比例模型及练习2组件已训练，未全部接入 | 比例/差额的跨回合识别及独立验证，不叠加两种校准项')
research = research.replace('最新重审结论', '2026-10-11重审结论')
research = research.replace('## 按优先级处理结果（2026-10-11）', '## 历史参数研究（2026-10-11）')
research = research.replace('## 已完成的运营ρ独立版本', '## 运营ρ独立研究及限制')
save('参数细化与六回合期限要求.md', '''# 当期参数与六回合期限要求

更新：2026-10-13（北京时间）。**只比较至正式6的累计收益；当前参数优先于历史经验，未知机制不补造，期限规范不代表跨期模型已实现。** 当前状态与结构缺口见[README](README.md)。

执行顺序：核对t回合已知条件与前景 → 绑定曲线/利率版本 → 计算当期及剩余回合 → 验证参数与状态 → 交付完整候选。输入、训练/假设参数、训练配置及评价指标的分类统一见[参数汇总](预测模型与训练参数汇总.md)；完整决策交付见[任务说明](Cesim_任务要求与当前情况说明.md#预算与决策读取更正2026-10-13用户确认)。

''' + outlook + curves + rates + finite + research)

# 结算清单压缩长表描述，同时保留全部流程与终局分支。
close = read('每回合结束后工作清单.md')
close = close.replace('更新：2026-10-12', '更新：2026-10-13', 1)
close = close.replace('日志、姓名和历史保留规则见[项目总览](README.md)。', '日志、姓名和历史保留规则见[任务说明](Cesim_任务要求与当前情况说明.md)。')
close = close.replace('## 逐项执行清单\n\n### 结果逐栏归档要求（2026-10-12新增）', '## 1. 逐栏归档范围')
close = close.replace('| 顺序 | 应做的事 |', '## 2. 结算后的执行顺序\n\n| 顺序 | 应做的事 |', 1)
close = close.replace('## 状态结转中必须单独核验的事项', '## 3. 状态结转核验')
close = close.replace('## 正式6结束后的单独分支', '## 4. 正式6终局分支')
close = close.replace('## 交付包与进入下一阶段的条件', '## 5. 交付与下一阶段门槛')
close = close.replace('当前机制缺口见[20项核验报告](output/issues_review/20261012T112446993158+0800/report.md)。', '当前机制缺口与简化范围见[README](README.md#当前问题与修复顺序)；[20项核验报告](output/issues_review/20261012T112446993158+0800/report.md)仅保留此前验收口径。')
close = close.replace('## 1. 逐栏归档范围', '**当前补采195/750页，剩余555页，从市场3练习2继续；核验脚本旧暂停标记不代表未获恢复授权。** 最新依据见[README](README.md)。下面是完整复盘规范，不表示这些步骤都已执行。库存/生产策略、自动短贷和股权变动按当前简化范围标记限制；流程保留可见实际记录，不把范围外缺口列成当前修复任务。\n\n## 1. 逐栏归档范围', 1)
save('每回合结束后工作清单.md', close)

operation = read('原生键盘标准操作.md')
operation = operation.replace('适用：', '**修改前核对最新本人值，试验后恢复并重入回读；只有输入框、本人列与重入值一致才算保存。** 2026-10-13整理未操作网页。正式2销售响应试验的恢复未完成核验，下次须先查当前值，不能认定已恢复。[试验日志](output/sales_response/20261012_manual_formal2/工作日志.md)\n\n适用：', 1)
operation = operation.replace('通过`cua.getState()`找到当前标签页，绑定并阅读返回文档。已有有效绑定时复用，不反复绑定。', '按当次工具文档绑定目标页面；需查找页面时先获取可用浏览器/标签页状态。已有有效绑定时复用。下方代码是历史API示例，执行前核对当前文档。')
operation = operation.replace('读取该列全部输入与预估项：绿色为未改动默认值，蓝色为改动值（用户2026-10-13确认）；旧快照缺少颜色时记录未知。按用户2026-10-11明确规则，其他组员在各自个人列的修改不会影响本人的决策及预算数据，不能仅凭其他列变化判定保存失败或停止试验；不向其他成员列或小组列写入。若本人列、所选区域或小组方案变化，重新核验。', '按上方读取提示核对完整本人列；其他成员自己的列变化不判本人保存失败。本人的列、区域或小组方案变化时重新核验，不写其他成员或小组列。')
save('原生键盘标准操作.md', operation)

structure = read('项目结构.md').replace('整理日期：2026-10-12', '整理日期：2026-10-13', 1)
structure = structure.replace('项目入口、要求、当前状态与历史更新', '关键提醒、最新状态、当前问题与导航')
structure = structure.replace('[参数与六回合期限](参数细化与六回合期限要求.md)、', '[建模重审与验收](建模重审与验收要求.md)、[参数与六回合期限](参数细化与六回合期限要求.md)、', 1)
structure = structure.replace('模型状态及姓名规则见[README](README.md)。', '模型状态见[README](README.md)，日志、姓名与交付规则见[任务说明](Cesim_任务要求与当前情况说明.md)。')
structure = structure.replace('以下链接从现有 README 汇集', '以下为固定版本入口，当前进度统一见README；旧验收不代表当前全部问题已解决。以下链接从既有归档汇集')
structure = structure.replace('| 20项问题核验 |', '| 帮助机制结构审查 | [结构重审](output/help_review/20261012/模型结构重审.md)；最新简化范围以README为准 |\n| 历史逐栏补采 | [最新续采](output/round_close/20261012T221044.031+0800/resume/20261013T103249/report.md)；195/750，仍未齐全 |\n| 20项问题此前核验 |', 1)
structure = structure.replace('分享范围按 README 姓名规则检查', '分享范围按[任务说明的姓名规则](Cesim_任务要求与当前情况说明.md)检查')
structure = structure.replace('| `project_structure/` |', '| `text_cleanup/` | 文本整理前快照、来源/代码保护与链接验收 |\n| `project_structure/` |')
save('项目结构.md', structure)

# 历史研究正文不改参数和误差，仅明确已更新的来源/状态边界。
notices = {
    '建模与回算报告.md': '本文为2026-10-11基础回算，保留原误差与当时限制。后续独立材料/利率模型已训练，两份旧源已恢复；不代表此历史链已替换或完整财务已通过。',
    '模型迁移与预估验证.md': '正式1实际200条已归档；下文“待实际”“本批未归档”仅指2026-10-11研究批次。迁移是否通过及冻结预测是否已评分仍须对应验收，不能因取得实际数据自动判定完成。',
    '正式1分步建模报告.md': '本文保留正式1采集时的输入、参数、误差和候选。正式1实际及正式2前景随后已取得；下文“当前”“前景未取得”指本报告时点，不作当前基准。跨期结构及正式3多产品接入仍未完成。',
    '需求拟合报告.md': '本文为首版历史需求拟合，保留冻结参数及原验证成绩。后续正式1实际已取得并新增独立模型，不能把旧待验证写作无实际数据，也不能用后续重训成绩替换首版事前成绩。',
    '练习与正式_已知数据差异.md': '本文保留练习2截图与正式1的当时对照。后续练习2/正式2已核对33项前景与给定值一致，15项曲线/销售响应/规则仍待配对，整体迁移未通过；可见一致不证明隐藏函数一致。',
    '预测模型与变量说明.md': '下文公式与“当前值”按所列历史版本使用，不自动支持正式3。研发/运营历史条件及跨期收益链未完整接通；当前简化范围以README为准。已有Word未同步本次整理。',
    '预测模型与训练参数汇总.md': '本表保留各归档参数和研究误差；正式1实际已取得、旧JSON已恢复，不代表每个历史版本均已完成外部验证。当前缺口、简化范围和组件接入状态以README为准，Word未同步本次整理。',
}
for name, notice in notices.items():
    content = read(name)
    title, body = content.split('\n', 1)
    # 已有相同入口句只留一个。
    body = body.replace('现行状态与待办见[README](README.md)；本文结论按所列版本和来源使用。\n', '')
    save(name, title + '\n\n**状态核对（2026-10-13）：**' + notice + ' 最新进度见[README](README.md)。\n' + body)

model_index = read('模型说明/README.md')
model_index = model_index.replace('当前正式3新增连接件自由生产；本目录保存公式仍按各自历史范围使用，不表示已支持多产品库存、订单预付款、自动短贷或当前完整预测。', '资料涉及正式3新增连接件；本目录公式仍按各自历史范围使用，多产品、订单预付款及跨期收益链未完整接入。最新状态及简化范围见[README](../README.md)，范围外机制不列当前修复任务。')
save('模型说明/README.md', model_index)

# 自检只核验文档变化；不导入或重跑任何业务模型。
after = {name: digest(ROOT / name) for name in texts}
changed_protected = [name for name, sha in protected.items() if digest(ROOT / name) != sha]
assert not changed_protected, changed_protected
missing = []
anchors_missing = []
for name, content in texts.items():
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
        if target.startswith(('https:', 'http:', 'codex:', '#')):
            continue
        raw_path, _, anchor = target.partition('#')
        raw_path = re.sub(r':\d+$', '', raw_path)
        path = Path(raw_path) if re.match(r'^[A-Za-z]:/', raw_path) else (ROOT / name).parent / raw_path
        if not path.exists():
            missing.append({'document': name, 'target': target})
        elif anchor and path.suffix == '.md':
            headings = re.findall(r'^#+\s+(.+)$', path.read_text(encoding='utf-8-sig'), re.M)
            slugs = [re.sub(r'[^\w\-\s]', '', h.lower()).replace(' ', '-') for h in headings]
            if anchor not in slugs:
                anchors_missing.append({'document': name, 'target': target})
assert not missing, missing
assert not anchors_missing, anchors_missing
assert '195/750' in texts['README.md'] and '剩余555' in texts['README.md']
assert 'PRACTICE2_COMPONENTS_TRAINED_MIGRATION_BLOCKED' in read('output/t2v0-um/20261012T181028387320+0800/report.md')
assert '| 20 |' in texts['建模重审与验收要求.md']
assert all(f'| {i} |' in texts['建模重审与验收要求.md'] for i in range(1, 21))
assert 'min{需求预估数量，产量}' in texts['README.md']
assert '## 4. 正式6终局分支' in texts['每回合结束后工作清单.md']
record = {'time': NOW.isoformat(), 'scope': '维护文档；历史正文/模型参数保留',
          'before': before, 'after': after, 'protected_count': len(protected),
          'protected_changed': changed_protected, 'missing_links': missing,
          'missing_anchors': anchors_missing, 'status': 'PASS',
          'not_checked': ['实时页面', '模型重训及完整算法验收', 'Word/PDF同步', '未修改的历史文档链接']}
(OUT / 'verification.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'protected_manifest.json').write_text(json.dumps(protected, ensure_ascii=False, indent=2), encoding='utf-8')
with LOG.open('a', encoding='utf-8') as f:
    f.write(f'\n完成：{datetime.now(timezone(timedelta(hours=8))).isoformat()}。\n\n整理{texts.__len__()}份Markdown：README集中状态及问题；任务说明按流程合并要求；重审细则独立；参数/回合/操作文档调整结构；历史报告加版本边界。旧README的索引、对话及阶段成果转入history，改前字节快照在before。\n\n验收：修改文档的本地文件链接及标题锚点通过，20项编号完整；{len(protected)}份既有原件、业务代码及历史文件哈希不变。完整清单见verification.json；不修改现有未提交业务改动。\n\n未做：实时页面核验、模型训练/修复、Word/PDF同步、Git提交。状态更新只据已有归档，不声称算法缺口已解决。\n')
print(json.dumps({'output': str(OUT), 'documents': len(texts), 'protected_files': len(protected), 'status': 'PASS'}, ensure_ascii=False))
