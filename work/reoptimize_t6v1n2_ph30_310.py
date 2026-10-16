"""Re-solve t6v1n2 under the user's Philippine 30k/310k market hypothesis."""
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import optimize_t6v1n2 as task
import numpy as np

ROOT, save, sha, app = task.ROOT, task.save, task.sha, task.app
SOURCE = ROOT/'output/t6v1n2/20261016_final'
OUT = ROOT/'output/t6v1n2/20261016_ph30_310'


def correct_total_fields(m):
    """The inherited exporter uses literal 5/105; take this scenario's actual totals."""
    coverage=app.read(OUT/'field_coverage.json')
    path=OUT/'report.md'
    text=path.read_text(encoding='utf-8')
    totals=m.market_forecast({})[:,2]
    for j,product in enumerate(app.PRODUCTS):
        field=next(f for f in coverage if f['key']==f'总市场需求, 千单位|{product}|菲律宾')
        field['plans']={name:float(totals[j]) for name in field['plans']}
        field.update(status='用户历史提示假设',reason='本次菲律宾市场总量假设，非官方前景或本组需求')
        lines=text.splitlines()
        matching=[i for i,line in enumerate(lines) if line.startswith(f'| 总市场需求, 千单位 | {product}/菲律宾 |')]
        assert len(matching)==1
        i=matching[0]; cells=lines[i].split('|')
        cells[5:10]=[f' {totals[j]:g} ']*5
        cells[10]=' 用户历史提示假设；总市场规模，不是本组需求 '
        lines[i]='|'.join(cells)
        text='\n'.join(lines)+'\n'
    save(OUT/'field_coverage.json',coverage)
    path.write_text(text,encoding='utf-8')
    assert [next(iter(f['plans'].values())) for f in coverage if f['key'].startswith('总市场需求, 千单位|')]==[30.,310.]


