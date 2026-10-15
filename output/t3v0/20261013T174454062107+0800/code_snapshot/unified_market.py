"""Independent unified-market assumption fit; old evidence and models stay immutable."""
import csv
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'code/model_v2'), str(ROOT/'code')]
import core
import country_demand
import formal_update_train as formal
import operations_rho as ops
import verify_visible_coefficients as visible
from scipy.optimize import least_squares
import numpy as np

MODEL_ID = 'unified-market'
CONTEXT = 'UNIFIED_MARKET_ASSUMPTION_FORMAL1'
CURVE2 = 'output/visible_coefficients/20261012_round2_json/coefficients.json'


def require_period(rows):
    if not rows or any(r['phase']!='formal' or r['round']!=1 or r['context_id']!=CONTEXT for r in rows):
        raise ValueError('This fitted version requires formal1 and unified-market assumption labels')
    if len({r['country'] for r in rows})!=1:
        raise ValueError('Country coefficients are independent')


def grouped_folds(rows):
    markets=sorted({r['market_id'] for r in rows})
    assert len(markets)>=4
    for i in range(0,len(markets),2):
        held=markets[i:i+2]
        train=[r for r in rows if r['market_id'] not in held]
        test=[r for r in rows if r['market_id'] in held]
        assert not {r['market_id'] for r in train} & {r['market_id'] for r in test}
        assert not {tuple(core.key(r)) for r in train} & {tuple(core.key(r)) for r in test}
        yield held,train,test


def prediction(rows, model, params):
    require_period(rows)
    if model['country']!=rows[0]['country']:
        raise ValueError('Country does not match model')
    for ids in core.old.groups(rows).values():
        if len(ids)!=10 or len({rows[i]['team_id'] for i in ids})!=10:
            raise ValueError('Supply all ten distinct competing teams in each market')
    return core.predict(rows,core.features(rows,params,model['rho'],model['piecewise']),model['beta'])


def select(rows, params):
    require_period(rows)
    path=[]
    for cfg in country_demand.CONFIGS:
        errors=[]
        for held,train,test in grouped_folds(rows):
            m=core.fit(train,params,**cfg)
            m['country']=rows[0]['country']
            errors.append(dict(held_markets=held,mae_pp=100*core.score(test,prediction(test,m,params)),
                               scale=m['scale']))
        path.append(dict(config=cfg,folds=errors,cv_share_mae_pp=float(np.mean([e['mae_pp'] for e in errors]))))
    winner=min(path,key=lambda p:(p['cv_share_mae_pp'],p['config']['loss']!='share',-p['config']['penalty']))
    return winner['config'],path


def train_country(rows, params, curve_max):
    require_period(rows)
    country=rows[0]['country']
    outer=[]; records=[]
    for held,train,test in grouped_folds(rows):
        cfg,path=select(train,params)
        m=core.fit(train,params,**cfg);m['country']=country
        p=prediction(test,m,params)
        outer.append(dict(held_markets=held,training_keys=m['training_keys'],test_keys=[core.key(r) for r in test],
                          selected=cfg,inner_cv_path=path,fitted=m,share_mae_pp=100*core.score(test,p)))
        y=core.actual_shares(test)
        for i,r in enumerate(test):
            total=sum(q['demand'] for q in test if core.old.group_key(q)==core.old.group_key(r))
            records.append(dict(market_id=r['market_id'],phase='formal',round=1,team_id=r['team_id'],country=country,
                category='nested_market_holdout_conditional',actual=r['demand'],actual_share=float(y[i]),
                predicted_share=float(p[i]),conditional_demand=float(p[i]*total),actual_total=total,
                uses_realized_total=True,uses_realized_rivals=True,source=r['sources']['demand']))
        print('HOLDOUT',country,held,round(outer[-1]['share_mae_pp'],5),flush=True)
    cfg,path=select(rows,params)
    model=core.fit(rows,params,**cfg);model['country']=country
    ids=[core.COUNTRIES.index(country),2,3,4]
    model.update(coefficients=dict(zip(country_demand.NAMES,[model['beta'][i] for i in ids])),
                 model_id=MODEL_ID,context_id=CONTEXT,phase='formal',round=1,market_scope=list(range(1,11)),
                 cv_path=path,outer_folds=outer,selected_cv_share_mae_pp=min(p['cv_share_mae_pp'] for p in path),
                 nested_market_holdout_share_mae_pp=float(np.mean([f['share_mae_pp'] for f in outer])),
                 training_share_mae_pp=100*core.score(rows,prediction(rows,model,params)),
                 rd_extrapolation_count=sum(r['rd']+.5*r['previous_rd']>curve_max for r in rows),
                 rd_effective_range=[min(r['rd']+.5*r['previous_rd'] for r in rows),max(r['rd']+.5*r['previous_rd'] for r in rows)])
    assert len(records)==len(rows)==100
    assert model['beta'][1-core.COUNTRIES.index(country)]==0
    p=prediction(rows,model,params)
    for indices in core.old.groups(rows).values():
        assert abs(sum(p[indices])-1)<1e-12
    changed=[dict(r,general=r['general']+10000) if r['market_id']==10 else r for r in rows]
    p2=prediction(changed,model,params)
    assert np.allclose(p[[i for i,r in enumerate(rows) if r['market_id']!=10]],
                       p2[[i for i,r in enumerate(rows) if r['market_id']!=10]],rtol=0,atol=1e-12)
    for bad in [[dict(r,round=2) for r in rows],rows[:-1],rows+[rows[0]]]:
        try: prediction(bad,model,params)
        except ValueError: pass
        else: raise AssertionError('Invalid prediction boundary accepted')
    return model,records


