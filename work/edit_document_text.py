"""One-time editorial pass; preserve a pre-edit copy and verify technical content."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output' / 'text_edit' / STAMP
OUT.mkdir(parents=True, exist_ok=False)
FILES = sorted(ROOT.glob('*.md')) + sorted((ROOT / 'code').rglob('*.md'))
BEFORE = {p: p.read_text(encoding='utf-8-sig') for p in FILES}
SOURCE = ROOT / 'code' / 'summarize_model_parameters.py'
BEFORE[SOURCE] = SOURCE.read_text(encoding='utf-8-sig')

def sha(data):
    return hashlib.sha256(data).hexdigest()

for p in BEFORE:
    dest = OUT / 'before' / p.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(p.read_bytes())

protected = [p for folder in ('raw', 'sources', 'quarantine', 'history')
             for p in (ROOT / folder).rglob('*') if p.is_file()]
protected += list(ROOT.glob('*.json')) + list(ROOT.glob('*.csv')) + list(ROOT.glob('*.docx'))
protected_hashes = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in protected}
(OUT / 'work_log.md').write_text(
    '# 说明文档文字整理\n\n'
    f'开始：{STAMP}（北京时间）。用户指定 README 等自行编写的说明文档。\n\n'
    '范围：根目录 Markdown、code 内说明和历史生成模板；同步参数汇总生成器的开篇文字。'
    '合并重复要求、调整段落与导航，不重训模型，不修改网页。历史归档与原件保留。'
    '编辑前副本保存于 before/，已有未提交内容一并保留。\n\n状态：进行中。\n',
    encoding='utf-8')

def replace_once(text, old, new):
    assert text.count(old) == 1, old[:100]
    return text.replace(old, new, 1)

def split_long_paragraphs(text):
    """Split prose only; never alter fenced code, tables, lists or formulas."""
    result = []
    fenced = False
    for line in text.splitlines():
        if line.startswith('```'):
            fenced = not fenced
        if not fenced and len(line) > 260 and not line.startswith(('#', '|', '-', '*')) and not re.match(r'\d+\.', line):
            # A sentence may contain a code span or link, so split only outside both.
            ticks = 0
            bracket = 0
            pieces = []
            start = 0
            for i, ch in enumerate(line):
                if ch == '`':
                    ticks ^= 1
                if not ticks:
                    if ch == '[':
                        bracket += 1
                    elif ch == ']':
                        bracket = max(0, bracket - 1)
                    if ch == '。' and not bracket and i - start >= 110 and len(line) - i > 65:
                        pieces.append(line[start:i + 1])
                        start = i + 1
            pieces.append(line[start:])
            result.append('\n\n'.join(pieces))
        else:
            result.append(line)
    return '\n'.join(result).rstrip() + '\n'

texts = dict(BEFORE)

# Put each document title before its navigation note.
nav = '项目总入口：[README](README.md)。本页保留专题证据，当前总进展与待办以README及最新归档为准。\n\n'
for p in FILES:
    text = texts[p]
    if text.startswith(nav):
        title, body = text[len(nav):].split('\n', 1)
        texts[p] = title + '\n\n现行状态与待办见[README](README.md)；本文结论按所列版本和来源使用。\n' + body

p = ROOT / 'README.md'
text = texts[p]
sections = re.split(r'(?m)(?=^## )', text)
head = sections.pop(0)
mapping = {s.splitlines()[0][3:]: s for s in sections}
assert len(mapping) == len(sections)

navigation = mapping['项目导航（2026-10-12）']
navigation = replace_once(navigation,
    '本次整理建立导航，保留固定路径、原件、历史快照和已有未提交修改。当前结论按下方带日期的入口查看；历史记录不自动代表当前模型已通过验收。',
    '阅读顺序：最新状态与待办 → 执行要求 → 回合流程 → 专题文档与代码。历史结果集中在文末，按归档日期使用。')
current = mapping['20项问题最新核验（2026-10-12）']
# Detailed outlook and curve requirements have one maintained home.
start = current.index('当前回合前景优先（2026-10-12）')
current = current[:start] + '''### 当期前景与曲线

每回合行动前核验需求、大客户订单、生产、货币和财务，并采集对应回合曲线。订单按投标、中标、交付和回款分别处理；JSON与SVG按原始点配对去重。定性信息不直接变成精确参数，缺项保留未知。详细口径见[执行要求](参数细化与六回合期限要求.md)与[图表读取方法](网页图表原始数据读取.md)。

页面内联 `Chart.create(...)` 的JSON可提供完整纵轴数据；生产计划页研发与运营各有200点，横轴标签仍取整。独立结果见[回合2拟合结果](output/visible_coefficients/20261012_round2_json/拟合报告.md)和[工作日志](output/visible_coefficients/20261012_round2_json/工作日志.md)。整体需求模型的逐回合版本选择及五部分完整接入仍待核验。

'''

logs = mapping['工作日志要求（2026-10-11用户新增）']
logs = logs.replace('## 工作日志要求（2026-10-11用户新增）', '## 日志、交付与姓名规则', 1)
logs = replace_once(logs,
    '本次进行中日志：[正式2更新日志01](output/formal_update/20261011_work_log_01.md)。已采集全部10市场正式1实际；正式2初值使用正式1期末，保留正式1前景未来信号，模型与最终HTML验收状态以追加日志为准。下方历史“当前进展”及未取得正式结果的叙述保留为当时记录，不作为本次新基准。',
    '正式2更新过程见[日志01](output/formal_update/20261011_work_log_01.md)，完成入口见下方版本记录；进度以追加验收为准。')
logs = logs.replace('用户界面偏好（2026-10-11）：', '### 交付偏好\n\n', 1)
logs = logs.replace('**姓名规则与固定提示（2026-10-11）：', '### 姓名规则与固定提示\n\n**', 1)

rules = mapping['已有要求与操作边界']
rules = replace_once(rules,
    '用户补充规则（2026-10-11）：同一小组成员各自修改自己的个人列，不影响我的个人决策输入及预算数据。个人试验以本人列、本人输入页和本人预算核验；其他成员自己的列变化不单独构成停止或样本无效的理由。本人列、所选区域或小组方案变化时须重新核验；同编号市场内不同小组的最终决策仍有竞争作用。此前因其他成员列变化而停止试验的记录保留为历史，不能据此认定个人数据被干扰。',
    '个人试验以本人列、输入页和预算核验。其他成员修改各自个人列不影响本人输入及预算，不单独构成停止试验或排除样本的理由；本人列、所选区域或小组方案变化时重新核验。同编号市场内各组的最终决策仍有竞争作用。此规则以用户2026-10-11的更正为准。')
rules = rules.replace('以下综合本项目7个既有对话的要求，定位见末尾对话表及', '既有7个对话的要求汇总如下，来源见文末对话表及')
rules = rules.replace('11. **交付可阅读。** 说明只保留关键内容及来源关联，避免重复归档数表；Word公式使用可编辑内置公式，中文宋体、英文 Times New Roman。',
    '11. **交付可阅读。** 同一要求只在对应专题完整说明，其他入口保留摘要和链接；相关表达合并，每段围绕一个主题，按结论、依据、限制组织。完整数表留在JSON/CSV；Word公式可编辑，中文宋体、英文 Times New Roman。')

review = mapping['建模重审要求与执行顺序']
review = review.replace('图表和显示值逐项对照JSON，并实测筛选、导出、打印、宽/窄屏、标签截断及颜色辨识。',
    '图表和显示值逐项对照JSON，并实测桌面宽屏筛选、导出、打印、标签截断及颜色辨识；兼容性范围按上文交付偏好执行。')

flow = mapping['正式回合流程（2026-10-11用户确认）']
flow = flow.replace('## 正式回合流程（2026-10-11用户确认）', '## 正式回合流程与技术步骤', 1)
technical = mapping['标准流程']
technical = technical.replace('## 标准流程\n\n以下是上述正式回合流程中归档、建模、验证及个人区核验的技术执行步骤；小组协商、截止结算与跨回合结转按上一节执行。',
    '### 归档、建模与个人区核验\n\n下表细化上面的建模和个人试验阶段；结算后的归档、评分与状态结转按[每回合结束后工作清单](每回合结束后工作清单.md)执行。', 1)
# Keep the technical steps within the lifecycle section, with one end-of-round entry.
flow += technical
flow += mapping['每回合结束后的独立流程（2026-10-12新增）'].replace(
    '## 每回合结束后的独立流程（2026-10-12新增）', '### 结算后的复盘与交接', 1)

read_first = mapping['先读什么']
read_first = read_first.replace('## 先读什么', '### 专题阅读与资料定位', 1)
index = mapping['文档、数据与代码索引'] + read_first
index = index.replace('目录用途：raw 保存网页快照及截图，raw/cross_market 保存跨市场原件；sources 保存PDF与用户截图；quarantine 保存错配采集，不用于拟合；code 保存实现；output 保存专题结果及Word预览；history 保留旧说明和本次整理前备份。',
    '目录职责及保存约定见[项目结构](项目结构.md)。')

next_steps = mapping['下一步与未完成项'].replace('## 下一步与未完成项', '## 后续工作与历史候选', 1)
next_steps = next_steps.replace('1. 进入任何新操作前',
    '最新未解决问题以上文20项核验为准；以下列出延续任务和历史候选，进入依赖阶段前仍须通过相应验收。\n\n1. 进入任何新操作前', 1)
historical_names = [
    '正式2更新完成入口（2026-10-11）', '参数优先级处理结果（2026-10-11）',
    '运营延续ρ独立分析（2026-10-11新增）', '分国家独立需求模型（2026-10-11新增）',
    '练习2背景补档与情境重审（2026-10-11新增）', '当前进展']
historical = '## 历史版本与阶段结果\n\n以下记录保留各次运行的结论及限制；“当前”“尚未取得”等表述对应当时截止点。现行状态以上文最新核验及独立版本为准。\n\n'
for name in historical_names:
    s = mapping[name]
    s = s.replace('## ' + name, '### ' + ('归档进展（2026-10-11）' if name == '当前进展' else name), 1)
    if name == '当前进展':
        s = s.replace('### 模型范围与关键澄清', '#### 该批次模型范围与关键澄清', 1)
    # This overview sentence repeats the goal and an obsolete status.
    s = s.replace('更新：2026-10-11（北京时间）。本项目保存 Cesim 规则、原始资料、Python 模型、核验及决策研究。目标是尽可能最大化**正式6结束时的累计收益**。当前完成归档、分步模型与条件验证，尚未完成六回合联合优化或正式实际结果检验。\n\n', '')
    historical += s
texts[p] = (head + '目标：尽可能最大化正式6结束时的累计收益。项目保存规则、原始资料、Python模型及核验；六回合联合优化尚未完成。\n\n'
            + navigation + current + mapping['unified-market假设独立版本（2026-10-12）']
            + next_steps + rules + logs + mapping['参数细化与六回合期限（2026-10-11用户新增要求）']
            + flow + review + index + mapping['复现与版本管理'] + mapping['对话目录'] + historical)
assert len(sections) == 21, len(sections)

# Move the finite objective before parameter details, keeping dated results together.
p = ROOT / '参数细化与六回合期限要求.md'
text = texts[p]
old_note = '更新：2026-10-11（北京时间）。来源：用户要求先记录未细化参数，并明确整个流程只有正式6回合，长期估算须按此调整。\n\n'
text = replace_once(text, old_note, '')
parts = re.split(r'(?m)(?=^## )', text)
param = {s.splitlines()[0][3:]: s for s in parts[1:]}
texts[p] = parts[0] + '规范整理：2026-10-12（北京时间）。六回合期限来自用户2026-10-11要求，前景、利率及曲线规则补充于2026-10-12。\n\n' + param['有限期限目标'] + ''.join(
    param[s.splitlines()[0][3:]] for s in parts[1:] if not s.startswith('## 有限期限目标'))

p = ROOT / 'Cesim_任务要求与当前情况说明.md'
texts[p] = texts[p].replace('## 当前关键状态', '## 归档时的网页状态（2026-10-11）', 1)
texts[p] = replace_once(texts[p],
    '- 固定提示：项目文档及输出不得出现个人真名，统一使用大写姓名首字母；新增、更新、展示及导出前检查。完整口径以README的“姓名规则与固定提示”为准。',
    '- 姓名与交付：人员统一用大写首字母，新增、展示和导出前检查；文字合并重复表达，按主题分段。完整口径见README的姓名规则与交付要求。')
texts[p] = replace_once(texts[p],
    '用户2026-10-11新增要求：整个流程仅正式6回合，先记录待细化参数，长期投入和融资估算按剩余回合调整；执行口径见[参数细化与六回合期限要求](参数细化与六回合期限要求.md)。不得计入正式7以后的收益或未经证实的终值，期末资产、债务及其他状态按真实计分规则处理。',
    '长期投入和融资按剩余正式回合比较，终止于正式6；期末状态按真实计分规则处理，不加入未经证实的终值。具体口径见[参数细化与六回合期限要求](参数细化与六回合期限要求.md)。')
texts[p] = texts[p].replace('## 下一阶段', '## 延续任务与验收', 1)
texts[p] = texts[p].replace('## 跨市场验证进展', '## 跨市场验证记录（2026-10-11）', 1)

p = ROOT / '每回合结束后工作清单.md'
texts[p] = replace_once(texts[p],
    '每次执行先在`output/round_close/<北京时间时间戳>/`排他创建工作日志，记录课程、市场、阶段、回合、团队、采集时间、授权范围和进行中状态。完成时追加验收；旧日志、证据和模型不覆盖。不要输出真名，姓名统一用首字母替代。',
    '执行记录放在`output/round_close/<北京时间时间戳>/`：开始时排他创建日志，记录身份、回合、来源时间和授权范围，完成时追加验收。日志、姓名和历史保留规则见[项目总览](README.md)。')
texts[p] = texts[p].replace('## 每回合最小交付包与交接门槛', '## 交付包与进入下一阶段的条件', 1)

p = ROOT / '项目结构.md'
texts[p] = texts[p].replace('这是现有项目的导航，不改变模型版本或数据口径。不要输出真名，姓名统一用首字母替代。',
    '本文说明目录职责和保存位置；模型状态及姓名规则见[README](README.md)。')
texts[p] = texts[p].replace('原始资料、网页快照和历史副本可能含姓名，分享只选已脱敏交付文件。详细边界以 README 的姓名规则为准。',
    '分享范围按 README 姓名规则检查，只选已脱敏交付文件；原件和历史副本保留。')

p = ROOT / '网页图表原始数据读取.md'
texts[p] = texts[p].replace('## 每回合重新拟合与同回合配对（2026-10-12用户新增）',
    '整理：2026-10-12。本文说明图表采集、点配对与拟合；逐回合使用规则见[参数要求](参数细化与六回合期限要求.md)。\n\n## 版本与点配对', 1)
texts[p] = replace_once(texts[p],
    '每回合曲线可能随情境变化，每回合重新采集并使用对应的新拟合参数。按市场、阶段、回合、情境和对象保存版本；缺少本回合数据时明确缺口，不静默沿用旧参数。历史训练匹配当时曲线，未来尚不可见的曲线仅作为情景假设；完整规则见[参数要求](参数细化与六回合期限要求.md)。',
    '每回合重新采集与拟合，版本标明市场、阶段、回合、情境和对象。历史训练匹配历史曲线；本回合缺失时记录缺口，未来曲线仅作为显式情景。')
texts[p] = texts[p].replace('不要输出真名，姓名统一用首字母替代。原始证据保留于raw，交付报告只包含所需图表数值。',
    '原始证据保留于raw，交付仅选所需图表数值；姓名处理按[README](README.md)执行。')
texts[p] = texts[p].replace('本次来源：[回合2图表JSON]', '### 来源与复现\n\n本次来源：[回合2图表JSON]', 1)

p = ROOT / '练习与正式_已知数据差异.md'
text = texts[p]
start = text.index('2026-10-11新增第7张用户截图')
end = text.index('## 结论与比较边界')
intro = text[start:end]
first, second = intro.strip().split('\n\n')
text = text[:start] + '归档：2026-10-11（北京时间）。本文比较练习2资料与当时已归档的正式1；后续正式2资料不在本批核验范围。\n\n## 截图批次与身份边界\n\n' + second.replace('归档日期：2026-10-11（北京时间）。', '').replace('正式比较对象是已归档的正式回合1，不是尚无资料的正式回合2。', '') + '\n\n' + first + '\n\n' + text[end:]
texts[p] = text.replace('正式2未归档，因此无法回答练习2与正式2是否相同；隐藏需求机制是否相同仍未确定。',
    '本批资料无法判断练习2与正式2是否相同，隐藏需求机制也仍未确定。')

p = ROOT / '原生键盘标准操作.md'
texts[p] = texts[p].replace('全选四步之间不要切换标签页或点击其他控件。', '上述四步之间保持同一标签页和控件焦点。')
texts[p] = texts[p].replace('只有上述核验完成，才标记“已保存”。调用未报错或输入框显示新值都不够。若是临时试验，结束后按同样步骤恢复',
    '输入框、个人列与重入回读一致，才标记“已保存”。\n\n临时试验结束后按同样步骤恢复')

p = ROOT / '建模与回算报告.md'
texts[p] = texts[p].replace('实际、预算、玩家预测及失败扰动分类型。历史区段的团队顺序一致，营销团队小组策略与实际报告配对通过；个人草稿不作执行策略。',
    '输入按实际、预算、玩家预测和失败扰动分类；历史团队顺序及营销团队策略—实际配对均通过核验，个人草稿不作执行策略。')

p = ROOT / '模型迁移与预估验证.md'
texts[p] = texts[p].replace('## 两类检验\n\n### 当前跨市场假设与对数模型', '## 跨市场假设与对数模型', 1)
texts[p] = texts[p].replace('**预算校准：** 固定', '## 预算校准与需求迁移\n\n**预算校准：** 固定', 1)
texts[p] = texts[p].replace('正式实际数据尚未归档，暂不能完成迁移检验。', '本批次尚未归档正式实际，迁移检验需另行完成。')

p = ROOT / '需求拟合报告.md'
texts[p] = texts[p].replace('下一阶段第1项已完成首版离线拟合、团队/回合留出及敏感性分析。模型具有初步预测价值，仍为探索模型，不能据此直接优化国别营销或宣称正式六回合最优。',
    '本批次完成首版离线拟合、团队/回合留出和敏感性分析。结果支持继续验证，国别营销优化及正式六回合最优仍未完成。')
texts[p] = texts[p].replace('下一步按[验证方案]', '后续预算校准与迁移检验按[验证方案]', 1)

p = ROOT / '正式1分步建模报告.md'
texts[p] = texts[p].replace('已读取引用聊天的隐藏函数分析，并实时确认', '本次归档时已读取引用聊天的隐藏函数分析，并确认', 1)
texts[p] = texts[p].replace('### 当前各项预测的情景值', '### 归档输入对应的预测情景', 1)
texts[p] = texts[p].replace('## 当前正式1预算的独立回算', '## 正式1归档预算的独立回算', 1)

p = ROOT / '预测模型与变量说明.md'
texts[p] = texts[p].replace('2026-10-11新增独立模型', '## 新增国别分支与版本边界\n\n2026-10-11新增独立模型', 1)
texts[p] = texts[p].replace('区分当前预测、对照模型、历史模型及尚未识别的分支。新增分国家模型已单独拟合，没有覆盖旧冻结参数或修改网页决策。',
    '下文“当前”指本次核对版本；预测、对照、历史模型和未识别分支分别说明。新增国别模型独立保存。')

# Match the opening structure in the generated summary and its source template.
for p in (ROOT / '预测模型与训练参数汇总.md', SOURCE):
    text = texts[p]
    text = text.replace('本文覆盖已有模型类型、主拟合/冻结/情境模型及明确保留的对照、消融与敏感性参数。',
        '## 阅读范围与口径\n\n本文汇集主拟合、冻结和情境模型，以及对照、消融和敏感性参数。', 1)
    text = text.replace('具体系数另见第14项来源，不能作为一套部署参数拼接。',
        '具体系数见第14项来源，不拼接为部署参数。', 1)
    texts[p] = text

p = ROOT / 'code' / 'README.md'
texts[p] = texts[p].replace('更新：2026-10-12。维护源代码在本目录，历史运行副本在 `output/`；固定路径保持不变。项目数据及报告导航见[项目结构](../项目结构.md)。',
    '更新：2026-10-12。按下表选择维护入口；历史运行副本在 `output/`，项目数据和报告见[项目结构](../项目结构.md)。')
texts[p] = texts[p].replace('## 依赖与复现注意', '## 运行前检查：依赖、路径与写入', 1)

p = ROOT / 'code' / 'model_v2' / 'README.md'
texts[p] = texts[p].replace('运行全部离线检查：', '## 运行与输出\n\n运行全部离线检查：', 1)
texts[p] = texts[p].replace('需求按可核验前景情境单独拟合。', '## 适用范围与验收状态\n\n需求按可核验前景情境单独拟合。', 1)
texts[p] = texts[p].replace('`--stage` 可选', '## 阶段选择与个人试验\n\n`--stage` 可选', 1)

p = ROOT / 'code' / '要求说明_模板.md'
text = texts[p]
prefix, rest = text.split('# Cesim任务要求与当前情况说明\n\n', 1)
text = '# Cesim任务要求与当前情况说明\n\n' + prefix.strip() + '\n\n' + rest
text = replace_once(text,
    '生成时间：{{time}}。状态：**按用户要求暂停**。本文件是任务交接与核验说明，不是已经求得的最优决策方案。\n\n用户最新要求为“剩余归档先暂停，把任务加入说明文档中后续进行”。因此停止剩余网页采集，只整理已经保存的材料、执行离线计算、保存代码与说明。当前未修改网页决策字段，未导入其他成员决策，未保存为小组正式决策。恢复执行需用户后续明确指示。',
    '生成时间：{{time}}。本模板对应历史暂停阶段，用于交接和核验，尚无最优方案。\n\n**该阶段按用户要求暂停剩余归档及后续执行。** 只整理已保存材料、完成离线计算并保存代码与说明；未修改网页字段、导入成员决策或保存小组方案。恢复须有用户后续明确指示，现行状态以README为准。')
text = text.replace('| 最新暂停 | 剩余归档、模型拟合、搜索优化、填入与小组提交全部列为待办，不自动继续 |',
    '| 暂停后的待办 | 剩余归档、拟合、搜索优化及填写见第9节；小组提交须另行协调 |')
text = text.replace('本说明第4—5节网页数值和计算可在上述原件与`计算核验.csv`交叉核验。',
    '文字按结论、依据和限制组织：合并同义要求，每段只说明一个主题，完整数表保留在来源文件。\n\n本说明第4—5节网页数值和计算可在上述原件与`计算核验.csv`交叉核验。')
texts[p] = text

def code_blocks(text):
    return Counter(re.findall(r'(?ms)^```[^\n]*\n.*?^```', text))

def table_rows(text):
    return Counter(line for line in text.splitlines() if line.startswith('|'))

def links(text):
    return set(re.findall(r'\]\(([^\n]+?)\)', text))

checks = []
for p in FILES:
    texts[p] = split_long_paragraphs(texts[p])
    assert code_blocks(BEFORE[p]) == code_blocks(texts[p]), ('code changed', p)
    # The sole table change is a shorter historical pause reference.
    before_rows, after_rows = table_rows(BEFORE[p]), table_rows(texts[p])
    if p.name != '要求说明_模板.md':
        assert before_rows == after_rows, ('table changed', p)
    assert links(BEFORE[p]) <= links(texts[p]), ('link removed', p, links(BEFORE[p]) - links(texts[p]))
    assert texts[p].count('```') % 2 == 0, p
    assert texts[p].startswith('# '), p
    if p.name == '要求说明_模板.md':
        assert Counter(re.findall(r'\{\{\w+\}\}', BEFORE[p])) == Counter(re.findall(r'\{\{\w+\}\}', texts[p]))
    checks.append({'path': str(p.relative_to(ROOT)), 'before_chars': len(BEFORE[p]),
                   'after_chars': len(texts[p]), 'code_blocks_unchanged': True,
                   'tables_unchanged': before_rows == after_rows, 'original_link_targets_retained': True})

assert '## 阅读范围与口径' in texts[SOURCE]
compile(texts[SOURCE], str(SOURCE), 'exec')
for p, text in texts.items():
    original_bytes = (OUT / 'before' / p.relative_to(ROOT)).read_bytes()
    original_newline = '\r\n' if original_bytes.count(b'\r\n') > original_bytes.count(b'\n') / 2 else '\n'
    with p.open('w', encoding='utf-8', newline=original_newline) as stream:
        stream.write(text)
assert all(sha((ROOT / rel).read_bytes()) == digest for rel, digest in protected_hashes.items())

manifest = {str(p.relative_to(ROOT)): {'before_sha256': sha((OUT / 'before' / p.relative_to(ROOT)).read_bytes()),
                                      'after_sha256': sha(p.read_bytes())} for p in texts}
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'verification.json').write_text(json.dumps({'documents': checks, 'generator_syntax_valid': True,
    'protected_file_count': len(protected_hashes), 'protected_files_unchanged': True,
    'note': '文字检查通过；未运行模型训练、网页操作或Word导出。'}, ensure_ascii=False, indent=2), encoding='utf-8')
with (OUT / 'work_log.md').open('a', encoding='utf-8') as stream:
    stream.write(f'\n完成：整理{len(FILES)}份说明文档，并同步参数汇总生成器开篇。'
                 f'代码块、技术数表、原链接目标和模板占位符检查通过；{len(protected_hashes)}份原件/历史/结构化数据/Word未改。'
                 '仅历史模板的暂停表格行改为章节引用。已有未提交修改保留在编辑前副本。\n')
print(json.dumps({'output': str(OUT), 'documents': len(FILES), 'protected': len(protected_hashes),
                  'before_chars': sum(len(BEFORE[p]) for p in FILES),
                  'after_chars': sum(len(texts[p]) for p in FILES)}, ensure_ascii=False))
