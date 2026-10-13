"""Independent operations carry analysis; never replaces existing model parameters."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GRID = np.linspace(0, 1, 1001)
VERSION = 'OPERATIONS_RHO_V1'


def factors(rows, params, grid=GRID):
    a, b, c = params
    x = np.array([r['operations'] for r in rows])[:, None] + np.array(
        [r['previous_operations'] for r in rows])[:, None] * grid
    return a + b * x / (c + x)


def weights(rows):
    counts = Counter((r['operations'], r['previous_operations']) for r in rows)
    return np.array([1 / (len(counts) * counts[r['operations'], r['previous_operations']]) for r in rows])


def profile(rows, params):
    f = factors(rows, params)
    y = np.array([r['effective_observed'] for r in rows])
    w = weights(rows)
    theta = np.sum(w[:, None] * f * y[:, None], axis=0) / np.sum(w[:, None] * f * f, axis=0)
    residual = theta * f - y[:, None]
    return theta, np.sum(w[:, None] * residual ** 2, axis=0)


def select(rows, params):
    theta, mse = profile(rows, params)
    i = int(np.argmin(mse))
    return dict(rho=float(GRID[i]), theta=float(theta[i]), weighted_rmse=float(np.sqrt(mse[i])), index=i)


def predict(rows, params, fit):
    return factors(rows, params, np.array([fit['rho']]))[:, 0] * fit['theta']


def metrics(rows, predictions):
    error = predictions - np.array([r['effective_observed'] for r in rows])
    w = weights(rows)
    return dict(strategy_weighted_mae=float(w @ abs(error)),
                strategy_weighted_rmse=float(np.sqrt(w @ (error ** 2))),
                team_mae=float(np.mean(abs(error))))


def strategy_cv(rows, params):
    result = []
    for strategy in sorted({(r['operations'], r['previous_operations']) for r in rows}):
        train = [r for r in rows if (r['operations'], r['previous_operations']) != strategy]
        test = [r for r in rows if (r['operations'], r['previous_operations']) == strategy]
        fitted = select(train, params)
        baseline_theta, _ = profile(train, params)
        baseline = dict(rho=.5, theta=float(baseline_theta[500]))
        result.append(dict(held_strategy=list(strategy), train_teams=[r['team'] for r in train],
                           held_teams=[r['team'] for r in test], fitted=fitted,
                           optimized=metrics(test, predict(test, params, fitted)),
                           fixed_05=metrics(test, predict(test, params, baseline))))
    return result


def rounding_profile(rows, params):
    # shortcut: ±0.005 assumes nearest two-decimal display rounding; verify against exact exports when available.
    f = factors(rows, params)
    lower, upper = [], []
    for r in rows:
        q = r['source']['production']['value']
        n = r['source']['workers']['value']
        assert q > .005 and n > .005
        lower.append((q - .005) / (n + .005))
        upper.append((q + .005) / (n - .005))
    low = np.max(np.array(lower)[:, None] / f, axis=0)
    high = np.min(np.array(upper)[:, None] / f, axis=0)
    feasible = np.flatnonzero(low <= high)
    return dict(display_rounding_assumption='nearest two decimals, independently unverified',
                feasible_grid_rhos=GRID[feasible].tolist(),
                feasible_range=[float(GRID[feasible[0]]), float(GRID[feasible[-1]])] if len(feasible) else None,
                interpretation='共同技术尺度与舍入区间同时兼容的网格集合；不是统计置信区间')


def self_test():
    params = [.45, .75, 400.1058201058195]
    rows = [dict(operations=o, previous_operations=p) for o, p in [(100, 900), (300, 200), (700, 700), (1500, 400)]]
    y = factors(rows, params, np.array([.37]))[:, 0] * .18
    rows = [dict(r, effective_observed=float(v)) for r, v in zip(rows, y)]
    fit = select(rows, params)
    assert abs(fit['rho'] - .37) < .0001 and abs(fit['theta'] - .18) < 1e-10
    duplicated = rows + [rows[0]] * 10
    assert abs(select(duplicated, params)['rho'] - fit['rho']) < 1e-10
    _, flat = profile([rows[0]], params)
    assert np.max(flat) < 1e-25  # One strategy cannot identify rho separately from theta.
    cv_rows = [dict(r, team=str(i)) for i, r in enumerate(rows)]
    for fold in strategy_cv(cv_rows, params):
        assert not set(fold['train_teams']) & set(fold['held_teams'])
    return dict(synthetic_recovery=True, duplicate_strategy_invariance=True,
                single_strategy_nonidentifiability=True, heldout_disjoint=True)


def main():
    checks = self_test()
    source = ROOT / '分步模型拟合与验证.json'
    old = json.loads(source.read_text(encoding='utf-8'))
    rows = old['efficiency']['input_rows']
    params = old['curves']['operations']['parameters']
    assert len(params) == 3 and all(np.isfinite(params)) and params[2] > 0
    for row in rows:
        assert all(np.isfinite(row[k]) for k in ['operations', 'previous_operations', 'effective_observed'])
        assert row['operations'] >= 0 and row['previous_operations'] >= 0 and row['effective_observed'] > 0
    train = [r for r in rows if r['round'] == 1]
    test = [r for r in rows if r['round'] == 2]
    assert len(train) == len(test) == 10
    chosen = select(train, params)
    theta, mse = profile(train, params)
    baseline = dict(rho=.5, theta=float(theta[500]))
    folds = strategy_cv(train, params)
    def cv_rmse(name):
        return float(np.sqrt(np.mean([r[name]['strategy_weighted_rmse'] ** 2 for r in folds])))
    cv_new, cv_old = cv_rmse('optimized'), cv_rmse('fixed_05')
    round2_theta, round2_mse = profile(test, params)
    interval = rounding_profile(train, params)
    out = ROOT / 'output' / 'operations_rho' / datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'operations_rho.py').write_bytes(Path(__file__).read_bytes())
    data = dict(version=VERSION, category='independent_operations_efficiency_research',
                scope='market5 practice1 fitted; practice2 separate cross-context retrospective diagnosis',
                formula='efficiency=theta*(a+b*(O+rho*Oprev)/(c+O+rho*Oprev))',
                grid=dict(lower=0, upper=1, step=.001, assumption='carry fraction bounded 0..1, not proven platform limit'),
                curve_parameters=params, rows=rows, chosen=chosen, baseline=baseline,
                training_optimized=metrics(train, predict(train, params, chosen)),
                training_fixed_05=metrics(train, predict(train, params, baseline)),
                strategy_cv=folds, cv_optimized_rmse=cv_new, cv_fixed_05_rmse=cv_old,
                rounding_compatibility=interval,
                round2_frozen_scale_diagnostic=dict(optimized=metrics(test, predict(test, params, chosen)),
                                                    fixed_05=metrics(test, predict(test, params, baseline))),
                round2_separate_fit_diagnostic=select(test, params),
                formal_candidate_status='RESEARCH_CANDIDATE_NOT_DEPLOYED',
                checks=checks, limitations=[
                    '仅4种练习1投入策略，上期投入均700；技术尺度与rho存在混杂',
                    '留出整种投入策略，外层训练内独立选择rho和theta；不是正式外部验证',
                    '练习2情境改变，不能以回溯误差选择正式1参数',
                    '曲线参数冻结；图形读数精度与曲线形式不确定性未传播',
                    '仅保留上一期投入；更早历史存量、技术变化、交互及大于1的rho未识别',
                    '运营400仍低于练习1投入范围600–1300；不输出利润最优投入'])
    data['operations_400_efficiency'] = {name: float(predict([dict(operations=400, previous_operations=700)], params, fitted)[0])
                                             for name, fitted in [('optimized', chosen), ('fixed_05', baseline)]}
    (out / 'model.json').write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    with (out / 'rho_profile.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['rho', 'practice1_theta', 'practice1_strategy_rmse', 'practice2_separate_theta', 'practice2_separate_strategy_rmse'])
        writer.writerows(zip(GRID, theta, np.sqrt(mse), round2_theta, np.sqrt(round2_mse)))
    summary = [f'# 运营延续比例独立版本 {VERSION}', '',
               '保留旧模型；未写入网页，未接入需求、利润排名或六回合决策。', '',
               f'练习1策略等权最小二乘选择：ρ={chosen["rho"]:.3f}，θ={chosen["theta"]:.8f}。',
               'ρ与θ同时重估；a、b、c沿用归档网页曲线。选择范围0–1、步长0.001属于研究约束。', '',
               '| 指标（千单位/人） | 优化ρ | 固定ρ=0.5 |', '| --- | ---: | ---: |',
               f'| 练习1策略等权训练RMSE | {chosen["weighted_rmse"]:.8f} | {np.sqrt(mse[500]):.8f} |',
               f'| 整策略留出RMSE | {cv_new:.8f} | {cv_old:.8f} |',
               f'| 练习2冻结尺度回溯MAE | {data["round2_frozen_scale_diagnostic"]["optimized"]["strategy_weighted_mae"]:.8f} | {data["round2_frozen_scale_diagnostic"]["fixed_05"]["strategy_weighted_mae"]:.8f} |', '',
               f'整策略留出的ρ：{[r["fitted"]["rho"] for r in folds]}。每折仅使用其余策略选择ρ及θ；重复策略等权。',
               f'优化ρ的留出误差是否优于固定0.5：{cv_new < cv_old}；即使优于，也不等于正式预测已验证。',
               f'假定产量/人数最近两位小数舍入时，共同尺度兼容ρ范围：{interval["feasible_range"]}（非置信区间；详见完整网格）。',
               f'运营400、上期700的效率预测：{data["operations_400_efficiency"]}；均属外推。', '',
               '练习2单独重估ρ和技术尺度只用于情境差异诊断，不影响练习1所选值。', '',
               '限制：', *['- ' + value for value in data['limitations']], '',
               '复现：`python code/operations_rho.py`。每次写入新时间戳目录；参数、原记录及行列来源见model.json；全网格见rho_profile.csv。',
               '自检：无噪声ρ恢复、重复策略不改变拟合、单策略不可识别、留出队伍互斥均通过。']
    (out / 'report.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    source_paths = {source, Path(__file__).resolve(), ROOT / old['curves']['operations']['source'],
                    ROOT / 'raw/20261011_practice1_outlook.json', ROOT / 'raw/20261011_practice2_outlook.json'}
    for row in rows:
        source_paths.update(ROOT / item['file'] for item in row['source'].values())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(version=VERSION, sources={str(p.relative_to(ROOT)): digest(p) for p in sorted(source_paths)},
                    outputs={p.name: digest(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    assert digest(source) == manifest['sources'][str(source.relative_to(ROOT))]
    print(json.dumps(dict(output=str(out), chosen=chosen, cv_optimized=cv_new, cv_fixed_05=cv_old,
                          compatible_rho_range=interval['feasible_range'], checks=checks), ensure_ascii=False))


if __name__ == '__main__':
    main()
