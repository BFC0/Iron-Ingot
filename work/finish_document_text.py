"""Finish the editorial pass against its saved baseline, without rerunning models."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/text_edit/20261012T121238503973+0800'
manifest = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
docs = [ROOT / rel for rel in manifest if rel.endswith('.md')]
p = ROOT / 'README.md'
text = p.read_text(encoding='utf-8')
start = text.index('### 归档、建模与个人区核验\n')
end = text.index('### 结算后的复盘与交接\n', start)
text = text[:start] + '''### 建模和个人试验的交付要求

归档与结构化输入须保留原件、截图、来源、类别及缺口，并完成唯一键、源单元格、数量守恒和财务平衡检查。计算链依次为：行业规模 → 竞争份额与需求 → 效率、产能与用工 → 交付 → 收入与成本 → 利息、税、利润及现金。

回算、留出和敏感性分析分别报告预算误差与实际需求误差。个人单变量试验须成功保存、取得完整相关预算、恢复基准并重入核验；无效输入不作校准。推荐表逐字段列出当前值、建议值、公式或模型、来源、理由、约束与不利情景；恢复填写后保存前后快照，比较本地模型与平台预算。

单位统一为数量千单位、金额千美元、单位价格及运输费美元/单位；增长与利率内部使用小数，网页按百分数显示。

''' + text[end:]
start = text.index('### 专题阅读与资料定位\n')
end = text.index('## 复现与版本管理\n', start)
# All four navigation entries already occur in the project navigation and index.
section = text[start:end]
paragraph_start = section.index('说明文档只写关键要求')
text = text[:start] + section[paragraph_start:] + text[end:]
text = text.replace('## 复现与版本管理\n',
    '跨市场原始资料按[跨市场索引](output/cross_market/archive_index.json)定位。\n\n## 复现与版本管理\n', 1)
text = text.replace('### 结算后的复盘与交接\n\n[每回合结束后工作清单](每回合结束后工作清单.md)单列10项任务、产物及验收标准，包含状态结转重点、正式6终局分支和最小交付包。结果公布后先评分旧冻结预测，再更新模型；下一回合重新核验前景五部分与曲线版本。该清单是执行规范，自动流程和完整财务机制仍以核验结果为准。',
    '### 结算后的复盘与交接\n\n按[每回合结束后工作清单](每回合结束后工作清单.md)执行10项任务，交付状态对照、冻结评分、模型更新与验收；正式6进入终局分支。清单是执行规范，自动流程和完整财务机制仍须另行核验。')
texts = {p: p.read_text(encoding='utf-8') for p in docs}
texts[ROOT / 'README.md'] = text
source = ROOT / 'code/summarize_model_parameters.py'
texts[source] = source.read_text(encoding='utf-8')

checks = []
missing_before, missing_after = set(), set()
def local_targets(document, content):
    result = set()
    for target in re.findall(r'\]\(([^\n]+?)\)', content):
        target = target.split('#')[0].strip('<>')
        if not target or re.match(r'^(https?://|codex://|mailto:)', target):
            continue
        target = re.sub(r':\d+$', '', target)
        path = Path(target)
        if not path.is_absolute():
            path = document.parent / path
        if not path.exists():
            result.add(str(path))
    return result

for p, content in texts.items():
    rel = str(p.relative_to(ROOT))
    baseline = (OUT / 'before' / p.relative_to(ROOT)).read_text(encoding='utf-8-sig')
    blocks = lambda s: Counter(re.findall(r'(?ms)^```[^\n]*\n.*?^```', s))
    targets = lambda s: set(re.findall(r'\]\(([^\n]+?)\)', s))
    if p.suffix == '.md':
        assert blocks(baseline) == blocks(content), p
        assert targets(baseline) <= targets(content), (p, targets(baseline) - targets(content))
        before_tables = Counter(s for s in baseline.splitlines() if s.startswith('|'))
        after_tables = Counter(s for s in content.splitlines() if s.startswith('|'))
        if p.name not in ('README.md', '要求说明_模板.md'):
            assert before_tables == after_tables, p
        missing_before.update(local_targets(p, baseline))
        missing_after.update(local_targets(p, content))
        checks.append({'path': rel, 'before_chars': len(baseline), 'after_chars': len(content),
            'code_blocks_unchanged': True, 'original_link_targets_retained': True,
            'technical_tables_unchanged': before_tables == after_tables,
            'note': 'README流程表融合为段落；历史模板暂停行简化为章节引用。' if before_tables != after_tables else ''})
    else:
        compile(content, str(p), 'exec')
    original_bytes = (OUT / 'before' / p.relative_to(ROOT)).read_bytes()
    newline = '\r\n' if original_bytes.count(b'\r\n') > original_bytes.count(b'\n') / 2 else '\n'
    with p.open('w', encoding='utf-8', newline=newline) as stream:
        stream.write(content)
    manifest[rel]['after_sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()

assert not missing_after - missing_before, missing_after - missing_before
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
verification = json.loads((OUT / 'verification.json').read_text(encoding='utf-8'))
verification['documents'] = checks
verification['new_broken_local_links'] = []
verification['preexisting_missing_local_links'] = sorted(missing_before)
verification['line_endings_match_baseline'] = True
(OUT / 'verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding='utf-8')
with (OUT / 'work_log.md').open('a', encoding='utf-8') as stream:
    stream.write('\n复核：README中重复导航和技术流程表进一步融合为段落；技术公式、数表及代码块保留，来源链接未丢失，无新增失效本地链接。'
                 '文件换行恢复为各自编辑前格式；未重训或重新导出Word。\n')
failed = ROOT / 'output/text_edit/20261012T121223492604+0800/work_log.md'
with failed.open('a', encoding='utf-8') as stream:
    stream.write('\n执行更正：首次预检查把README二级章节数误记为22，实际为21；断言中止于写回前，没有修改项目说明。'
                 '已修正并在20261012T121238503973+0800目录完成，验收以该目录为准。\n')
print(json.dumps({'documents': len(docs), 'README_chars_before': next(x['before_chars'] for x in checks if x['path'] == 'README.md'),
    'README_chars_after': len(text), 'new_broken_local_links': 0, 'preexisting_missing_local_links': len(missing_before)}, ensure_ascii=False))
