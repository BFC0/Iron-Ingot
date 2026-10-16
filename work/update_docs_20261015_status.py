from pathlib import Path
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output/text_cleanup' / (stamp + '_status_sync')
OUT.mkdir(parents=True, exist_ok=False)
log = OUT / 'work_log.md'
log.write_text('# 说明文档状态同步\n\n北京时间：' + stamp + '\n\n用户授权：更新说明文档信息。范围为当前状态、版本导航、公式适用范围和目录职责；依据已有正式5结算、正式6初值及t5v1—t5v3交付证据，不访问平台、不重训、不改代码或冻结产物。保留磁盘已有未提交内容。不要输出真名，姓名统一用首字母替代。\n\n状态：进行中；先备份，后修改并验收。\n', encoding='utf-8')
files = ['README.md', 'code/README.md', 'code/model_v2/README.md', '模型说明/README.md', '模型版本重新统计.md', '训练拟合模型与版本清单.md', '训练拟合模型与版本清单_文字说明版.md', '预测模型与训练参数汇总.md', '预测模型与变量说明.md', '模型说明/完整计算流程图.md', '项目结构.md']
before = {f: (ROOT / f).read_bytes() for f in files}
texts = {f: b.decode('utf-8-sig').replace('\r\n', '\n') for f, b in before.items()}
for f, b in before.items():
    dest = OUT / 'before' / f
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b)
hashes_before = {f: sha256(b).hexdigest() for f, b in before.items()}
(OUT / 'before_hashes.json').write_text(json.dumps(hashes_before, ensure_ascii=False, indent=2), encoding='utf-8')

def replace(f, old, new):
    assert texts[f].count(old) == 1, (f, old[:70], texts[f].count(old))
    texts[f] = texts[f].replace(old, new, 1)

rows = '''| 正式5营销代理训练与条件应用 | [t5v1](output/t5v1/20261015T171355804/report.md)、[运行说明](code/model_v2/t5v1_README.md) | 正式4营销合计费用代理重估并接入正式5重要性；细分营销未识别，其余组件继承t5v0b，不是全套重新训练。 |
| 有效投资映射与条件优化 | [t5v2](output/t5v2/20261015_effective_investment/report.md)、[运行说明](code/model_v2/t5v2_README.md) | 正式5投入映射接入需求、效率与财务计算；正式6迁移仍属情景，完整全参数最优未验证。 |
| 统一对手默认价格需求情景 | [t5v3](output/t5v3/20261015_common_default_prices/report.md)、[运行说明](code/model_v2/t5v3_README.md) | 冻结t5v2系数，九队统一采用本组正式5期初默认价格，逐队重算并归一化份额；无新训练、无新版优化，精度增益未验证。 |
'''
for f in ['训练拟合模型与版本清单.md', '训练拟合模型与版本清单_文字说明版.md', '预测模型与训练参数汇总.md']:
    replace(f, '| 分类 | 当前证据 | 口径 |\n| --- | --- | --- |\n', '| 分类 | 当前证据 | 口径 |\n| --- | --- | --- |\n' + rows)
    texts[f] = texts[f].replace('正式4最新实际训练（有缺口）', '正式4成本与风险训练（有缺口）')
replace('模型版本重新统计.md', '| --- | --- | --- |\n', '| --- | --- | --- |\n' + rows)
replace('模型版本重新统计.md', '最新实际训练（有缺口）', '正式4成本与风险训练（有缺口）')

replace('模型说明/README.md', '## 当前模型和应用入口\n\n', '''## 当前模型和应用入口

| 类别 | 入口与适用范围 |
| --- | --- |
| 最新需求竞争情景 | [t5v3](../code/model_v2/t5v3_README.md)：正式5九队统一默认价格，冻结t5v2系数；未重做优化，未验证精度增益。 |
| 最近条件优化 | [t5v2](../code/model_v2/t5v2_README.md)：正式5有效投资映射接入需求、效率及财务链；正式6迁移仍为情景。 |
| 营销代理训练与前一应用 | [t5v1](../code/model_v2/t5v1_README.md)：正式4营销合计费用代理重估，细分响应未识别，其余组件继承t5v0b。 |

以上均按正式5历史用途查阅；正式6新增菲律宾需求及印尼投资尚未完成模型适配，当前回合与待办见[项目总览](../README.md)。t5v2两期候选不能直接作为t5v3或正式6推荐。

''')
replace('code/README.md', '| 工作 | 维护入口 | 输出与限制 |\n| --- | --- | --- |\n', '''| 工作 | 维护入口 | 输出与限制 |
| --- | --- | --- |
| 正式5统一对手价格情景 | [t5v3](model_v2/t5v3_README.md) | 逐队重算需求份额，冻结t5v2系数；无新版优化，正式6默认拒绝外推 |
| 正式5有效投资映射 | [t5v2](model_v2/t5v2_README.md) | 独立条件应用及验收；正式6迁移仍为显式假设 |
| 正式4营销代理重估与正式5应用 | [t5v1](model_v2/t5v1_README.md) | 两类营销合计响应，细分未识别；不是完整全参数最优 |
''')
replace('code/model_v2/README.md', '## 当前工作入口\n\n', '## 当前工作入口\n\n以下t5版本按正式5历史训练或情景用途保存；当前正式6的新增菲律宾需求、印尼投资及终局规则仍需适配，不能直接复用42项旧推荐。当前回合和证据见[项目总览](../../README.md)。\n\n')