def mechanism_rows(rows):
    result=[]
    for r in rows:
        if r['country']!=core.COUNTRIES[0]: continue
        p=ROOT/r['sources']['demand']['file'];c=r['team_column']
        refs={k:formal.field(p,label,c) for k,label in [('q','生产规模, 千单位'),('workers','生产线人工数量'),
            ('assets','资产总计'),('equity','股东权益合计'),('long','长期贷款'),('short','短期贷款'),
            ('rate','长期贷款利率，%'),('materials','原材料购买')]}
        v={k:ref['value'] for k,ref in refs.items()}
        assert all(v[k]>0 for k in ['q','workers','assets','equity'])
        result.append(dict(market_id=r['market_id'],team_id=r['team_id'],operations=r['operations'],
            previous_operations=r['previous_operations'],effective_observed=v['q']/v['workers'],
            source=dict(production=refs['q'],workers=refs['workers']),refs=refs,
            equity_ratio=v['equity']/v['assets'],leverage=(v['long']+v['short'])/v['equity'],
            premium=v['rate']/100-.03,production=v['q'],material_cost=v['materials'],uplift=v['materials']/v['q']-900))
    assert len(result)==100
    return result


def fit_mechanisms(rows, params):
    chosen=ops.select(rows,params)
    held=[]
    for market in range(1,11):
        tr=[r for r in rows if r['market_id']!=market];te=[r for r in rows if r['market_id']==market]
        fitted=ops.select(tr,params)
        held.append(dict(held_market=market,fitted=fitted,metrics=ops.metrics(te,ops.predict(te,params,fitted))))
    result=dict(operations_efficiency=dict(chosen=chosen,curve_parameters=params,
        training_metrics=ops.metrics(rows,ops.predict(rows,params,chosen)),market_holdouts=held,
        estimator='existing strategy-equal rho grid and technology scale',rho_interpretation='effective-input proxy, not identified full stock'),risk={})
    priors=core.read('分步模型拟合与验证.json')['finance']['risk_candidates']
    for prior in priors:
        form=prior['form']
        def predict_risk(p,rr):
            return p[0]*np.exp(-p[1]*np.array([r['equity_ratio'] for r in rr])) if form=='solvency_exponential' else p[0]*np.array([r['leverage'] for r in rr])**p[1]
        def fit_risk(rr):
            fit=least_squares(lambda p:predict_risk(p,rr)-[r['premium'] for r in rr],prior['parameters'],bounds=([0,0],[10,30]),max_nfev=2000)
            assert fit.success
            return fit.x
        fitted=fit_risk(rows);folds=[]
        for market in range(1,11):
            tr=[r for r in rows if r['market_id']!=market];te=[r for r in rows if r['market_id']==market]
            p=fit_risk(tr)
            folds.append(dict(held_market=market,parameters=p.tolist(),mae_basis_points=float(np.mean(abs(predict_risk(p,te)-[r['premium'] for r in te])))*10000))
        result['risk'][form]=dict(parameters=fitted.tolist(),market_holdouts=folds,forecast=False,
            holdout_mae_basis_points=float(np.mean([f['mae_basis_points'] for f in folds])),
            interpretation='conditional actual end-state association; repayment/interest timing unverified')
    uplift=float(np.median([r['uplift'] for r in rows]));folds=[]
    for market in range(1,11):
        tr=[r for r in rows if r['market_id']!=market];te=[r for r in rows if r['market_id']==market]
        u=float(np.median([r['uplift'] for r in tr]))
        folds.append(dict(held_market=market,uplift=u,mae_kusd=float(np.mean([abs(r['production']*(900+u)-r['material_cost']) for r in te]))))
    result['materials']=dict(uplift_usd_per_unit=uplift,market_holdouts=folds,
                            interpretation='empirical displayed-cost residual, not published markup; formal1 only')
    return result


