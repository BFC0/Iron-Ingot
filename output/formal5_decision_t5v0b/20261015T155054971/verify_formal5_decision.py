"""Cross-check the partial search against the public t5v0b connector path."""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'code')]
import t5v0b as model

read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=ROOT/(ROOT/'work/formal5_decision_active.txt').read_text(encoding='utf-8-sig').strip()
result=read(out/'result.json')
registry=read(ROOT/'output/t5v0b/20261015T153107587428+0800/models_full.json')
checks=[]
with model.app.no_training():
    for plan in result['plans']:
        allocation,priority=plan['policy'][1]
        request=dict(version='t5v0b',market_id=5,phase='formal',round=5,demand_basis='FORMAL4_OWN_SHARE_HELD',
            connector=dict(product=dict(capacity=412.25,efficiency=17.,prices={'泰国':36.,'印尼':32.}),
                allocation_pct=allocation,country_priority=[model.COUNTRIES[k] for k in priority],
                material_form='published',scope='BEFORE_UNVERIFIED_ORDERS'))
        actual=model.apply_request(registry,request)['connector']
        expected=plan['nominal']['products'][1]
        assert abs(actual['contribution_kusd']-expected['severance']-expected['contribution'])<1e-8
        assert abs(actual['closing_inventory_kunits']-expected['inventory'])<1e-8
        checks.append(plan['name'])
decisions=read(out/'decisions.json')
assert len(decisions)==84
for plan in result['plans'][1:]:
    rows=[x for x in decisions if x['plan']==plan['name']]
    assert len({x['key'] for x in rows})==42
    assert [x['suggested'] for x in rows if x['row']==34]==['第二']
assert all(x['suggested']==x['current'] for x in decisions if x['row'] in [9,10,13,14,18,19,21,22,25,26,29,30,49,51,52,46,47,54])
assert all(x['exists'] for x in read(out/'link_checks.json'))
sources=read(out/'sources.json')
assert all(sha(ROOT/k)==v for k,v in sources.items())
doc=read(out/'document_hashes.json')['README']
assert sha(ROOT/'README.md')==doc['after'] and sha(ROOT/doc['backup'])==doc['before']
validation=dict(status='PASS',t5v0b_connector_path_crosscheck=checks,decision_records=84,
    unique_fields_per_plan=42,source_hashes=len(sources),document_backup_and_hashes=True,
    remaining_net_profit_and_cash='UNSOLVED')
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(validation,ensure_ascii=False))
print('REPORT',str(out/'report.md'))
print((out/'report.md').read_text(encoding='utf-8').split('## 同基准比较')[1].split('### 为什么选B')[0])