replace('预测模型与变量说明.md', '最新实际训练为[t5v0]', '正式4成本、工资与风险训练基线为[t5v0]')
replace('预测模型与变量说明.md', '需求主分支保持SHARE', '''后续应用按组件区分：[t5v1](code/model_v2/t5v1_README.md)重估正式4营销合计费用代理并接入正式5重要性；[t5v2](code/model_v2/t5v2_README.md)接入正式5投入→有效投资映射，研发采用0.75×当期＋0.50×上期，运营采用当期＋0.35×上期。该映射来自正式5网页区间试验，历史截距、更早存量和正式6迁移仍有假设，不推广为全回合规则。

[t5v3](code/model_v2/t5v3_README.md)冻结t5v2系数，令其他九队采用本组正式5期初默认价格（复合梁泰国1860／印尼2180、连接件泰国36／印尼32美元/单位），以正式4真实需求份额为锚点逐队重估吸引力，再在十队内归一化。对手非价格行为冻结属于分析假设；没有重新优化，也未验证实际精度增益。旧t5v2利润和建议不能标为t5v3结果，正式6默认拒绝外推。

需求主分支保持SHARE''')
replace('预测模型与变量说明.md', '尚未同步本次t5v0及正式5文档更新', '尚未同步本次t5v1—t5v3及正式6适用边界更新')

replace('模型说明/完整计算流程图.md', '  COST --> LIMIT[完整正式5至6财务及状态链未通过]', '''  COST --> LIMIT[完整正式5至6财务及状态链未通过]
  T5 --> V0B[t5v0a及t5v0b 正式5公布条件与需求情景]
  M4[正式4营销合计费用代理] --> V1[t5v1 营销响应重估与正式5条件优化]
  V0B --> V1
  V1 --> V2[t5v2 正式5有效投资映射与条件优化]
  C5 --> V2
  V2 --> V3[t5v3 九队统一默认价格与份额归一化]
  V3 --> V3L[无新训练 无新版优化 精度增益未验证]
  R5ACT[正式5已结算实际与最终42字段] --> PAIR[先匹配冻结候选 不同方案不直接计事前成绩]
  R6[正式6已归档56字段 48参数 600点曲线] --> GAP6[菲律宾需求 印尼投资 15项独立期初状态待核]
  GAP6 --> END6[仅评价正式6新增收益 按终局处理 不创建正式7预测]''')
replace('模型说明/完整计算流程图.md', 't5v0及正式5曲线的来源与状态见', 't5v1—t5v3接口与边界见[模型索引](README.md)，正式5配对及正式6适配状态见[项目总览](../README.md)。t5v0及正式5曲线的来源与状态见')

replace('项目结构.md', '| 同期市场共享假设版本 |', '''| 正式5结算与正式6初值 | [采集总览](output/round_close/20261015_formal5_close/overall_report.md)、[正式6初值](output/round_close/20261015_formal5_close/formal6_initial/report.md)；新增国家及投资字段需适配，15项独立期初状态仍缺 |
| 正式5后续应用与竞争情景 | [t5v1](code/model_v2/t5v1_README.md)、[t5v2](code/model_v2/t5v2_README.md)、[t5v3](code/model_v2/t5v3_README.md)；营销代理、有效投资、统一对手价分别保存，t5v3未重新优化 |
| 同期市场共享假设版本 |''')
replace('项目结构.md', '| `project_structure/` |', '''| `t5v0a/`、`t5v0b/`、`t5v1/`、`t5v2/`、`t5v3/` | 正式5条件应用和独立版本；模型、请求、代码快照与验收按版本查阅 |
| `formal5_marketing_r4/`、`effective_investment/`、`forecast_dependency_audit/` | 营销代理训练、投入映射试验与玩家预估依赖审计 |
| `formal5_two_policies_t5v2/`、`beam_indonesia_price/` | 正式5两期候选和定价诊断；历史结果不作为正式6推荐 |
| `project_structure/` |''')

