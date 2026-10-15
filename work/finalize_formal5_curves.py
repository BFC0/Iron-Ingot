"""Verify saved round 5 fits and register their documentation without replacing training."""
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code')]
sys.dont_write_bytecode = True
import numpy as np
from stepwise_model import curve_value


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


out = Path(sys.argv[1]).resolve()
assert out.parent == ROOT/'output/t5v0' and out.name.endswith('_formal5_curves')
for name, base in [('source_hashes.json', ROOT), ('output_hashes.json', out)]:
    assert all(sha(base/p) == digest for p, digest in read(out/name).items())
result = read(out/'formal5_curves.json')
assert (result['version'], result['round'], result['label']) == ('t5v0', 5, '回合5曲线')
with (out/'curve_points.csv').open(encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 600 and all(r['version'] == 't5v0' and r['round'] == '5' for r in rows)
for curve in result['curves'].values():
    assert curve['round'] == 5 and curve['label'].startswith('回合5曲线')
    xy = np.array(curve['points'])
    error = curve_value(xy[:, 0], curve['parameters'], curve['form'])-xy[:, 1]
    held = curve['held_indices']
    held_error = curve_value(xy[held, 0], curve['train_parameters'], curve['form'])-xy[held, 1]
    assert len(held) == 100 and set(held).isdisjoint(curve['train_indices'])
    for error_values, prefix in [(error, 'full'), (held_error, 'held')]:
        assert np.isclose(np.mean(abs(error_values)), curve[prefix+'_mae'], rtol=1e-12, atol=1e-14)
        assert np.isclose(np.max(abs(error_values)), curve[prefix+'_max_error'], rtol=1e-12, atol=1e-14)
    selected = [r for r in rows if r['label'] == curve['label']]
    assert len(selected) == 200
    assert np.allclose([float(r['fitted_multiplier']) for r in selected], error+xy[:, 1], rtol=1e-12)
assert not list(out.rglob('*.html'))

rel = out.relative_to(ROOT).as_posix()
description = '回合5三曲线600点独立拟合，标注“回合5曲线”；上期投入900/1300/750千美元。保留正式4训练注册表；图形近似不代表经营预测精度。'
row = f'| 正式5曲线（t5v0独立保存） | [回合5曲线报告]({rel}/report.md)、[参数]({rel}/formal5_curves.json)、[验收]({rel}/acceptance.json) | {description} |\n'
changes = {}
for name in ['README.md', '训练拟合模型与版本清单.md', '训练拟合模型与版本清单_文字说明版.md']:
    p = ROOT/name
    text = p.read_text(encoding='utf-8-sig')
    anchor = '| 最新实际训练（有缺口）' if name == 'README.md' else '| 正式4最新实际训练'
    assert text.count(anchor) == 1, name
    changes[p] = text.replace(anchor, row+anchor, 1)
section = '\n## t5v0 · 回合5曲线（独立产物）\n\n'+description+'\n\n'
for name, prefix in [('code/model_v2/t5v0_README.md', '../../'), ('模型说明/T5V0_正式4训练与缺口.md', '../')]:
    p = ROOT/name
    text = p.read_text(encoding='utf-8-sig')
    assert '## t5v0 · 回合5曲线（独立产物）' not in text
    changes[p] = text.rstrip()+'\n'+section+f'[报告]({prefix}{rel}/report.md) · [参数]({prefix}{rel}/formal5_curves.json) · [验收]({prefix}{rel}/acceptance.json)。\n\n复现：`python code/model_v2/fit_formal5_curves.py`；每次独立输出。\n'

backup = out/'documentation_before'
backup.mkdir(exist_ok=False)
hashes = []
for path, text in changes.items():
    target = backup/path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    before = sha(path)
    assert sha(target) == before
    path.write_text(text, encoding='utf-8')
    hashes.append(dict(path=path.relative_to(ROOT).as_posix(), before_sha256=before, after_sha256=sha(path),
                       backup=target.relative_to(out).as_posix()))
    links = re.findall(r'\[[^\]]*\]\(([^)]+)\)', text)
    added = [link for link in links if out.name in link]
    assert len(added) == 3 and all((path.parent/link).is_file() for link in added)
for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', (out/'report.md').read_text(encoding='utf-8')):
    assert (out/link).is_file()
with (out/'documentation_hashes.json').open('x', encoding='utf-8') as f:
    json.dump(hashes, f, ensure_ascii=False, indent=2)
shutil.copy2(Path(__file__), out/'code_snapshot'/Path(__file__).name)
with (out/'final_verification.json').open('x', encoding='utf-8') as f:
    json.dump(dict(status='PASS', round=5, version='t5v0', curves=3, points=600, source_hashes=True,
                   recomputed_full_and_held_metrics=True, csv_predictions_match=True,
                   documentation_backups_and_hashes=True, added_links_valid=True,
                   no_html_report=True, business_validation=False), f, ensure_ascii=False, indent=2)
with (out/'work_log.md').open('a', encoding='utf-8') as f:
    f.write('\n交付验收：独立复算全点/留点误差与CSV一致；五份说明已按磁盘现状备份，改前/改后哈希及新增链接通过。\n'
            '未实时访问平台、未验证自动支出映射或经营预测；原一次性任务已处于PAUSED，不另建重复任务。\n')
with (out/'final_output_hashes.json').open('x', encoding='utf-8') as f:
    json.dump({p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file() and p.name != 'final_output_hashes.json'}, f, ensure_ascii=False, indent=2)
print('PASS: 3 curves, 600 points, independent metric/CSV verification; 5 document backups, hashes and links.')
