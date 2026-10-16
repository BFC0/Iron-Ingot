"""All-input conditional search, using formal4 curves; never a verified profit optimizer."""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
import numpy as np
from scipy.optimize import differential_evolution, minimize
import t4v1a as frozen

BUNDLE = ROOT/'output/t4v1a/20261014T175143627079+0800'
INITIAL = ROOT/'output/round_close/20261013_formal3_close/formal4_initial/verification/20261014T002441'
OUT = ROOT/Path((ROOT/'work/formal4_all_active.txt').read_text(encoding='utf-8'))
P = ['复合梁','连接件']
C = ['泰国','印尼']
NAMES = ['复合梁泰国售价','复合梁印尼售价','连接件泰国售价','连接件印尼售价',
         '一般营销复合梁泰国','一般营销复合梁印尼','一般营销连接件泰国','一般营销连接件印尼',
         '设计师营销复合梁泰国','设计师营销复合梁印尼','设计师营销连接件泰国','设计师营销连接件印尼',
         '复合梁研发','连接件研发','运营','复合梁机器投资','连接件机器投资档数','复合梁产能分配','连接件产能分配','长期贷款变化百千美元']


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def save(name,value):
    with (OUT/name).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')


def curve(x, item):
    p=item['parameters']
    return p[0]+p[1]*(x+p[2])**p[3] if item['form']=='power' else p[0]+p[1]*x/(p[2]+x)


