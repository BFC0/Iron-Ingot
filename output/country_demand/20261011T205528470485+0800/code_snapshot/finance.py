"""Conditional accounts; unidentified branches are never treated as complete profits."""
from itertools import product
from scipy.optimize import least_squares
from core import *
from build_model_inputs import production_and_delivery


def accounts(state, decision, demand, efficiency, p):
    assert state['inventory']==0 and state['short_debt']==0 and state['equity']>0
    assert efficiency>0 and len(demand)==2 and all(v>=0 for v in demand)
    assert all(v>0 for v in decision['prices']) and 0<=decision['long_rate']<1
    assert decision['machine_investment']>=0 and decision['long_change']>=-state['long_debt']
    cap=state['capacity']*(1-p['machine_capacity_decline'])+decision['machine_investment']
    prod=production_and_delivery(cap,decision['allocation'],efficiency,demand,decision['priority'],p['wage'],
                                 p['second_shift'],p['third_shift'],state['workers'],p['attrition'],p['severance'])
    revenue=sum(s*v for s,v in zip(prod['sales'],decision['prices']))
    materials=prod['production']*(p['material_cost']+p['uplift'])
    transport=sum(s*v for s,v in zip(prod['sales'],p['transport']))
    marketing=sum(decision['general'])+sum(decision['designer'])+p['marketing_fixed']
    overhead=p['overhead_fixed']+prod['firing']+decision['rd']+decision['operations']
    ebitda=revenue-materials-prod['payroll']-transport-marketing-overhead
    machine_capex=decision['machine_investment']*p['machine_unit_capex']
    building_capex=p['building_capex']
    machine_dep=(state['machine_book']+machine_capex)*p['machine_depreciation']
    building_dep=state['building_book']*p['building_depreciation']
    ebit=ebitda-machine_dep-building_dep
    ar,ap=revenue*p['ar_days']/365,materials*p['ap_days']/365
    long_end=state['long_debt']+decision['long_change']
    long_interest=(state['long_debt']+long_end)/2*decision['long_rate']
    cash_before=state['cash']+ebitda-long_interest+state['ar']-ar+ap-state['ap']-machine_capex-building_capex+decision['long_change']
    cash_interest=state['cash']*p['cash_rate']
    for iteration in range(100):
        pretax=ebit+cash_interest-long_interest
        tax=max(pretax-state['tax_loss'],0)*p['tax_rate']
        cash=cash_before+cash_interest-tax
        updated=max((state['cash']+cash)/2,0)*p['cash_rate']
        if abs(updated-cash_interest)<1e-10:
            break
        cash_interest=updated
    else:
        raise RuntimeError('Cash/tax iteration did not converge')
    profit=pretax-tax
    equity=state['equity']+profit
    assets=state['machine_book']+machine_capex-machine_dep+state['building_book']+building_capex-building_dep+ar+cash
    balance_error=assets-(long_end+ap+equity)
    assert abs(balance_error)<=1e-6
    assert abs(sum(prod['sales'])-prod['production'])<=1e-6
    short_needed=max(p['minimum_cash']-cash,0)
    return dict(production=prod,capacity=cap,sales=prod['sales'],efficiency=efficiency,revenue=revenue,
        materials=materials,transport=transport,marketing=marketing,overhead=overhead,ebitda=ebitda,
        machine_capex=machine_capex,building_capex=building_capex,machine_depreciation=machine_dep,
        building_depreciation=building_dep,ebit=ebit,long_interest=long_interest,cash_interest=cash_interest,
        pretax=pretax,tax=tax,profit=profit,ar=ar,ap=ap,cash=cash,long_debt=long_end,
        short_debt_needed_before_unidentified_short_interest=short_needed,equity=equity,assets=assets,
        balance_error=balance_error,tax_loss_end=max(state['tax_loss']-max(pretax,0),0)+max(-pretax,0),
        fully_computed_in_scope=short_needed==0,iterations=iteration+1,
        delivered_fraction=sum(prod['sales'])/sum(demand) if sum(demand)>0 else None,
        end_inventory=0,scope='零期初库存/零大客户；低现金为未识别短贷分支；税亏与厂房时序仍为条件假设')


