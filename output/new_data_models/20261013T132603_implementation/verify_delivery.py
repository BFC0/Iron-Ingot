"""Verify the final independent offline artifacts without rewriting them."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[3]
runs = [root / 'output/new_data_models' / name for name in (
    '20261013T152112212996+0800', '20261013T152122527055+0800',
    '20261013T152134292290+0800')]

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

hash_count = 0
for run in runs:
    verification = read(run / 'verification.json')
    assert verification['status'] == 'COMPLETE'
    assert verification['source_hashes_unchanged']
    assert not verification['platform_modified'] and not verification['old_models_replaced']
    for name, expected in verification['artifacts'].items():
        assert hashlib.sha256((run / name).read_bytes()).hexdigest() == expected, name
        hash_count += 1
    assert (run / '当前问题与不足.md').is_file()
    assert (run / '因缺数据无法验证.md').is_file()

manifests = [read(run / 'manifest.json') for run in runs]
assert all(m['input_hashes'] == manifests[0]['input_hashes'] for m in manifests)
splits = read(runs[1] / '划分.json')
for split in splits:
    held = str(split['held_market'])
    train, test = set(split['train_ids']), set(split['test_ids'])
    assert not train.intersection(test)
    assert all(key.split('|')[0] != held for key in train)
    assert all(key.split('|')[0] == held for key in test)

experiments = read(runs[1] / '实验.json')
models = read(runs[2] / '模型参数.json')
assert models['enabled'] is False and models['scope'] == 'research_only'
assert set(models['models']) == {key for key, item in experiments.items() if item.get('allowed_refit')}
assert len(models['models']) == 2
assert all('|practice|' in key for key in models['models'])
for key in models['models']:
    item = experiments[key]
    assert item['relative_improvement'] > .01
    assert item['improved_market_fraction'] >= 2 / 3
    assert item['delta_interval_95'][0] > 0
    assert item['bootstrap_samples'] == 1000 and item['seed'] == 20261013
assert experiments['B0']['max_abs_difference'] == 0
assert not any(item.get('allow_deployment') for item in experiments.values())
report = (runs[1] / 'report.html').read_text(encoding='utf-8')
assert '筛选字段或实验' in report and '相对改善 5.56%' in report and '相对改善 14.95%' in report
assert '<script src=' not in report
result = dict(status='PASS', artifact_hashes_checked=hash_count,
              disjoint_market_folds=len(splits), frozen_input_files=len(manifests[0]['input_hashes']),
              research_models=2, deployed_models=0, html_checked='静态内容，未重新核验浏览器交互',
              runs=[str(run.relative_to(root)) for run in runs])
(Path(__file__).parent / 'delivery_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
