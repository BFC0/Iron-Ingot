"""Digitize the archived practice-2 screenshot; never replace model inputs."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from fit_chart_json import fit_points
from stepwise_model import curve_value

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'sources/用户提供_练习回合2_production.png'
OUT = ROOT / 'output/visible_coefficients/practice2_screenshot'


def main():
    im = Image.open(SOURCE).convert('RGB')
    assert im.size == (1164, 1119), 'Calibration applies only to the archived original image.'
    a = np.asarray(im)
    # shortcut: manually read tick anchors have ±2 px uncertainty; replace with practice-2 JSON when available.
    y_ticks = np.array([838.5, 865.4, 892.2, 918.8, 945.8, 972.6, 999.3])
    y_axis = np.polyfit(y_ticks, [1.2, 1, .8, .6, .4, .2, 0], 1)
    assert np.max(abs(np.polyval(y_axis, y_ticks)-np.arange(1.2, -.01, -.2))) < .002
    formal = json.loads((ROOT / 'output/visible_coefficients/20261012_round2_json/coefficients.json').read_text(encoding='utf-8'))
    result = dict(source=str(SOURCE.relative_to(ROOT)), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  phase='practice', round=2, identity_basis='User-provided screenshot; market and capture time unverified',
                  status='SCREENSHOT_APPROXIMATION_NOT_PLATFORM_PARAMETERS',
                  units='Effective investment: thousand USD; multiplier: dimensionless',
                  calibration_uncertainty_pixels=2, y_axis_pixel_to_value=y_axis.tolist(), curves={})
    overlay = im.copy()
    draw = ImageDraw.Draw(overlay)
    report = ['# 练习回合2截图曲线拟合', '', '来源：用户提供的练习2生产计划截图，原图1164×1119像素。',
              '复用现有幂函数与饱和函数；仅保存独立结果，不替换任何冻结模型。', '',
              '横轴为有效投资（千美元），不是当期研发/运营支出。纵轴为无量纲乘数。',
              '按橙黄色像素逐列取线条中位位置；剔除圆形回合效果标记及左端陡峭区域。',
              '每隔4像素取点，交错拟合与留点核验；同一条截图曲线的留点并非独立需求验证。',
              '刻度锚点由原图读出，采用±2像素坐标标定敏感性检查；它不是统计置信区间。', '']
    for name, left, right, labels, marker, form in [
        ('rd', 80, 516, [0,121,241,362,482,603,724,844,965,1085], (345,364), 'power'),
        ('operations', 614, 1050, [0,152,304,456,608,760,912,1064,1216,1368], (879,898), 'saturation')]:
        ticks = left + np.arange(10)*44
        x_axis = np.polyfit(ticks, labels, 1)
        assert np.max(abs(np.polyval(x_axis, ticks)-labels)) <= .6
        mask = (a[:,:,0] > 245) & (a[:,:,1] > 175) & (a[:,:,1] < 230) & (a[:,:,2] < 125)
        pixels = []
        for px in range(left+4, right, 4):
            if marker[0] <= px <= marker[1]:
                continue
            ys = np.flatnonzero(mask[839:999, px])+839
            assert len(ys), (name, px, 'Missing curve pixel')
            if ys[-1]-ys[0] > 3:
                continue
            pixels.append([px, float(np.median(ys))])
        pixels = np.array(pixels)
        x = np.polyval(x_axis, pixels[:,0])
        y = np.polyval(y_axis, pixels[:,1])
        assert len(x) > 80 and np.all(np.diff(x) > 0) and np.all((y > 0) & (y < 1.2))
        fit = fit_points(x, y, form)
        assert fit['held_max_error'] < .01
        grid = np.linspace(x[0], x[-1], 400)
        fitted = curve_value(grid, fit['parameters'], form)
        exact = curve_value(grid, formal['curves'][name]['parameters'], form)
        delta = fitted-exact
        sensitivity = []
        # Shift each axis origin and scale independently; 16 calibration corner cases.
        for xo in [-2,2]:
            for xs in [-2,2]:
                sx = (pixels[:,0]-left-xo)*x_axis[0]*396/(396+xs)
                for yo in [-2,2]:
                    for ys in [-2,2]:
                        sy = (999.3+yo-pixels[:,1])*1.2/(160.8+ys)
                        sf = fit_points(np.maximum(sx,0), sy, form)
                        sensitivity.append(curve_value(grid, sf['parameters'], form))
        sensitivity = np.array(sensitivity)
        uncertainty = np.max(abs(sensitivity-fitted), axis=0)
        supported = abs(delta) > uncertainty + formal['curves'][name]['full_max_error'] + fit['full_max_error']
        comparison = dict(grid=grid.tolist(), difference=delta.tolist(), calibration_deviation=uncertainty.tolist(),
                          fraction_exceeding_calibration_and_fit_errors=float(np.mean(supported)),
                          max_abs_difference=float(np.max(abs(delta))))
        examples = []
        for v in [200,400,600,800,1000]:
            i = int(np.argmin(abs(grid-v)))
            examples.append(dict(effective_investment=v, practice=float(curve_value(v,fit['parameters'],form)),
                                 formal=float(curve_value(v,formal['curves'][name]['parameters'],form)),
                                 calibration_deviation=float(uncertainty[i])))
        result['curves'][name] = dict(**fit, form=form, pixels=pixels.tolist(), points=np.c_[x,y].tolist(),
                                     tick_pixels=ticks.tolist(), tick_labels=labels, x_axis_pixel_to_value=x_axis.tolist(),
                                     marker_exclusion_pixel_x=marker, observed_range=[float(x[0]),float(x[-1])],
                                     comparison=comparison, examples=examples)
        inverse_x = (grid-x_axis[1])/x_axis[0]
        inverse_y = (fitted-y_axis[1])/y_axis[0]
        draw.line(list(zip(inverse_x,inverse_y)), fill='#1268d3', width=2)
        for px,py in pixels[::4]:
            draw.ellipse((px-2,py-2,px+2,py+2), fill='#c62828')
        title = '研发→需求乘数' if name == 'rd' else '运营→效率乘数'
        formula = 'a+b*(x+c)**d' if form == 'power' else 'a+b*x/(c+x)'
        report += [f'## {title}', '', f'公式：`{formula}`；参数：`{fit["parameters"]}`。',
                   f'提取{len(x)}点，可观测有效投资范围{x[0]:.1f}–{x[-1]:.1f}千美元。',
                   f'留点平均绝对误差{fit["held_mae"]:.6f}，最大误差{fit["held_max_error"]:.6f}。',
                   '', '| 有效投资，千美元 | 练习2截图拟合 | 正式2 JSON拟合 | 坐标敏感性最大偏差 |',
                   '|---:|---:|---:|---:|']
        report += [f'| {r["effective_investment"]} | {r["practice"]:.4f} | {r["formal"]:.4f} | {r["calibration_deviation"]:.4f} |' for r in examples]
        report += ['', f'共同观测范围最大乘数差{comparison["max_abs_difference"]:.4f}；网格中{np.mean(supported):.1%}的差异超过本次坐标敏感性偏差与两边拟合最大误差之和。', '']
    report += ['## 比较结论', '',
               '在200–1000千美元有效投资样例中，练习2研发截图拟合比正式2拟合高约0.030–0.038，运营高约0.004–0.005。',
               '本次保守判据下，两曲线均没有点足以排除相同曲线的可能；不能证明相同，也不能严格证明不同。',
               '小的留点误差说明公式能近似截图线条，不代表像素标定、来源身份或实际需求机制已经验证。', '',
               '## 边界', '', '近零区域斜率高、像素分辨率不足，未外推0投入乘数。参数是图形近似，不能当作后台真实参数。',
               '坐标敏感性只覆盖上述±2像素标定变化，未覆盖所有截图缩放、来源身份或后台机制不确定性。',
               '曲线相容不等于严格相同；可见差异也不直接证明后台机制变更。销售需求乘数不在本次拟合范围。',
               '叠加核验图：蓝线为拟合，红点为部分提取点。来源SHA256：`'+result['source_sha256']+'`。']
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'coefficients.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (OUT/'拟合报告.md').write_text('\n'.join(report)+'\n', encoding='utf-8')
    overlay.save(OUT/'pixel_fit_overlay.png')
    print(json.dumps({k:dict(parameters=v['parameters'], held_max=v['held_max_error'], examples=v['examples'],
                            fraction_distinguishable=v['comparison']['fraction_exceeding_calibration_and_fit_errors'])
                      for k,v in result['curves'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
