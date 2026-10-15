from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
files = sorted(set(ROOT.glob('*.md')) | set((ROOT/'模型说明').glob('*.md')) | set((ROOT/'code').rglob('*.md')))
long_status = '最新实际训练为t4v1（正式3完整10市场、100队），去重清单29类；t4v1a为非重训应用情景版。历史公式、参数和误差保留各自范围，未部署，完整剩余回合收益未验证。'
for p in files:
    t = p.read_text(encoding='utf-8')
    t = t.replace(long_status, '历史公式、参数和误差保留各自版本范围；具体进展在所属主题维护。')
    p.write_text(t,encoding='utf-8')
p = ROOT/'预测模型与变量说明.md'
t = p.read_text(encoding='utf-8')
title = t.splitlines()[0]
start = t.index('## 当前模型与公式适用范围')
body = t[start:]
old_start = body.index('## 新增国别分支与版本边界')
current, historical = body[:old_start], body[old_start:]
historical = historical.replace('Word版尚未包含本新增分支。','本次Word版已同步此国别分支说明，其参数仍按历史版本使用。')
historical = historical.replace('当前','该历史版本').replace('已拟合值','历史拟合值')
historical = historical.replace('该历史版本部署候选','该历史版本候选（未部署）')
historical = historical.replace('## 新增国别分支与版本边界','## 历史国别分支与统一口径')
current = current.replace('O3+ρO2+ρ²O1','O₃+ρO₂+ρ²O₁')
intro = '更新：2026-10-14（北京时间）。本文先说明最新模型及应用边界，再按需求、投入响应、生产成本、财务与期限列出通用和历史公式。正文中的数值按所列历史版本解释，最新参数见[模型目录](模型说明/README.md)与[参数汇总](预测模型与训练参数汇总.md)。\n\n已知条件、可控决策、玩家预估、预算和模型输出分别分类；训练参数、假设参数、选参配置与评价指标分开记录。曲线近似及条件回算不能替代后续实际验证。'
headings = re.findall(r'^## (.+)$',current+historical,re.M)
toc = '**主题导航：** '+' · '.join('['+h+'](#'+re.sub(r'[^\w\- ]','',h.lower()).replace(' ','-')+')' for h in headings)
p.write_text(title+'\n\n'+intro+'\n\n'+toc+'\n\n'+current+historical,encoding='utf-8')

# Runbooks with only short narrative paragraphs now have named data/command/limit sections.
for rel in ['code/model_v2/t3v0_README.md','code/model_v2/t4v0_README.md','模型说明/T3V0_正式2重训及正式3附加曲线.md','模型说明/T4V0_正式3实际训练.md']:
    p = ROOT/rel
    t = p.read_text(encoding='utf-8')
    t = t.replace('最新训练目录：','本版本训练目录：')
    t = t.replace('权威注册表为','本版本注册表为')
    p.write_text(t,encoding='utf-8')
