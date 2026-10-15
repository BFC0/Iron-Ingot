"""Verify t3v1 provenance, training boundaries and protected t3v0 artifacts."""
import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1]).resolve()
assert out.is_relative_to(root/'output/t3v1')
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = read(out/'manifest.json')
assert manifest['version'] == 't3v1'
assert all(sha(out/p) == h for p,h in manifest['output_hashes'].items())
for p,h in manifest['input_hashes'].items():
    source = Path(p)
    # Historical code is verified against its frozen snapshot after later edits.
    if source.is_relative_to(root/'code'):
        source = out/'code_snapshot'/source.relative_to(root/'code')
    assert sha(source) == h
models = read(out/'models.json')
assert models['version'] == 't3v1' and not models['deployment_enabled']
assert models['connector_actual_rows'] == 0 and models['assumption']['enabled']
assert models['assumption']['classification'] == 'USER_AUTHORIZED_MODEL_ASSUMPTION_NOT_OFFICIAL_EQUALITY_PROOF'
source = root/models['assumption']['source']
assert sha(source) == models['assumption']['source_sha256']
assert models['assumption']['source_excerpt'] in read(source)['text']
assert all(p in models['assumption']['source_excerpt'] for p in ['每组产品','产品组合'])
data = read(out/'dataset.json')
assert len(data['rows']) == 200 and len(data['state_pairs']) == 100
assert data['synthetic_training_rows'] == data['connector_actual_rows'] == 0
assert all((r['phase'],r['round'],r['product']) == ('formal',2,'复合梁') for r in data['rows'])
for name,m in models['demand'].items():
    assert all(k[1:3] == ['formal',2] for k in m['training_keys'])
    if name == 'ABS':
        continue
    for f in m['nested_validation']['folds']:
        assert not {k[0] for k in f['training_keys']} & {k[0] for k in f['test_keys']}
curves = read(out/'response_curves.json')
assert curves['product_mapping'] == {'复合梁':'复合梁','连接件':'复合梁'}
observed = read(out/'formal3_observed_curves.json')
assert set(observed['curves']) == {'rd/复合梁','rd/连接件','operations/泰国'}
assert curves['curves']['3']['rd'] == observed['curves']['rd/复合梁']
old = root/models['inherited_components']['path']
old_manifest = read(old/'manifest.json')
assert all(sha(old/p) == h for p,h in old_manifest['output_hashes'].items())
pred = read(out/'example_prediction.json')
assert pred['category'] == 'SYNTHETIC_DEMONSTRATION_NOT_CURRENT_RECOMMENDATION'
assert pred['allocation']['total_workers'] <= 100+1e-7
assert not pred['allocation']['actual_validation']
checks = read(out/'checks.json')
assert checks['example_prediction_replay'] and checks['nested_market_disjoint']
assert checks['same_estimator_replay_max_beta_difference'] < 1e-8
print(json.dumps(dict(status='PASS',training_actual_rows=200,connector_actual_rows=0,
                     assumption_source_verified=True,products_isolated=True,
                     original_t3v0_hashes_preserved=True,artifact_hashes_verified=True,
                     independent_connector_or_joint_validation=False),ensure_ascii=False))
