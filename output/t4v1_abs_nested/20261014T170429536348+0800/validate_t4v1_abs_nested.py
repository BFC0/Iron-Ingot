"""Read-only ABS audit against frozen t4v1 evidence; no production registry changes."""
import argparse
import copy
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/t4v1/20261014T153914569881+0800'
REGISTRY = ROOT / 'output/t4v1_deduplicated/20261014T162452595723+0800/models_full.json'
SNAPSHOT = SOURCE / 'code_snapshot'
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(SNAPSHOT/'model_v2'), str(SNAPSHOT)]
import t4v1 as model
import numpy as np
from scipy.optimize import lsq_linear

core = model.base.core


def keys(rows):
    return [core.key(r) for r in rows]


def abs_x(rows, params):
    return np.c_[[[int(r['country'] == c) for c in core.COUNTRIES] for r in rows],
                 core.features(rows, params)]


def fit_abs(rows, params, penalty):
    fit_rows = [r for r in rows if r['demand'] > 0]
    assert fit_rows and all(r['price'] > 0 for r in rows)
    x = abs_x(fit_rows, params)
    w = core.equal_weights(fit_rows)
    scale = np.sqrt(np.sum(w[:, None] * x[:, 2:]**2, axis=0))
    scale[scale < 1e-12] = 1
    z = x.copy()
    z[:, 2:] /= scale
    result = lsq_linear(np.vstack([z*np.sqrt(w)[:, None],
                        np.diag([0, 0]+[np.sqrt(penalty)]*5)]),
                        np.r_[np.log([r['demand'] for r in fit_rows])*np.sqrt(w), np.zeros(7)],
                        bounds=([-np.inf]*2+[0]*5, [np.inf]*7), tol=1e-12)
    assert result.success
    beta = result.x.copy()
    beta[2:] /= scale
    return dict(beta=beta.tolist(), scale=scale.tolist(), scaled_beta=result.x.tolist(),
                penalty=penalty, rho=.5, piecewise=False, training_keys=keys(fit_rows),
                zero_demand_exclusions=len(rows)-len(fit_rows))


def select_abs(rows, params):
    path = []
    for penalty in core.PENALTIES:
        folds = []
        for held in sorted({r['market_id'] for r in rows}):
            tr = [r for r in rows if r['market_id'] != held]
            te = [r for r in rows if r['market_id'] == held]
            m = fit_abs(tr, params, penalty)
            p = np.exp(abs_x(te, params) @ m['beta'])
            folds.append(dict(held_market=held, scale=m['scale'],
                              mae_kunits=float(np.mean(abs(p-[r['demand'] for r in te])))))
        path.append(dict(penalty=penalty, mae_kunits=float(np.mean([f['mae_kunits'] for f in folds])), folds=folds))
    chosen = min(path, key=lambda p: p['mae_kunits'])
    return dict(**fit_abs(rows, params, chosen['penalty']), cv_path=path,
                internal_selection_mae_kunits=chosen['mae_kunits'])