def parameters():
    m=read('分步模型拟合与验证.json')
    p=dict(wage=28,second_shift=1.65,third_shift=2.56,attrition=.1,severance=.35,
           material_cost=900,uplift=m['finance']['materials']['uplift_usd_per_unit'],transport=[30,120],
           marketing_fixed=50,overhead_fixed=4000,machine_unit_capex=100,building_capex=800,
           machine_depreciation=.15,machine_capacity_decline=.15,building_depreciation=.07,ar_days=30,ap_days=30,cash_rate=.01,
           tax_rate=.29,minimum_cash=2000)
    return p


def parameter_sources():
    published={}
    name='20261011_model_v2_round1_outlook'
    for key,label,factor,occ in [
        ('wage','泰国',1,0),('second_shift','两班倒',1,0),('third_shift','三班倒',1,0),
        ('attrition','年人员离职率（without costs），%',.01,0),('severance','裁员成本，占薪资%',.01,0),
        ('material_cost','复合梁',1,0),('marketing_fixed','市场调研',1,0),('overhead_fixed','基础成本',1,0),
        ('machine_unit_capex','机器, 复合梁',1,0),('machine_depreciation','机器',.01,0),
        ('machine_capacity_decline','机器',.01,1),('cash_rate','现金及现金等价物',.01,0),
        ('tax_rate','企业所得税率, %',.01,0),('minimum_cash','最低现金, 千 美元',1,0)]:
        ref=step.source(name,label,1,occ)
        published[key]=dict(value=ref['value']*factor,source=ref,phase='formal',round=1,
                            context_id='M5_P1_FORMAL1_VISIBLE',status='当期公布参数')
        assert abs(parameters()[key]-published[key]['value'])<1e-12
    published['transport']=dict(value=[30,120],source=[step.source(name,'泰国 -> 泰国'),step.source(name,'泰国 -> 印尼')],
                                phase='formal',round=1,context_id='M5_P1_FORMAL1_VISIBLE',status='当期公布参数')
    for key in ['uplift','building_capex','building_depreciation','ar_days','ap_days']:
        published[key]=dict(value=parameters()[key],status='经验或条件关系，未完成独立试验',
                            source='分步模型拟合与验证.json',phase='formal',round=1,context_id='M5_P1_FORMAL1_VISIBLE')
    assert set(published)==set(parameters())
    return published