def main():
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out=ROOT/'output/unified-market'/stamp;out.mkdir(parents=True,exist_ok=False)
    log=out/'work_log.md'
    log.write_text(f'# unified-market工作日志\n\n北京时间：{stamp}。进行中。\n\n用户授权同一期市场共享前景、曲线和销售需求系数的假设版本，重新训练并独立保存。正式1实际为训练标签；正式2曲线另列，未来系数不冒充已训练。运营图实际为效率乘数。不要输出真名，姓名统一用首字母替代。旧模型与原件不覆盖，平台不修改。\n',encoding='utf-8')
    snapshot=out/'code_snapshot';snapshot.mkdir()
    for p in [* (ROOT/'code/model_v2').glob('*.py'),* (ROOT/'code').glob('*.py')]:
        shutil.copy2(p,snapshot/p.name)
    manifest=dict(model_id=MODEL_ID,status='RUNNING',assumption_verified=False,run_id=stamp)
    core.write(out/'manifest.json',manifest)
    try:
        rows,cells,sources,links=formal.dataset(formal.SOURCE)
        paths={s['file'] for s in sources}|{core.FROZEN,core.FUTURE,'分步模型拟合与验证.json',CURVE2,
            'output/visible_coefficients/20261012_archive_review/coefficients.json',
            'output/formal_update/20261011T230135216100+0800_training/models.json'}
        old_curves=core.read('output/visible_coefficients/20261012_archive_review/coefficients.json')
        paths.update(old_curves['sources'])
        c2=core.read(CURVE2);paths.add(c2['source'])
        paths.add((formal.SOURCE/'formal1_outlook.json').relative_to(ROOT).as_posix())
        before={p:core.digest(ROOT/p) for p in paths}
        for r in rows:
            r.update(context_id=CONTEXT,context_verified=False,context_fit_eligible=True,
                     assumption_id=MODEL_ID,eligibility_basis='user-authorized assumption, not independent outlook verification')
        require_period([r for r in rows if r['country']==core.COUNTRIES[0]])
        assert len({tuple(core.key(r)) for r in rows})==200
        curves=visible.fit_curves()
        for name in ['rd','operations']:
            assert np.allclose(curves[name]['parameters'],old_curves['curves'][name]['parameters'],rtol=1e-9,atol=1e-9)
        registry={f'formal/{i}':dict(phase='formal',round=i,market_scope=list(range(1,11)),
            sharing_basis='unified-market user assumption',independently_verified_markets=[5],curves=c['curves'])
            for i,c in [(1,dict(curves=curves)),(2,c2)]}
        # Freeze-score historical models with their original curves before fitting.
        frozen=core.read(core.FROZEN);baseline={}
        for country in core.COUNTRIES:
            pool=[r for r in rows if r['country']==country]
            beta=frozen['models']['B']['competitive']['coefficients']
            p=core.predict(pool,core.features(pool,frozen['rd_curve_parameters']),beta)
            baseline[country]=dict(share_mae_pp=100*core.score(pool,p),forecast=False,
                                   interpretation='historical mixed-context B, actual rivals; not comparable training protocol')
        core.write(out/'historical_frozen_evaluation_before_fit.json',baseline)
        core.write(out/'dataset.json',dict(rows=rows,sources=sources,reset_links=links))
        models={};predictions=[]
        for country in core.COUNTRIES:
            pool=[r for r in rows if r['country']==country]
            m,pr=train_country(pool,curves['rd']['parameters'],curves['rd']['axes']['axis_max'])
            models[country]=m;predictions+=pr
        mr=mechanism_rows(rows)
        mechanisms=fit_mechanisms(mr,curves['operations']['parameters'])
        for name,c in registry.items():
            c['demand_coefficients_status']='RETRAINED_SHARED_WITHIN_COUNTRY' if name=='formal/1' else 'NO_ACTUAL_LABELS_NOT_TRAINED'
        core.write(out/'models.json',dict(model_id=MODEL_ID,phase='formal',round=1,assumption_verified=False,
            demand=models,mechanisms=mechanisms,curve_registry=registry,
            formula='u=-e_c ln(P/P0)+b_G,c ln(1+G_total/1000)+b_H,c ln(1+H_total/1000)+b_R,c ln(f_R,1(R+0.5Rprev)); share=softmax within own market/country; D=T*share',
            assumptions=['Same-period outlook and chart/sales coefficients shared across markets, authorized but not empirically verified',
                         'Country coefficients independent; no cross-market demand transmission',
                         'R&D rho=.5 and marketing scale1000 retained; marketing uses company-total proxy',
                         'Operations curve predicts efficiency, not direct demand; industry total external',
                         'Curves change by round; formal2 coefficients/technology/risk not inferred from formal1'],
            not_retrained=['formal2 demand: no actual labels','practice rounds: no matching independently archived curve versions',
                           'full finance accounts: deterministic incomplete branches','six-round optimizer: validation gates remain']))
        core.write(out/'mechanism_dataset.json',mr)
        core.write(out/'predictions.json',predictions)
        with (out/'predictions.csv').open('x',encoding='utf-8-sig',newline='') as f:
            cols=[k for k in predictions[0] if k!='source'];w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
            w.writerows({k:r[k] for k in cols} for r in predictions)
        assert all(core.digest(ROOT/p)==h for p,h in before.items()),'Protected source/model changed'
        checks=dict(unique_actual_keys=200,source_and_old_models_unchanged=True,all_ten_markets_used=True,
            country_models=2,complete_competition_groups=True,shares_sum_to_one=True,
            market_prediction_isolation=True,wrong_period_and_missing_or_duplicate_team_rejected=True,
            nested_outer_inner_market_disjoint=True,fold_local_scaling=True,curve_refit_replay=True,
            formal2_not_fitted_without_labels=True)
        core.write(out/'checks.json',checks)
        lines=['# unified-market 假设版本','',f'独立运行：{stamp}；正式1，10市场100队200条国别实际。',
            '', '用户假设：同一期各市场前景、需求响应、研发和运营曲线及销售各类系数相同。该假设允许本版本合并训练，不作为已核实规则，也不改变旧版本情境隔离。',
            '同国家跨市场共享四项需求系数；泰国/印尼分别训练。竞争份额只在本市场、本国家内归一化。',
            '运营图纵轴为效率乘数，进入生产效率；没有额外直接乘需求。研发曲线与销售研发项只计一次。',
            '', '| 国家 | 价格 | 一般营销代理 | 设计师营销代理 | 研发 | 嵌套整市场留出MAE(pp) | 样本内MAE(pp) |',
            '|---|---:|---:|---:|---:|---:|---:|']
        for country,m in models.items():
            lines.append('| '+country+' | '+' | '.join(f'{m["coefficients"][k]:.6g}' for k in country_demand.NAMES)+f' | {m["nested_market_holdout_share_mae_pp"]:.6f} | {m["training_share_mae_pp"]:.6f} |')
        lines += ['', '验证：5个外层折，每折留出2整个市场；内层仅在其余8市场选log/share损失及11档正则，每折重新计算标准化。各市场等权。外层成绩是同回合、给定已实现竞争决策的跨市场条件验证，不是正式2事前预测。',
            '正式1研发/运营SVG曲线重新拟合并精确复现；正式2另登记已核验JSON曲线。两个回合版本不混用；正式2需求系数仍待实际标签，未宣称同回合假设同时证明跨回合系数不变。',
            '', '生产效率ρ/技术尺度、两风险函数和材料单位差额也用100队正式1实际重新拟合，另做整市场留出；风险仅给定实际期末状态，材料差额为经验残差。参数与各折结果见models.json。',
            '', '缺国别营销，使用公司合计代理；行业总量仍外生。ρ与技术存量未完全识别，高投入外推需单列。练习回合缺配套曲线版本，本次不混入；短贷、库存、订单完整财务及六回合优化未实现。',
            '', '产物：models.json、dataset.json、mechanism_dataset.json、predictions.json/CSV、checks.json、manifest.json、代码快照和本日志。保留旧模型，不更新其latest，不操作平台。']
        (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        manifest.update(status='COMPLETE_INDEPENDENT_ASSUMPTION_VERSION',input_hashes=before,
                        code_hashes={p.name:core.digest(p) for p in snapshot.iterdir()})
        with log.open('a',encoding='utf-8') as f:
            f.write('\n完成：需求两国共享模型、效率、两风险函数、材料差额已重训；整市场留出及边界检查通过。正式2曲线单列，需求无标签未拟合；旧模型和源哈希不变。\n')
    except Exception as exc:
        manifest.update(status='FAILED',error_type=type(exc).__name__)
        raise
    finally:
        manifest['output_hashes']={p.relative_to(out).as_posix():core.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}
        core.write(out/'manifest.json',manifest)
    print('OUTPUT',out,flush=True)


if __name__=='__main__':
    main()
