"""Synchronize current budget prose and labels with the user's quantity cap."""
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output/budget_semantics' / (stamp + '_sales_min')
OUT.mkdir(parents=True, exist_ok=False)
log = OUT / '工作日志.md'
log.write_text('# 预算销量上限更正\n\n2026-10-13用户进一步明确：预算销量为min{预估数量，产量}。'
               '姓名统一用首字母。\n\n进行中：同步现行说明、生成器及派生标签；保留编辑前副本和原始证据。\n', encoding='utf-8')
formula = '预算销量 = min{决策填写的需求预估数量，产量}'
old_assumption = '按当时决策填写的需求预估测算，并默认按预估数量售出（用户2026-10-13更正）；须同时检查保存有效性'
new_assumption = formula + '（用户2026-10-13更正）；须同时检查保存有效性'
prose = [
    ('并默认按预估数量售出产品', '预算销量取需求预估数量与产量的较小值，即min{预估数量，产量}'),
    ('默认按预估数量售出产品', '预算销量取需求预估数量与产量的较小值，即min{预估数量，产量}'),
    ('并默认按预估数量售出的预算数值', '预算销量按min{预估数量，产量}计算，所得预算数值'),
    ('预算按填写的需求预估测算售出数量', '预算销量按min{填写的需求预估数量，产量}计算'),
    ('按决策需求预估售出的预算假设', '预算销量取min{决策需求预估数量，产量}的口径'),
    ('预算按填写的需求预估测算售出数量。', '预算销量按min{填写的需求预估数量，产量}计算。'),
]
files = ['README.md', 'Cesim_任务要求与当前情况说明.md', '参数细化与六回合期限要求.md',
         '原生键盘标准操作.md', '预测模型与变量说明.md', '预测模型与训练参数汇总.md',
         'code/summarize_model_parameters.py', 'code/label_data.py',
         'output/data_labels/说明.md', '数据分组索引.json', '分组表格行索引.csv',
         'output/data_labels/cell_labels.json', 'output/data_labels/数据标签.csv',
         'output/budget_semantics/20261013T101746756276+0800/正式3更正.md']
changes = []
for relative in files:
    path = ROOT / relative
    original = path.read_bytes()
    before = original.decode('utf-8-sig')
    after = before.replace(old_assumption, new_assumption)
    for old, new in prose:
        after = after.replace(old, new)
    if relative == 'code/summarize_model_parameters.py':
        after = after.replace('min{预估数量，产量}', 'min{{预估数量，产量}}')
    if relative == 'code/label_data.py':
        after = after.replace("assert '按当时决策填写的需求预估测算' in probe[0]['assumption']",
                              "assert '预算销量 = min{决策填写的需求预估数量，产量}' in probe[0]['assumption']")
    if relative == 'README.md':
        after = after.replace('预算按填写的需求预估测算售出数量', '预算销量按min{填写的需求预估数量，产量}计算')
    assert after != before, relative
    assert '默认按预估数量售出' not in after, relative
    backup = OUT / 'before' / relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(original)
    path.write_bytes(after.encode('utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'))
    if path.suffix == '.json':
        json.loads(after)
    if path.suffix == '.py':
        compile(after, str(path), 'exec')
    changes.append(dict(file=relative, before_sha256=hashlib.sha256(original).hexdigest(),
                        after_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

sys.path.insert(0, str(ROOT / 'code'))
from label_data import budget_source
for name, subtype in [('baseline', '试验前基准预算'), ('probe_B', '手填试验后网页预算'), ('ordinary', '常规网页预算')]:
    assert budget_source({'file': name + '.json'}) == (subtype, new_assumption)
labels = json.loads((ROOT / 'output/data_labels/cell_labels.json').read_text(encoding='utf-8-sig'))
budgets = [c for row in labels for c in row['cells'] if c['category'] == 'budget']
assert budgets and all(c['assumption'] == new_assumption and c['usable_as_actual'] is False for c in budgets)
previous = json.loads((ROOT / 'output/budget_semantics/20261013T101746756276+0800/verification.json').read_text(encoding='utf-8-sig'))
assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha
           for p, sha in previous['round3_source_hashes'].items())
(OUT / '更正说明.md').write_text('# 预算销量现行口径\n\n' + formula + '。\n\n'
    '需求预估不超过产量时，预算销量等于需求预估；需求预估超过产量时，预算销量等于产量。'
    '撤回“全部售出”及随后“默认按预估数量售出”的不完整表述。需求预估、产量与销量须采用相同数量单位和对象范围；'
    '国别交付、物流及大客户订单的具体拆分按对应规则单独核验。预算仍为条件计算，不能当作实际需求或已实现销量。\n\n'
    '现行文档、预算标签及其生成器已同步。旧before副本、冻结模型和历史代码快照保留当时记录，其中旧表述不作为现行口径。'
    '根目录Word文档检查未发现“全部售出”或“理想条件”旧段落；本次不修改其公式。\n', encoding='utf-8')
(OUT / 'verification.json').write_text(json.dumps(dict(status='PASS', changes=changes,
    budget_subtypes_checked=3, budget_cells_checked=len(budgets),
    round3_sources_unchanged=True, models_retrained=False, platform_modified=False,
    historical_snapshots_preserved=True), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
with log.open('a', encoding='utf-8') as stream:
    stream.write(f'\n完成：{len(changes)}个活动文件同步，三种预算来源与{len(budgets)}个预算标签断言通过；'
                 'JSON解析、Python语法检查通过，正式3原件哈希不变。未重训或修改平台；历史副本中的旧口径由本次更正说明取代。\n')
print(json.dumps(dict(output=str(OUT), changed_files=len(changes), budget_cells=len(budgets), status='PASS'), ensure_ascii=False))
