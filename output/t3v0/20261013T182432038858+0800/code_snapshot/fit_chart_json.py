"""Fit archived Chart.create JSON; keep earlier frozen demand models intact."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from stepwise_model import curve_value

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'raw/20261012_round2_production_chart_code.json'
OUT = ROOT / 'output/visible_coefficients/20261012_round2_json'


def fit_points(x, y, form):
    initial = [.1, .2, .5, .2] if form == 'power' else [.45, .8, 400]
    bounds = ([-2, 0, .0001, .001], [2, 10, 1000, 1]) if form == 'power' else ([0, 0, .001], [2, 3, 100000])

    def solve(ids, start):
        result = least_squares(lambda p: curve_value(x[ids], p, form)-y[ids], start,
                               bounds=bounds, max_nfev=5000, xtol=1e-12, ftol=1e-12, gtol=1e-12)
        assert result.success, result.message
        return result.x

    train, test = np.arange(0, len(x), 2), np.arange(1, len(x), 2)
    held_params = solve(train, initial)
    params = solve(np.arange(len(x)), held_params)
    held_error = curve_value(x[test], held_params, form)-y[test]
    full_error = curve_value(x, params, form)-y
    grid = curve_value(np.linspace(x[0], x[-1], 1000), params, form)
    assert np.all(np.isfinite(grid)) and np.all(grid > 0) and np.all(np.diff(grid) >= 0)
    assert np.max(abs(held_error)) < .02
    return dict(parameters=params.tolist(), train_parameters=held_params.tolist(),
                train_indices=train.tolist(), held_indices=test.tolist(),
                held_mae=float(np.mean(abs(held_error))), held_max_error=float(np.max(abs(held_error))),
                full_mae=float(np.mean(abs(full_error))), full_max_error=float(np.max(abs(full_error))))


def main():
    doc = json.loads(SOURCE.read_text(encoding='utf-8'))
    assert doc['round'] == 2 and 'panel=productionplanning' in doc['source_url']
    result = dict(source=SOURCE.relative_to(ROOT).as_posix(), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  captured_at=doc['captured_at'], round=2, unit='有效投资：千美元；乘数：无量纲',
                  status='VISIBLE_ROUND2_CURVE_FIT_NOT_DEMAND_VALIDATION', curves={})
    prior = json.loads((ROOT/'分步模型拟合与验证.json').read_text(encoding='utf-8'))['curves']
    for name, chart_id, form, axis in [('rd', 'quality.control.chart', 'power', '需求乘数'),
                                      ('operations', 'cost.efficiency.chart', 'saturation', '效率乘数')]:
        matches = [c for c in doc['charts'] if c['id'] == chart_id]
        assert len(matches) == 1
        chart = matches[0]['data']
        assert chart['chart']['yAxisName'] == axis
        x = np.array([float(p['label']) for p in chart['categories'][0]['category']])
        lines = [s for s in chart['dataset'] if s['seriesname'].startswith('曲线,')]
        assert len(lines) == 1
        y = np.array([float(p['value']) for p in lines[0]['data']])
        assert len(x) == len(y) == 200 and x[0] == 0
        assert np.all(np.isfinite(x)) and np.all(np.isfinite(y))
        assert np.all(np.diff(x) > 0) and np.all(np.diff(y) >= 0) and np.all(y > 0)
        fitted = fit_points(x, y, form)
        # shortcut: equal spacing is a sensitivity assumption, use explicit unrounded x values when available.
        indices = np.arange(1, len(x))
        step_low = float(np.max((x[1:]-.5)/indices))
        step_high = float(np.min((x[1:]+.5)/indices))
        assert step_low <= step_high
        uniform_x = np.arange(len(x))*(step_low+step_high)/2
        assert np.max(abs(uniform_x-x)) <= .5+1e-10
        sensitivity = fit_points(uniform_x, y, form)
        sensitivity['step_interval_from_rounded_labels'] = [step_low, step_high]
        sensitivity['assumption'] = 'x从0开始等间距；间距取全部标签±0.5兼容区间的中点'
        grid = np.linspace(x[0], x[-1], 1000)
        sensitivity['max_prediction_difference_from_label_fit'] = float(np.max(abs(
            curve_value(grid, fitted['parameters'], form)-curve_value(grid, sensitivity['parameters'], form))))
        effects = []
        for series in chart['dataset']:
            if not series['seriesname'].startswith('回合效果,'):
                continue
            assert len(series['data']) == len(x)
            for i, p in enumerate(series['data']):
                if p['value'] == 'NaN':
                    continue
                value = float(p['value'])
                assert np.isfinite(value)
                effects.append(dict(index=i, effective_investment_label=float(x[i]), observed_multiplier=value,
                                    fitted_multiplier=float(curve_value(x[i], fitted['parameters'], form))))
        assert len(effects) == 1
        previous = curve_value(x, prior[name]['parameters'], form)
        examples = [dict(effective_investment_kusd=v, multiplier=float(curve_value(v, fitted['parameters'], form)))
                    for v in [0, 200, 400, 600, 800, 1000]]
        result['curves'][name] = dict(**fitted, form=form,
            formula='a+b*(x+c)**d' if form=='power' else 'a+b*x/(c+x)',
            chart_id=chart_id, x_range=[float(x[0]), float(x[-1])], points=np.c_[x,y].tolist(),
            x_limit='页面标签取整至千美元，约±0.5；纵轴为初始化JSON原始数值',
            equal_spacing_sensitivity=sensitivity, round_effect=effects, examples=examples,
            prior_curve_mae_on_new_points=float(np.mean(abs(previous-y))),
            prior_curve_max_error_on_new_points=float(np.max(abs(previous-y))))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'coefficients.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    report = ['# 回合2图表原始数据拟合', '',
              '来源：生产计划页Chart.create初始化JSON，市场5、回合2，采集时间2026-10-12 09:28:42北京时间。',
              '每条曲线200点；100个偶数索引点拟合，100个奇数索引点核验；最终参数用全部200点重新拟合。',
              'x为本回合有效投资（千美元），不等同于当期支出。乘数无量纲。', '']
    for name, c in result['curves'].items():
        title = '研发→需求乘数' if name == 'rd' else '运营→效率乘数'
        report += [f'## {title}', '', f"公式：`{c['formula']}`。",
                   f"参数（a,b,c{',d' if name == 'rd' else ''}）：`{c['parameters']}`。",
                   f"有效投资范围：{c['x_range'][0]:g}–{c['x_range'][1]:g}千美元。",
                   f"交错留点MAE：{c['held_mae']:.9g}；最大误差：{c['held_max_error']:.9g}。",
                   f"全点MAE：{c['full_mae']:.9g}；最大误差：{c['full_max_error']:.9g}。",
                   f"旧曲线对新点MAE：{c['prior_curve_mae_on_new_points']:.9g}（包括旧版SVG横轴标定误差）。",
                   '', '| 有效投资，千美元 | 拟合乘数 |', '|---:|---:|']
        report += [f"| {r['effective_investment_kusd']} | {r['multiplier']:.6f} |" for r in c['examples']]
        e = c['round_effect'][0]
        s = c['equal_spacing_sensitivity']
        report += ['', f"页面回合效果点：横轴标签{e['effective_investment_label']:g}，乘数{e['observed_multiplier']:.9f}；公式近似{e['fitted_multiplier']:.9f}。",
                   f"若假定原始x等间距，留点MAE为{s['held_mae']:.9g}，两套公式在可见范围内最大差异为{s['max_prediction_difference_from_label_fit']:.9g}。这是假设敏感性检查，不是页面提供了未取整x。", '']
    report += ['## 使用边界', '',
               '本次参数独立保存，不覆盖冻结需求模型。研发曲线可用于有效投资→需求乘数；运营曲线用于有效投资→效率乘数，再结合技术尺度计算生产效率。',
               '曲线拟合误差不等于需求预测误差；历史投入延续、竞争份额作用系数、技术尺度、行业总需求仍需独立估计与验证。',
               '研发低投入段拟合误差较大，须同时查看最大误差；接近零投入时不以全范围平均误差表示局部精度。',
               '不能把回合2曲线套入历史实际需求后称为事前验证，也不能仅凭两次曲线差异断定平台改变后台机制。',
               '销售页数据未在本次采集；不能用此前回合1散点权重冒充回合2需求函数。', '',
               f"来源SHA256：`{result['source_sha256']}`。"]
    (OUT/'拟合报告.md').write_text('\n'.join(report)+'\n', encoding='utf-8')
    print(json.dumps({k:{key:v[key] for key in ['parameters','held_mae','held_max_error']} for k,v in result['curves'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