def efficiency_and_risk():
    m=read('分步模型拟合与验证.json')
    rows=m['efficiency']['input_rows']
    params=m['curves']['operations']['parameters']
    models=[]
    for rho in RHOS:
        train=[r for r in rows if r['round']==1]
        test=[r for r in rows if r['round']==2]
        def factor(r):
            return float(step.curve_value(r['operations']+rho*r['previous_operations'],params,'saturation'))
        ratios=np.array([r['effective_observed']/factor(r) for r in train])
        technology=float(np.mean(ratios))
        unique={}
        for r,ratio in zip(train,ratios):
            unique.setdefault((r['operations'],r['previous_operations']),[]).append(float(ratio))
        balanced=float(np.mean([np.mean(v) for v in unique.values()]))
        intervals=[]
        for r in rows:
            q=r['source']['production']['value']; n=r['source']['workers']['value']
            assert n>.005
            intervals.append(dict(round=r['round'],team=r['team'],observed=r['effective_observed'],
                lower=(q-.005)/(n+.005),upper=(q+.005)/(n-.005),
                predicted=technology*factor(r),source=r['source'],
                rounding='产量及人数显示两位小数时的±0.005区间；舍入模式未独立证明'))
        models.append(dict(rho=rho,technology_scale=technology,strategy_balanced_scale=balanced,
            forward_mae=float(np.mean([abs(technology*factor(r)-r['effective_observed']) for r in test])),
            train_strategy_count=len(unique),train_n=len(train),train_current_operations_range=[min(r['operations'] for r in train),max(r['operations'] for r in train)],
            operations_400_prediction=technology*float(step.curve_value(400+rho*700,params,'saturation')),
            operations_400_is_extrapolation=True,intervals=intervals,
            note='技术尺度用练习1重估；练习2仅回溯诊断，不能据前向误差选rho'))
    risks=[]
    for candidate in m['finance']['risk_candidates']:
        # Recover train observations from source-linked reports, not fitted predictions.
        data=read('结构化模型输入.json')
        history=step.historical_accounts(data)
        training=[]
        for h in history:
            if h['round']!=1: continue
            f={k:v['value'] for k,v in h['fields'].items()}
            training.append(dict(team=h['team'],equity_ratio=f['equity']/f['assets'],leverage=(f['long_debt']+f['short_debt'])/f['equity'],premium=f['long_rate']/100-.03))
        def risk_predict(p,r):
            return p[0]*np.exp(-p[1]*r['equity_ratio']) if candidate['form']=='solvency_exponential' else p[0]*r['leverage']**p[1]
        deleted=[]
        for h in training:
            sub=[r for r in training if r['team']!=h['team']]
            fit=least_squares(lambda p:np.array([risk_predict(p,r)-r['premium'] for r in sub]),candidate['parameters'],bounds=([0,0],[10,30]),max_nfev=2000)
            if not fit.success: raise RuntimeError(fit.message)
            deleted.append(dict(removed=h['team'],parameters=fit.x.tolist(),heldout_error_bp=(risk_predict(fit.x,h)-h['premium'])*10000))
        risks.append(dict(**candidate,leave_team_out=deleted,training_rows=training,
                          equity_ratio_range=[min(r['equity_ratio'] for r in training),max(r['equity_ratio'] for r in training)],
                          interpretation='给定实际期末状态的风险关联，非独立前瞻计息识别'))
    return dict(efficiency=models,risk=risks,curve_scope=m['curves'],parameter_provenance=parameter_sources(),low_operations_verified=False,
                note='图形交错留点只检验拟合近似；无其他市场独立曲线与运营400保存试验')


