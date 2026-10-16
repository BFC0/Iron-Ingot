"""Fit archived round 5 curves independently within t5v0; preserve round 4 training."""
import csv
import importlib.util
import inspect
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

SOURCE = ROOT/'output/round_close/20261014_formal4_close/formal5_initial'
EXTRACTOR = SOURCE.parent/'frozen_review/verify_formal5_initial.py'


def main():
    spec = importlib.util.spec_from_file_location('formal5_source', EXTRACTOR)
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    read, sha = source.read, source.sha
    now = datetime.now(timezone(timedelta(hours=8)))
    out = ROOT/'output/t5v0'/(now.strftime('%Y%m%dT%H%M%S%f%z')+'_formal5_curves')
    out.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        with (out/name).open('x', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')

    log = out/'work_log.md'
    with log.open('x', encoding='utf-8') as f:
        f.write('# t5v0 · 回合5曲线工作日志\n\n'+now.isoformat()+'（北京时间）开始。\n'
                '用户授权立即执行原一次性任务。不要输出真名，姓名统一用首字母替代。\n'
                '范围：复用已核归档，独立拟合三条回合5曲线；保留原件及t5v0正式4训练。状态：进行中。\n')
    snapshot = out/'code_snapshot'
    snapshot.mkdir()
    code_paths = [Path(__file__), ROOT/'code/fit_chart_json.py', ROOT/'code/stepwise_model.py', EXTRACTOR, source.RULE]
    for path in code_paths:
        shutil.copy2(path, snapshot/path.name)
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in code_paths}
    acceptance = read(SOURCE/'acceptance.json')
    for name in ['formal5_curves.json', 'version_manifest.json', 'source_manifest.json',
                 'curves_original_chart_literals.json', 'curve_pairings.json',
                 'curve_source_svg_10.svg', 'curve_source_svg_11.svg']:
        path = SOURCE/name
        assert sha(path) == acceptance['output_hashes'][name], name
        manifest[path.relative_to(ROOT).as_posix()] = sha(path)
    manifest[(SOURCE/'acceptance.json').relative_to(ROOT).as_posix()] = sha(SOURCE/'acceptance.json')
    version = read(SOURCE/'version_manifest.json')
    assert version['valid_period'] == 'formal5' and version['market_id'] == 5
    for item in version['sources']:
        assert sha(ROOT/item['path']) == item['sha256'], item['path']
        manifest[item['path']] = item['sha256']
    assert sha(EXTRACTOR) == version['code_sha256'] and sha(source.RULE) == version['reused_rules_sha256']
    checklist = read(source.RAW/'own_formal5_decisionchecklist.json')
    assert any(s.get('selected') == '回合5' for s in checklist['selects'])
    raw_path = source.RAW/'own_formal5_productionplanning.json'
    raw = read(raw_path)
    assert '市场5' in raw['text'] or '市场 5' in raw['text']
    assert 'panel=productionplanning' in raw['url']
    charts, errors = source.rules.rules.charts(source.html(raw))
    assert not errors
    selected = [c for c in charts if c['id'] in ('quality.control.chart', 'cost.efficiency.chart')]
    assert selected == read(SOURCE/'curves_original_chart_literals.json')
    pairing_code = inspect.getsource(source.rules.pair_curve_y)
    assert pairing_code.count('> 500') == 1
    namespace = dict(source.rules.__dict__)
    # The archived viewport is 467.6px; reuse its verified 400px minimum.
    exec(pairing_code.replace('> 500', '> 400'), namespace)
    pairings = namespace['pair_curve_y'](selected, re.findall(r'<svg\b[\s\S]*?</svg>', source.html(raw), re.I))
    assert len(pairings) == 3 and all(p['status'] == 'pass_y_values' and p['points'] == 200 for p in pairings)
    docs = read(SOURCE/'formal5_curves.json')
    curves, rows = {}, []
    report = ['# t5v0 · 回合5曲线', '', f'拟合时间：{now.isoformat()}（北京时间）。',
              '不要输出真名，姓名统一用首字母替代。', '',
              '来源：已核归档的市场5、PYT正式5生产计划页，采集于2026-10-14 23:30:59（北京时间）。',
              '三条曲线各200点：偶数索引100点训练、奇数索引100点留出，最终参数再用全部200点拟合。',
              'JSON/SVG是同源表示，不增加独立样本。研发公式为`a+b*(x+c)**d`；运营为`a+b*x/(c+x)`。', '',
              '| 回合5曲线 | 参数a,b,c,d（运营无d） | 留出MAE | 留出最大误差 | 全点MAE | 全点最大误差 |',
              '|---|---|---:|---:|---:|---:|']
    for doc in docs:
        assert doc['valid_period'] == 'formal5' and doc['market_id'] == 5
        assert doc['source_sha256'] == sha(raw_path)
        chart = next(c for c in selected if c['id'] == doc['chart_id'])
        series = next(s for s in chart['data']['dataset'] if s['seriesname'] == doc['series'])
        x = np.array([float(p['label']) for p in chart['data']['categories'][0]['category']])
        y = np.array([float(p['value']) for p in series['data']])
        assert np.array_equal(x, np.array(doc['x_labels'], dtype=float))
        assert np.array_equal(y, np.array(doc['original_y_values'], dtype=float))
        assert len(x) == len(y) == 200 and x[0] == 0
        assert np.all(np.isfinite(x)) and np.all(np.isfinite(y)) and np.all(y > 0)
        assert np.all(np.diff(x) > 0) and np.all(np.diff(y) >= 0)
        name = doc['series'].split(', ')[1]
        upstream = doc['upstream_condition']
        prev, final = upstream['previous_formal4_actual_input'], upstream['final_group_source']
        for ref in (prev, final):
            assert sha(ROOT/ref['source_path']) == ref['sha256']
            manifest[ref['source_path']] = ref['sha256']
        assert prev['value'] == final['value'] == version['upstream_formal4_actual_inputs'][name]
        form = 'power' if doc['chart_id'] == 'quality.control.chart' else 'saturation'
        key = ('rd/' if form == 'power' else 'operations/')+name
        label = '回合5曲线 · '+name+('研发→需求乘数' if form == 'power' else '运营→效率乘数')
        fitted = fit_points(x, y, form)
        # shortcut: equal spacing remains a sensitivity assumption until unrounded x is available.
        ids = np.arange(1, len(x))
        low, high = float(np.max((x[1:]-.5)/ids)), float(np.min((x[1:]+.5)/ids))
        assert low <= high
        uniform_x = np.arange(len(x))*(low+high)/2
        assert np.max(abs(uniform_x-x)) <= .5+1e-10
        sensitivity = fit_points(uniform_x, y, form)
        grid = np.linspace(x[0], x[-1], 1000)
        sensitivity.update(assumption=True, step_interval=[low, high], max_prediction_difference=float(np.max(abs(
            curve_value(grid, fitted['parameters'], form)-curve_value(grid, sensitivity['parameters'], form)))))
        fitted.update(version='t5v0', round=5, label=label, form=form,
                      formula='a+b*(x+c)**d' if form == 'power' else 'a+b*x/(c+x)',
                      x_range=[float(x[0]), float(x[-1])], points=np.c_[x, y].tolist(),
                      source=doc['source_path'], source_sha256=sha(raw_path), upstream_condition=upstream,
                      json_svg_pairing=next(p for p in pairings if p['series'] == doc['series']),
                      equal_spacing_sensitivity=sensitivity)
        curves[key] = fitted
        prediction = curve_value(x, fitted['parameters'], form)
        rows.extend(dict(version='t5v0', round=5, label=label, index=i, x_kusd=float(a),
                         multiplier=float(b), fitted_multiplier=float(c), residual=float(c-b),
                         split='train' if i % 2 == 0 else 'held') for i, (a, b, c) in enumerate(zip(x, y, prediction)))
        report.append(f"| {label} | {fitted['parameters']} | {fitted['held_mae']:.9g} | {fitted['held_max_error']:.9g} | {fitted['full_mae']:.9g} | {fitted['full_max_error']:.9g} |")
    assert len(curves) == 3 and len(rows) == 600
    save('formal5_curves.json', dict(version='t5v0', round=5, valid_period='formal5', label='回合5曲线',
         market_id=5, area='PYT', generated_at=now.isoformat(), captured_at=raw['captured_at'],
         units='有效投资：千美元；乘数：无量纲', status='VISIBLE_CURVE_FIT_NOT_BUSINESS_VALIDATION',
         training_round4_use=False, curves=curves))
    with (out/'curve_points.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    report += ['', '## 来源、验证及使用边界', '',
               '原始600点与网页初始化JSON逐点一致，三条JSON/SVG重新配对通过；源文件SHA256与归档验收一致。',
               '上期正式4实际研发900/1300、运营750千美元已与小组最终决策来源核对。',
               '横轴为网页取整的有效投资标签，约±0.5千美元；自动支出到有效横轴映射未证明。',
               '等间距横轴仅作敏感性假设，参数及预测差异另存JSON。各曲线只适用其保存的横轴范围及市场5正式5情境。',
               '留点误差检验图形插值近似，不代表跨回合需求、效率或利润预测精度；其他市场未核验。',
               '本次未实时访问平台，复用已核归档；未重训或覆盖t5v0正式4模型，未修改或提交平台决策。', '',
               '[回合5曲线参数与600点](formal5_curves.json) · [600点CSV](curve_points.csv) · [来源哈希](source_hashes.json) · [验收](acceptance.json)']
    with (out/'report.md').open('x', encoding='utf-8') as f:
        f.write('\n'.join(report)+'\n')
    assert all(sha(ROOT/p) == digest for p, digest in manifest.items())
    save('source_hashes.json', manifest)
    save('acceptance.json', dict(status='PASS', version='t5v0', round=5, label='回合5曲线', curves=3, points=600,
         held_points_per_curve=100, original_points_equal_raw_html=True, json_svg_pairings=True,
         source_hashes_match_archive=True, upstream_inputs_paired=True, positive_monotone_grid=True,
         round4_training_unchanged=True, business_validation=False))
    with log.open('a', encoding='utf-8') as f:
        f.write('\n完成：三条回合5曲线、600点独立拟合；来源、上期投入、SVG、留点及正值单调检查通过。\n')
    save('output_hashes.json', {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()})
    print(out)
    print(json.dumps({k: {m: c[m] for m in ('held_mae', 'held_max_error', 'full_mae', 'full_max_error')} for k, c in curves.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
