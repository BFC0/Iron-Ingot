"""Refit archived visible curves and decode sales importance; never changes decisions."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from stepwise_model import NS, curve_value, fit_curves

ROOT = Path(__file__).resolve().parents[1]
COLORS = {'价格': '#7cb342', '一般营销': '#ffab40', '设计师营销': '#ed242d', '研发': '#9c27b0'}


def sales_importance(path):
    doc = json.loads(path.read_text(encoding='utf-8'))
    graphs = [ET.fromstring(s) for s in doc['graphs'] if 'Relative importance' in s]
    assert len(graphs) == 1
    tree = graphs[0]
    ticks = [(float(t.get('x')), float(''.join(t.itertext())))
             for t in tree.findall('.//s:text', NS) if t.get('y') == '226']
    assert len(ticks) == 4 and [v for _, v in ticks] == [0, 1, 2, 3]
    slope, intercept = np.polyfit(*np.array(ticks).T, 1)
    assert np.allclose([slope*x+intercept for x, _ in ticks], [0, 1, 2, 3])
    result = {}
    for label, color in COLORS.items():
        # shortcut: archived markers share y=122.75; decode other states only after checking their plot groups.
        paths = [p.get('d') for p in tree.findall('.//s:path', NS)
                 if p.get('stroke') == color and ',116.75' in p.get('d', '')]
        assert len(paths) == 1, (path, label)
        match = re.match(r'M([\d.]+),116.75', paths[0])
        assert match
        value = float(slope*float(match[1])+intercept)
        assert -1e-10 <= value <= 3+1e-10
        result[label] = value
    assert abs(result['价格']-3) < 1e-10
    return result


def main():
    out = ROOT / 'output/visible_coefficients/20261012_archive_review'
    out.mkdir(parents=True, exist_ok=True)
    curves = fit_curves()
    for curve in curves.values():
        points = np.array(curve['points'])
        values = curve_value(points[:, 0], curve['parameters'], curve['form'])
        assert np.all(np.isfinite(values)) and np.all(values > 0)
        assert np.all(np.diff(values) >= 0)
        assert curve['held_vertex_max_error'] < .02
        curve['full_vertex_max_error'] = float(np.max(abs(values-points[:, 1])))
    sales = {country: sales_importance(ROOT / f'raw/20261011_{name}_svg.json')
             for country, name in [('泰国', 'thailand'), ('印尼', 'indonesia')]}
    examples = {label: [{'effective_investment_kusd': x,
                        'multiplier': float(curve_value(x, c['parameters'], c['form']))}
                       for x in [0, 200, 400, 600, 800, 1000]]
                for label, c in curves.items()}
    sources = {c['source'] for c in curves.values()} | {
        'raw/20261011_thailand_svg.json', 'raw/20261011_indonesia_svg.json',
        'raw/20261011_demand_multiplier_help.json'}
    result = dict(curves=curves, sales_relative_importance=sales, examples=examples,
                  status='ARCHIVED_CURVE_APPROXIMATION_NOT_CURRENT_ROUND_CALIBRATION',
                  sales_limit='0至3的相对重要性坐标，不能直接当需求弹性、乘数或归一化份额；归档帮助正文与坐标标签不一致，以可见刻度解码。',
                  sources={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(sources)})
    (out/'coefficients.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    lines = ['# 网页可见系数复核', '',
             '基于2026-10-11归档重新拟合；没有访问当前网页或修改决策。', '',
             '研发曲线和运营曲线已被现有模型使用。运营图纵轴是效率乘数，进入生产效率与工资计算；不直接乘入需求。', '',
             'x单位为千美元，表示图中的本回合有效投资。有效投资与当期投入、历史投入的映射仍需另行估计，不能由曲线形状识别。', '']
    for label, c in curves.items():
        lines += [f"## {label}", '', f"公式：`{c['formula']}`；参数：`{c['parameters']}`。",
                  f"可见范围：0至{c['axes']['axis_max']:.2f}千美元。交错留点MAE={c['held_vertex_mae']:.8f}，最大误差={c['held_vertex_max_error']:.8f}。",
                  '留点来自同一曲线，只核验公式近似程度，不是需求预测验证。', '', '| 有效投资 | 乘数 |', '|---:|---:|']
        lines += [f"| {r['effective_investment_kusd']} | {r['multiplier']:.6f} |" for r in examples[label]]
        lines += ['']
    lines += ['## 销售图', '',
              '销售图为四类因素的散点，横轴是相对重要性（0至3），纵轴是相对竞争位置。每类每国只有一个点，无法识别投入响应函数。', '',
              '| 国家 | 价格 | 一般营销 | 设计师营销 | 研发 |', '|---|---:|---:|---:|---:|']
    lines += ['| '+country+' | '+' | '.join(f'{values[k]:.6f}' for k in COLORS)+' |' for country, values in sales.items()]
    lines += ['', result['sales_limit'], '',
              '现有需求模型采用价格对数、营销log1p和拟合研发乘数的对数，另用实际需求估计其作用系数并计算竞争份额。',
              '可见重要性用于核验方向与国别差异；若作为约束或先验加入模型，须重新进行训练内选参和独立留出比较，不能直接替换现有弹性。', '',
              '后续计算顺序：投入→有效投资→曲线乘数→竞争需求份额→给定行业总量下的需求→供给约束下的销量→财务。',
              '研发若已进入销售综合作用，不应再次直接乘需求，以免重复计算。']
    (out/'说明.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(output=str(out), sales=sales,
                          errors={k:v['held_vertex_mae'] for k,v in curves.items()}), ensure_ascii=False))


if __name__ == '__main__':
    main()
