"""Verify immutable t5v0 sources, decision categories, saved fits and market isolation."""
import json
import sys
from pathlib import Path

import t5v0 as t
import numpy as np


def verify(out):
    nd=t.nd; manifest=nd.read(out/('manifest_final.json' if (out/'manifest_final.json').exists() else 'manifest.json'));model=nd.read(out/'models_full.json');data=nd.read(out/'dataset.json')
    assert model['version']=='t5v0' and model['training_round']==4 and not model['deployment_enabled']
    for path,digest in manifest['input_hashes'].items():
        assert nd.sha(t.ROOT/path)==digest,path
    for path,digest in manifest['output_hashes'].items():
        assert nd.sha(out/path)==digest,path
    fields=nd.read(out/'captured_final_group_fields.json')
    assert len(fields)==42 and Counter(r['category'] for r in fields)=={
        'ROUND_4_GROUP_FINAL_DECISION':29,'ROUND_4_GROUP_FINAL_PLAYER_ESTIMATE':13}
    assert len(data['own_final_decision_rows'])==4 and model['demand']=={}
    for r in data['own_final_decision_rows']:
        for name in ('price','general','designer','rd','operations'):
            ref=r['sources'][name]
            assert ref['round']==4 and ref['column']==1 and ref['category']=='ROUND_4_GROUP_FINAL_DECISION'
            raw=nd.read(t.ROOT/ref['source'])
            assert nd.numeric(raw['tables'][ref['table']][ref['row']][1])[0]==r[name]
    assert len(data['state_pairs'])==100 and len({(p['market_id'],p['team_id']) for p in data['state_pairs']})==100
    for pair in data['state_pairs']:
        for label,round_ in [('initial',3),('closing',4)]:
            for name,ref in pair[label]['refs'].items():
                assert ref['round']==round_ and ref['category']=='actual_result'
                assert pair[label]['values'][name]==ref['value']
    curves=nd.read(out/'formal4_curves.json')
    assert curves['round']==4 and len(curves['curves'])==3
    for name,c in curves['curves'].items():
        assert c['round']==4 and len(c['points'])==200 and c['json_svg_max_y_delta']<1e-10
        xy=np.array(c['points']);p=t.prior.curve_value(xy[:,0],c['parameters'],c['form'])
        assert abs(float(np.mean(abs(p-xy[:,1])))-c['full_mae'])<1e-12
    for product,m in model['materials'].items():
        rows=data['materials'][product]
        assert all(r['round']==4 for r in rows)
        for form,fit in m['models'].items():
            metrics=t.prior.material.evaluate(fit,rows)
            assert abs(metrics['mae_kusd']-fit['evaluation']['mae_kusd'])<1e-10
        assert len(m['nested_market_validation'])==10
        for fold in m['nested_market_validation']:
            assert fold['held_market'] not in fold['train_markets'] and len(fold['train_markets'])==9
    for form,m in model['risk'].items():
        assert len(m['market_holdouts'])==10
        for fold in m['market_holdouts']:
            held=[r for r in data['risk'] if r['market_id']==fold['held_market']]
            value=float(np.mean(abs(t.prior.interest.premium(form,fold['parameters'],held)-[r['premium'] for r in held])))*10000
            assert abs(value-fold['mae_bp'])<1e-10
    for product,m in model['labor'].items():
        assert m['rank']==2 and len(m['holdouts'])==10
        for fold in m['holdouts']:
            assert 'parameters' in fold
            held=[r for r in data['wages'][product] if r['market']==fold['held_market']]
            beta=np.array(fold['parameters'])-1
            value=float(np.mean([abs(r['scale']*(1+np.array(r['x'])@beta)-r['actual']) for r in held]))
            assert abs(value-fold['mae_kusd'])<1e-9
    for product,m in model['efficiency'].items():
        assert m['training_n']==1 and 'UNIDENTIFIABLE' in m['status']
        for s in m['scenarios']:
            value=s['theta']*float(t.prior.curve_value(s['effective_input'],model['curves']['operations/泰国']['parameters'],'saturation'))
            assert abs(value-m['production']['value']/m['workers']['value'])<1e-12
    inventory=nd.read(out/'model_inventory_final.json')
    assert inventory['count']==len(inventory['models'])==29
    assert set(inventory['models'])==set(nd.read(t.OLD/'model_inventory_final.json')['models'])
    for item in inventory['models'].values():
        assert (out/item['artifact']).is_file()
    assert not list(out.rglob('*.html'))
    report=(out/'report.md').read_text(encoding='utf-8')
    assert all(s in report for s in ('其他99队','暂停','事前评分0项','当前全部问题与不足','因缺乏数据而无法验证的问题'))
    result=dict(status='PASS_WITH_EXPLICIT_TRAINING_GAPS',source_hashes=True,output_hashes=True,
        decision_sources=True,own_decision_pairs=4,state_pairs=100,curve_replay=True,material_replay=True,
        risk_holdout_replay=True,wage_holdout_replay=True,market_isolation=True,model_inventory=29,
        html_reports=0,complete_all_models_trained=False)
    path=out/'verification.json'
    if path.exists():
        assert nd.read(path)==result
    else:
        nd.save(path,result)
    print(json.dumps(result,ensure_ascii=False))


from collections import Counter
if __name__=='__main__':
    verify(Path(sys.argv[1]))
