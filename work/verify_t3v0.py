"""Verify saved t3v0 files without fitting or changing model artifacts."""
import csv
import hashlib
import json
import sys
from pathlib import Path
from collections import defaultdict
from xml.etree import ElementTree

root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[1]).resolve()
assert out.is_relative_to(root/'output/t3v0')
read=lambda name:json.loads((out/name).read_text(encoding='utf-8'))
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
manifest=read('manifest.json')
assert manifest['version']=='t3v0' and manifest['status']=='COMPLETE_RESEARCH_WITH_EXPLICIT_GAPS'
assert all(sha(out/name)==digest for name,digest in manifest['output_hashes'].items())
assert all(sha(Path(name))==digest for name,digest in manifest['input_hashes'].items())
dataset=read('dataset.json');rows=dataset['rows'];pairs=dataset['state_pairs']
assert len(rows)==200 and len(pairs)==100
assert all((r['phase'],r['round'],r['product'])==('formal',2,'复合梁') for r in rows)
assert len({(r['market_id'],r['team_id'],r['country']) for r in rows})==200
pair_by_id={(p['market_id'],p['team_id']):p for p in pairs}
for r in rows:
    p=pair_by_id[r['market_id'],r['team_id']]
    assert r['previous_rd']==p['initial']['values']['rd']
    assert r['previous_operations']==p['initial']['values']['operations']
    assert r['rd']==p['closing']['values']['rd']
    assert r['operations']==p['closing']['values']['operations']
models=read('models.json')
assert models['training_round']==2 and not models['deployment_enabled']
for name,m in models['demand'].items():
    assert all(k[1:3]==['formal',2] for k in m['training_keys'])
    if name=='ABS':continue
    for fold in m['nested_validation']['folds']:
        assert not {k[0] for k in fold['training_keys']} & {k[0] for k in fold['test_keys']}
        assert not set(map(tuple,fold['training_keys'])) & set(map(tuple,fold['test_keys']))
        assert set(fold['held_markets'])=={k[0] for k in fold['test_keys']}
pred=read('predictions.json')
assert len(pred)==400
with (out/'predictions.csv').open(encoding='utf-8-sig',newline='') as stream:
    exported=list(csv.DictReader(stream))
assert len(exported)==len(pred)
for a,b in zip(exported,pred):
    assert all(a[k]==str(b[k]) for k in a)
groups=defaultdict(list)
for r in pred:groups[(r['model'],r['market'],r['country'])].append(r)
for group in groups.values():
    assert len(group)==10
    assert abs(sum(r['predicted_share_pp'] for r in group)-100)<1e-9
    assert abs(sum(r['actual_share_pp'] for r in group)-100)<1e-9
curves2=read('formal2_curves.json');curves3=read('formal3_curves.json')
assert curves2['round']==2 and curves3['round']==3 and not curves3['training_use']
assert len(curves3['curves'])==3 and sum(len(c['points']) for c in curves3['curves'].values())==600
for c in curves3['curves'].values():
    assert set(c['train_indices']).isdisjoint(c['held_indices'])
    assert len(c['train_indices'])==len(c['held_indices'])==100
    assert c['held_max_error']<.02
ElementTree.parse(out/'formal3_curves.svg')
doc=(out/'report.html').read_text(encoding='utf-8')
assert 'formal3_curves.svg' in doc and 'let selected=[]' in doc
embedded=json.loads(doc.split('<script>const data=',1)[1].split(';const byId=',1)[0])
assert embedded==pred
accounts=read('labor_and_accounts.json')['accounts_replay']
assert sum(r['passed'] is True for r in accounts)==300
assert not any(r['passed'] is False for r in accounts)
assert read('calculation_flow.json')['remaining']['remaining_profit'] is None
assert not read('lagged_efficiency.json')['deploy']
print(json.dumps(dict(status='PASS',input_and_output_hashes=True,state_pairs=100,actual_rows=200,
    nested_market_disjoint=True,share_conservation=True,html_csv_json_rows=400,
    formal2_curve_training_binding=True,separate_formal3_points=600,accounts=300,
    unknown_future_preserved=True),ensure_ascii=False))
