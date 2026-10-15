"""Training-only selection; retrospective forward and influence diagnostics."""
from core import *


def options():
    for standardized in [False, True]:
        for piecewise in [False, True]:
            for rho in RHOS:
                for penalty in PENALTIES:
                    yield dict(standardized=standardized,piecewise=piecewise,rho=rho,penalty=penalty,loss='log')


def cv(rows, params, config):
    errors = np.zeros(len(rows))
    scales = []
    for column in sorted({r['team_column'] for r in rows}):
        train = [r for r in rows if r['team_column'] != column]
        test_ids = [i for i,r in enumerate(rows) if r['team_column'] == column]
        model = fit(train, params, **config)
        assert not {tuple(key(r)) for r in train} & {tuple(key(rows[i])) for i in test_ids}
        prediction = predict(rows, features(rows,params,config['rho'],config['piecewise']), model['beta'])
        errors[test_ids] = abs(prediction[test_ids] - actual_shares(rows)[test_ids])
        scales.append(dict(heldout_column=column, scale=model['scale'], inactive_columns=model['inactive_columns']))
    return float(equal_weights(rows) @ errors), scales


def choose(rows, params, configs):
    path = []
    for config in configs:
        error, scales = cv(rows,params,config)
        path.append(dict(**config, cv_share_mae_pp=error*100, fold_scales=scales,
                         parameter_count=7 if config['piecewise'] else 5))
    best = min(r['cv_share_mae_pp'] for r in path)
    close = [r for r in path if r['cv_share_mae_pp'] <= best*1.01]
    chosen = min(close,key=lambda r:(r['parameter_count'],r['cv_share_mae_pp']))
    config = {k:chosen[k] for k in ['standardized','piecewise','rho','penalty','loss']}
    return config, path


def prediction_rows(rows, model, params, label, train):
    pred = predict(rows,features(rows,params,model['rho'],model['piecewise']),model['beta'])
    actual = actual_shares(rows)
    result = []
    for i,r in enumerate(rows):
        peers = [q for q in train if q['country']==r['country']]
        effective_rd = r['rd']+model['rho']*r['previous_rd']
        in_range = all(min(q[k] for q in peers)<=r[k]<=max(q[k] for q in peers)
                       for k in ['price','general','designer','rd'])
        total = sum(rows[j]['demand'] for j in old.groups(rows)[old.group_key(r)])
        result.append(dict(model=label,market_id=r['market_id'],country=r['country'],phase=r['phase'],round=r['round'],
                           team=r['team'],team_id=r['team_id'],competition='已实现对手策略',decision='历史决策',
                           category='retrospective_model',price=r['price'],actual=r['demand'],
                           actual_share=float(actual[i]),predicted_share=float(pred[i]),
                           predicted=float(pred[i]*total),residual=float((pred[i]-actual[i])*total),
                           total_assumption=total,oracle_total=True,in_training_range=in_range,
                           effective_rd=effective_rd,rd_curve_extrapolation=effective_rd>1200,
                           source=r['sources']['demand'],unit='千单位'))
    return result


