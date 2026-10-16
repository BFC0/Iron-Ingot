"""Add product margin interpretation to the saved search without rerunning it."""
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import optimize_t6v1n1 as task

out = (task.ROOT/Path((task.ROOT/'work/t6v1n1_active_run.txt').read_text(encoding='utf-8-sig').strip())).resolve()
manifest = task.app.read(out/'manifest.json')
changed = 'work/optimize_t6v1n1.py'
assert task.sha(out/'optimize_t6v1n1.py') == manifest['source_hashes'][changed]
for rel, expected in manifest['source_hashes'].items():
    if rel != changed: assert task.sha(task.ROOT/rel) == expected, rel
for rel, expected in manifest['output_hashes'].items():
    assert task.sha(out/rel) == expected, rel
backup = out/'before_margin_review'
backup.mkdir()
for name in ['report.md', 'checks.json', 'source_hashes.json', 'manifest.json', 'optimize_t6v1n1.py', 'work_log.md']:
    shutil.copy2(out/name, backup/name)
m = task.app.ApplicationModel(out)
checks = task.mechanism_checks(m)
result = task.app.read(out/'result.json')
candidates = result['candidates']
task.report(m, out, task.app.read(out/'current_fields.json'), candidates, checks)
record = task.app.read(out/'checks.json')
record['mechanisms'] = checks
task.save(out/'checks.json', record)
task.save(out/'margin_review.json', dict(
    formula='sales_kunits * (price_USD - ph_freight_USD - inventory_weighted_manufacturing_cost_USD)',
    scope='中性产品毛贡献，不是净利润；未扣营销研发固定税费融资及机会成本',
    plans=[dict(name=c['name'], unit_margins=task.ph_margin(m, c).tolist()) for c in candidates],
    source_before_sha256=manifest['source_hashes'][changed], source_after_sha256=task.sha(task.ROOT/changed),
    reason='30%目标梁毛贡献为负；抢占推荐加入产品毛贡献非负筛选，未更改搜索结果'))
manifest['source_hashes'][changed] = task.sha(task.ROOT/changed)
manifest['source_hashes'][Path(__file__).resolve().relative_to(task.ROOT).as_posix()] = task.sha(Path(__file__))
task.save(out/'source_hashes.json', manifest['source_hashes'])
shutil.copy2(task.ROOT/changed, out/'optimize_t6v1n1.py')
shutil.copy2(Path(__file__), out/'finalize_t6v1n1.py')
with (out/'work_log.md').open('a', encoding='utf-8') as stream:
    stream.write('\n'+task.w.datetime.now(task.w.TZ).isoformat()+' 补充验收：新增泰国价格系数及对手降价方向检查；按产品毛贡献复核，30%目标梁毛贡献为负，抢占建议收敛到20%候选。未重跑或更改优化结果，改前报告/检查/脚本/清单已保存于before_margin_review，脚本改前改后哈希见margin_review.json。\n')
manifest['output_hashes'] = {p.relative_to(out).as_posix():task.sha(p) for p in out.rglob('*') if p.is_file() and p != out/'manifest.json'}
task.save(out/'manifest.json', manifest)
task.verify(out)
print('MARGIN_REVIEW_AND_FINAL_REPLAY_PASS', out)
