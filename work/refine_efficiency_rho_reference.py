"""Offline nine-market profile refinement; parameters are reference values only."""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code'), str(ROOT/'code/model_v2')]
import numpy as np
from scipy.optimize import minimize_scalar
import diagnose_own_efficiency as d

SOURCE = ROOT/'output/own_efficiency_scenarios/20261014T170508965934+0800'


def profile(rows, params, rho, full):
    assert rows and all(r['market_id'] != 5 for r in rows)
    x = d.history_model.effective_operations(rows, rho, full)
    a, b, c = params
    factor = a+b*x/(c+x)
    w = d.ops.weights(rows)
    y = np.array([r['effective_observed'] for r in rows])
    theta = float(np.sum(w*factor*y)/np.sum(w*factor**2))
    return theta, float(np.sum(w*(theta*factor-y)**2))


def refine(rows, params, full):
    grid_values = [profile(rows, params, float(rho), full) for rho in d.ops.GRID]
    index = min(range(len(grid_values)), key=lambda i: grid_values[i][1])
    coarse = float(d.ops.GRID[index])
    left, right = max(0., coarse-.001), min(1., coarse+.001)
    solver = minimize_scalar(lambda rho: profile(rows, params, rho, full)[1],
                             bounds=(left, right), method='bounded', options=dict(xatol=1e-13, maxiter=500))
    assert solver.success
    rho = min([left, coarse, float(solver.x), right], key=lambda r: profile(rows, params, r, full)[1])
    theta, mse = profile(rows, params, rho, full)
    assert mse <= grid_values[index][1]+1e-20
    zoom = np.linspace(left, right, 2001)
    assert mse <= min(profile(rows, params, float(r), full)[1] for r in zoom)+1e-15
    return dict(coarse_rho=coarse, coarse_theta=grid_values[index][0], coarse_weighted_mse=grid_values[index][1],
                rho=rho, theta=theta, weighted_mse=mse, weighted_rmse=float(np.sqrt(mse)),
                coarse_weighted_rmse=float(np.sqrt(grid_values[index][1])), local_bounds=[left,right],
                full_history=full, at_local_boundary=rho in (left,right), solver_success=bool(solver.success),
                scope='LOCAL_MINIMUM_REFERENCE_ONLY_NOT_DEPLOYED'), zoom


def self_check():
    params = [.45,.75,400.]
    for full in (False, True):
        rows = [dict(market_id=i+1, operations=o, previous_operations=p, earlier_operations=e)
                for i,(o,p,e) in enumerate([(100,900,200),(300,200,700),(700,700,0),(1500,400,900)])]
        model = dict(rho=.371234, theta=.18, full_history=full)
        y = d.history_model.efficiency_predict(rows, params, model)
        rows = [dict(r,effective_observed=float(v)) for r,v in zip(rows,y)]
        fitted,_ = refine(rows, params, full)
        assert abs(fitted['rho']-model['rho']) < 1e-7
        assert abs(fitted['theta']-model['theta']) < 1e-9
        try:
            profile([dict(rows[0],market_id=5)], params, .5, full)
        except AssertionError:
            pass
        else:
            raise AssertionError('Held market admitted to training objective')
    return dict(synthetic_local_recovery=True, market5_rejected_by_objective=True)


