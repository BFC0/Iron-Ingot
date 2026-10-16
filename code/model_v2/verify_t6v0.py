"""Replay t6v0 provenance, fits, training-only screens and untouched holdouts."""
import json
import sys
from pathlib import Path
import t6v0 as t
import numpy as np


def verify(out):
    nd=t.nd; model=nd.read(out/'models_full.json'); data=nd.read(out/'dataset.json')
    manifest=nd.read(out/'manifest.json')
    assert model['version']=='t6v0' and model['training_round']==5 and not model['deployment_enabled']
    for p,h in manifest['input_hashes'].items(): assert nd.sha(t.ROOT/p)==h,p
    for p,h in manifest['output_hashes'].items(): assert nd.sha(out/p)==h,p
    assert len(data['state_pairs'])==100
    for pair in data['state_pairs']:
        for kind,round_ in [('initial',4),('closing',5)]:
            for k,r in pair[kind]['refs'].items():
                assert r['round']==round_ and r['category']=='actual_result'
                assert pair[kind]['values'][k]==r['value']
    fields=nd.read(out/'captured_final_group_fields.json')
    assert len(fields)==42 and sum(r['category']=='ROUND_5_GROUP_FINAL_DECISION' for r in fields)==29
    for row in data['own_final_decision_rows']:
        for k in ('price','general','designer','rd','operations'):
            r=row['sources'][k]
            assert r['category']=='ROUND_5_GROUP_FINAL_DECISION' and r['round']==5
            assert nd.numeric(nd.read(t.ROOT/r['source'])['tables'][r['table']][r['row']][1])[0]==row[k]
    curves=nd.read(out/'formal5_curves.json')
    assert curves['round']==5 and len(curves['curves'])==3
    for c in curves['curves'].values():
        xy=np.array(c['points']); assert len(xy)==200 and c['json_svg_max_y_delta']<1e-10
        p=t.prior.curve_value(xy[:,0],c['parameters'],c['form'])
        assert abs(float(np.mean(abs(p-xy[:,1])))-c['full_mae'])<1e-12
    rows=nd.read(out/'demand_actual_rows.json');screening=nd.read(out/'demand_screening.json')
    assert sum(map(len,rows.values()))+len(nd.read(out/'demand_invalid_rows.json'))==400
    core=t.prior.base.core
    for product,variants in model['demand'].items():
        params=model['curves']['rd/'+product]['parameters']
        for row in rows[product]:
            assert row['round']==5 and row['price']>0 and row['demand']>0
            for k,r in row['sources'].items():
                assert r['category']=='actual_result'
                raw=nd.read(t.ROOT/r['source'])
                assert nd.numeric(raw['tables'][r['table']][r['row']][r['column']])[0]==row[k]
        for kind,m in variants.items():
            if kind=='ABS':
                assert m['training_round']==m['curve_round']==5
                for f in m['nested_validation']['folds']:
                    assert f['held_market'] not in f['train_markets']
                    test=[r for r in rows[product] if r['market_id']==f['held_market']]
                    x=np.c_[[[int(r['country']==c) for c in core.COUNTRIES] for r in test],core.features(test,params)]
                    err=float(np.mean(abs(np.exp(x@f['beta'])-[r['demand'] for r in test])))
                    assert abs(err-f['mae_kunits'])<1e-9
                continue
            pool=[r for r in rows[product] if kind=='SHARE' or r['country']==kind.split('/')[1]]
            kept,audit=t.demand_training.screen(pool,params)
            assert audit==screening[product+'/'+kind]
            assert len(kept)==m['n_retained']
            assert np.allclose(t.demand_training.fit(kept,params)['beta'],m['beta'],atol=1e-10,rtol=0)
            for a in audit['audits']:
                if 'suspected_supply_distorted_low_demand' in a['reasons']:
                    assert a['supply_evidence'] and a['log_share_residual']<audit['residual_median']-audit['low_residual_distance']
            for f in m['nested_validation']['folds']:
                held=f['held_market']; assert held not in f['train_markets'] and len(f['train_markets'])==9
                train=[r for r in pool if r['market_id']!=held];test=[r for r in pool if r['market_id']==held]
                kept,fold_audit=t.demand_training.screen(train,params)
                assert fold_audit==f['training_screen'] and len(test)==f['test_n']
                assert all(a['key'][0]!=held for a in fold_audit['audits'])
                beta=t.demand_training.fit(kept,params)['beta']
                assert np.allclose(beta,f['beta'],atol=1e-10,rtol=0)
                p=core.predict(test,core.features(test,params,.5,False),beta)
                assert abs(100*core.score(test,p)-f['mae_pp'])<1e-10
                for ids in core.old.groups(test).values(): assert abs(sum(p[ids])-1)<1e-12
            assert sum(f['test_n'] for f in m['nested_validation']['folds'])==len(pool)
    for product,m in model['materials'].items():
        for form,fit in m['models'].items():
            assert abs(t.prior.material.evaluate(fit,data['materials'][product])['mae_kusd']-fit['evaluation']['mae_kusd'])<1e-9
        for f in m['nested_market_validation']: assert f['held_market'] not in f['train_markets']
    for form,m in model['risk'].items():
        for f in m['market_holdouts']:
            test=[r for r in data['risk'] if r['market_id']==f['held_market']]
            err=float(np.mean(abs(t.prior.interest.premium(form,f['parameters'],test)-[r['premium'] for r in test])))*10000
            assert abs(err-f['mae_bp'])<1e-9
    for product,m in model['labor'].items():
        assert m['rank']==2
        for f in m['holdouts']:
            test=[r for r in data['wages'][product] if r['market']==f['held_market']]
            beta=np.array(f['parameters'])-1
            err=float(np.mean([abs(r['scale']*(1+np.array(r['x'])@beta)-r['actual']) for r in test]))
            assert abs(err-f['mae_kusd'])<1e-9
    inventory=nd.read(out/'model_inventory_final.json')
    assert len(inventory['models'])==inventory['count']==29
    for v in inventory['models'].values(): assert (out/v['artifact']).is_file()
    checks=nd.read(out/'checks.json')
    assert checks['severance_failures']==checks['physics_failures']==0 and checks['route_missing']==0
    assert not list(out.rglob('*.html'))
    result=dict(status='PASS_WITH_EXPLICIT_ASSUMPTIONS_AND_GAPS',training_round=5,
        actual_sources_verified=True,source_and_output_hashes=True,curve_replay=True,
        demand_screen_and_fold_replay=True,holdout_includes_all_valid_rows=True,
        material_risk_wage_replay=True,model_count=29,complete_all_models_trained=False)
    nd.save(out/'verification.json',result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': verify(Path(sys.argv[1]))