def run(rows, out):
    params = read(FROZEN)['rd_curve_parameters']
    usable = [r for r in rows if r['usable_for_fit']]
    result = dict(status='RETROSPECTIVE_RESEARCH_NOT_FORMAL_VALIDATION', pools={}, predictions=[],
                  assumptions=['已实现当期对手策略','给定实际行业总量的份额诊断，不能当作可实现事前需求成绩',
                               '研发曲线采用原冻结版本；仅市场5可见曲线，跨市场迁移未证明',
                               '合计营销代理，不做国别分配优化','非负与softmax为研究约束，不是已识别的平台机制'],
                  selection='练习1内按整队历史留出；每折重算尺度；市场/国家等权MAE；误差相差≤1%优先较少参数',
                  curve_ceiling_kusd=1200)
    for name,pool in [('A',[r for r in usable if r['market_id']==5]),('B',usable)]:
        train = [r for r in pool if r['round']==1]
        test = [r for r in pool if r['round']==2]
        selected,path = choose(train,params,list(options()))
        # Zero-preserving share loss is compared at the continuation selected inside training only.
        share_configs = [dict(standardized=True,piecewise=p,rho=selected['rho'],penalty=l,loss='share')
                         for p in [False,True] for l in PENALTIES]
        share_selected,share_path = choose(train,params,share_configs)
        path += share_path
        best=min(r['cv_share_mae_pp'] for r in path)
        candidates=[r for r in path if r['cv_share_mae_pp']<=best*1.01]
        win=min(candidates,key=lambda r:(r['parameter_count'],r['cv_share_mae_pp']))
        selected={k:win[k] for k in ['standardized','piecewise','rho','penalty','loss']}
        model=fit(train,params,**selected)
        final=fit(pool,params,**selected)
        forward=prediction_rows(test,model,params,name+'-v2-forward',train)
        full=prediction_rows(pool,final,params,name+'-v2-refit',pool)
        result['predictions'] += forward+full
        frozen=read(FROZEN)['models'][name]['competitive']
        baseline_model=dict(beta=frozen['coefficients'],rho=.5,piecewise=False)
        baseline=prediction_rows(pool,baseline_model,params,name+'-frozen',pool)
        result['predictions'] += baseline
        # The old forward model selects only within practice1; frozen full-data fits stay separately labeled.
        penalty,_=old.choose_penalty(train,old.feature_matrix(train,params),'competitive')
        old_forward=dict(beta=old.fit(train,old.feature_matrix(train,params),penalty).tolist(),rho=.5,piecewise=False)
        result['predictions'] += prediction_rows(test,old_forward,params,name+'-old-forward',train)
        diagnostics=[]
        for field in ['market_id','team_id']:
            for unit in sorted({r[field] for r in pool}):
                sub=[r for r in pool if r[field]!=unit]
                if len(sub)<10:
                    continue
                fitted=fit(sub,params,**selected)
                diagnostics.append(dict(removed_field=field,removed=unit,beta=fitted['beta'],scale=fitted['scale'],
                                         note='删队改变竞争组；仅影响诊断，非可比成绩'))
        positive=[r for r in pool if r['demand']>0]
        xx=features(positive,params,selected['rho'],selected['piecewise'])
        for ids in old.groups(positive).values():
            xx[ids]-=xx[ids].mean(axis=0)
        w=equal_weights(positive)
        high=np.array([r['country']=='印尼' and r['price']>1.5*r['initial_price'] for r in positive])
        info=w*xx[:,1]**2
        corr=np.corrcoef(xx.T)
        rng=np.random.default_rng(20261011)
        units=sorted({r['market_id'] if name=='B' else r['team_id'] for r in pool})
        bootstrap=[]
        for _ in range(200):
            sample=[]
            for i,unit in enumerate(rng.choice(units,len(units),replace=True)):
                cluster=[r for r in pool if (r['market_id'] if name=='B' else r['team_id'])==unit]
                sample.extend(dict(r,market_id=100+i,team_id=f'{i}:{r["team_id"]}') if name=='B'
                              else dict(r,team_id=f'{i}:{r["team_id"]}') for r in cluster)
            bootstrap.append(fit(sample,params,**selected)['beta'])
        result['pools'][name]=dict(selected=selected,cv_path=path,forward_model=model,refit_model=final,
            forward_share_mae_pp=score(test,np.array([r['predicted_share'] for r in forward]))*100,
            fold_manifest=[dict(heldout_column=c,train_keys=[key(r) for r in train if r['team_column']!=c],
                                test_keys=[key(r) for r in train if r['team_column']==c]) for c in range(1,11)],
            outer_train_keys=[key(r) for r in train],outer_test_keys=[key(r) for r in test],
            influence=diagnostics,high_price_information_fraction=float(info[high].sum()/info.sum()),
            correlations=[[float(v) if np.isfinite(v) else None for v in line] for line in corr],
            zero_count=sum(r['demand']==0 for r in pool),
            coefficient_boundary=[i for i,v in enumerate(final['beta']) if v<1e-7],
            resampling=dict(seed=20261011,n=200,unit='whole_market' if name=='B' else 'team_history',
                            beta=bootstrap,quantiles=np.quantile(bootstrap,[.05,.5,.95],axis=0).tolist(),
                            label='描述性重采样分布，不是置信区间；重复抽取的簇单独编号'),
            fit_in_range_n=sum(r['rd']+selected['rho']*r['previous_rd']<=1200 for r in pool),
            joint_extrapolation_note='单变量在范围内不证明联合策略在历史支持范围内')
        write(out / f'demand_{name}_checkpoint.json',result['pools'][name])
        print(f'{name}: selected={selected}; forward share MAE={result["pools"][name]["forward_share_mae_pp"]:.4f}pp',flush=True)
    result['stage2_gate']=False
    result['stage2_gate_reason']='结构比较已运行；零值舍入、跨市场曲线迁移、营销内生性、低投入效率与稳定性仍未获独立证据，不可确定推荐'
    return result
