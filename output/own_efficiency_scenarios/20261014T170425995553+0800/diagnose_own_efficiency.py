"""Restore single-company rho scenarios separately from the immutable market registry."""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code'), str(Path(__file__).parent)]
import numpy as np
import t4v1 as t
import operations_rho as ops
import optimize_t4v1_connector as history_model

REGISTRY = ROOT/'output/t4v1_deduplicated/20261014T162452595723+0800/models_full.json'
ORIGINAL = ROOT/'output/t4v1/20261014T153914569881+0800'
HISTORY = ROOT/'output/t4v1_connector_optimization/20261014T162353579815+0800'
read = history_model.read
save = history_model.save


def scenarios(q, n, current, previous, curve):
    assert q['value'] > 0 and n['value'] > n['half'] >= 0
    lo = (q['value']-q['half'])/(n['value']+n['half'])
    hi = (q['value']+q['half'])/(n['value']-n['half'])
    result = []
    for rho in t.base.core.RHOS:
        x = current+rho*previous
        f = float(t.curve_value(x, curve['parameters'], 'saturation'))
        assert np.isfinite(f) and f > 0
        theta = q['value']/n['value']/f
        result.append(dict(rho=rho, theta=theta, effective_operations=x, factor=f,
                           actual_efficiency=q['value']/n['value'], reconstructed_efficiency=theta*f,
                           theta_display_interval=[lo/f, hi/f], efficiency_display_interval=[lo, hi],
                           within_curve_range=curve['x_range'][0] <= x <= curve['x_range'][1]))
    assert len(result) == len(t.base.core.RHOS)
    assert all(np.isclose(r['reconstructed_efficiency'], q['value']/n['value'], rtol=1e-13, atol=0) for r in result)
    return result


