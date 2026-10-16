"""Seal verified outputs and update model navigation with backups and hashes."""
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import optimize_t6v1n2 as task

ROOT, save, sha = task.ROOT, task.save, task.sha
out = ROOT/'output/t6v1n2/20261016_final'
assert not (out/'manifest.json').exists()
task.verify(out)
sources = task.app.read(out/'source_hashes.json')
for rel in ['code/model_v2/core.py','code/cross_market_validation.py','code/stepwise_model.py',
            'work/build_t6v1.py','work/seal_t6v1n2.py']:
    sources[rel] = sha(ROOT/rel)
save(out/'source_hashes.json',sources)
result = task.app.read(out/'result.json')
prior = task.app.read(out/'prior_candidates_replay.json')
robust = result['candidates'][1]
worst = min(e['profit'] for e in robust['evaluations'])
old_worst = min(e['profit'] for e in prior[1]['evaluations'])
assert worst > old_worst
save(out/'comparison_summary.json',dict(robust_price_before=prior[1]['x'][1],robust_price_after=robust['x'][1],
    robust_worst_before=old_worst,robust_worst_after=worst,worst_improvement=worst-old_worst,
    scope='旧方案与新方案统一在t6v1n2及18情景下比较，不是实际收益'))
link=out.relative_to(ROOT).as_posix()+'/report.md'
documents={}
for rel in ['README.md','code/model_v2/README.md']:
    path=ROOT/rel
    backup=out/'documents_before'/rel
    backup.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(path,backup)
    before=path.read_text(encoding='utf-8-sig')
    assert 't6v1n2' not in before
    if rel=='README.md':
        anchor='| 菲律宾泰国迁移及份额优化 |'
        row=f'| 印尼梁定价链修复及压力优化 | **t6v1n2**：[56字段与五候选]({link})、[运行说明](code/model_v2/t6v1n2_README.md) | 基于t6v1n1统一研发公司代理口径，新增旧市场价格及投入增益失效压力，共18情景90次回放；稳健印尼梁价{robust["x"][1]:.1f}美元，统一压力最低利润{worst:.2f}千美元仍亏损。细分机制未识别，部分优化、未写平台。 |\n'
    else:
        anchor='- [t6v1n1菲律宾泰国迁移]'
        row=f'- [t6v1n2印尼梁定价链修复](t6v1n2_README.md)：[56项与五候选](../../{link})；统一研发公司代理口径、18情景90回放；压力下仍亏损，非安全盈利或全参数最优。\n\n'
    assert before.count(anchor)==1
    path.write_text(before.replace(anchor,row+anchor,1),encoding='utf-8')
    documents[rel]=dict(before_sha256=sha(backup),backup_sha256=sha(backup),after_sha256=sha(path))
save(out/'document_changes.json',documents)
gaps=[]
for path in [out/'report.md',ROOT/'code/model_v2/t6v1n2_README.md']+[ROOT/rel for rel in documents]:
    for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8-sig')):
        if '://' in target or target.startswith('#'): continue
        if not (path.parent/target.strip('<>').split('#')[0]).exists():
            rel=path.relative_to(ROOT).as_posix()
            assert rel in documents and ']('+target+')' in (out/'documents_before'/rel).read_text(encoding='utf-8-sig'),(str(path),target)
            gaps.append(dict(document=rel,preexisting_missing=target))
save(out/'link_checks.json',dict(new_links_valid=True,preexisting_gaps=gaps))
for rel in ['code/model_v2/t6v1n2.py','work/optimize_t6v1n2.py','work/seal_t6v1n2.py']:
    shutil.copy2(ROOT/rel,out/Path(rel).name)
(ROOT/'work/t6v1n2_active_run.txt').write_text(out.relative_to(ROOT).as_posix()+'\n',encoding='utf-8')
with (out/'work_log.md').open('a',encoding='utf-8') as stream:
    stream.write(f'\n完成：五候选、18情景、90次保存回放、56字段、六市场独立需求公式与守恒/非法输入/物流核验。稳健价格{robust["x"][1]:.1f}，统一压力最低利润{worst:.2f}千美元，仍亏损。稳健两种子收敛；其他候选触及1200轮上限，仅为已找到候选。新链接核验、说明改前备份与改前改后哈希已保存，未写平台。\n')
task.verify(out)
save(out/'manifest.json',dict(version='t6v1n2',base_version='t6v1n1',source_hashes=sources,documents=documents,
    output_hashes={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}))
manifest=task.app.read(out/'manifest.json')
assert all(sha(out/p)==h for p,h in manifest['output_hashes'].items())
print('SEALED',out,'WORST_IMPROVEMENT',worst-old_worst,flush=True)
