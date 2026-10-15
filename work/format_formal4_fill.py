"""Reorder the saved decision report; preserve authoritative decision values."""
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/formal4_all/20261014T211634211494+0800'
REV = OUT / 'formatting' / datetime.now().astimezone().strftime('%Y%m%dT%H%M%S%f%z')
REV.mkdir(parents=True, exist_ok=False)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report = OUT / 'report.md'
sources = ['decisions.json', 'decisions.csv', 'joint_result.json', 'inputs.json']
before = {name: sha(OUT / name) for name in ['report.md', *sources]}
shutil.copy2(report, REV / 'report_before.md')
(REV / 'work_log.md').write_bytes('任务：修复表格空行，按平台子页和子类重排42项输入。范围：仅修改报告排版，保留候选数值与分析结论。\n'.encode())

data = json.loads((OUT / 'decisions.json').read_text(encoding='utf-8-sig'))
plans = list(dict.fromkeys(x['plan'] for x in data))
assert len(plans) == 2 and len(data) == 84
lookup = [{x['source_row']: x for x in data if x['plan'] == p} for p in plans]
groups = [
    ('1. 需求', [
        ('复合梁', [(65, '泰国市场增长预估'), (66, '印尼市场增长预估'), (58, '泰国需求预估'), (59, '印尼需求预估')]),
        ('连接件', [(68, '泰国市场增长预估'), (69, '印尼市场增长预估'), (61, '泰国需求预估'), (62, '印尼需求预估')])]),
    ('2. 生产 → 投资', [
        ('下一回合需求增长预估', [(72, '复合梁'), (73, '连接件')]),
        ('泰国机器投资', [(46, '复合梁'), (47, '连接件')])]),
    ('3. 生产 → 计划', [
        ('分包制造（列表附加项，保留关闭／未求解）', [(41, '分包制造')]),
        ('产能分配', [(42, '复合梁'), (43, '连接件')]),
        ('效率预估', [(76, '复合梁'), (77, '连接件')]),
        ('研发／质量管理', [(51, '复合梁'), (52, '连接件')]),
        ('运营改进', [(49, '泰国')])]),
    ('4. 销售 → 泰国', [
        ('复合梁', [(9, '每单位价格'), (18, '一般营销'), (25, '设计师营销')]),
        ('连接件', [(13, '每单位价格'), (21, '一般营销'), (29, '设计师营销')])]),
    ('5. 销售 → 印尼', [
        ('复合梁', [(10, '每单位价格'), (19, '一般营销'), (26, '设计师营销')]),
        ('连接件', [(14, '每单位价格'), (22, '一般营销'), (30, '设计师营销')])]),
    ('6. 销售 → 大客户订单（保留当前值／未求解）', [
        ('复合梁', [(11, '报价'), (27, '设计师营销')]),
        ('连接件', [(15, '报价'), (31, '设计师营销')])]),
    ('7. 物流', [
        ('复合梁', [(34, '泰国'), (35, '印尼')]),
        ('连接件', [(37, '泰国'), (38, '印尼')])]),
    ('8. 财务', [
        ('长期贷款', [(54, '长期贷款变化'), (79, '长期贷款利率预估')])]),
]
order = [i for _, subs in groups for _, rows in subs for i, _ in rows]
assert len(order) == len(set(order)) == 42
assert all(set(order) == set(items) for items in lookup)

def fmt(value):
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return str(value).replace('\xa0', '').replace('|', '\\|')

lines = ['## 按平台子页填写（42项）', '',
         '**两套候选二选一，全程使用同一列。** “中性收益优先”和“不利收益优先”对应原报告的两套候选；本次仅整理格式和顺序，没有重新计算。', '',
         '按归档控件顺序排列；先按下面的页面顺序，再逐项填写各子类。分包制造为归档列表附加项，未在可编辑控件中确认；大客户订单及分包共5项仍未求解。`FALSE` 表示关闭。', '',
         '增长、需求、效率和利率均为预估字段；单位见各行。物流同一产品的两国优先级配套填写。', '']
seen = []
for page, subs in groups:
    lines += [f'### {page}', '']
    for sub, rows in subs:
        lines += [f'#### {sub}', '', '| 项目／地区 | 单位 | 归档当前 | 中性收益优先 | 不利收益优先 |', '|---|---|---:|---:|---:|']
        for row, label in rows:
            a, b = (items[row] for items in lookup)
            assert a['key'] == b['key'] and a['current'] == b['current']
            vals = [label, a['unit'], a['current'], a['suggested'], b['suggested']]
            lines.append('| ' + ' | '.join(map(fmt, vals)) + ' |')
            for cell, item in zip(vals[-2:], (a, b)):
                if isinstance(item['suggested'], (int, float)):
                    assert float(fmt(cell)) == item['suggested']
            seen.append(row)
        lines.append('')
block = '\n'.join(lines)
text = report.read_text(encoding='utf-8-sig')
text, count = re.subn(r'## 完整输入表[^\n]*\n.*?(?=\n## 情景结果)', '', text, flags=re.S)
assert count == 1
pos = text.index('## 建议如何使用结果')
text = text[:pos] + block + '\n\n' + text[pos:]
# Remove blank lines only between adjacent table rows; retain paragraph spacing.
text = re.sub(r'(?m)(^\|[^\n]*\|)\n(?:[ \t]*\n)+(?=\|)', r'\1\n', text)
text = re.sub(r'\n{3,}', '\n\n', text).rstrip() + '\n'
report.write_bytes(text.encode('utf-8'))

tables = re.findall(r'(?m)^\|[^\n]+(?:\n\|[^\n]+)*', text)
assert len(tables) == sum(len(s) for _, s in groups) + 4
for table in tables:
    rows = table.splitlines()
    assert len(rows) >= 3 and re.fullmatch(r'[| :\-]+', rows[1])
    assert len({r.count('|') for r in rows}) == 1
assert seen == order
links = []
for target in re.findall(r'\]\(([^)]+)\)', text):
    if '://' not in target and not target.startswith('#'):
        exists = (OUT / target.split('#')[0]).exists()
        links.append({'target': target, 'exists': exists})
        assert exists, target
assert all(sha(OUT / name) == before[name] for name in sources)
receipt = dict(status='PASS_FORMAT_AND_FIELD_ORDER', before_sha256=before,
               report_after_sha256=sha(report), tables=len(tables), fields_per_plan=42,
               source_row_order=order, exact_suggestions_preserved=True,
               source_files_unchanged=True, links=links,
               scope='仅报告排版与输入顺序；原计算验收和模型限制继续保留')
(REV / 'acceptance.json').write_bytes((json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode())
with (REV / 'work_log.md').open('a', encoding='utf-8', newline='\n') as f:
    f.write(f'验收：{len(tables)}个表格结构通过；两套候选各42项无遗漏，精确数值与来源文件不变，报告本地链接全部存在。\n')
print(json.dumps({'report': str(report), 'receipt': str(REV / 'acceptance.json'), 'tables': len(tables), 'fields_per_plan': 42}, ensure_ascii=False))