def self_check():
    rows = scenarios(dict(value=18.38, half=.005), dict(value=109.63, half=.005),
                     600, 750, dict(parameters=[.45, .75, 400], x_range=[0, 1120]))
    assert [r['rho'] for r in rows] == t.base.core.RHOS
    assert all(r['theta_display_interval'][0] < r['theta'] < r['theta_display_interval'][1] for r in rows)
    assert not rows[-1]['within_curve_range']
    return dict(single_observation_reconstruction=True, complete_original_rho_grid=True,
                rounding_intervals=True, extrapolation_flag=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    checks = self_check()
    if args.self_check:
        print(json.dumps(checks)); return
    protected = [REGISTRY, *[p for p in ORIGINAL.rglob('*') if p.is_file()]]
    hashes = {p.relative_to(ROOT).as_posix(): t.nd.sha(p) for p in protected}
    for p in [Path(__file__), ROOT/'code/model_v2/t4v1.py', ROOT/'code/model_v2/core.py',
              ROOT/'code/operations_rho.py', ROOT/'code/model_v2/optimize_t4v1_connector.py',
              HISTORY/'efficiency_results.json', HISTORY/'history.json']:
        hashes[p.relative_to(ROOT).as_posix()] = t.nd.sha(p)
    def verify_ref(ref):
        path = ROOT/ref['source']
        digest = t.nd.sha(path)
        assert digest == ref['sha256'], ref['source']
        hashes[path.relative_to(ROOT).as_posix()] = digest
    registry, data = read(REGISTRY), read(ORIGINAL/'dataset.json')
    original = read(ORIGINAL/'models_full.json')
    assert registry['efficiency'] == original['efficiency']
    curve = registry['curves']['operations/泰国']
    assert curve == original['curves']['operations/泰国'] and curve['round'] == 3
    verify_ref(dict(source=curve['source'], sha256=curve['source_sha256']))
    actual = t.Actuals(t.load_previous()+read(t.AUDIT/'rows.json'))
    own = data['own_final_decision_rows']
    assert len({r['team_id'] for r in own}) == 1 and {r['market_id'] for r in own} == {5}
    team = own[0]['team_id']
    pairs = {(r['market_id'], r['team_id']): r for r in data['state_pairs']}
    historical = {(r['market_id'], r['team_id']): r for r in read(HISTORY/'history.json')}
    saved_history = read(HISTORY/'efficiency_results.json')
    single, market_models, comparisons = {}, {}, []
    for product in t.PRODUCTS:
        model = registry['efficiency'][product]
        rows = model['rows']
        for r in rows:
            market, tid = r['market_id'], r['team_id']
            for name, label in [('production', '生产规模, 千单位'), ('workers', '生产线人工数量')]:
                ref = actual.get(market, 3, tid, 'productiondetails', label, product)
                assert ref == r['source'][name]
                verify_ref(ref)
            for rnd, field, state in [(2, 'previous_operations', 'initial'), (3, 'operations', 'closing')]:
                ref = actual.get(market, rnd, tid, 'incomestatement', '运营改进')
                assert ref == pairs[market, tid][state]['refs']['operations'] and ref['value'] == r[field]
                verify_ref(ref)
            assert r['effective_observed'] == r['source']['production']['value']/r['source']['workers']['value']
        own_row = next(r for r in rows if r['team_id'] == team)
        q, n = own_row['source']['production'], own_row['source']['workers']
        current = own[0]['sources']['operations']
        assert all(r['sources']['operations'] == current for r in own)
        verify_ref(current)
        fields = read(t.DECISIONS)['fields']
        decision = t.final_field(fields, '运营改进, 千 美元', '', '泰国')
        assert dict(decision, sha256=current['sha256']) == current
        # Actual result and captured final group input must agree before restoring the original call.
        assert current['value'] == own_row['operations']
        pair = pairs[5, team]
        previous = pair['initial']['refs']['operations']
        single[product] = dict(status='SINGLE_COMPANY_CALIBRATION_RHO_UNIDENTIFIABLE', market_id=5,
            team_id=team, phase='formal', round=3, training_n=1, production=q, workers=n,
            current_operations=current, current_operations_actual=pair['closing']['refs']['operations'],
            previous_operations=previous, curve=curve,
            units=dict(production='千单位', workers='人', operations='千美元', efficiency='千单位/人', theta='千单位/人', factor='无量纲'),
            scenarios=scenarios(q, n, current['value'], previous['value'], curve),
            selected_rho=None, deployment_enabled=False)
        train = [r for r in rows if r['market_id'] != 5]
        test = [r for r in rows if r['market_id'] == 5]
        keys = [[r['market_id'], r['team_id']] for r in train]
        assert {k[0] for k in keys} == set(range(1, 11))-{5}
        assert all(k[1] != team for k in keys)
        fold = next(f for f in model['holdouts'] if f['market'] == 5)
        replay = ops.select(train, curve['parameters'])
        assert replay == fold['fit']
        baseline_predictions = ops.predict(test, curve['parameters'], replay)
        assert ops.metrics(test, baseline_predictions) == fold['metrics']
        variants = dict(baseline=dict(fit=replay, training_keys=keys, test_keys=[[5,r['team_id']] for r in test],
                       metrics=fold['metrics'], predictions=baseline_predictions.tolist()))
        augmented = []
        for r in rows:
            refs = historical[r['market_id'], r['team_id']]['refs']['operations']
            for rnd, ref in zip((1, 2), refs):
                verify_ref(ref)
                assert ref == actual.get(r['market_id'], rnd, r['team_id'], 'incomestatement', '运营改进')
            assert refs[1]['value'] == r['previous_operations']
            augmented.append(dict(r, earlier_operations=refs[0]['value']))
        htrain = [r for r in augmented if r['market_id'] != 5]
        htest = [r for r in augmented if r['market_id'] == 5]
        hfold = next(f for f in saved_history[product]['full_history']['folds'] if f['market'] == 5)
        assert hfold['training_keys'] == keys and hfold['test_keys'] == variants['baseline']['test_keys']
        hfit = history_model.efficiency_fit(htrain, curve['parameters'], True)
        assert hfit == hfold['fit']
        hp = history_model.efficiency_predict(htest, curve['parameters'], hfit)
        assert ops.metrics(htest, hp) == hfold['metrics']
        for r, prediction in zip(htest, hp):
            saved = next(p for p in saved_history[product]['full_history']['predictions'] if p['team']==r['team_id'])
            assert np.isclose(saved['predicted'], prediction, rtol=1e-13, atol=0)
        variants['history_candidate'] = dict(fit=hfit, training_keys=keys, test_keys=hfold['test_keys'],
            metrics=hfold['metrics'], predictions=hp.tolist(), operations_history=[
                dict(team_id=r['team_id'], refs=historical[r['market_id'],r['team_id']]['refs']['operations']) for r in augmented])
        market_models[product] = variants
        idx = next(i for i,r in enumerate(test) if r['team_id'] == team)
        lo, hi = single[product]['scenarios'][0]['efficiency_display_interval']
        for name, values in variants.items():
            prediction = values['predictions'][idx]
            comparisons.append(dict(product=product, variant=name, actual=own_row['effective_observed'],
                predicted=prediction, residual=prediction-own_row['effective_observed'],
                error_pct=100*(prediction/own_row['effective_observed']-1), display_interval=[lo,hi],
                rounding_compatible=lo<=prediction<=hi, training_n=len(train), training_markets=sorted({k[0] for k in keys})))
    assert set(single) == set(t.PRODUCTS) and sum(len(v['scenarios']) for v in single.values()) == 10
    for path, digest in hashes.items():
        assert t.nd.sha(ROOT/path) == digest, path
    checks.update(both_products_complete=True, nine_market_training_isolated=True, saved_holdout_parameter_replay=True,
                  history_holdout_replay=True, source_hashes_and_numeric_refs_verified=True, original_archive_and_registry_unchanged=True)
    out = ROOT/'output/own_efficiency_scenarios'/datetime.now(t.nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
    out.mkdir(parents=True, exist_ok=False)
    save(out/'single_company_scenarios.json', dict(products=single, formula='e=q/n=theta*f(O3+rho*O2)',
        rounding='显示值半末位舍入区间；假定最近舍入，非统计置信区间；theta区间未传播运营输入/曲线误差',
        applicability='仅正式3市场5本组双产品校准；rho不可识别；非效率修正或泛化改进'))
    save(out/'market_holdout_diagnostics.json', dict(held_market=5, products=market_models, comparisons=comparisons,
        scope='同回合同曲线条件回放；效率rho/theta仅其他9市场训练；市场5公布曲线冻结，不是未知曲线市场外推'))
    save(out/'checks.json', checks)
    with (out/'scenarios.csv').open('w', encoding='utf-8-sig', newline='') as f:
        records = [dict(product=p, production=v['production']['value'], workers=v['workers']['value'],
                        current_operations=v['current_operations']['value'], previous_operations=v['previous_operations']['value'], **r)
                   for p,v in single.items() for r in v['scenarios']]
        writer = csv.DictWriter(f, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    lines = ['# 本组双产品效率情景与整市场留出诊断', '', '2026-10-14（北京时间）。仅本地真实归档；匿名团队 '+team+'。', '',
        '本组每个ρ均由单个θ精确复算q/n；ρ不可识别，不选择最优ρ、不自动修正效率、不部署。', '',
        '## 来源与覆盖原因', '', f'当前入口：`{REGISTRY.relative_to(ROOT).as_posix()}`；数据与冻结结果：`{ORIGINAL.relative_to(ROOT).as_posix()}`。',
        '`t4v1.main`先将本组scenarios写入efficiency[product]，随后逐市场拟合在同一键写入chosen/holdouts/rows，覆盖scenarios。',
        '独立脚本恢复原RHOS与正式3运营曲线，不修改共享训练代码。单公司情景和全市场留出诊断分别保存，原注册表完整保留。', '',
        '## 逐ρ校准', '', '| 产品 | ρ | θ（千单位/人） | 有效运营（千美元） | q/n | 曲线范围内 |', '|---|---:|---:|---:|---:|---|']
    for p,v in single.items():
        lines += [f"| {p} | {r['rho']} | {r['theta']:.10g} | {r['effective_operations']:.6g} | {r['reconstructed_efficiency']:.10g} | {r['within_curve_range']} |" for r in v['scenarios']]
    lines += ['', '生产量/人数：复合梁18.38千单位/109.63人；连接件62千单位/3.70人。当期运营600、上期750千美元。',
        f"曲线x范围：{curve['x_range']}千美元；范围外情景仅数学外推。JSON保存完整来源行列、SHA256、单位和舍入区间。", '',
        '## 仅其他9市场训练的预测', '', '| 产品 | 版本 | 实际q/n | 预测 | 预测−实际 | 相对偏差 | 舍入兼容 |', '|---|---|---:|---:|---:|---:|---|']
    for c in comparisons:
        lines.append(f"| {c['product']} | {c['variant']} | {c['actual']:.10g} | {c['predicted']:.10g} | {c['residual']:.8g} | {c['error_pct']:.6f}% | {c['rounding_compatible']} |")
    lines += ['', '原基线每产品市场5折重新拟合并与已保存参数/指标精确比较。历史候选额外核验训练键、正式1/2来源、参数与全部市场5折外预测。',
        '基线有效投入O3+ρO2；历史候选O3+ρO2+ρ²O1。θ、ρ均仅在其他9市场估计；连接件正产量/正人数仅87队，训练数详见JSON。', '',
        '## 数据限制与验收', '', '显示产量/人数独立最近舍入是区间假设，运营支出与曲线误差未传播；是否超区间只诊断显示舍入能否解释偏差。',
        '正式1之前存量未知；历史候选曾参考本批数据诊断，仍属探索性同期条件回放。曲线来自市场5公布正式3图，不宣称曲线来源也留出。',
        '正式4实际、跨回合稳定性、人员变化因果作用、完整利润及未来投入效果未验证。单样本精确拟合不代表泛化改善；不叠加残差。',
        '通过：10情景复算、双产品完整、9市场隔离、基线与历史市场5折复算、源哈希与数值引用、原训练归档及注册表未改动。', '',
        '复现：`python code/model_v2/diagnose_own_efficiency.py`；最小自检加`--self-check`。每次创建独立目录。',
        '交付：single_company_scenarios.json、scenarios.csv、market_holdout_diagnostics.json、checks.json、manifest.json及脚本快照。', '',
        '未重复采集教程，未修改平台决策、共享代码或全局文档，未生成HTML。风险：条件回放与单样本校准均不能作为部署或效率调整依据。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    save(out/'manifest.json', dict(input_hashes=hashes, protected_inputs_unchanged=True,
        output_hashes={p.name:t.nd.sha(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(output=str(out), checks=checks, comparisons=comparisons), ensure_ascii=False))


if __name__ == '__main__':
    main()
