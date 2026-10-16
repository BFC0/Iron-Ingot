"""Fit and verify all archived formal6 input curves without changing application models."""
import csv
import hashlib
import importlib.util
import inspect
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code')]
import numpy as np
from fit_chart_json import fit_points
from stepwise_model import curve_value

SOURCE = ROOT/'output/round_close/20261015_formal5_close/formal6_initial'
RULE = ROOT/'output/round_close/20261013_formal3_close/historical_supplement/audit/verify_historical_supplement.py'
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    out = ROOT/'output/formal6_curves'/now.strftime('%Y%m%dT%H%M%S%f%z')
    out.mkdir(parents=True, exist_ok=False)

    def save(name, obj):
        with (out/name).open('x', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')

    log = out/'work_log.md'
    log.write_text(f'# 回合6全部曲线拟合\n\n{now.isoformat()}（北京时间）开始；状态：进行中。\n'
                   '授权：用户要求立即执行原定时任务。复用归档，独立交付全部投入曲线。\n'
                   '不要输出真名，姓名统一用首字母替代。保留原件、已有修改及应用模型。\n', encoding='utf-8')
    sources = {}
    for item in read(SOURCE/'source_manifest.json'):
        assert sha(ROOT/item['source']) == item['sha256'], item['source']
        sources[item['source']] = item['sha256']
    for p in list(SOURCE.glob('*')) + [Path(__file__), RULE, ROOT/'code/fit_chart_json.py', ROOT/'code/stepwise_model.py']:
        if p.is_file():
            sources[p.relative_to(ROOT).as_posix()] = sha(p)
    frozen = ROOT/'output/t6v1/20261016T001633520/models_full.json'
    sources[frozen.relative_to(ROOT).as_posix()] = sha(frozen)
    previous = read(SOURCE/'previous_actual_inputs.json')
    assert [p['previous_actual']['value'] for p in previous] == [2600., 231., 754.]
    for item in previous:
        for key in ['previous_actual', 'final_group']:
            ref = item[key]
            path = ROOT/ref['source']
            assert sha(path) == ref['sha256']
            assert float(re.sub(r'\s', '', str(read(path)['tables'][ref['table']][ref['row']][ref['column']]))) == item['previous_actual']['value']
            sources[path.relative_to(ROOT).as_posix()] = sha(path)
    raw = read(SOURCE.parent/'own_formal6_productionplanning.json')
    checklist = read(SOURCE.parent/'own_formal6_decisionchecklist.json')
    assert any(s.get('selected') == '回合6' for s in checklist['selects'])
    assert 'panel=productionplanning' in raw['url']
    spec = importlib.util.spec_from_file_location('curve_rules', RULE)
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    html = ''.join(raw['html_parts'])
    charts, errors = rules.rules.charts(html)
    assert not errors
    charts = [c for c in charts if c['id'] in ['quality.control.chart', 'cost.efficiency.chart']]
    assert charts == read(SOURCE/'curve_original_literals.json')
    pairing_code = inspect.getsource(rules.pair_curve_y)
    assert pairing_code.count('> 500') == 1
    namespace = dict(rules.__dict__)
    # Archived SVG viewport is below 500px; reuse the archived 400px threshold.
    exec(pairing_code.replace('> 500', '> 400'), namespace)
    pairings = namespace['pair_curve_y'](charts, re.findall(r'<svg\b[\s\S]*?</svg>', html, re.I))
    assert pairings == read(SOURCE/'curve_pairings.json')
    assert len(pairings) == 3 and all(p['status'] == 'pass_y_values' and p['points'] == 200 for p in pairings)
    curves, rows = {}, []
    frozen_curves = read(frozen)['curves']
    report = ['# 回合6全部投入曲线拟合', '', f'执行时间：{now.isoformat()}（北京时间）。', '',
              '覆盖市场5、PYT已归档正式6生产计划页的全部三条投入曲线，共600点；原件采集时间：'+raw['captured_at']+'。',
              '每条偶数索引100点训练、奇数索引100点留出，最终参数使用全部200点；乘数无量纲，横轴有效投资单位为千美元。',
              '研发公式：`a+b*(x+c)**d`；运营公式：`a+b*x/(c+x)`。横轴是取整标签，约±0.5千美元。', '',
              '| 曲线 | 有效投资范围（千美元） | 参数a,b,c,d（运营无d） | 留点MAE | 留点最大误差 | 全点MAE | 全点最大误差 |',
              '|---|---|---|---:|---:|---:|---:|']
    for chart in charts:
        x = np.array([float(re.sub(r'\s', '', p['label'])) for p in chart['data']['categories'][0]['category']])
        for series in chart['data']['dataset']:
            if not series['seriesname'].startswith('曲线,'):
                continue
            name = series['seriesname'].split(', ')[1]
            form = 'power' if chart['id'] == 'quality.control.chart' else 'saturation'
            key = ('rd/' if form == 'power' else 'operations/')+name
            y = np.array([float(p['value']) for p in series['data']])
            assert len(x) == len(y) == 200 and x[0] == 0
            assert np.isfinite(x).all() and np.isfinite(y).all() and np.all(y > 0)
            assert np.all(np.diff(x) > 0) and np.all(np.diff(y) >= 0)
            fit = fit_points(x, y, form)
            ids = np.arange(1, len(x))
            low, high = float(max((x[1:]-.5)/ids)), float(min((x[1:]+.5)/ids))
            assert low <= high
            # shortcut: equal spacing is a sensitivity assumption until unrounded x is available.
            uniform_x = np.arange(len(x))*(low+high)/2
            assert max(abs(uniform_x-x)) <= .5+1e-10
            sensitivity = fit_points(uniform_x, y, form)
            grid = np.linspace(x[0], x[-1], 1000)
            sensitivity.update(assumption='等间距横轴，仅作敏感性分析', step_interval=[low, high],
                max_prediction_difference=float(max(abs(curve_value(grid, fit['parameters'], form)-curve_value(grid, sensitivity['parameters'], form)))))
            assert np.array_equal(np.c_[x, y], frozen_curves[key]['points'])
            assert np.allclose(fit['parameters'], frozen_curves[key]['parameters'], rtol=1e-10, atol=1e-12)
            predicted = curve_value(x, fit['parameters'], form)
            held = fit['held_indices']
            assert len(held) == 100 and set(held).isdisjoint(fit['train_indices'])
            for residual, prefix in [(predicted-y, 'full'), (curve_value(x[held], fit['train_parameters'], form)-y[held], 'held')]:
                assert np.isclose(np.mean(abs(residual)), fit[prefix+'_mae'], rtol=1e-12, atol=1e-14)
                assert np.isclose(max(abs(residual)), fit[prefix+'_max_error'], rtol=1e-12, atol=1e-14)
            curves[key] = dict(fit, round=6, form=form, x_range=[float(x[0]), float(x[-1])], points=np.c_[x, y].tolist(),
                equal_spacing_sensitivity=sensitivity, source=raw['url'], chart_id=chart['id'], series=series['seriesname'])
            rows.extend(dict(curve=key, round=6, index=i, x_kusd=float(a), multiplier=float(b), fitted_multiplier=float(c),
                residual=float(c-b), split='train' if i % 2 == 0 else 'held') for i, (a, b, c) in enumerate(zip(x, y, predicted)))
            report.append(f"| {key} | {x[0]:g}–{x[-1]:g} | {fit['parameters']} | {fit['held_mae']:.9g} | {fit['held_max_error']:.9g} | {fit['full_mae']:.9g} | {fit['full_max_error']:.9g} |")
    assert set(curves) == {'rd/复合梁', 'rd/连接件', 'operations/泰国'} and len(rows) == 600
    save('formal6_curves.json', dict(round=6, market_id=5, area='PYT', status='VISIBLE_CURVE_FIT_NOT_BUSINESS_VALIDATION',
        captured_at=raw['captured_at'], generated_at=now.isoformat(), units='有效投资千美元；乘数无量纲',
        previous_actual_inputs=previous, curves=curves, json_svg_pairings=pairings))
    with (out/'curve_points.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with (out/'curve_points.csv').open(encoding='utf-8-sig', newline='') as f:
        saved = list(csv.DictReader(f))
    assert len(saved) == 600 and all(float(a['fitted_multiplier']) == b['fitted_multiplier'] for a, b in zip(saved, rows))
    report += ['', '## 核验与适用边界', '',
        '原始JSON重新提取及JSON/SVG三条配对通过；SVG不增加独立样本。上期正式5实际研发2600/231、运营754千美元与最终小组方案逐项核对。',
        '重新拟合参数及600点与既有t6v1一致。正值、单调、留点及CSV复算检查通过。',
        '适用范围为所归档市场5正式6及上述横轴区间。等间距横轴敏感性参数及预测差异保存在JSON；不是未经取整的真实横轴。',
        '有效投资不等于当期支出；上期投入不代表完整历史存量。未独立识别正式6当期支出到有效投资的映射。',
        '图形插值误差不代表需求、效率或利润预测精度，未验证其他市场或跨回合泛化。',
        '本次复用归档，未实时访问平台；未重训经营模型、重做决策优化或修改平台输入；既有t6v0/t6v1和历史模型保持原样。', '',
        '[曲线参数与600点](formal6_curves.json) · [逐点CSV](curve_points.csv) · [验收](acceptance.json) · [来源哈希](source_hashes.json)', '',
        '复现：使用项目NumPy/SciPy环境运行 `python code/model_v2/fit_formal6_curves.py`，每次输出独立目录。']
    (out/'report.md').write_text('\n'.join(report)+'\n', encoding='utf-8')
    snapshot = out/'code_snapshot'; snapshot.mkdir()
    for p in [Path(__file__), ROOT/'code/fit_chart_json.py', ROOT/'code/stepwise_model.py']:
        shutil.copy2(p, snapshot/p.name)
    save('source_hashes.json', sources)
    assert all(sha(ROOT/p) == h for p, h in sources.items())
    save('acceptance.json', dict(status='PASS', round=6, curves=3, points=600, held_points_per_curve=100,
        source_hashes_verified=True, original_json_reextracted=True, json_svg_pairings=True, previous_inputs_paired=True,
        metrics_recomputed=True, csv_verified=True, t6v1_matches=True, business_validation=False))
    rel = out.relative_to(ROOT).as_posix()
    documents = {'README.md': ('| 回合6终局条件应用 |',
        f'| 正式6全部投入曲线 | [拟合报告]({rel}/report.md)、[参数]({rel}/formal6_curves.json)、[验收]({rel}/acceptance.json) | 三曲线600点独立重拟合；100点/条留出；与t6v1一致，上期投入2600/231/754已配对。仅图形近似，支出映射及经营预测未独立验证。 |\n'),
        'code/model_v2/README.md': ('- [t6v1终局应用]',
        f'- [正式6全部曲线](../../{rel}/report.md)：三曲线600点，独立复算与t6v1一致；运行 `python code/model_v2/fit_formal6_curves.py`。\n\n')}
    changes = []
    for name, (anchor, addition) in documents.items():
        path = ROOT/name
        text = path.read_text(encoding='utf-8-sig')
        assert text.count(anchor) == 1
        backup = out/'documents_before'/name; backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        before = sha(path); assert sha(backup) == before
        # Replace the current curve entry on reruns, preserving historical output directories.
        text = re.sub(r'^\| 正式6全部投入曲线 \|.*\n', '', text, flags=re.M)
        text = re.sub(r'^- \[正式6全部曲线\].*\n\n', '', text, flags=re.M)
        path.write_text(text.replace(anchor, addition+anchor, 1), encoding='utf-8')
        changes.append(dict(path=name, before_sha256=before, after_sha256=sha(path), backup=backup.relative_to(out).as_posix()))
    save('document_changes.json', changes)
    for path in [out/'report.md']+[ROOT/p for p in documents]:
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if path == out/'report.md' or out.name in link:
                assert (path.parent/link).is_file(), link
    assert all(sha(ROOT/p) == h for p, h in sources.items())
    with log.open('a', encoding='utf-8') as f:
        f.write('\n验收完成：三曲线600点拟合、来源哈希、SVG、上期投入、留点/全点误差、CSV及t6v1一致性通过；两份说明按当前磁盘内容备份，改前/改后哈希及新增链接通过。未生成HTML报告。\n')
    save('output_hashes.json', {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()})
    print(out)
    print(json.dumps({k: {m: c[m] for m in ['x_range', 'held_mae', 'held_max_error', 'full_max_error']} for k, c in curves.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
