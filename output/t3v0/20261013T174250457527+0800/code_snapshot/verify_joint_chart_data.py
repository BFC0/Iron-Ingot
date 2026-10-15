"""Pair same-capture SVG and JSON; do not count rendered copies as new samples."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from fit_chart_json import SOURCE, fit_points
from stepwise_model import NS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/visible_coefficients/20261012_round2_joint'


def svg_values(svg):
    tree = ET.fromstring(svg)
    plots = [r for r in tree.findall('.//s:rect', NS) if r.get('fill') == '#eeeeee'
             and float(r.get('width', 0)) > 500 and float(r.get('height', 0)) > 100]
    assert len(plots) == 1
    plot = plots[0]
    labels = [float(''.join(t.itertext())) for t in tree.findall('.//s:text', NS)
              if t.get('x') == '35.4' and re.fullmatch(r'\d+(\.\d+)?', ''.join(t.itertext()))]
    assert min(labels) == 0
    paths = [p.get('d') for p in tree.findall('.//s:path', NS)
             if p.get('stroke') == '#ffcd34' and len(p.get('d', '')) > 500]
    assert len(paths) == 1
    vertices = np.array([(float(x), float(y)) for x,y in
        re.findall(r'[ML](-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', paths[0])
        if float(x) >= float(plot.get('x'))])
    assert len(vertices) == 200 and np.all(np.diff(vertices[:,0]) > 0)
    values = (float(plot.get('y'))+float(plot.get('height'))-vertices[:,1])/float(plot.get('height'))*max(labels)
    return values, float(np.ptp(np.diff(vertices[:,0])))


def main():
    doc = json.loads(SOURCE.read_text(encoding='utf-8'))
    original = json.loads((ROOT/'output/visible_coefficients/20261012_round2_json/coefficients.json').read_text(encoding='utf-8'))
    sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert sha == original['source_sha256'] and doc['round'] == original['round'] == 2
    result = dict(source_sha256=sha, round=2, unique_points_per_curve=200,
                  method='Same-index pair; JSON y and label x for fit, SVG y for consistency verification; no duplicate training', curves={})
    for name, axis in [('rd','需求乘数'), ('operations','效率乘数')]:
        old = original['curves'][name]
        chart = next(c['data'] for c in doc['charts'] if c['id'] == old['chart_id'])
        svg = [s for s in doc['graphs'] if axis in s]
        assert len(svg) == 1
        sy, spacing_error = svg_values(svg[0])
        y = np.array([float(p['value']) for p in chart['dataset'][0]['data']])
        x = np.array([float(p['label']) for p in chart['categories'][0]['category']])
        discrepancy = float(np.max(abs(sy-y)))
        assert discrepancy < 1e-10, discrepancy
        fit = fit_points(x, y, old['form'])
        assert np.allclose(fit['parameters'],old['parameters'],rtol=1e-9,atol=1e-9)
        assert not set(fit['train_indices']) & set(fit['held_indices'])
        result['curves'][name] = dict(**fit, json_svg_y_max_difference=discrepancy,
                                      svg_pixel_spacing_variation=spacing_error,
                                      incremental_independent_samples=0)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines = ['# 同回合JSON与SVG联合核验', '',
             '两种表示来自同一次回合2采集，研发及运营各200个点按索引配对。',
             '使用JSON纵轴数值训练，以SVG渲染坐标还原的纵轴值交叉核验；每点只计一次。', '']
    for name,c in result['curves'].items():
        lines += [f"- {name}：JSON与SVG最大纵轴差异{c['json_svg_y_max_difference']:.3g}；配对去重拟合留点MAE {c['held_mae']:.9g}。"]
    lines += ['', 'SVG没有提供新增独立纵轴信息，配对去重后参数与JSON版一致；没有证据证明重复联合训练能提高精度。',
              'SVG使用类别轴的等像素间距，不证明实际投资数值必然等间距，不能据此恢复精确未取整x。可继续保留标签取整区间的敏感性结果。',
              '每回合仍需重新采集与拟合；本次没有改造整体需求模型的版本选择，也没有推断未来回合参数。']
    (OUT/'联合核验说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:dict(max_y_difference=v['json_svg_y_max_difference'],held_mae=v['held_mae']) for k,v in result['curves'].items()}))


if __name__ == '__main__':
    main()