def main():
    checks = self_check()
    if '--self-check' in sys.argv:
        print(json.dumps(checks)); return
    manifest = d.read(SOURCE/'manifest.json')
    for path,digest in manifest['input_hashes'].items():
        assert d.t.nd.sha(ROOT/path) == digest, path
    for path,digest in manifest['output_hashes'].items():
        assert d.t.nd.sha(SOURCE/path) == digest, path
    hashes = dict(manifest['input_hashes'])
    for p in [Path(__file__), *[p for p in SOURCE.iterdir() if p.is_file()]]:
        hashes[p.relative_to(ROOT).as_posix()] = d.t.nd.sha(p)
    registry = d.read(d.REGISTRY)
    saved = d.read(SOURCE/'market_holdout_diagnostics.json')
    history = {(r['market_id'],r['team_id']):r for r in d.read(d.HISTORY/'history.json')}
    own_team = d.read(SOURCE/'single_company_scenarios.json')['products']['复合梁']['team_id']
    params = registry['curves']['operations/泰国']['parameters']
    result, zoom_rows = [], []
    for product in d.t.PRODUCTS:
        rows = [dict(r,earlier_operations=history[r['market_id'],r['team_id']]['refs']['operations'][0]['value'])
                for r in registry['efficiency'][product]['rows']]
        train = [r for r in rows if r['market_id'] != 5]
        test = [r for r in rows if r['market_id'] == 5]
        assert {r['market_id'] for r in train} == set(range(1,11))-{5}
        assert all(r['team_id'] != own_team for r in train)
        for full,name in [(False,'baseline'),(True,'history_candidate')]:
            keys = [[r['market_id'],r['team_id']] for r in train]
            stored = saved['products'][product][name]
            assert keys == stored['training_keys']
            fit, zoom = refine(train,params,full)
            assert np.isclose(fit['coarse_rho'], stored['fit']['rho'], atol=1e-15, rtol=0)
            assert np.isclose(fit['coarse_theta'], stored['fit']['theta'], atol=1e-13, rtol=1e-14)
            for rho in zoom:
                theta,mse = profile(train,params,float(rho),full)
                zoom_rows.append(dict(product=product,variant=name,rho=float(rho),theta=theta,
                                      weighted_mse=mse,weighted_rmse=float(np.sqrt(mse))))
            predictions = d.history_model.efficiency_predict(test,params,fit)
            original_predictions = np.array(stored['predictions'])
            assert np.allclose(d.history_model.efficiency_predict(test,params,dict(
                rho=fit['coarse_rho'],theta=fit['coarse_theta'],full_history=full)),original_predictions,rtol=1e-13,atol=0)
            i = next(i for i,r in enumerate(test) if r['team_id']==own_team)
            actual = test[i]['effective_observed']
            result.append(dict(product=product,variant=name,fit=fit,training_n=len(train),training_keys=keys,
                test_keys=[[r['market_id'],r['team_id']] for r in test],
                heldout_metrics=d.ops.metrics(test,predictions),coarse_heldout_metrics=stored['metrics'],
                market5_predictions=[dict(team_id=r['team_id'],actual=r['effective_observed'],
                    predicted=float(p),coarse_predicted=float(cp)) for r,p,cp in zip(test,predictions,original_predictions)],
                own_actual=actual,own_predicted=float(predictions[i]),own_error_pct=float(100*(predictions[i]/actual-1)),
                own_coarse_error_pct=float(100*(original_predictions[i]/actual-1)),
                training_rmse_reduction_pct=float(100*(1-fit['weighted_rmse']/fit['coarse_weighted_rmse']))))
    for path,digest in hashes.items():
        assert d.t.nd.sha(ROOT/path) == digest, path
    checks.update(nine_market_training_isolated=True, coarse_model_replayed=True, fine_grid_minimum_checked=True,
                  no_market5_selection=True, original_files_unchanged=True)
    out = ROOT/'output/efficiency_rho_local_reference'/datetime.now(d.t.nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
    out.mkdir(parents=True,exist_ok=False)
    d.save(out/'reference.json',dict(status='REFERENCE_ONLY_NOT_DEPLOYED',results=result,checks=checks,
        curve_parameters=params,held_market=5,objective='strategy-weighted MSE of q/n; analytic theta at each rho',
        strategy_weights='inverse count per distinct (O3,O2) strategy; same as original baseline and history candidate',
        refinement='original 0.001 grid minimum +/-0.001 clipped to [0,1]; bounded scalar minimization; 2001-point local replay',
        limitations=['Local numerical minimum, not a statistical confidence estimate',
                     'Market5 curve frozen; only efficiency rho/theta training excludes market5',
                     'Same-round conditional replay; earlier stock, curve and rounding uncertainty not propagated']))
    with (out/'local_profile.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w = csv.DictWriter(f,fieldnames=list(zoom_rows[0]));w.writeheader();w.writerows(zoom_rows)
    lines = ['# 其他9市场效率ρ局部精细参考', '', '仅供参考；没有改动模型、注册表、平台决策或原报告。', '',
        '每个产品分别对原基线、历史候选重估ρ与θ。目标保持原策略加权平方误差，解析重估θ；不是直接最小化MAE。',
        '先复算原0.001网格最小点，在其±0.001范围数值细化，并以约0.000001步长的2001点网格检查。',
        '全部选参只用其他9市场；市场5仅在参数确定后回放，不据其误差挑选版本或ρ。', '',
        '| 产品 | 版本 | 原ρ | 局部ρ参考 | θ参考 | 训练加权RMSE（原→细化） | RMSE减少 |',
        '|---|---|---:|---:|---:|---:|---:|']
    for r in result:
        f=r['fit']
        lines.append(f"| {r['product']} | {r['variant']} | {f['coarse_rho']:.3f} | {f['rho']:.9f} | {f['theta']:.10g} | {f['coarse_weighted_rmse']:.10g} → {f['weighted_rmse']:.10g} | {r['training_rmse_reduction_pct']:.7f}% |")
    lines += ['', '效率、θ、RMSE单位：千单位/人；平方误差单位为其平方。参考ρ显示9位仅方便复算，不表示估计精度。', '',
        '| 产品 | 版本 | 本组偏差（原→细化） | 市场5策略加权MAE（原→细化） |', '|---|---|---:|---:|']
    for r in result:
        lines.append(f"| {r['product']} | {r['variant']} | {r['own_coarse_error_pct']:.6f}% → {r['own_error_pct']:.6f}% | {r['coarse_heldout_metrics']['strategy_weighted_mae']:.10g} → {r['heldout_metrics']['strategy_weighted_mae']:.10g} |")
    lines += ['', '选参保持正式3公布运营曲线和原策略权重；历史候选为O3+ρO2+ρ²O1，原基线为O3+ρO2。',
        '9市场训练样本：复合梁90队，连接件77队；市场5均10队留出。训练键、局部边界、MSE及全市场5回放保存在reference.json。',
        '本组单观测仍不能识别ρ；本次参考值是其他9市场加权目标的局部数值最小点。',
        '未将细化误差改善解释为泛化提升；没有用市场5重选ρ，没有叠加残差，没有部署。',
        '限制：同期条件回放、未知更早运营存量、人员作用、显示舍入与曲线误差；未验证正式4或完整利润。', '',
        '验收：合成参数恢复、市场5输入被训练目标拒绝、原参数复算、细网格最小值检查及原输入哈希未改动通过。',
        '复现：`python work/refine_efficiency_rho_reference.py`；最小自检加`--self-check`。每次创建独立目录。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    d.save(out/'manifest.json',dict(input_hashes=hashes,output_hashes={p.name:d.t.nd.sha(p) for p in out.iterdir()}))
    print(json.dumps(dict(output=str(out),checks=checks,reference=[dict(product=r['product'],variant=r['variant'],
        rho=r['fit']['rho'],theta=r['fit']['theta'],gain_pct=r['training_rmse_reduction_pct']) for r in result]),ensure_ascii=False))


if __name__ == '__main__':
    main()
