"""Read-only verification of a frozen t5v2 bundle."""
import hashlib,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
import numpy as np
import t5v2

ROOT=Path(__file__).resolve().parents[2]
def verify(bundle):
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=read(bundle/'version_manifest.json')
    for name,h in manifest['outputs'].items():assert sha(bundle/name)==h,name
    for name,h in manifest['runtime'].items():assert sha(ROOT/name)==h,name
    for name,h in read(bundle/'t5v1_before_hashes.json').items():assert sha(ROOT/name)==h,name
    assert read(bundle/'sources/probe/checklist_before.json')==read(bundle/'sources/probe/checklist_final_restored.json')
    mappings=read(bundle/'effective_investment_models.json')
    for r in mappings['records']:
        item=mappings['models'][r['key']]
        effective=item['current_weight']*r['input']+item['previous_weight']*item['previous_input']
        assert r['lower']-1e-8<=effective<=r['upper']+1e-8
    reg=read(bundle/'models_full.json');result=read(bundle/'full_result.json')
    assert reg['version']=='t5v2' and reg['base_version']=='t5v1'
    count=0
    for p in result['comparisons']:
        for cfg,expected in zip(result['configs'],p['evaluations']):
            actual=t5v2.apply_request(reg,dict(version='t5v2',market_id=5,phase='formal',round=5,plan=p['name'],scenario=cfg['name']))
            assert abs(actual['profit_5_to_6']-expected['profit_5_to_6'])<1e-8
            assert actual['balance_error_max']<1e-7 and actual['quantity_error_max']<1e-8
            x=p['x'];a,b=actual['periods']
            assert np.allclose(a['effective_rd_kusd'],.75*np.array(x[12:14])+.5*np.array([900,1300]))
            assert abs(a['effective_operations_kusd']-(x[14]+262.5))<1e-8
            if cfg.get('future_mapping')!='freeze_formal5':
                assert np.allclose(b['effective_rd_kusd'],1.25*np.array(x[12:14]))
                assert abs(b['effective_operations_kusd']-1.35*x[14])<1e-8
            count+=1
        if p['name']!='最新网页基准':assert all(e['feasible'] for e in p['evaluations'][:3])
    decisions=read(bundle/'decisions.json');sensitivity=read(bundle/'sensitivity_all_candidates.json')
    assert len(decisions)==126
    for p in result['comparisons'][1:]:
        assert len({r['row'] for r in decisions if r['plan']==p['name']})==42
        assert len({r['row'] for r in sensitivity if r['plan']==p['name']})==42
    width=None
    for line in (bundle/'report.md').read_text(encoding='utf-8').splitlines():
        if line.startswith('|'):
            n=len(line.split('|'));assert width is None or width==n; width=n
        else:width=None
    for name in ['report.md']:
        for link in re.findall(r'\]\(([^)]+)\)',(bundle/name).read_text(encoding='utf-8')):assert (bundle/link).resolve().exists(),link
    assert abs(read(bundle/'validation.json')['budget_replay_error'])<10
    return dict(status='PASS',frozen_replays=count,t5v1_preserved=True,platform_restored=True,candidate_fields=126,all_links_and_hashes=True)

if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1])),ensure_ascii=False))
