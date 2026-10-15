"""Append-only supplementary fits, rule diagnostics and saved-artifact verification."""
import json
import hashlib
import math
import sys
from collections import Counter
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'code')]
sys.dont_write_bytecode=True
import t4v1 as t
from connector_free_production import self_check as connector_check
from joint_allocation import self_check as joint_check


def verify(out):
    nd=t.nd; registry=nd.read(out/'models.json'); dataset=nd.read(out/'dataset.json')
    manifest=nd.read(out/('manifest_final.json' if (out/'manifest_final.json').exists() else 'manifest.json'))
    assert registry['version']=='t4v1' and registry['training_round']==3
    assert not registry['deployment_enabled']
    assert all(nd.sha(ROOT/p)==h for p,h in manifest['input_hashes'].items())
    for path,digest in manifest['output_hashes'].items():
        if path=='work_log.md':
            lines=(out/path).read_bytes().splitlines(keepends=True)
            assert any(hashlib.sha256(b''.join(lines[:i])).hexdigest()==digest for i in range(1,len(lines)+1))
        else:
            assert nd.sha(out/path)==digest, path
    previous=t.load_previous()
    source_rows=nd.read(t.AUDIT/'rows.json'); actual=t.Actuals(previous+source_rows)
    assert len(dataset['state_pairs']) == 100
    assert {p['market_id'] for p in dataset['state_pairs']} == set(range(1, 11))
    for product,rows in dataset['competitive_rows_by_product'].items():
        assert len(rows)>=100 and all(r['round']==3 and r['product']==product for r in rows)
        assert len({tuple(t.base.core.key(r)) for r in rows})==len(rows)
        params=registry['curves']['rd/'+product]['parameters']
        for name,model in registry['demand'][product].items():
            if name=='ABS':
                continue
            pool=[r for r in rows if name=='SHARE' or r['country']==name.split('/')[1]]
            prediction=t.base.core.predict(pool,t.base.core.features(pool,params,model['rho'],model['piecewise']),model['beta'])
            assert abs(100*t.base.core.score(pool,prediction)-model['training_mae_pp'])<1e-10
            for fold in model['nested_validation']['folds']:
                train={k[0] for k in fold['training_keys']};test={k[0] for k in fold['test_keys']}
                assert not train&test and set(fold['held_markets'])==test
            for key,ids in t.base.core.old.groups(pool).items():
                expected=next(g['active_rows'] for g in model['competition_group_counts']
                              if (g['market'],g['country']) == (key[0],key[-1]))
                assert len(ids)==expected and 1<=len(ids)<=10 and abs(sum(prediction[ids])-1)<1e-10
    if '--check-only' in sys.argv:
        print(json.dumps(dict(source_hashes=True,output_hashes=True,demand_replay=True,market_isolation=True,share_conservation=True)))
        return
    ledger=nd.read(out/'published_formal3.json')['ledger'];samples={p:[] for p in t.PRODUCTS}
    severance=[];wages={p:[] for p in t.PRODUCTS};physics=[];reviews=[]
    for pair in dataset['state_pairs']:
        market,team=pair['market_id'],pair['team_id']
        try:
            event=actual.get(market,3,team,'productionhr','招聘 + / 裁员 -')
            cost=actual.get(market,3,team,'incomestatement','解雇成本')
            prediction=max(-event['value'],0)*ledger['泰国'][0]['value']*ledger['裁员成本，占薪资%'][0]['value']/100
            tolerance=cost['half']+event['half']*ledger['泰国'][0]['value']*ledger['裁员成本，占薪资%'][0]['value']/100
            severance.append(dict(market=market,team_id=team,actual=cost,prediction=prediction,tolerance=tolerance,
                                  passed=abs(cost['value']-prediction)<=tolerance+1e-9))
        except ValueError as e:
            reviews.append(dict(model='B',market=market,team_id=team,reason=str(e)))
        for product in t.PRODUCTS:
            try:
                q=actual.get(market,3,team,'productiondetails','生产规模, 千单位',product)
                n=actual.get(market,3,team,'productiondetails','生产线人工数量',product)
                c=actual.get(market,3,team,'productiondetails',f'机器产能, {product}, 千单位')
                wage=actual.get(market,3,team,'productiondetails','工资分摊, 千 美元',product)
                sample=dict(key=[market,'formal',3,team,'泰国',product],market=market,phase='formal',round=3,
                    team_id=team,country='泰国',product=product,values=dict(q=q['value'],workers=n['value'],
                    operations=pair['closing']['values']['operations'],previous_operations=pair['initial']['values']['operations'],
                    wage=wage['value'],capacity=c['value']),refs={})
                for key,ref in [('q',q),('workers',n),('wage',wage),('capacity',c)]:
                    sample['refs'][key]=dict(display_half_unit=ref['half'])
                if min(q['value'],n['value'],c['value'])>0 and q['value']<=c['value']:
                    scale=n['value']*ledger['泰国'][0]['value']
                    wages[product].append(dict(market=market,team_id=team,x=t.shift_basis(q['value'],c['value']).tolist(),
                        y=wage['value']/scale-1,scale=scale,actual=wage['value']))
                for name,total_label,intensity_label in [('co2','二氧化碳排放, 公吨','二氧化碳排放, kg'),
                    ('energy','能源消耗, MWh','能源消耗, kWh'),('water','用水量, m3','用水量, l')]:
                    def env(label):
                        rr=[r for r in actual.rows if r['market']==market and r['phase']=='formal' and r['round']==3
                            and r['panel']=='productionenvironmental' and r['cells'][0]==product and r['section_path'][-1]==label]
                        if len(rr)!=1:
                            raise ValueError('Missing/ambiguous resource field')
                        r=rr[0];col=next(i for i,v in enumerate(r['team_order'],1) if nd.team_id(market,v)==team)
                        value,half=nd.numeric(r['cells'][col]);return value,half
                    total,th=env(total_label);intensity,ih=env(intensity_label)
                    sample['values'][name]=total;sample['values'][name+'_intensity']=intensity
                    sample['refs'][name]=dict(display_half_unit=th);sample['refs'][name+'_intensity']=dict(display_half_unit=ih)
                    predicted=q['value']*intensity
                    tol=th+q['half']*abs(intensity)+ih*abs(q['value'])+q['half']*ih
                    physics.append(dict(model='E',channel=name,market=market,team_id=team,product=product,
                        actual=total,predicted=predicted,tolerance=tol,passed=abs(total-predicted)<=tol+1e-8))
                samples[product].append(sample)
            except ValueError as e:
                reviews.append(dict(model='C/E',market=market,team_id=team,product=product,reason=str(e)))
            for country in t.base.core.COUNTRIES:
                def route(panel,intensity):
                    rr=[r for r in actual.rows if r['market']==market and r['round']==3 and r['phase']=='formal'
                        and r['panel']==panel and r['cells'][0]=='运往 '+country
                        and product in next((s for s in reversed(r['section_path']) if any(p in s for p in t.PRODUCTS)),'')
                        and (panel!='logisticsemissions' or ('平均每单位销售, g CO2' in r['section_path'])==intensity)]
                    if len(rr)!=1:
                        raise ValueError('Missing/ambiguous route field')
                    r=rr[0];col=next(i for i,v in enumerate(r['team_order'],1) if nd.team_id(market,v)==team)
                    return nd.numeric(r['cells'][col])
                try:
                    qty,qh=route('logisticsdetails',False);total,th=route('logisticsemissions',False);intensity,ih=route('logisticsemissions',True)
                    pred=qty*intensity;tol=th+qh*abs(intensity)+ih*abs(qty)+qh*ih
                    physics.append(dict(model='F',channel=country,market=market,team_id=team,product=product,
                        actual=total,predicted=pred,tolerance=tol,passed=abs(total-pred)<=tol+1e-8))
                except ValueError as e:
                    reviews.append(dict(model='F',market=market,team_id=team,product=product,reason=str(e)))
    fitted_wages={}
    for product,rows in wages.items():
        x=np.asarray([r['x'] for r in rows]);rank=int(np.linalg.matrix_rank(x));folds=[]
        if rank==2:
            beta=t.base.origin_fit(x,[r['y'] for r in rows],[r['market'] for r in rows])
            for market in sorted({r['market'] for r in rows}):
                tr=[r for r in rows if r['market']!=market];te=[r for r in rows if r['market']==market]
                xx=np.asarray([r['x'] for r in tr])
                if np.linalg.matrix_rank(xx)<2:
                    folds.append(dict(market=market,status='UNIDENTIFIABLE'));continue
                b=t.base.origin_fit(xx,[r['y'] for r in tr],[r['market'] for r in tr])
                folds.append(dict(market=market,beta=b.tolist(),mae_kusd=float(np.mean([abs(r['scale']*(1+np.asarray(r['x'])@b)-r['actual']) for r in te]))))
            fitted_wages[product]=dict(status='RETRAINED_CONDITIONAL_WAGE',parameters=(1+beta).tolist(),rank=rank,n=len(rows),folds=folds)
        else:
            fitted_wages[product]=dict(status='UNIDENTIFIABLE_SHIFT_COEFFICIENTS',rank=rank,n=len(rows))
    experiments={};a_fits={};a_predictions=[];a_calibration=[]
    values=dict(base_wage=ledger['泰国'][0]['value'],second_shift=ledger['两班倒'][0]['value'],
                third_shift=ledger['三班倒'][0]['value'],attrition=ledger['年人员离职率（without costs），%'][0]['value']/100,
                severance_ratio=ledger['裁员成本，占薪资%'][0]['value']/100)
    frozen=dict(curves=dict(operations=registry['curves']['operations/泰国']))
    for product,rows in samples.items():
        e,p,s,f,c=nd.run_experiments(rows,{('formal',3):dict(values=values)},frozen,refit=True)
        experiments.update(e);a_fits.update(f);a_predictions+=p;a_calibration+=c
    nd.save(out/'supplementary_A.json',dict(experiments=experiments,fits=a_fits,predictions=a_predictions,calibration=a_calibration,
        limitation='环境总量与单位强度同源；不能当新增独立需求信号'))
    d_result=lagged_efficiency(actual,dataset['state_pairs'],registry['curves']['operations/泰国']['parameters'])
    nd.save(out/'lagged_efficiency.json',d_result)
    connector=connector_check();joint=joint_check()
    result=dict(source_hashes=True,saved_model_replay=True,fold_market_isolation=True,share_conservation=True,
                severance=severance,wages=fitted_wages,physical_formulas=physics,missing_or_ambiguous=reviews,
                E_counts=dict(Counter(r['passed'] for r in physics if r['model']=='E')),
                F_counts=dict(Counter(r['passed'] for r in physics if r['model']=='F')),
                connector=connector,joint_allocation=joint,
                A=dict(experiments=experiments,fits=a_fits),D=d_result)
    nd.save(out/'supplementary_verification.json',result)
    nd.save(out/'connector_checks.json',dict(connector=connector,joint_allocation=joint))
    nd.csv_write(out/'physics_checks.csv',physics)
    nd.csv_write(out/'severance_checks.csv',severance)
    print(json.dumps(dict(demand_replay=True,market_isolation=True,physical=len(physics),
                         physical_failures=sum(not r['passed'] for r in physics),severance=len(severance),
                         severance_failures=sum(not r['passed'] for r in severance),wages=fitted_wages,
                         source_hashes=True),ensure_ascii=False))