replace('README.md', '| 最新条件优化版本 |', '| 最近条件优化版本（正式5历史） |')
replace('README.md', '| 最新实际训练（有缺口） |', '| 正式4成本与风险训练（有缺口） |')
replace('README.md', '正式4→5结转20项中5项已核或条件核验、15项未知', '正式5→6结转20项中两项库存和长期贷款参考匹配、两项机器产能条件相容，15项缺独立期初核验')
replace('README.md', '原176份预测/模型已冻结，但本组实际方案未采用候选，不能计为候选事前成绩', '原176份预测/模型历史冻结保留；正式5最终方案严格匹配中性候选39/42项，两项效率差异与显示舍入相容，另有一项营销金额不同，整套预测不能直接计为实际方案事前成绩')
record = (OUT / 'work_log.md').relative_to(ROOT).as_posix()
replace('README.md', '本次文档整理的改前内容、哈希、范围及验收见[整理记录](output/text_cleanup/20261015T0914153097102+0800_docs_now/work_log.md)；', f'本次说明同步的改前内容、哈希、范围及验收见[同步记录]({record})；[此前整理](output/text_cleanup/20261015T0914153097102+0800_docs_now/work_log.md)保留；')

def links(f, text):
    result = []
    for target in re.findall(r'\]\(([^)]+)\)', text):
        target = unquote(target.strip('<>'))
        if re.match(r'^[a-z]+://', target, re.I):
            continue
        base, _, anchor = target.partition('#')
        base = re.sub(r':\d+$', '', base)
        path = (ROOT / f).parent / base if base else ROOT / f
        result.append((target, path, anchor))
    return result

checks = {}
for f in files:
    assert (ROOT / f).read_bytes() == before[f], 'Concurrent change: ' + f
    assert texts[f] != before[f].decode('utf-8-sig').replace('\r\n', '\n'), f
    old_missing = {target for target, path, _ in links(f, before[f].decode('utf-8-sig')) if not path.exists()}
    missing = {target for target, path, _ in links(f, texts[f]) if not path.exists()}
    assert not (missing - old_missing), (f, missing - old_missing)
    checks[f] = {'backup_matches': sha256((OUT / 'before' / f).read_bytes()).hexdigest() == hashes_before[f], 'local_links_checked': len(links(f, texts[f])), 'preexisting_missing_links': sorted(old_missing), 'new_missing_links': sorted(missing - old_missing)}
    original = before[f]
    newline = '\r\n' if b'\r\n' in original else '\n'
    content = texts[f].replace('\n', newline).encode('utf-8')
    if original.startswith(b'\xef\xbb\xbf'):
        content = b'\xef\xbb\xbf' + content
    (ROOT / f).write_bytes(content)
    checks[f]['after_sha256'] = sha256(content).hexdigest()
assert all(c['backup_matches'] and not c['new_missing_links'] for c in checks.values())
assert '39/42' in texts['README.md'] and '正式5→6' in texts['README.md']
assert all('t5v3' in texts[f] for f in files)
(OUT / 'after_hashes.json').write_text(json.dumps({f: c['after_sha256'] for f, c in checks.items()}, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'verification.json').write_text(json.dumps({'status': 'PASS', 'changed_documents': len(files), 'checks': checks, 'scope': 'documentation only; evidence reused; no model or platform changes'}, ensure_ascii=False, indent=2), encoding='utf-8')
with log.open('a', encoding='utf-8') as stream:
    stream.write('\n完成：同步11份Markdown说明的版本入口与适用边界，更新正式5最终方案配对、正式5→6状态结转、正式6适配与终局提醒。任务要求和AGENTS规则已核对，无需改写。\n\n验收：11份修改前磁盘备份哈希一致，新增失效本地链接为0；已有缺失链接单列于[核验清单](verification.json)。[改前哈希](before_hashes.json)与[改后哈希](after_hashes.json)已保存；已有未提交修改保留。版本历史参数、历史误差及冻结结果未改。\n\n未完成项：Word未同步；未核实时平台或重跑模型，正式6适配及15项期初状态缺口不因本次说明更新关闭。\n')
print(json.dumps({'status': 'PASS', 'documents': len(files), 'record': record, 'preexisting_missing_links': {f: c['preexisting_missing_links'] for f, c in checks.items() if c['preexisting_missing_links']}}, ensure_ascii=False))