def stress():
    m=read('分步模型拟合与验证.json')
    inp=m['decisions']['current_inputs']; state=inp['state']
    baseline=dict(inp['decision'],long_rate=inp['decision']['long_rate']/100)
    p=parameters()
    original=step.accounts_from_state(state,inp['decision'],inp['demand'],inp['efficiency'],dict(material_cost=p['material_cost']),p['uplift'])
    replay=accounts(state,baseline,inp['demand'],inp['efficiency'],p)
    assert max(abs(replay[k]-original[k]) for k in ['profit','cash','assets','balance_error','revenue'])<1e-9
    tests=[dict(name='归档基准',demand_scale=[1,1],efficiency_delta=0,cost_scale=1,rate_delta=0,ar_days=30)]
    for factor in [-.3,-.2,-.1,.1,.2]:
        for country in ['泰国','印尼','两国']:
            tests.append(dict(name=f'{country}需求{factor:+.0%}',demand_scale=[1+factor if country in [c,'两国'] else 1 for c in COUNTRIES],
                              efficiency_delta=0,cost_scale=1,rate_delta=0,ar_days=30))
    for e in [-.01,-.005,.005,.01]:
        tests.append(dict(tests[0],name=f'效率{e:+}',efficiency_delta=e))
    for c in [.9,.95,1.05,1.1]:
        tests.append(dict(tests[0],name=f'可变成本×{c}',cost_scale=c))
    for r in [.005,.01]:
        tests.append(dict(tests[0],name=f'利率+{r*100}个百分点',rate_delta=r))
    for days in [45,60]:
        tests.append(dict(tests[0],name=f'回款{days}天',ar_days=days))
    tests += [dict(tests[0],name='需求-20%与效率-0.01',demand_scale=[.8,.8],efficiency_delta=-.01),
              dict(tests[0],name='成本+10%与回款60天',cost_scale=1.1,ar_days=60),
              dict(tests[0],name='组合不利',demand_scale=[.7,.7],efficiency_delta=-.01,cost_scale=1.1,rate_delta=.01,ar_days=60)]
    def evaluate(test):
        pars=dict(p,wage=p['wage']*test['cost_scale'],material_cost=p['material_cost']*test['cost_scale'],
                  transport=[v*test['cost_scale'] for v in p['transport']],ar_days=test['ar_days'])
        decision=dict(baseline,long_rate=baseline['long_rate']+test['rate_delta'])
        dem=(np.array(inp['demand'])*test['demand_scale']).tolist()
        return dict(test,output=accounts(state,decision,dem,inp['efficiency']+test['efficiency_delta'],pars))
    deterministic=[evaluate(t) for t in tests]
    boundaries=[]
    for inv in [0,1,10,20]:
        capacity=state['capacity']*.85+inv
        for allocation in [0,100/3-1e-5,100/3+1e-5,200/3-1e-5,200/3+1e-5,100]:
            demand=[capacity,capacity]
            d=dict(baseline,machine_investment=inv,allocation=allocation)
            boundaries.append(dict(machine_investment=inv,allocation=allocation,
                                   legal_ui_range_verified=False,output=accounts(state,d,demand,inp['efficiency'],p)))
    firing_production=state['workers']*.9*inp['efficiency']
    for q in [firing_production-1e-5,firing_production+1e-5]:
        d=dict(baseline,allocation=100,machine_investment=10)
        boundaries.append(dict(firing_boundary_quantity=q,output=accounts(state,d,[q,0],inp['efficiency'],p),
                               legal_ui_range_verified=False))
    rng=np.random.default_rng(20261011)
    n=2000
    u=np.column_stack([(rng.permutation(n)+rng.random(n))/n for _ in range(6)])
    samples=[]
    for i,row in enumerate(u):
        t=dict(name=f'分层样本{i}',demand_scale=(.7+.5*row[:2]).tolist(),efficiency_delta=-.01+.02*row[2],
               cost_scale=.9+.2*row[3],rate_delta=.01*row[4],ar_days=[30,45,60][min(int(row[5]*3),2)])
        samples.append(evaluate(t))
    valid=[r for r in samples if r['output']['fully_computed_in_scope']]
    return dict(kind='ASSUMED_STRESS_OF_ARCHIVED_PERSONAL_BASELINE_NOT_SEARCH_CANDIDATES',units=UNITS,
                baseline=baseline,parameters=p,deterministic=deterministic,boundaries=boundaries,samples=samples,
                sampling=dict(seed=20261011,n=n,method='每个连续维度2000等宽分层随机排列，加层内均匀抖动；应收天数映射为30/45/60',
                              ranges=dict(country_demand_scale=[.7,1.2],efficiency_delta=[-.01,.01],cost_scale=[.9,1.1],rate_delta=[0,.01],ar_days=[30,45,60]),
                              source='用户指定假定范围，不是官方概率分布；每国需求只施加一次缩放'),
                summary=dict(n=n,fully_computed_n=len(valid),scope_failure_fraction=1-len(valid)/n,
                             profit_quantiles=np.quantile([r['output']['profit'] for r in valid],[.05,.5,.95]).tolist() if valid else None,
                             cash_quantiles=np.quantile([r['output']['cash'] for r in valid],[.05,.5,.95]).tolist() if valid else None),
                coverage=dict(single_demand=True,single_efficiency=True,single_cost=True,single_interest=True,receivables=True,
                              two_factor=True,combined_adverse=True,shift_and_firing_math=True,machine_math=True,
                              rival_strategies=False,demand_model_variants=False,risk_linkage=False,long_loan_cash_boundary=False,
                              short_loan_interest=False,inventory=False,bulk_orders=False,cross_round=False,final_candidates=False),
                checks=dict(old_adapter_equivalence=True,balance_error_max=max(abs(r['output']['balance_error']) for r in samples),
                            all_samples_counted=len(samples)==n),
                limit='分位数与失败占比仅描述此假定测试集合；未完成联合候选压力测试，不称为真实概率或全部可能最坏值')