class AuditedShare(model.DemandFit):
    def fit(self, ids, config):
        assert len(ids) == len(set(ids)) and all(0 <= i < len(self.rows) for i in ids)
        m = super().fit(ids, config)
        rr = [self.rows[i] for i in ids]
        assert m['training_keys'] == keys(rr)
        keep = [i for i in ids if config['loss'] == 'share' or self.rows[i]['demand'] > 0]
        x = self.features(config['rho'], config['piecewise'])[keep].copy()
        for group in core.old.groups([self.rows[i] for i in keep]).values():
            x[group] -= x[group].mean(axis=0)
        scale = np.sqrt(np.sum(core.equal_weights([self.rows[i] for i in keep])[:, None]*x*x, axis=0)) if config['standardized'] else np.ones(x.shape[1])
        scale[scale < 1e-12] = 1
        assert np.allclose(m['scale'], scale, atol=1e-12, rtol=1e-12)
        return m


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    registry = core.read(str(REGISTRY.relative_to(core.ROOT))) if core.ROOT == ROOT else json.loads(REGISTRY.read_text(encoding='utf-8'))
    data = json.loads((SOURCE/'dataset.json').read_text(encoding='utf-8'))
    curves = json.loads((SOURCE/'formal3_curves.json').read_text(encoding='utf-8'))['curves']
    industry = json.loads((SOURCE/'industry.json').read_text(encoding='utf-8'))
    manifest = json.loads((REGISTRY.parent/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['source'] == str(SOURCE.relative_to(ROOT)).replace('\\', '/')
    assert core.digest(REGISTRY) == manifest['output_hashes']['models_full.json']
    for name in ('dataset.json', 'formal3_curves.json', 'industry.json'):
        assert core.digest(SOURCE/name) == manifest['source_hashes'][name]
    inputs = [REGISTRY, REGISTRY.parent/'manifest.json', SOURCE/'dataset.json', SOURCE/'formal3_curves.json', SOURCE/'industry.json']
    inputs += sorted(SNAPSHOT.rglob('*.py'))
    hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): core.digest(p) for p in inputs}
    exclusions = [e for e in data['exclusions'] if e['model'] == 'DEMAND']
    assert all(e['price'] == e['demand'] == e['sales'] == 0 for e in exclusions)
    core.write(out/'original_exclusions.json', exclusions)
    all_predictions, all_groups, summary, checks = [], [], {}, {}
    for product, rows in data['competitive_rows_by_product'].items():
        params = curves['rd/'+product]['parameters']
        saved = registry['demand'][product]['ABS']
        assert len({tuple(k) for k in keys(rows)}) == len(rows)
        assert saved['training_keys'] == keys([r for r in rows if r['demand'] > 0])
        assert {r['round'] for r in rows} == {3} and {r['phase'] for r in rows} == {'formal'}
        refit = model.absolute_fit(rows, params)
        own = fit_abs(rows, params, saved['penalty'])
        assert refit['penalty'] == saved['penalty']
        assert np.allclose(refit['beta'], saved['beta'], atol=1e-10, rtol=1e-10)
        assert np.allclose(own['beta'], saved['beta'], atol=1e-10, rtol=1e-10)
        x = abs_x(rows, params)
        direct = np.exp(x @ saved['beta'])
        scaled_x = x.copy()
        scaled_x[:, 2:] /= own['scale']
        assert np.allclose(direct, np.exp(scaled_x @ own['scaled_beta']), atol=1e-9, rtol=1e-12)
        checks[product] = dict(saved_beta_max_difference=float(np.max(abs(np.array(own['beta'])-saved['beta']))),
                               saved_penalty_reselected=True, scale_inverse_reproduced=True,
                               included_zero_demand_exclusions=saved['zero_demand_exclusions'],
                               original_zero_price_exclusions=sum(e['product'] == product for e in exclusions))
        saved_rows = [dict(product=product, market=r['market_id'], country=r['country'], team=r['team_id'],
                           actual_kunits=r['demand'], saved_abs_prediction_kunits=float(p)) for r, p in zip(rows, direct)]
        write_csv(out/(product+'_saved_parameters_predictions.csv'), saved_rows)
        folds, product_predictions, group_results = [], [], []
        for held in sorted({r['market_id'] for r in rows}):
            print('NESTED', product, 'market', held, flush=True)
            tr = [copy.deepcopy(r) for r in rows if r['market_id'] != held]
            te = [copy.deepcopy(r) for r in rows if r['market_id'] == held]
            assert not {r['market_id'] for r in tr} & {r['market_id'] for r in te}
            assert not set(map(tuple, keys(tr))) & set(map(tuple, keys(te)))
            abs_model = select_abs(tr, params)
            engine = AuditedShare(tr, params)
            share_model = engine.select(list(range(len(tr))))
            partitions = [dict(held_market=m, training_keys=keys([r for r in tr if r['market_id'] != m]),
                               test_keys=keys([r for r in tr if r['market_id'] == m])) for m in sorted({r['market_id'] for r in tr})]
            assert all(held not in {k[0] for k in f['training_keys']+f['test_keys']} for f in partitions)
            a = np.exp(abs_x(te, params) @ abs_model['beta'])
            s = core.predict(te, core.features(te, params, share_model['rho'], share_model['piecewise']), share_model['beta'])
            changed = [dict(r, demand=r['demand']*123+17) for r in te]
            assert np.array_equal(a, np.exp(abs_x(changed, params) @ abs_model['beta']))
            assert np.array_equal(s, core.predict(changed, core.features(changed, params, share_model['rho'], share_model['piecewise']), share_model['beta']))
            y = np.array([r['demand'] for r in te])
            q = np.zeros(len(te))
            actual_share, abs_normalized_share, abs_fraction_actual_total = np.zeros(len(te)), np.zeros(len(te)), np.zeros(len(te))
            for group, ids in core.old.groups(te).items():
                total = float(sum(y[ids]))
                assert total > 0
                evidence = next(v for v in industry if (v['market'], v['country'], v['product']) == (held, group[-1], product))
                assert abs(total-evidence['actual_total_kunits']) < 1e-8
                excluded = [e for e in exclusions if (e['market'], e['country'], e['product']) == (held, group[-1], product)]
                assert len(ids)+len(excluded) == 10
                assert abs(sum(s[ids])-1) < 1e-12
                q[ids] = s[ids]*total
                actual_share[ids] = y[ids]/total
                abs_normalized_share[ids] = a[ids]/sum(a[ids])
                abs_fraction_actual_total[ids] = a[ids]/total
                group_results.append(dict(product=product, market=held, country=group[-1], active_teams=len(ids),
                    excluded_zero_price_teams=len(excluded), actual_total_kunits=total, abs_total_kunits=float(sum(a[ids])),
                    abs_total_bias_kunits=float(sum(a[ids])-total), abs_total_bias_pct=float(100*(sum(a[ids])/total-1)),
                    share_total_kunits=float(sum(q[ids])), share_sum=float(sum(s[ids])),
                    abs_mae_kunits=float(np.mean(abs(a[ids]-y[ids]))), share_mae_kunits=float(np.mean(abs(q[ids]-y[ids]))),
                    abs_normalized_share_mae_pp=float(100*np.mean(abs(abs_normalized_share[ids]-actual_share[ids]))),
                    abs_actual_total_fraction_mae_pp=float(100*np.mean(abs(abs_fraction_actual_total[ids]-actual_share[ids]))),
                    share_mae_pp=float(100*np.mean(abs(s[ids]-actual_share[ids])))))
            fold_results = group_results[-2:]
            metrics = {k:float(np.mean([g[k] for g in fold_results])) for k in ('abs_mae_kunits', 'share_mae_kunits', 'abs_normalized_share_mae_pp', 'abs_actual_total_fraction_mae_pp', 'share_mae_pp')}
            folds.append(dict(held_market=held, training_keys=keys(tr), test_keys=keys(te),
                              inner_partitions=partitions, ABS=abs_model, SHARE=share_model, metrics=metrics,
                              test_label_perturbation_prediction_invariant=True, share_fit_scale_checks=engine.calls))
            for i, r in enumerate(te):
                product_predictions.append(dict(product=product, key=core.key(r), market=held, country=r['country'], team=r['team_id'],
                    actual_kunits=float(y[i]), abs_kunits=float(a[i]), share_conditional_kunits=float(q[i]),
                    actual_share=float(actual_share[i]), abs_normalized_share=float(abs_normalized_share[i]),
                    abs_fraction_actual_total=float(abs_fraction_actual_total[i]), share=float(s[i])))
            core.write(out/(product+'_folds_partial.json'), folds)
        assert len(product_predictions) == len(rows)
        assert {tuple(p['key']) for p in product_predictions} == set(map(tuple, keys(rows)))
        summary[product] = dict(n=len(rows), markets=len(folds),
            **{k:float(np.mean([f['metrics'][k] for f in folds])) for k in folds[0]['metrics']},
            abs_worse_markets=[f['held_market'] for f in folds if f['metrics']['abs_mae_kunits'] > f['metrics']['share_mae_kunits']],
            max_abs_country_total_bias_pct=float(max(abs(g['abs_total_bias_pct']) for g in group_results)))
        core.write(out/(product+'_nested.json'), dict(folds=folds, predictions=product_predictions, summary=summary[product]))
        (out/(product+'_folds_partial.json')).unlink()
        all_predictions.extend(product_predictions)
        all_groups.extend(group_results)
    checks['isolation'] = dict(outer_market_disjoint=True, inner_market_disjoint=True, fold_local_scales_checked=True,
        test_label_perturbation_passed=True, shared_test_sets=True, original_group_sizes_preserved=True,
        industry_total_use='TEST_LABEL_CONDITIONAL_BASELINE_ONLY_NOT_PROSPECTIVE_INPUT',
        curve_parameters='Fixed formal3 published curve fit; no demand-label fitting or formal4 curve use')
    core.write(out/'checks.json', checks)
    core.write(out/'summary.json', summary)
    core.write(out/'predictions.json', all_predictions)
    write_csv(out/'predictions.csv', [dict(p, key=json.dumps(p['key'], ensure_ascii=False)) for p in all_predictions])
    write_csv(out/'country_market_metrics.csv', all_groups)
    lines = ['# 双产品 ABS 参数复算与嵌套整市场验证', '',
        '来源：当前去重注册表 `'+str(REGISTRY.relative_to(ROOT))+'`；原证据 `'+str(SOURCE.relative_to(ROOT))+'`。来源哈希已核对，未改写原归档、冻结评价或主预测。', '',
        '外层逐一留出完整市场；内层仅在其余9市场选参、计算训练尺度。ABS沿用原11个惩罚候选、rho=0.5、国家截距和5个非负特征系数，以内层逐市场数量MAE选惩罚；SHARE沿用原配置网格和份额MAE选参。两者折外测试键完全相同。SHARE选参目标为份额而ABS为数量，比较反映既有算法各自的选参方法。', '',
        '| 产品 | 有效记录 | ABS数量MAE（千单位） | SHARE×实际总量MAE（千单位） | ABS不利市场 | 最大国家总量绝对偏差 |',
        '|---|---:|---:|---:|---|---:|']
    for p, s in summary.items():
        lines.append(f"| {p} | {s['n']} | {s['abs_mae_kunits']:.6f} | {s['share_mae_kunits']:.6f} | {s['abs_worse_markets']} | {s['max_abs_country_total_bias_pct']:.2f}% |")
    lines += ['', '数量MAE以每市场内两国等权、每国家内有效竞争队等权，再10市场等权汇总；避免连接件活跃队数不同带来权重变化。内层ABS严格沿用原算法的每市场有效记录平均口径，其训练权重仍为市场/国家等权。两个产品量级不同，禁止合并原始数量MAE排名。', '',
        'SHARE数量使用留出市场的实际行业总量，是已知结果条件基线，非事前输入。ABS数量不使用该总量；其合计并不受守恒约束。`country_market_metrics.csv`给出各市场/国家数量MAE、总量偏差和份额指标，逐市场汇总见各产品nested.json的folds.metrics。', '',
        '份额MAE单位为百分点：SHARE为softmax份额；ABS normalized share为ABS预测除以本国ABS预测总量，单独评价竞争分配，不代表ABS数量可靠；ABS actual-total fraction为ABS预测除以实际总量，合计不必为1，可同时受规模和分配误差影响。SHARE在原市场/国家/产品有效竞争集合内守恒，零价零需求原始排除队保留在排除表，不伪造正数、不加入softmax正份额。', '',
        f"原始排除共{len(exclusions)}条（详见original_exclusions.json）；已纳入记录的ABS zero_demand_exclusions=0仅说明入模数据内没有再排除，不代表原始200条连接件数据均入模。", '',
        '保存参数复算使用原始尺度beta：q=exp(country_intercept + features @ beta_features)。价格特征为本国-log(price/initial_price)，营销为log1p(公司合计投入/1000)，研发为log(正式3曲线(rd+0.5×previous_rd))；连接件initial_price=1仅为线性对数价格参考，不启用复合梁的分段价格阈值。保存参数预测与训练内重拟合、标准化逆变换均通过自检；这些复算误差不作为独立成绩。', '',
        '隔离核验：训练脚本仅把外层训练行传入选参函数；每次SHARE拟合重核训练尺度，ABS训练尺度在每个内折单独计算并保存。保存全部外层/内层训练测试键、候选路径、尺度及最终配置。将外层测试需求任意改动后，ABS数量和SHARE份额预测均不变；SHARE条件数量会随作为基线条件的实际总量改变，这属于明示的结果条件使用。正式3发布曲线固定，只拟合图表点、不拟合需求标签；未使用正式4曲线。', '',
        '建议：本次证据足以把ABS列为同期条件研究的并列参考，显示不依赖实际行业总量的数量基准及规模偏差；不构成替换SHARE主预测或生产采用的充分证据。逐产品按上表及不利市场使用，不默认平均两种预测。实际竞争投入仍使用公司合计营销/研发代理，模型不适用于零价零需求及分产品投入未知条件的直接外推。', '',
        '仍缺跨回合验证：用回合开始前冻结参数和完整本组方案、对手可用信息及当期曲线/研发历史，在后续真实结算需求上评分；正式4及更多独立回合的数量/份额/行业总量误差、价格与产品投入变化稳定性，以及成本/供给约束下的最终收益验证。同期10市场留出不能证明跨回合系数稳定，原冻结结果没有匹配事前预测，本次不补造事前成绩。', '',
        '复现：从项目根目录运行 `python work/validate_t4v1_abs_nested.py`（需要已有numpy/scipy环境），每次新增独立输出目录。JSON/CSV不省略折外预测；脚本复用原训练归档的冻结代码快照，避免与并行工作互相覆盖。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    shutil.copy2(Path(__file__), out/Path(__file__).name)
    assert all(core.digest(ROOT/p) == digest for p, digest in hashes.items())
    core.write(out/'manifest.json', dict(source_hashes=hashes, script_sha256=core.digest(Path(__file__)),
        output_hashes={p.name:core.digest(p) for p in out.iterdir() if p.is_file()},
        immutable_sources_verified=True, no_platform_mutations=True, no_deployment=True))
    print(json.dumps(dict(output=str(out), summary=summary, checks=checks), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    target = args.output or ROOT/'output/t4v1_abs_nested'/datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S%f+0800')
    run(target)
