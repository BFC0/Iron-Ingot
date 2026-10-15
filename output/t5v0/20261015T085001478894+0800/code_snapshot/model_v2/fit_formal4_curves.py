"""Fit the archived formal4 curves as a separate t4v0 artifact."""
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code')]
sys.dont_write_bytecode = True
import numpy as np
from fit_chart_json import fit_points
from stepwise_model import curve_value

SOURCE = ROOT/'output/round_close/20261013_formal3_close/formal4_initial/curves/20261014T004027'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open('x', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    out = ROOT/'output/t4v0'/f"{now.strftime('%Y%m%dT%H%M%S%f%z')}_formal4_curves"
    out.mkdir(parents=True, exist_ok=False)
    log = out/'work_log.md'
    log.write_text(f'# 回合4曲线拟合工作日志\n\n开始：{now.isoformat()}（北京时间）。\n'
                   '授权：立即执行，用回合4数据拟合网页曲线，保存到t4v0并明确标注回合4曲线。\n'
                   '不要输出真名，姓名统一用首字母替代。仅处理归档曲线，不填写平台决策。\n'
                   '状态：进行中。保留已有正式3训练结果及全部原件。\n', encoding='utf-8')
    snapshot = out/'code_snapshot'
    snapshot.mkdir()
    for path in [Path(__file__), ROOT/'code/fit_chart_json.py', ROOT/'code/stepwise_model.py']:
        shutil.copy2(path, snapshot/path.name)
    spec = importlib.util.spec_from_file_location('formal4_extraction', SOURCE/'extract.py')
    extraction = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extraction)
    version = read(SOURCE/'version_index.json')
    raw_path = ROOT/version['sources'][0]['path']
    assert sha(raw_path) == version['sources'][0]['sha256']
    raw = read(raw_path)
    assert raw['market'] == 5 and raw['area'] == 'PYT' and raw['selected_period']['id'] == 'formal4'
    charts, errors = extraction.rules.rules.charts(raw['html'])
    assert not errors
    svg = re.findall(r'<svg\b[\s\S]*?</svg>', raw['html'], re.I)
    pairings = extraction.rules.pair_curve_y(charts, svg)
    assert len(pairings) == 3 and all(p['status'] == 'pass_y_values' for p in pairings)
    manifest = {str(p.relative_to(ROOT)): sha(p) for p in [raw_path, SOURCE/'version_index.json', SOURCE/'extract.py']}
    curves, rows, panels = {}, [], []
    report = ['# t4v0 · 回合4曲线', '', f'拟合时间：{now.isoformat()}（北京时间）。',
              '来源：市场5，PYT个人生产计划页的正式4归档。三条曲线各200点，共600点。',
              '每条曲线按偶数索引100点训练、奇数索引100点留出，再以全部200点拟合最终参数。',
              'JSON与SVG仅是同一批点的两种表示，不重复计权。', '',
              '| 曲线 | 参数a,b,c,d（运营无d） | 留出MAE | 留出最大误差 | 全点MAE | 全点最大误差 |',
              '|---|---|---:|---:|---:|---:|']
    for item in read(SOURCE/'curve_index.json'):
        path = SOURCE/item['file']
        manifest[str(path.relative_to(ROOT))] = sha(path)
        doc = read(path)
        assert doc['valid_period'] == 'formal4' and doc['market'] == 5
        assert doc['source_sha256'] == sha(raw_path)
        chart = next(c for c in charts if c['id'] == doc['chart_id'])
        series = next(s for s in chart['data']['dataset'] if s['seriesname'] == doc['series'])
        x = np.array([float(p['label']) for p in chart['data']['categories'][0]['category']])
        y = np.array([float(p['value']) for p in series['data']])
        assert np.array_equal(x, np.array(doc['x_labels'], dtype=float))
        assert np.array_equal(y, np.array(doc['original_y_values'], dtype=float))
        assert len(x) == len(y) == 200 and x[0] == 0
        assert np.all(np.isfinite(x)) and np.all(np.isfinite(y))
        assert np.all(np.diff(x) > 0) and np.all(np.diff(y) >= 0) and np.all(y > 0)
        form = 'power' if doc['chart_id'] == 'quality.control.chart' else 'saturation'
        title = '回合4曲线 · '+doc['series'].split(', ')[1]+('研发→需求乘数' if form == 'power' else '运营→效率乘数')
        fitted = fit_points(x, y, form)
        # shortcut: uniform spacing is only a sensitivity assumption until unrounded x is available.
        indices = np.arange(1, len(x))
        low, high = float(np.max((x[1:]-.5)/indices)), float(np.min((x[1:]+.5)/indices))
        assert low <= high
        uniform_x = np.arange(len(x))*(low+high)/2
        assert np.max(abs(uniform_x-x)) <= .5+1e-10
        sensitivity = fit_points(uniform_x, y, form)
        fitted.update(version='t4v0', round=4, label=title, form=form,
                      formula='a+b*(x+c)**d' if form == 'power' else 'a+b*x/(c+x)',
                      points=np.c_[x, y].tolist(), x_range=[float(x[0]), float(x[-1])],
                      source=str(raw_path.relative_to(ROOT)), source_sha256=sha(raw_path),
                      upstream_condition=doc['upstream_condition'],
                      json_svg_pairing=next(p for p in pairings if p['series'] == doc['series']),
                      equal_spacing_sensitivity=dict(**sensitivity, step_interval=[low, high], assumption=True))
        curves[item['file'].removesuffix('.json')] = fitted
        predicted = curve_value(x, fitted['parameters'], form)
        rows.extend(dict(version='t4v0', round=4, curve_label=title, index=i, x_kusd=float(a),
                         original_multiplier=float(b), fitted_multiplier=float(c), residual=float(c-b),
                         split='train' if i % 2 == 0 else 'held') for i, (a, b, c) in enumerate(zip(x, y, predicted)))
        report.append(f"| {title} | {fitted['parameters']} | {fitted['held_mae']:.9g} | {fitted['held_max_error']:.9g} | {fitted['full_mae']:.9g} | {fitted['full_max_error']:.9g} |")
        def line(values):
            return ' '.join(f'{60+float(a)/x[-1]*780:.3f},{280-float(b)/1.25*230:.3f}' for a, b in zip(x, values))
        panels.append(f'<section><h2>{title}</h2><p>公式：{fitted["formula"]}；上期实际投入：{doc["upstream_condition"]["previous_value"]:g}千美元。</p>'
                      f'<svg viewBox="0 0 900 340" role="img" aria-label="{title}，原始值与拟合值对照">'
                      '<path d="M60,40V280H840" fill="none" stroke="#666"/>'
                      f'<polyline points="{line(y)}" fill="none" stroke="#167786" stroke-width="3"/>'
                      f'<polyline points="{line(predicted)}" fill="none" stroke="#ce623a" stroke-width="2" stroke-dasharray="6 4"/>'
                      f'<text x="60" y="305">0</text><text x="760" y="305">{x[-1]:g} 千美元</text>'
                      '<text x="12" y="280">0</text><text x="8" y="52">1.25</text><text x="60" y="24">乘数（无量纲）</text></svg>'
                      f'<p>留出MAE {fitted["held_mae"]:.9g}；最大误差 {fitted["held_max_error"]:.9g}。</p></section>')
    assert len(curves) == 3 and len(rows) == 600
    result = dict(version='t4v0', round=4, label='回合4曲线', market=5, area='PYT',
                  generated_at=now.isoformat(), captured_at=raw.get('captured_at'),
                  status='FORMAL4_VISIBLE_CURVE_FIT_NOT_DEMAND_VALIDATION', training_use=False,
                  units='有效投资：千美元；乘数：无量纲', curves=curves)
    save(out/'formal4_curves.json', result)
    with (out/'curve_points.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    report += ['', '## 当前不足与使用边界', '',
               '横轴为网页取整后的有效投资标签（约±0.5千美元），不是当期支出；等间距结果仅作敏感性假设。',
               '适用归档的市场5、正式4情境与上期研发1000/400、运营600千美元条件；不将其他团队或回合视作相同曲线。',
               '研发用于需求乘数，运营用于效率乘数；仅在保存的横轴范围内使用。', '',
               '## 缺乏数据而无法验证', '',
               '正式4实际经营结果、投入跨期映射及其他市场曲线未在本次验证；图形拟合误差不等于经营预测误差。',
               '本次只新增回合4曲线，正式3训练注册表和参数保留；未向平台写入决策。']
    (out/'report.md').write_text('\n'.join(report)+'\n', encoding='utf-8')
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>t4v0 · 回合4曲线</title><style>body{font:16px system-ui;background:#f4f2ed;color:#222;max-width:1100px;margin:40px auto}section{background:white;padding:24px;margin:24px 0}svg{width:100%}a{color:#167786}</style><h1>t4v0 · 回合4曲线</h1><p>市场5 · 正式4 · 600点。青色实线为网页原始值，橙色虚线为拟合值。</p><p>横轴为有效投资标签，已取整；仅验证图形近似，经营结果与跨期映射尚待验证。</p><p><a href="report.md">完整报告及参数</a> · <a href="formal4_curves.json">JSON</a> · <a href="curve_points.csv">600点CSV</a></p>'+''.join(panels)+'</html>'
    (out/'report.html').write_text(html, encoding='utf-8')
    assert all(sha(ROOT/p) == digest for p, digest in manifest.items())
    save(out/'source_hashes.json', manifest)
    save(out/'acceptance.json', dict(status='PASS', curves=3, points=600, round=4, version='t4v0',
                                   source_identity=True, source_unchanged=True, json_svg_pairings=True,
                                   held_points_per_curve=100, positive_monotone_grid=True,
                                   original_points_equal_raw_html=True, business_validation=False))
    with log.open('a', encoding='utf-8') as f:
        f.write('\n完成：三条回合4曲线拟合；600点、来源身份/哈希、JSON/SVG、留点、正值单调性检查通过。\n'
                '已保存JSON、CSV、中文HTML/Markdown及代码快照。正式3注册表未修改。\n')
    save(out/'output_hashes.json', {p.name: sha(p) for p in out.iterdir() if p.is_file()})
    print(out)
    print(json.dumps({k: {m: c[m] for m in ('held_mae', 'held_max_error', 'full_mae')} for k, c in curves.items()}))


if __name__ == '__main__':
    main()
