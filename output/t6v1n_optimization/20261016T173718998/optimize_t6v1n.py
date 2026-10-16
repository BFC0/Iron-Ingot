"""Re-solve the saved t6v1n outlook with the existing terminal-round optimizer."""
import argparse
import itertools
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import build_t6v1 as workflow
import build_t6v1n as forecast
import t6v1n as app
import numpy as np

ROOT = workflow.ROOT
SOURCE = ROOT/'output/t6v1n/20261016T130746833'
save, sha = workflow.save, workflow.sha


def main(out, iterations):
    out = out.resolve()
    assert (out/'work_log.md').exists() and not (out/'manifest.json').exists()
    sources = {p.relative_to(ROOT).as_posix(): sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    for rel in ['work/build_t6v1.py', 'work/build_t6v1n.py', 'work/optimize_t6v1n.py',
                'code/model_v2/t6v1.py', 'code/model_v2/t6v1n.py']:
        sources[rel] = sha(ROOT/rel)
    # Verify the frozen evidence actually used, independent of changing documentation.
    old_sources = app.read(SOURCE/'manifest.json')['source_hashes']
    for rel, expected in old_sources.items():
        assert sha(ROOT/rel) == expected, rel
        sources[rel] = expected
    r = app.read(SOURCE/'models_full.json')
    save(out/'models_full.json', r)
    fields = app.read(forecast.BASE/'current_fields.json')
    save(out/'current_fields.json', fields)
    shutil.copy2(forecast.BASE/'published_parameters.json', out/'published_parameters.json')
    m = app.ApplicationModel(out)
    checks = workflow.self_check(m)
    top_down, replay = forecast.verify(out)
    checks['top_down_outlook_conservation'] = top_down['top_down_conservation']
    save(out/'initial_checks.json', checks)
    save(out/'regression_replay.json', replay)
    print('INPUT_AND_MECHANISM_CHECKS_PASS', len(fields), flush=True)
    candidates = workflow.solve(m, out, iterations)
    baseline = m.evaluate(m.baseline, details=True)
    for q in candidates:
        x = m.validate(q['x'])
        fixed = [app.ORDERS.index(tuple(o)) for o in q['evaluations'][0]['priorities']]
        for cfg, ev in zip(r['scenarios'], q['evaluations']):
            actual = m.evaluate(x, cfg, True, priorities=fixed)
            assert abs(actual['profit']-ev['profit']) < 1e-8
            assert ev['feasible'] and ev['production_indonesia'] == [0., 0.]
            assert abs(ev['balance_error']) < 1e-7 and ev['quantity_error'] < 1e-8
            assert np.allclose(np.array(ev['market_totals'])*ev['own_shares'], ev['demand'])
            # All 36 logistic pairs must agree with the saved priority optimum.
            for order in itertools.product(range(6), repeat=2):
                assert m.evaluate(x, cfg, True, priorities=order)['profit'] <= ev['profit']+1e-7
    save(out/'result.json', dict(version='t6v1n', base_version='t6v1', start_round=6, end_round=6,
        status='PARTIAL_CONDITIONAL_OPTIMIZATION_WITH_UNSOLVED_MECHANISMS', candidates=candidates, baseline=baseline))
    save(out/'example_request.json', dict(version='t6v1n', round=6, decision_vector=candidates[1]['x'], scenario='中性'))
    save(out/'checks.json', dict(status='PASS_CONDITIONAL_IMPLEMENTATION_AND_REPLAY', mechanisms=checks,
        fields=56, candidate_scenarios=18, logistics_replays=648, training_performed=False,
        optimization_performed=True, platform_verified=False, independent_forward_validation=False))
    shutil.copy2(forecast.BASE/'input_review.md', out/'input_review.md')
    # Reuse the field ordering and complete report; retain the original model and solver.
    workflow.reports(m, out, fields, candidates, checks)
    text = (out/'report.md').read_text(encoding='utf-8').replace('# t6v1 回合6终局条件方案', '# t6v1n 正式6前景优化方案')
    text = text.replace('基于冻结t6v0，未重训', '基于t6v1n自上而下总量与竞争份额、冻结t6v0参数，已重新优化、未重训')
    text = text.replace(' · [印尼投资影响](indonesia_investment_checks.json)', '')
    extra = ['', '## 前景总量、基准增量与风险', '',
        '使用已归档正式6前景，未作平台实时读取。下面的参考基准将归档菲律宾零价格替换为指导价，不能称原草稿预算。仅比较正式6新增条件税后利润，金额千美元。', '',
        '| 产品 | 泰国总量 | 印尼总量 | 菲律宾总量 |', '|---|---:|---:|---:|']
    for p, row in zip(app.PRODUCTS, m.market_forecast({})):
        extra.append('| '+p+' | '+' | '.join(f'{v:.6f}' for v in row)+' |')
    extra += ['', '总量单位：千单位。前景4%/5%为点情景，不是实际增长或置信区间。', '',
        '| 方案 | 中性利润 | 相对参考基准增量 | 联合不利利润 | 六种核心情景最低利润 | 中性期末现金 | 中性长贷 | 中性库存（梁/连接件，千单位） |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    plans = [dict(name='参考基准', evaluations=[dict(scenario=c['name'], **m.evaluate(m.baseline, c, True)) for c in r['scenarios']])]+candidates
    for q in plans:
        ev = q['evaluations'][0]
        adverse = next(e for e in q['evaluations'] if e['scenario'] == '联合不利')
        extra.append(f"| {q['name']} | {ev['profit']:.2f} | {ev['profit']-baseline['profit']:.2f} | {adverse['profit']:.2f} | {min(e['profit'] for e in q['evaluations'][:6]):.2f} | {ev['cash']:.2f} | {ev['long_debt']:.2f} | {ev['closing_inventory'][0]:.4f}/{ev['closing_inventory'][1]:.4f} |")
    traces = app.read(out/'search_trace.json')
    extra += ['', '### 搜索及推荐依据', '',
        '复用28维差分进化：每目标种子11/29，各最多'+str(iterations)+'轮；之后显示精度坐标改进、机器与贷款全档位检查。物流各产品6种顺序。12项营销配置因合计代理仍不可识别，4项投标与1项分包未求解。', '',
        '| 目标 | 种子 | 迭代 | 求解器收敛 | 惩罚后目标收益 |', '|---|---:|---:|---|---:|']
    extra += [f"| {t['plan']} | {t['seed']} | {t['iterations']} | {'是' if t['success'] else '否'} | {-t['objective']:.2f} |" for t in traces]
    extra += ['', '推荐稳健候选，依据是在相同六种核心情景下的最低条件利润；应同时权衡中性收益和现金。达到迭代上限而未收敛时仅保留已找到候选，不宣称局部或全局最优。此前t6v1候选不作为新版推荐。', '',
        '五部分前景处理：需求接入总量与份额；大客户机会因中标履约缺口保留未求解；生产接入印尼本期零产量与行政公布成本；货币无新增参数；财务沿用公布利率基准，风险附加利率随融资状态重算。', '',
        '代码：[优化入口](../../../work/optimize_t6v1n.py)。没有新增训练标签，没有验证独立前向精度；全期现金时序和15项独立期初缺口未关闭。']
    text += '\n'.join(extra)+'\n'
    (out/'report.md').write_text(text, encoding='utf-8')
    coverage = app.read(out/'field_coverage.json')
    assert len(coverage) == len({f['key'] for f in coverage}) == 56
    assert {f['key'] for f in fields} == {f['key'] for f in coverage}
    documents = {}
    for rel in ['README.md', 'code/model_v2/README.md']:
        path = ROOT/rel
        backup = out/'documents_before'/rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        old = path.read_text(encoding='utf-8-sig')
        link = out.relative_to(ROOT).as_posix()+'/report.md'
        if rel == 'README.md':
            new = re.sub(r'^\| 自上而下需求应用 \|.*$', lambda _: '| 自上而下需求应用 | **t6v1n**：[前景优化与56项建议]('+link+')、[运行说明](code/model_v2/t6v1n_README.md) | 已按正式6前景重新求解中性/稳健两候选，需求随总量与竞争份额重算；部分优化、未重训、未操作平台，投标/分包及细分机制缺口保留。 |', old, count=1, flags=re.M)
        else:
            new = re.sub(r'^- \[t6v1n自上而下需求\].*$', lambda _: '- [t6v1n自上而下需求](t6v1n_README.md)：市场总量先估、逐决策重算份额；[正式6前景优化及56项建议](../../'+link+')，部分优化、未重训。', old, count=1, flags=re.M)
        assert new != old
        path.write_text(new, encoding='utf-8')
        documents[rel] = dict(before_sha256=sha(backup), backup_sha256=sha(backup), after_sha256=sha(path))
    save(out/'source_hashes.json', sources)
    gaps = []
    for path in [out/'report.md', out/'input_review.md']+[ROOT/rel for rel in documents]:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8-sig')):
            if '://' in target or target.startswith('#'):
                continue
            if not (path.parent/target.strip('<>').split('#')[0]).exists():
                assert path.is_relative_to(ROOT) and path.relative_to(ROOT).as_posix() in documents
                assert ']('+target+')' in (out/'documents_before'/path.relative_to(ROOT)).read_text(encoding='utf-8-sig')
                gaps.append(dict(document=path.relative_to(ROOT).as_posix(), target=target))
    save(out/'document_changes.json', documents)
    save(out/'link_checks.json', dict(new_links_valid=True, preexisting_gaps=gaps))
    for rel, expected in sources.items():
        assert sha(ROOT/rel) == expected, rel
    save(out/'source_hashes.json', sources)
    shutil.copy2(Path(__file__), out/'optimize_t6v1n.py')
    with (out/'work_log.md').open('a', encoding='utf-8') as stream:
        stream.write('\n\n状态：已完成。北京时间：'+workflow.datetime.now(workflow.TZ).isoformat()+'。已重新搜索两候选、56字段覆盖、18情景回放、648物流比较及守恒检查通过。文档备份与哈希、链接已核验。未重训、未操作平台；未求解及前向精度边界保留。\n')
    save(out/'manifest.json', dict(version='t6v1n', completed_at=workflow.datetime.now(workflow.TZ).isoformat(),
        source_hashes=sources, documents=documents,
        output_hashes={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE', out, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--iterations', type=int, default=300)
    args = parser.parse_args()
    main(args.out, args.iterations)
