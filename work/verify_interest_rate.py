"""Check one saved interest-rate delivery without retraining or platform writes."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code')]
import interest_rate_model as model

out = Path(sys.argv[1]).resolve()
assert out.parent == ROOT/'output/interest_rate'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
manifest = read(out/'manifest.json')
assert manifest['status'] == 'COMPLETE'
for prefix, paths in [(ROOT, manifest['input_hashes']), (out, manifest['output_hashes'])]:
    for path, sha in paths.items():
        assert hashlib.sha256((prefix/path).read_bytes()).hexdigest() == sha, path
rows = read(out/'dataset.json')['rows']
validation = read(out/'validation.json')['nested_market_holdouts']
assert len(rows) == len(validation) == 100
assert {(r['market_id'], r['team_column']) for r in rows} == {(r['market_id'], r['team_column']) for r in validation}
assert all('team' not in r and r['phase'] == 'formal' and r['round'] == 1 for r in rows)
fitted = read(out/'model.json')
assert abs(sum(abs(r['error_bp']) for r in validation)/100 - fitted['nested_market_holdout_mae_basis_points']) < 1e-12
scenario = read(out/'scenario.json')
assert scenario['rate_parameter_source'].endswith('/formal2_outlook.json')
assert model.predict(fitted, scenario['inputs']['predicted_closing_state'], 2.5, 2)['long_rate_percent'] == scenario['long_rate_percent']
model.self_check()
print('Passed: source/output hashes, 100 unique actual rows and holdouts, error units, formal2 source, prediction reproduction, invalid-input checks')