def main():
    r=read(BUNDLE/'models_full.json');request=read(BUNDLE/'example_request.json');data=read(BUNDLE/'inputs.json')
    with (INITIAL/'formal4_current_checklist.csv').open(encoding='utf-8-sig',newline='') as f:
        fields=list(csv.DictReader(f))[2:]
    values={int(x['source_row']):x['PYT_value'] for x in fields}
    num=lambda i:float(values[i].replace('\xa0','').replace(' ',''))
    assert len(fields)==42 and len({x['key'] for x in fields})==42
    state=next(x['closing']['values'] for x in data['financial_state_pairs'] if x['team_id']==r['target_team_id'])
    opening_residual=state['assets']-state['long_debt']-state['ap']-state['equity']
    assert abs(opening_residual)<=2, 'Opening displayed accounts exceed rounding tolerance'
    curves=r['formal4_curves']['curves']
    assert all(x['round']==4 for x in curves.values())
    rdcurves=[curves['rd_beam'],curves['rd_connector']];opcurve=curves['operations_thailand']
    coefficients=[r['demand'][p]['SHARE'] for p in P]
    beta=np.array([x['beta'][:5] for x in coefficients])
    baseprices=np.array([[num(9),num(10)],[num(13),num(14)]])
    gbase=np.array([[num(18),num(19)],[num(21),num(22)]])
    dbase=np.array([[num(25),num(26)],[num(29),num(30)]])
    rdbase=np.array([num(51),num(52)]);rdprevious=np.array([1000.,400.])
    efbase=np.array([num(76),num(77)])
    opsrho=np.array([r['efficiency'][p]['chosen']['rho'] for p in P])
    rdrho=np.array([x['rho'] for x in coefficients])
    reference=frozen.demand_reference(r,request['competitors'],request['market_totals_kunits'],request['growth'])
    shares=np.array([[next(x['share'] for x in reference['predictions'] if x['team_id']==r['target_team_id'] and x['product']==p and x['country']==c) for c in C] for p in P])
    totals=np.array([[r['formal3_market_totals_kunits'][p][c]*(.825 if j==0 else 1.05) for c in C] for j,p in enumerate(P)])
    materials=np.array([r['application_parameters']['material/'+p]['value']+r['materials'][p]['models']['additive']['parameter'] for p in P])
    freight=np.array([[30.,90.],[.5,2.]])
    pricesupport=np.array([[[min(x['price'] for x in request['competitors'] if x['product']==p and x['country']==c),max(x['price'] for x in request['competitors'] if x['product']==p and x['country']==c)] for c in C] for p in P])
    bounds=pricesupport.reshape(4,2).tolist()+[[0,2700]]*4+[[0,3840]]*4+[[0,1000],[0,2000],[0,968],[0,20],[0,20],[0,100],[0,100],[-127,100]]
    baseline=np.array([*baseprices.ravel(),*gbase.ravel(),*dbase.ravel(),*rdbase,num(49),0.,0.,num(42),num(43),0.])
    common=dict(marketing='local',mapping='direct',beam_growth=0.,connector_growth=.05,wage_growth=.0,
                material_scale=1.,rival_price=1.,rival_marketing=1.,efficiency_scale=1.,ar_days=30.,interest_timing=.5,
                tax_loss=0.,building_capex=800.,marketing_decay=0.,base_rate=.05)
    configs=[dict(common,name='正式4曲线_国别响应_中性'),dict(common,name='正式4曲线_合计代理_中性',marketing='total'),
             dict(common,name='正式4曲线_历史横轴假设',mapping='lagged'),
             dict(common,name='联合不利',beam_growth=-.15,connector_growth=0.,wage_growth=.1,material_scale=1.1,rival_price=.9,rival_marketing=1.5,efficiency_scale=.9,ar_days=60.,interest_timing=0.,base_rate=.06)]

    def evaluate(x, cfg, details=False, constraint_penalty=False, summary=False):
        x=np.asarray(x,float)
        if x.ndim==1:x=x[:,None]
        n=x.shape[1];price=x[:4].reshape(2,2,n);general=x[4:8].reshape(2,2,n);designer=x[8:12].reshape(2,2,n)
        rd=x[12:14];ops=x[14];invest=np.array([np.rint(x[15]),20*np.rint(x[16])]);allocation=x[17:19]/100;loanchange=100*np.rint(x[19])
        cap=np.broadcast_to(np.array([31.03,85.])[:,None],(2,n)).copy()+invest
        cash=np.full(n,state['cash']);ar=np.full(n,state['ar']);ap=np.full(n,state['ap']);machine=np.full(n,state['machine_book']);building=np.full(n,state['building_book'])
        debt=np.full(n,state['long_debt']);equity=np.full(n,state['equity']);loss=np.full(n,cfg['tax_loss']);assets=np.full(n,state['assets'])
        inventory=np.zeros((2,n));invbook=np.zeros((2,n));workers=np.broadcast_to(np.array([109.63,3.70])[:,None],(2,n)).copy()
        rdprev=np.broadcast_to(rdprevious[:,None],(2,n)).copy();opsprev=np.full(n,600.)
        previousg=np.broadcast_to(gbase[:,:,None],(2,2,n)).copy();previousd=np.broadcast_to(dbase[:,:,None],(2,2,n)).copy()
        totalprofit=np.zeros(n);minimumcash=np.full(n,np.inf);maxbalance=np.zeros(n);domain=np.ones(n,bool);periods=[]
        logprice=-beta[:,0:2,None]*np.log(price/baseprices[:,:,None])
        for j,m in enumerate(coefficients):
            if m['piecewise']:
                anchor=np.array([own['initial_price'] for own in request['competitors'] if own['product']==P[j] and own['team_id']==r['target_team_id']])
                for k in range(2):
                    logprice[j,k]-=m['beta'][5+k]*(np.maximum(np.log(price[j,k]/(1.5*anchor[k])),0)-max(math.log(baseprices[j,k]/(1.5*anchor[k])),0))
        for t in range(3):
            mdec=cfg['marketing_decay'];ge=general+mdec*previousg;de=designer+mdec*previousd
            gb=gbase*(1+mdec);db=dbase*(1+mdec)
            if cfg['marketing']=='total':
                gm=np.log((1000+ge.sum(axis=(0,1)))/(1000+gb.sum()))[None,None,:]
                dm=np.log((1000+de.sum(axis=(0,1)))/(1000+db.sum()))[None,None,:]
            else:
                gm=np.log((1000+ge)/(1000+gb[:,:,None]));dm=np.log((1000+de)/(1000+db[:,:,None]))
            lag=cfg['mapping']=='lagged';rex=rd+(rdrho[:,None]*rdprev if lag else 0)
            ranchor=rdbase+(rdrho*rdprevious if lag else 0)
            oe=np.broadcast_to(ops[None,:],(2,n))+(opsrho[:,None]*opsprev if lag else 0)
            oa=np.full(2,600.)+(opsrho*600 if lag else 0)
            rdlog=np.array([np.log(curve(rex[j],rdcurves[j])/curve(ranchor[j],rdcurves[j])) for j in range(2)])
            efficiency=efbase[:,None]*curve(oe,opcurve)/curve(oa[:,None],opcurve)*cfg['efficiency_scale']
            domain &= np.all(rex<=2000+1e-9,axis=0)&np.all(oe<=1296+1e-9,axis=0)
            change=logprice+beta[:,2,None,None]*gm+beta[:,3,None,None]*dm+beta[:,4,None,None]*rdlog[:,None,:]
            # shortcut: historical rivals remain fixed except explicit shocks; new spend effects are unverified anchored scenarios.
            rival=np.empty((2,2))
            for j,m in enumerate(coefficients):
                for k in range(2):
                    pool=[a for a in request['competitors'] if a['product']==P[j] and a['country']==C[k] and a['team_id']!=r['target_team_id']]
                    delta=[]
                    for a in pool:
                        dp=-m['beta'][k]*math.log(cfg['rival_price'])
                        if m['piecewise']:
                            dp-=m['beta'][5+k]*(max(math.log(a['price']*cfg['rival_price']/(1.5*a['initial_price'])),0)-max(math.log(a['price']/(1.5*a['initial_price'])),0))
                        dp+=m['beta'][2]*math.log((1000+a['general']*cfg['rival_marketing'])/(1000+a['general']))+m['beta'][3]*math.log((1000+a['designer']*cfg['rival_marketing'])/(1000+a['designer']))
                        basefeat=frozen.core.features([a],r['curves']['rd/'+P[j]]['parameters'],m['rho'],m['piecewise'])[0]
                        delta.append((float(basefeat@np.array(m['beta'])),dp))
                    scale=max(z[0] for z in delta);weights=np.exp([z[0]-scale for z in delta])
                    rival[j,k]=float(np.dot(weights,np.exp([z[1] for z in delta]))/weights.sum())
            adjusted=shares[:,:,None]*np.exp(change)
            predictedshare=adjusted/(adjusted+(1-shares[:,:,None])*rival[:,:,None])
            growth=np.array([(1+cfg['beam_growth'])**t,(1+cfg['connector_growth'])**t])[:,None,None]
            demand=predictedshare*totals[:,:,None]*growth
            if cfg['name']=='联合不利':demand[0]*=.8/.825
            q=cap*allocation
            q[0]=np.minimum(q[0],np.maximum(demand[0].sum(axis=0)-inventory[0],0))
            available=inventory+q;sales=np.zeros((2,2,n));net=price-freight[:,:,None]
            for j in range(2):
                domestic=net[j,0]>=net[j,1]
                first=np.where(domestic,0,1);firstd=np.where(domestic,demand[j,0],demand[j,1]);firstsale=np.minimum(firstd,available[j])
                secondsale=np.minimum(np.where(domestic,demand[j,1],demand[j,0]),available[j]-firstsale)
                sales[j,0]=np.where(domestic,firstsale,secondsale);sales[j,1]=np.where(domestic,secondsale,firstsale)
            closing=available-sales.sum(axis=1)
            wage=33*(1+cfg['wage_growth'])**t
            b1=np.minimum(q,cap/3);b2=np.minimum(np.maximum(q-cap/3,0),cap/3);b3=np.maximum(q-2*cap/3,0)
            payroll=(b1+1.65*b2+2.56*b3)/efficiency*wage
            newworkers=q/efficiency;firing=np.maximum(workers*.9-newworkers,0)*wage*.35
            productioncost=q*materials[:,None]*cfg['material_scale']+payroll
            poolbook=invbook+productioncost
            endingbook=np.divide(poolbook*closing,available,out=np.zeros_like(poolbook),where=available>0)
            cogs=(poolbook-endingbook).sum(axis=0)
            revenue=(sales*price).sum(axis=(0,1));transport=(sales*freight[:,:,None]).sum(axis=(0,1))
            spending=general.sum(axis=(0,1))+designer.sum(axis=(0,1))+rd.sum(axis=0)+ops
            ebitda=revenue-cogs-transport-.6*closing.sum(axis=0)-firing.sum(axis=0)-spending-6050
            capex=(invest*np.array([58.,1.])[:,None]).sum(axis=0) if t==0 else np.zeros(n)
            bc=cfg['building_capex'];md=.15*(machine+capex);bd=.07*building
            ebit=ebitda-md-bd
            change_debt=loanchange if t==0 else np.zeros(n);newdebt=debt+change_debt
            startassets=assets+change_debt
            ratio=np.divide(equity,startassets,out=np.zeros(n),where=startassets>0)
            domain &= np.isfinite(ratio)&(ratio>=0)&(ratio<=.9480600573326143)
            premium=r['risk']['solvency_exponential']['parameters']
            rate=cfg['base_rate']+premium[0]*np.exp(-premium[1]*np.clip(ratio,0,1))
            interest=(cfg['interest_timing']*newdebt+(1-cfg['interest_timing'])*debt)*rate
            newar=revenue*cfg['ar_days']/365;newap=(q*materials[:,None]*cfg['material_scale']).sum(axis=0)*30/365
            k=cash+ebitda-interest+ar-newar+newap-ap+invbook.sum(axis=0)-endingbook.sum(axis=0)-capex-bc+change_debt
            cash_notax=(k+.005*cash)/.995
            pretax_notax=ebit-interest+.005*(cash+cash_notax)
            taxed=pretax_notax>loss
            newcash=np.where(taxed,(k+.005*cash*.71-.29*(ebit-interest-loss))/(1-.005*.71),cash_notax)
            cashinterest=.005*(cash+newcash);pretax=ebit-interest+cashinterest;tax=np.maximum(pretax-loss,0)*.29
            profit=pretax-tax;newequity=equity+profit;newmachine=machine+capex-md;newbuilding=building+bc-bd
            newassets=newmachine+newbuilding+newar+newcash+endingbook.sum(axis=0)
            error=newassets-(newdebt+newap+newequity+opening_residual)
            maxbalance=np.maximum(maxbalance,abs(error));minimumcash=np.minimum(minimumcash,newcash)
            if t==0:minimumcash=np.minimum(minimumcash,cash+change_debt-capex-bc)
            domain &= (newdebt>=0)&(startassets>0)&(ratio>=0)&(ratio<=.9480600573326143)&(newequity>0)
            totalprofit+=profit
            if details:
                periods.append(dict(round=4+t,profit=float(profit[0]),cash=float(newcash[0]),long_debt=float(newdebt[0]),
                    prices=price[:,:,0].tolist(),demand=demand[:,:,0].tolist(),production=q[:,0].tolist(),sales=sales[:,:,0].tolist(),
                    capacity=cap[:,0].tolist(),efficiency=efficiency[:,0].tolist(),workers=newworkers[:,0].tolist(),
                    payroll=payroll[:,0].tolist(),severance=firing[:,0].tolist(),closing_inventory=closing[:,0].tolist(),
                    inventory_book_value=endingbook[:,0].tolist(),ebitda=float(ebitda[0]),interest=float(interest[0]),rate=float(rate[0]),
                    tax=float(tax[0]),assets=float(newassets[0]),equity=float(newequity[0]),balance_error=float(error[0]),
                    rd_effective_x=rex[:,0].tolist(),operations_effective_x=oe[:,0].tolist()))
            cash,ar,ap,machine,building,debt,equity,assets=newcash,newar,newap,newmachine,newbuilding,newdebt,newequity,newassets
            loss=np.maximum(loss-np.maximum(pretax,0),0)+np.maximum(-pretax,0)
            inventory,invbook,workers=closing,endingbook,newworkers
            rdprev,opsprev,previousg,previousd=rd,ops,general,designer
            cap=cap*.85
        penalty=np.maximum(2050-minimumcash,0)*100+np.maximum(x[4:8].sum(axis=0)-2700,0)*100+np.maximum(x[8:12].sum(axis=0)-3840,0)*100
        penalty+=np.where(domain,0,1e8)
        score=totalprofit-penalty
        if constraint_penalty:return penalty
        if summary:return totalprofit,minimumcash,penalty
        if details:return dict(config=cfg,scenario_profit_4_to_6=float(totalprofit[0]),minimum_cash=float(minimumcash[0]),max_balance_error=float(maxbalance[0]),domain_valid=bool(domain[0]),penalty=float(penalty[0]),periods=periods,ranking_eligible=False)
        return score

    def objective(x, adverse_objective=False):
        if adverse_objective:return -np.min(np.array([evaluate(x,c) for c in configs]),axis=0)
        return -np.min(np.array([evaluate(x,c) for c in configs[:3]]),axis=0)+evaluate(x,configs[3],constraint_penalty=True)

    # Baseline anchoring, accounting identity and batch evaluation are checked before any search.
    base=evaluate(baseline,configs[0],True)
    assert np.allclose(base['periods'][0]['demand'],shares*totals,atol=1e-10)
    assert base['max_balance_error']<1e-6
    assert np.allclose(evaluate(np.column_stack([baseline,baseline]),configs[0]),evaluate(baseline,configs[0]))
    assert all(4<=p['round']<=6 for p in base['periods'])
    assert np.allclose(base['periods'][0]['rd_effective_x'],rdbase)
    assert np.allclose(base['periods'][0]['operations_effective_x'],[600,600])
    print('pre-search checks PASS',flush=True)
    searches=[];winners=[];leaders=[]
    for adverse_objective in [False,True]:
        best=None
        for seed in [11,29]:
            fn=lambda x:objective(x,adverse_objective)
            opt=differential_evolution(fn,bounds,seed=seed,popsize=12,maxiter=700,tol=.001,atol=2.5,polish=False,
                vectorized=True,updating='deferred',integrality=[False]*15+[True,True,False,False,True])
            if not opt.success:
                opt=differential_evolution(fn,bounds,seed=seed+1,popsize=12,maxiter=1400,tol=.001,atol=2.5,polish=False,
                    vectorized=True,updating='deferred',init=opt.population,integrality=[False]*15+[True,True,False,False,True])
            assert opt.success,opt.message
            searches.append(dict(objective_type='adverse' if adverse_objective else 'neutral',seed=seed,x=opt.x.tolist(),objective=-float(opt.fun),converged=True,iterations=opt.nit))
            print('search',adverse_objective,seed,-float(opt.fun),opt.nit,flush=True)
            if best is None or opt.fun<best.fun:best=opt
        leaders.extend(dict(objective_type='adverse' if adverse_objective else 'neutral',x=best.population[i].tolist(),score=-float(best.population_energies[i])) for i in np.argsort(best.population_energies)[:100])
        x=best.x.copy()
        x[:2]=np.round(x[:2]);x[2:4]=np.round(x[2:4],1);x[4:15]=np.round(x[4:15]);x[17:19]=np.round(x[17:19],1)
        x[15:17]=np.rint(x[15:17]);x[19]=np.rint(x[19])
        for _ in range(5):
            if all(evaluate(x,c,True)['penalty']==0 for c in configs):break
            x[19]+=1
        assert all(evaluate(x,c,True)['penalty']==0 for c in configs), 'Rounded plan is infeasible'
        winners.append(x)
    x=winners[0]
    candidates=[('中性收益优先且联合不利现金达标候选',winners[0]),('联合不利收益优先候选',winners[1]),('归档基准',baseline)]
    previous=read(ROOT/'output/formal4_decision/20261014T205406575489+0800/result.json')
    old=baseline.copy();old[:4]=np.array([a['prices'] for a in previous['products']]).ravel();old[17:19]=[a['allocation'] for a in previous['products']]
    candidates.append(('此前价格生产候选',old))
    extras=[dict(common,name='营销延续0.5',marketing_decay=.5),dict(common,name='未来税亏20000',tax_loss=20000.),
            dict(common,name='厂房投资为零情景',building_capex=0.),dict(common,name='按期末长债计息情景',interest_timing=1.)]
    allconfigs=configs+extras
    comparisons=[]
    for name,z in candidates:
        result=[evaluate(z,c,True) for c in allconfigs]
        assert all(a['max_balance_error']<1e-6 for a in result)
        comparisons.append(dict(name=name,x=z.tolist(),evaluations=result))
    assert all(a['domain_valid'] and a['penalty']==0 for a in comparisons[0]['evaluations'])
    assert min(a['scenario_profit_4_to_6'] for a in comparisons[0]['evaluations'][:3])>=min(a['scenario_profit_4_to_6'] for a in comparisons[2]['evaluations'][:3])
    delta=abs(searches[0]['objective']-searches[1]['objective'])
    save('joint_result.json',dict(status='ALL_INPUT_CONDITIONAL_SCENARIO_SEARCH_NOT_VERIFIED_OPTIMUM',curve_round=4,training_round=3,
        remaining_profit_ranking=False,live_readback=False,variables=NAMES,bounds=bounds,searches=searches,seed_objective_difference=delta,
        comparisons=comparisons,unknowns=['有效投入映射','真实国别营销系数','未来前景和曲线','税亏','计息时点','厂房现金时序','招标中标函数','未披露合同','分包成本机制'],
        policy='正式4选择本向量；正式5/6同价格、同名义营销研发运营和同产能分配，机器投资仅正式4，贷款变化仅正式4；未来滚动决策未优化',
        assumptions=['正式4曲线用于所有新增研发运营效果；直接横轴为主情景，历史横轴仅敏感性','正式3冻结份额是锚点，未将其称作正式4实际份额',
            '机器本期生效，现有容量未来每期衰减15%；厂房投资800/年、折旧7%、应收30/60天、应付30天为未核实情景',
            '库存加权平均计价、现金平均计息、税亏0/20000均为情景，不是已核机制','未知正式5/6曲线显式假设沿用正式4曲线，不称已知事实',
            '八项营销全部参与搜索，国别响应与公司总额代理是两种未验证假设，不宣称真实因果回报'],
        checks=dict(formal4_curves_only=True,anchored_baseline_demand=True,batch_equals_scalar=True,balance_identity=True,
                    curve_domain=True,searches_converged=True,seed_difference_kusd=delta,complete_profit_validation=False)))
    save('inputs.json',dict(registry_path=str(BUNDLE.relative_to(ROOT)),baseline=baseline.tolist(),baseline_state=state,opening_display_rounding_residual_kusd=opening_residual,
        original_fields=fields,formal4_curves=curves,scenario_configs=allconfigs))
    save('search_leaders.json',leaders)
    rng=np.random.default_rng(20261014);count=2000
    u=np.column_stack([(rng.permutation(count)+rng.random(count))/count for _ in range(8)])
    samples=[];plans=np.column_stack([z for name,z in candidates])
    for i,row in enumerate(u):
        cfg=dict(common,name='分层压力',marketing='local' if row[0]<.5 else 'total',mapping='direct' if row[1]<.5 else 'lagged',
            beam_growth=-.15+.25*row[2],wage_growth=.1*row[3],material_scale=.9+.2*row[4],
            rival_price=.9+.2*row[5],efficiency_scale=.9+.2*row[6],ar_days=30.+30*row[7])
        profits,cashmin,penalty=evaluate(plans,cfg,summary=True)
        samples.append(dict(index=i,config=cfg,profits=profits.tolist(),minimum_cash=cashmin.tolist(),invalid_or_cash_shortfall=(penalty>0).tolist()))
    save('stress_2000.json',dict(seed=20261014,method='8维等宽分层排列及层内均匀抖动；每条使用同一冲击比较4方案；不是概率分布',plans=[name for name,z in candidates],samples=samples,
        summary=[dict(name=name,profit_quantiles=np.quantile([s['profits'][j] for s in samples],[.05,.5,.95]).tolist(),minimum_cash_min=min(s['minimum_cash'][j] for s in samples),scope_failure_fraction=sum(s['invalid_or_cash_shortfall'][j] for s in samples)/count) for j,(name,z) in enumerate(candidates)]))
    print('OUTPUT',OUT,flush=True);print('CANDIDATE',json.dumps(dict(zip(NAMES,x.tolist())),ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