def lagged_efficiency(actual,pairs,current_curve):
    previous_curve=t.nd.read(t.base.CURVE2)['curves']['operations']['parameters'];paths=[];excluded=[]
    for pair in pairs:
        market,team=pair['market_id'],pair['team_id']
        try:
            history=[]
            for round_ in (2,3):
                q=actual.get(market,round_,team,'productiondetails','生产规模, 千单位','复合梁' if round_==3 else None)['value']
                n=actual.get(market,round_,team,'productiondetails','生产线人工数量','复合梁' if round_==3 else None)['value']
                if min(q,n)<=0:
                    raise ValueError('Nonpositive production/workers')
                ops=actual.get(market,round_,team,'incomestatement','运营改进')['value']
                prev=actual.get(market,round_-1,team,'incomestatement','运营改进')['value']
                history.append(dict(market_id=market,operations=ops,previous_operations=prev,effective_observed=q/n))
            workers=actual.get(market,2,team,'productionhr','生产人员数量, 上回合')['value']
            event=actual.get(market,2,team,'productionhr','招聘 + / 裁员 -')['value']
            if workers<=0:
                raise ValueError('Nonpositive opening workers')
            paths.append(dict(previous=history[0],current=history[1],hire=max(event,0)/workers,fire=max(-event,0)/workers,team_id=team))
        except ValueError as e:
            excluded.append(dict(market=market,team_id=team,reason=str(e)))
    markets=sorted({p['current']['market_id'] for p in paths})
    if len(markets)<5:
        return dict(status='INSUFFICIENT_FIVE_COMPLETE_TRANSITION_MARKETS',markets=markets,excluded=excluded)
    def fit(train,test):
        previous=t.base.ops.select([p['previous'] for p in train],previous_curve)
        current=t.base.ops.select([p['current'] for p in train],current_curve)
        def design(records):
            a=t.base.ops.predict([p['previous'] for p in records],previous_curve,previous)
            b=t.base.ops.predict([p['current'] for p in records],current_curve,current)
            x=[[math.log(p['previous']['effective_observed']/v),p['hire'],p['fire']] for p,v in zip(records,a)]
            y=[math.log(p['current']['effective_observed']/v) for p,v in zip(records,b)]
            return np.array(x),np.array(y),b
        x,y,_=design(train);model,predict=t.nd.select_ridge(x,y,[p['current']['market_id'] for p in train])
        xt,yt,b=design(test);correction=predict(model,xt)
        return dict(previous_base=previous,current_base=current,residual=model),[
            dict(market=p['current']['market_id'],team_id=p['team_id'],actual=p['current']['effective_observed'],
                 baseline=float(v),candidate=float(v*math.exp(c))) for p,v,c in zip(test,b,correction)]
    folds=[];predictions=[]
    for held in markets:
        tr=[p for p in paths if p['current']['market_id']!=held];te=[p for p in paths if p['current']['market_id']==held]
        model,p=fit(tr,te);folds.append(dict(held_market=held,fit=model));predictions+=p
    model,_=fit(paths,paths)
    return dict(status='RETRAINED_FORMAL2_TO_FORMAL3_CONDITIONAL_RESEARCH',product='复合梁',n=len(paths),
        model=model,folds=folds,predictions=predictions,comparison=t.nd.paired_summary(predictions,'baseline','candidate'),
        excluded=excluded,curve_rounds=[2,3],previous_curve_sha256=t.nd.sha(t.base.CURVE2),deployment=False,
        limitation='外层市场隔离；内层残差基底使用外层训练信息，内层选参仍可能偏乐观；单一转移，非时间外预测')


if __name__=='__main__':
    verify(Path(sys.argv[1]))