def repair_export():
    manifest=app.read(OUT/'manifest.json')
    assert sha(OUT/Path(__file__).name)==manifest['source_hashes'][Path(__file__).relative_to(ROOT).as_posix()]
    for rel,h in manifest['output_hashes'].items(): assert sha(OUT/rel)==h,rel
    backup=OUT/'before_export_correction'
    backup.mkdir()
    for name in ['report.md','field_coverage.json','manifest.json',Path(__file__).name]:
        shutil.copy2(OUT/name,backup/name)
    correct_total_fields(app.ApplicationModel(OUT))
    manifest['source_hashes'][Path(__file__).relative_to(ROOT).as_posix()]=sha(Path(__file__))
    save(OUT/'source_hashes.json',manifest['source_hashes'])
    shutil.copy2(Path(__file__),OUT/Path(__file__).name)
    with (OUT/'work_log.md').open('a',encoding='utf-8') as stream:
        stream.write('\n交付复核修正：复用导出函数存在5/105硬编码，计算和优化一直使用30/310；已同步56字段与报告的两项总量及其来源标记，改前报告、字段、脚本和清单另存。未修改模型和候选数值。\n')
    manifest['output_hashes']={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p!=OUT/'manifest.json'}
    save(OUT/'manifest.json',manifest)
    print('EXPORT_TOTALS_PASS 30/310; decisions unchanged',flush=True)


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    (OUT/'work_log.md').write_text('用户要求：菲律宾总市场复合梁约30k、连接件310k，按该假设重新计算。解释为30/310千单位，非本组需求；沿用t6v1n2，五候选全部重求解，不操作平台。\n',encoding='utf-8')
    manifest=app.read(SOURCE/'manifest.json')
    for rel,h in manifest['output_hashes'].items(): assert sha(SOURCE/rel)==h,rel
    for rel,h in manifest['source_hashes'].items(): assert sha(ROOT/rel)==h,rel
    sources={p.relative_to(ROOT).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    sources.update(manifest['source_hashes'])
    sources[Path(__file__).relative_to(ROOT).as_posix()]=sha(Path(__file__))
    save(OUT/'source_hashes.json',sources)
    r=app.read(SOURCE/'models_full.json')
    previous=np.array(r['market_forecast']['new_market_totals'])
    new=np.array([30.,310.])
    assert np.array_equal(previous,[5.,105.])
    r['market_forecast']['new_market_totals']=new.tolist()
    r['market_forecast']['new_market_scope']='2026-10-16用户提供往年提示假设：复合梁30000、连接件310000单位；不是本轮官方前景或已实现值'
    r['market_hypothesis']=dict(source='用户本轮消息',unit='千单位',philippines_totals=new.tolist(),
        prior_totals=previous.tolist(),official_outlook_preserved=True,independently_verified=False)
    for j in range(2): r['market_totals'][j][2]=float(new[j])
    for cfg in r['scenarios']:
        if 'new_market_totals' in cfg:
            cfg['new_market_totals']=(np.array(cfg['new_market_totals'])/previous*new).tolist()
            assert np.allclose(cfg['new_market_totals'],[21.,217.])
    save(OUT/'models_full.json',r)
    fields=app.read(SOURCE/'current_fields.json')
    save(OUT/'current_fields.json',fields)
    shutil.copy2(SOURCE/'published_parameters.json',OUT/'published_parameters.json')
    m=app.ApplicationModel(OUT)
    initial=task.checks(m)
    assert np.array_equal(m.market_forecast({})[:,2],new)
    for cfg in r['scenarios']:
        if 'new_market_totals' in cfg:
            assert np.allclose(m.market_forecast(cfg)[:,2],np.array([21.,217.])*cfg.get('market_scale',1.))
    initial['user_market_totals_and_scaled_stress']=True
    save(OUT/'initial_checks.json',initial)
    print('INPUT_PASS totals',new.tolist(),'stress',[21,217],flush=True)
    candidates=task.old.solve(m,OUT,1200)
    previous_plans=[]
    for c in app.read(SOURCE/'result.json')['candidates']:
        previous_plans.append(dict(name=c['name'],x=c['x'],evaluations=[dict(scenario=cfg['name'],
            **m.evaluate(c['x'],cfg,True,priorities=c['fixed_priorities'])) for cfg in r['scenarios']]))
    save(OUT/'prior_candidates_replay.json',previous_plans)
    save(OUT/'result.json',dict(version='t6v1n2',base_version='t6v1n1',start_round=6,end_round=6,
        status='USER_PHILIPPINES_TOTAL_HYPOTHESIS_PARTIAL_OPTIMIZATION',market_hypothesis=r['market_hypothesis'],
        candidates=candidates,baseline=m.evaluate(m.baseline,details=True)))
    save(OUT/'example_request.json',dict(version='t6v1n2',round=6,decision_vector=candidates[1]['x'],scenario='中性'))
    task.report(m,OUT,fields,candidates)
    path=OUT/'report.md'
    text=path.read_text(encoding='utf-8')
    text=text.replace('# t6v1n2：基于t6v1n1的印尼梁定价链修复与优化',
        '# t6v1n2：菲律宾总市场30k／310k假设下的重新优化',1)
    text=text.replace('2026-10-16，北京时间。正式6终局；',
        '本次只更换菲律宾总量假设：复合梁30千单位、连接件310千单位；是市场总量，不是本组销量。来源为用户提供的往年提示，未独立核实。原官方前景5/105千单位与历史方案保留；菲律宾缩量30%改为21/217千单位，联合缩量另乘0.9。其余需求系数、成本、竞争与修复机制不变。\n\n2026-10-16，北京时间。正式6终局；',1)
    text=text.replace('菲律宾5/105千单位、指导价','菲律宾采用本次用户假设30/310千单位、指导价')
    text=text.replace('旧候选也在本次新版18情景下回放','此前5/105千单位下的t6v1n2候选也在本次30/310千单位及18情景下回放')
    path.write_text(text,encoding='utf-8')
    correct_total_fields(m)
    task.verify(OUT)
    summary=[]
    for c in candidates:
        e=c['evaluations'][0]
        summary.append(dict(name=c['name'],ph_prices=[c['x'][2],c['x'][5]],ph_demand=np.array(e['demand'])[:,2].tolist(),
            ph_sales=np.array(e['sales'])[:,2].tolist(),ph_shares=e['ph_sales_shares'],profit=e['profit'],cash=e['cash'],
            worst_profit=min(v['profit'] for v in c['evaluations']),indonesia_beam_price=c['x'][1]))
    save(OUT/'comparison_summary.json',summary)
    link=OUT.relative_to(ROOT).as_posix()+'/report.md'
    documents={}
    for rel in ['README.md','code/model_v2/README.md']:
        p=ROOT/rel; backup=OUT/'documents_before'/rel
        backup.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,backup)
        before=p.read_text(encoding='utf-8-sig')
        if rel=='README.md':
            anchor='| 印尼梁定价链修复及压力优化 |'
            row='| 菲律宾30k/310k用户假设重算 | **t6v1n2**：[五候选与56字段]('+link+') | 菲律宾总量30/310千单位、缩量压力21/217；其余参数不重训，五方案重新联合求解，18情景90回放。用户历史提示假设，非本轮官方值；未写平台。 |\n'
        else:
            anchor='- [t6v1n2印尼梁定价链修复]'
            row='- [t6v1n2菲律宾30k/310k假设](../../'+link+')：用户总量假设下重求五候选、56字段，压力同比例重算；未写平台。\n\n'
        assert before.count(anchor)==1 and link not in before
        p.write_text(before.replace(anchor,row+anchor,1),encoding='utf-8')
        documents[rel]=dict(before_sha256=sha(backup),backup_sha256=sha(backup),after_sha256=sha(p))
    save(OUT/'document_changes.json',documents)
    gaps=[]
    for p in [path]+[ROOT/rel for rel in documents]:
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8-sig')):
            if '://' in target or target.startswith('#'): continue
            if not (p.parent/target.strip('<>').split('#')[0]).exists():
                rel=p.relative_to(ROOT).as_posix()
                assert rel in documents and ']('+target+')' in (OUT/'documents_before'/rel).read_text(encoding='utf-8-sig')
                gaps.append(dict(document=rel,preexisting_missing=target))
    save(OUT/'link_checks.json',dict(new_links_valid=True,preexisting_gaps=gaps))
    shutil.copy2(Path(__file__),OUT/Path(__file__).name)
    with (OUT/'work_log.md').open('a',encoding='utf-8') as stream:
        stream.write('\n完成五候选、18情景90回放、56字段及用户总量/同比例压力自检。新链接核验；说明改前备份与哈希保存；原模型与5/105假设结果哈希不变。未重训或操作平台。\n')
    (ROOT/'work/t6v1n2_active_run.txt').write_text(OUT.relative_to(ROOT).as_posix()+'\n',encoding='utf-8')
    save(OUT/'manifest.json',dict(version='t6v1n2',market_hypothesis=r['market_hypothesis'],documents=documents,
        source_hashes=sources,output_hashes={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()}))
    print('COMPLETE',OUT,summary,flush=True)


if __name__=='__main__':
    if sys.argv[1:]==['--repair-export']: repair_export()
    elif not sys.argv[1:]: main()
    else: raise ValueError('仅支持无参数新运行或--repair-export修复现有导出')
