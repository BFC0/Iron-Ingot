"""Joint formal5 conditional optimizer; preserves frozen models and never writes Cesim."""
import copy
import csv
import hashlib
import json
import math
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'code')]
import numpy as np
from scipy.optimize import differential_evolution
import t5v0b as model

OUT=ROOT/(ROOT/'work/formal5_full_active.txt').read_text(encoding='utf-8-sig').strip()
INITIAL=ROOT/'output/round_close/20261014_formal4_close/formal5_initial'
BUNDLE=ROOT/'output/t5v0b/20261015T153107587428+0800'
OLD=ROOT/'output/t4v1_deduplicated/20261014T162452595723+0800'
P=['复合梁','连接件'];C=['泰国','印尼']
ROWS=[9,10,13,14,18,19,21,22,25,26,29,30,51,52,49,46,47,42,43,54]
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
number=lambda v:float(str(v).replace('\xa0','').replace(' ',''))


def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def chart_records(script):
    records=[]
    for match in re.finditer(r'Chart\.create\("([^"]+)",\s*"([^"]+)",\s*',script):
        if match[1] in ['quality.control.chart','cost.efficiency.chart']:
            data,_=json.JSONDecoder().raw_decode(script[match.end():])
            records.append(dict(id=match[1],type=match[2],data=data))
    return records


def curve(x,item):
    p=item['parameters']
    return p[0]+p[1]*(x+p[2])**p[3] if item['form']=='power' else p[0]+p[1]*x/(p[2]+x)


class ScenarioModel:
    def __init__(self):
        self.r=read(BUNDLE/'models_full.json');self.old=read(OLD/'models_full.json')
        self.fields=[x for x in read(INITIAL/'current_42_drafts_all_columns.json') if x['column_identity']=='PYT']
        live=read(OUT/'latest/checklist.json')['tables'][1]
        self.current={x['row']:number(live[x['row']][5]) if x['value'] not in ['第一','第二','FALSE','TRUE'] else live[x['row']][5] for x in self.fields}
        assert len(self.current)==42 and all(self.current[x['row']]==x['value'] for x in self.fields)
        records=chart_records(read(OUT/'latest/planning_curves.json')['chart_scripts'][0])
        archived=read(INITIAL/'curves_original_chart_literals.json')
        for a in records:
            b=next(x for x in archived if x['id']==a['id'])
            assert a['data']['categories']==b['data']['categories']
            assert a['data']['dataset']==b['data']['dataset']
        save('latest/curves_original_verified.json',records)
        self.curves=self.r['application_curves']['curves']
        self.rdcurves=[self.curves['rd/'+p] for p in P];self.opcurve=self.curves['operations/泰国']
        self.beta={name:np.array([[[self.old['demand'][p][name if name=='SHARE' else 'COUNTRY/'+c]['beta'][i]
            for i in range(5)] for c in C] for p in P]) for name in ['SHARE','COUNTRY']}
        self.tail={name:np.array([[self.old['demand'][p][name if name=='SHARE' else 'COUNTRY/'+c]['beta'][5+k]
            if self.old['demand'][p][name if name=='SHARE' else 'COUNTRY/'+c]['piecewise'] else 0.
            for k,c in enumerate(C)] for p in P]) for name in ['SHARE','COUNTRY']}
        dataset=read(ROOT/'output/t5v0/20261015T085218049188+0800/dataset.json')
        own=dataset['own_final_decision_rows'];tid=own[0]['team_id']
        self.state=next(x['closing']['values'] for x in dataset['state_pairs'] if x['market_id']==5 and x['team_id']==tid)
        self.baseprices=np.array([[self.current[9],self.current[10]],[self.current[13],self.current[14]]])
        self.gb=np.array([[self.current[18],self.current[19]],[self.current[21],self.current[22]]])
        self.db=np.array([[self.current[25],self.current[26]],[self.current[29],self.current[30]]])
        self.rdbase=np.array([900.,1300.]);self.opsbase=750.
        self.effbase=np.array([self.r['efficiency'][p]['production']['value']/self.r['efficiency'][p]['workers']['value'] for p in P])
        self.prevworkers=sum(self.r['efficiency'][p]['workers']['value'] for p in P)
        self.totals=np.array([[self.r['formal4_market_totals_kunits'][p][c] for c in C] for p in P])
        self.share=np.array([[self.r['formal4_own_demand_kunits'][p][c] for c in C] for p in P])/self.totals
        self.capbase=np.array([41.67,412.25]);self.invbase=np.array([0.,202.40]);self.invbook=np.array([0.,3516.])
        self.freight=np.array([[30.,120.],[.5,2.]])
        self.costs={name:np.array([model.prior.material_scenarios(self.r,p,1)[name]['unit_cost_usd'] for p in P]) for name in ['published','additive','proportional']}
        self.pars={k:v['value'] for k,v in self.r['application_parameters'].items()}
        support=[];self.price_sources=[]
        for j in range(2):
            for k in range(2):
                vals=[]
                for m in range(1,11):
                    path=ROOT/f'output/round_close/20261014_formal4_close/raw/market{m}_formal4_marketdetails.json'
                    table=read(path)['tables'][0];row=table[[[3,4],[6,7]][j][k]]
                    vals += [number(v) for v in row[1:] if str(v).strip() and number(v)>0]
                    self.price_sources.append(path)
                support.append([min(vals),max(vals)])
        self.bounds=support+[[0,2700]]*4+[[0,3840]]*4+[[0,2600],[0,2600],[0,1620],[0,20],[0,20],[0,100],[0,100],[-102,100]]
        self.baseline=np.array([self.current[i] if i not in [47,54] else self.current[i]/(20 if i==47 else 100) for i in ROWS],float)
        self.other_assets=self.state['assets']-(self.state['cash']+self.state['ar']+self.state['machine_book']+self.state['building_book']+self.invbook.sum())
        save('input_manifest.json',dict(current=self.current,curves_600_exact_match=True,
            price_bounds=support,bounds=self.bounds,rows=ROWS,opening_state_inferred=self.state,
            inventory_quantity=self.invbase.tolist(),inventory_book=self.invbook.tolist(),
            display_rounding_other_assets=self.other_assets,workers=self.prevworkers,efficiency_anchor=self.effbase.tolist(),
            demand_coefficients={k:v.tolist() for k,v in self.beta.items()},tail_coefficients={k:v.tolist() for k,v in self.tail.items()},
            latest_capture='2026-10-15 16:13—16:25 +08:00',material_scenarios={k:v.tolist() for k,v in self.costs.items()}))

    def demand(self,x,cfg,t):
        n=x.shape[1];price=x[:4].reshape(2,2,n);g=x[4:8].reshape(2,2,n);d=x[8:12].reshape(2,2,n)
        b=self.beta[cfg['response']];tail=self.tail[cfg['response']]
        logp=-b[:,:,0,None]*np.log(price/self.baseprices[:,:,None])*cfg.get('price_elasticity',1.)
        # The historical piecewise threshold used initial beam prices 1800/2000; connector models have no tail.
        thresholds=np.array([[2700.,3000.],[1.5,1.5]])
        logp-=tail[:,:,None]*(np.maximum(np.log(price/thresholds[:,:,None]),0)-np.maximum(np.log(self.baseprices/thresholds),0)[:,:,None])
        gm=np.log((1000+g)/(1000+self.gb[:,:,None]));dm=np.log((1000+d)/(1000+self.db[:,:,None]))
        if cfg.get('marketing_proxy')=='total':
            gm=np.broadcast_to(np.log((1000+g.sum(axis=(0,1)))/(1000+self.gb.sum()))[None,None,:],(2,2,n))
            dm=np.broadcast_to(np.log((1000+d.sum(axis=(0,1)))/(1000+self.db.sum()))[None,None,:],(2,2,n))
        rdlog=np.array([np.log(curve(x[12+j],self.rdcurves[j])/curve(self.rdbase[j],self.rdcurves[j])) for j in range(2)])
        delta=logp+cfg.get('marketing_scale',1.)*(b[:,:,2,None]*gm+b[:,:,3,None]*dm)+b[:,:,4,None]*rdlog[:,None,:]
        delta=np.clip(delta,-30,30)
        odds=self.share[:,:,None]*np.exp(delta)
        s=odds/(odds+(1-self.share[:,:,None])*cfg.get('rival_attractiveness',1.))
        growth=np.array([1.07,.95])*cfg.get('market_scale',1.)
        total=self.totals*growth[None,:]
        if t:total=total*np.array(cfg['future_growth'])[:,None]
        demand=s*total[:,:,None]
        return demand

    def evaluate(self,decision,cfg,details=False,budget=False,overrides=None):
        x=np.asarray(decision,float);x=x[:,None] if x.ndim==1 else x
        n=x.shape[1];overrides=overrides or {};prices=x[:4].reshape(2,2,n)
        inv=np.broadcast_to(self.invbase[:,None],(2,n)).copy();book=np.broadcast_to(self.invbook[:,None],(2,n)).copy()
        cap=np.broadcast_to(self.capbase[:,None],(2,n)).copy();invest=np.array([np.rint(x[15]),20*np.rint(x[16])])
        cap+=invest
        cash=np.full(n,self.state['cash']);ar=np.full(n,self.state['ar']);ap=np.full(n,self.state['ap'])
        machine=np.full(n,self.state['machine_book']);building=np.full(n,self.state['building_book'])
        equity=np.full(n,self.state['equity']);assets=np.full(n,self.state['assets']);debt=np.full(n,self.state['long_debt'])
        loss=np.full(n,cfg.get('tax_loss',0.));workers=np.full(n,self.prevworkers)
        total=np.zeros(n);minimum=np.full(n,np.inf);balance_max=np.zeros(n);quantity_error=np.zeros(n);periods=[]
        valid=np.ones(n,bool)
        for t in range(2):
            demand=self.demand(x,cfg,t)
            if budget and t==0:
                demand=np.broadcast_to(np.array([[self.current[58],self.current[59]],[self.current[61],self.current[62]]])[:,:,None],(2,2,n)).copy()
            for j,rows in enumerate([[58,59],[61,62]]):
                for k,row in enumerate(rows):
                    if t==0 and row in overrides:demand[j,k]=overrides[row]
            for j,rows in enumerate([[65,66],[68,69]]):
                for k,row in enumerate(rows):
                    if row in overrides:demand[j,k]*=(1+overrides[row]/100)/[1.07,.95][k]
            if t:
                for j,row in enumerate([72,73]):
                    if row in overrides:demand[j]*=(1+overrides[row]/100)/cfg['future_growth'][j]
            ef=self.effbase[:,None]*curve(x[14],self.opcurve)/curve(self.opsbase,self.opcurve)*cfg.get('efficiency_scale',1.)
            if budget:ef=np.broadcast_to(np.array([self.current[76],self.current[77]])[:,None],(2,n)).copy()
            for j,row in enumerate([76,77]):
                if row in overrides:ef[j]=overrides[row]
            q=cap*x[17:19]/100
            if t and cfg.get('recourse',True):q=np.minimum(cap,np.maximum(demand.sum(axis=1)-inv,0))
            else:q[0]=np.minimum(q[0],np.maximum(demand[0].sum(axis=0)-inv[0],0))
            available=inv+q;sales=np.zeros((2,2,n));net=prices-self.freight[:,:,None]
            priorities=[]
            for j in range(2):
                domestic=net[j,0]>=net[j,1]
                key=34 if j==0 else 37
                if key in overrides:domestic=np.full(n,overrides[key]=='第一')
                key2=35 if j==0 else 38
                if key2 in overrides:domestic=np.full(n,overrides[key2]!='第一')
                first=np.minimum(np.where(domestic,demand[j,0],demand[j,1]),available[j])
                second=np.minimum(np.where(domestic,demand[j,1],demand[j,0]),available[j]-first)
                sales[j,0]=np.where(domestic,first,second);sales[j,1]=np.where(domestic,second,first)
                priorities.append(np.where(domestic,0,1))
            ending=np.maximum(available-sales.sum(axis=1),0)
            wage=43.5*(cfg.get('future_wage',1.) if t else 1.)
            bands=[np.minimum(q,cap/3),np.minimum(np.maximum(q-cap/3,0),cap/3),np.maximum(q-2*cap/3,0)]
            payroll=(bands[0]+1.65*bands[1]+2.56*bands[2])/ef*wage
            newworkers=(q/ef).sum(axis=0)
            firing=np.maximum(workers*.9-newworkers,0)*wage*.35
            if cfg.get('firing_scope')=='product':
                prev=np.array([92.84,25.10])[:,None] if t==0 else prev_product_workers
                firing=(np.maximum(prev*.9-q/ef,0)*wage*.35).sum(axis=0)
            material=self.costs[cfg.get('material','proportional')]*cfg.get('material_scale',1.)
            material_cost=q*material[:,None];production_cost=material_cost+payroll
            current_unit=np.divide(production_cost,q,out=np.divide(book,np.maximum(inv,1e-30)),where=q>1e-12)
            if cfg.get('valuation')=='weighted':current_unit=np.divide(book+production_cost,available,out=np.zeros_like(book),where=available>0)
            endingbook=ending*current_unit
            cogs=(book+production_cost-endingbook).sum(axis=0)
            revenue=(sales*prices).sum(axis=(0,1));transport=(sales*self.freight[:,:,None]).sum(axis=(0,1))
            spending=x[4:15].sum(axis=0)
            ebitda=revenue-cogs-transport-.6*ending.sum(axis=0)-spending-firing-10050
            capex=(invest*np.array([78.,1.1])[:,None]).sum(axis=0) if t==0 else np.zeros(n)
            building_capex=cfg.get('building_capex',800.)
            md=(machine+capex)*.15;bd=building*.07;ebit=ebitda-md-bd
            change=100*np.rint(x[19]) if t==0 else np.zeros(n);newdebt=debt+change
            ratio=equity/np.maximum(assets+change,1.)
            risk=self.r['risk']['solvency_exponential']['parameters']
            rate=.05+risk[0]*np.exp(-risk[1]*np.clip(ratio,0,1))
            if budget:rate=np.full(n,self.current[79]/100)
            if 79 in overrides:rate=np.full(n,overrides[79]/100)
            timing=cfg.get('interest_timing',.5)
            interest=((1-timing)*debt+timing*newdebt)*rate
            newar=revenue*cfg.get('ar_days',30.)/365
            newap=material_cost.sum(axis=0)*30/365
            # Inventory cash adjustment removes the accounting stock movement already included in EBITDA.
            k=cash+ebitda-interest+ar-newar+newap-ap+book.sum(axis=0)-endingbook.sum(axis=0)-capex-building_capex+change
            no_tax_cash=(k+.005*cash)/.995
            taxable=ebit-interest+.005*(cash+no_tax_cash)-loss>0
            newcash=np.where(taxable,(k+.005*cash*.71-.29*(ebit-interest-loss))/(1-.005*.71),no_tax_cash)
            cash_interest=.005*(cash+newcash)
            pretax=ebit-interest+cash_interest;tax=np.maximum(pretax-loss,0)*.29;profit=pretax-tax
            newequity=equity+profit
            newmachine=machine+capex-md;newbuilding=building+building_capex-bd
            newassets=newmachine+newbuilding+newar+newcash+endingbook.sum(axis=0)+self.other_assets
            error=newassets-newequity-newdebt-newap
            balance_max=np.maximum(balance_max,np.abs(error));quantity_error=np.maximum(quantity_error,np.abs(inv+q-sales.sum(axis=1)-ending).max(axis=0))
            min_this=np.minimum(newcash,cash+change-capex-building_capex)
            minimum=np.minimum(minimum,min_this)
            valid &= (newdebt>=0)&(newequity>0)&(ratio>.25)&(ratio<.97)&np.isfinite(profit)
            total+=profit
            if details:
                periods.append(dict(round=5+t,profit=float(profit[0]),cash=float(newcash[0]),minimum_sampled_cash=float(min_this[0]),
                    revenue=float(revenue[0]),ebitda=float(ebitda[0]),ebit=float(ebit[0]),tax=float(tax[0]),
                    rate=float(rate[0]),long_interest=float(interest[0]),cash_interest=float(cash_interest[0]),
                    long_debt=float(newdebt[0]),assets=float(newassets[0]),equity=float(newequity[0]),
                    demand=demand[:,:,0].tolist(),sales=sales[:,:,0].tolist(),production=q[:,0].tolist(),
                    opening_inventory=inv[:,0].tolist(),closing_inventory=ending[:,0].tolist(),inventory_book=endingbook[:,0].tolist(),
                    capacity=cap[:,0].tolist(),efficiency=ef[:,0].tolist(),workers=float(newworkers[0]),
                    materials=material_cost[:,0].tolist(),payroll=payroll[:,0].tolist(),firing=float(firing[0]),
                    transport=float(transport[0]),holding=float(.6*ending[:,0].sum()),spending=float(spending[0]),
                    machine_capex=float(capex[0]),depreciation=float(md[0]+bd[0]),priority=[int(v[0]) for v in priorities],balance_error=float(error[0])))
            cash,ar,ap,machine,building,debt,equity,assets=newcash,newar,newap,newmachine,newbuilding,newdebt,newequity,newassets
            loss=np.maximum(loss-np.maximum(pretax,0),0)+np.maximum(-pretax,0)
            inv,book,workers=ending,endingbook,newworkers;prev_product_workers=q/ef;cap*=.85
        penalty=np.maximum(3000-minimum,0)*100+np.where(valid,0.,1e8)
        penalty+=np.maximum(x[4:8].sum(axis=0)-2700,0)*100+np.maximum(x[8:12].sum(axis=0)-3840,0)*100
        if details:return dict(profit_5_to_6=float(total[0]),sampled_minimum_cash=float(minimum[0]),feasible=bool(penalty[0]<1e-6),
            penalty=float(penalty[0]),balance_error_max=float(balance_max[0]),quantity_error_max=float(quantity_error[0]),periods=periods)
        return total,minimum,penalty


def configs():
    common=dict(response='SHARE',future_growth=[1.,1.],material='proportional',recourse=True)
    return [dict(common,name='中性SHARE'),dict(common,name='国别COUNTRY',response='COUNTRY'),
        dict(common,name='联合不利',market_scale=.9,rival_attractiveness=1.25,efficiency_scale=.9,material_scale=1.1,
            future_growth=[.9,.95],future_wage=1.1,ar_days=60.,interest_timing=0.),
        dict(common,name='价格弹性增强20%',price_elasticity=1.2),dict(common,name='价格弹性减弱20%',price_elasticity=.8),
        dict(common,name='营销系数减半',marketing_scale=.5),dict(common,name='营销合计代理',marketing_proxy='total'),
        dict(common,name='期末长贷计息',interest_timing=1.),dict(common,name='按产品解聘',firing_scope='product'),
        dict(common,name='加权平均库存计价',valuation='weighted'),dict(common,name='材料固定加价',material='additive'),
        dict(common,name='材料公布价',material='published'),dict(common,name='未来固定生产配比',recourse=False),
        dict(common,name='正式6市场增长5%',future_growth=[1.05,1.05]),dict(common,name='正式6市场萎缩10%',future_growth=[.9,.9])]


def search(m,cfgs):
    integrality=[False]*15+[True,True,False,False,True]
    traces=[];winners=[]
    for objective in ['中性','稳健']:
        active=cfgs[:1] if objective=='中性' else cfgs[:3]
        def fn(x):
            ev=[m.evaluate(x,c) for c in active]
            profits=np.min([v[0] for v in ev],axis=0)
            penalty=np.max([m.evaluate(x,c)[2] for c in cfgs[:3]],axis=0)
            return -profits+penalty
        best=None
        for seed in [11,29]:
            z=differential_evolution(fn,m.bounds,popsize=10,maxiter=700,tol=.0003,atol=.5,polish=False,
                seed=seed,vectorized=True,updating='deferred',integrality=integrality,x0=m.baseline)
            traces.append(dict(objective=objective,seed=seed,success=bool(z.success),iterations=z.nit,score=-float(z.fun),x=z.x.tolist()))
            print('search',objective,seed,z.success,-z.fun,z.nit,flush=True)
            if best is None or z.fun<best.fun:best=z
        x=best.x.copy();x[:2]=np.round(x[:2]);x[2:4]=np.round(x[2:4],1);x[4:15]=np.round(x[4:15]);x[17:19]=np.round(x[17:19],1)
        x[15:17]=np.rint(x[15:17]);x[19]=np.rint(x[19])
        # Coordinate polish uses platform display steps and checks every legal machine and loan step.
        for _ in range(5):
            changed=False
            for j in range(20):
                vals=[x[j]]
                step=1. if j<2 or 4<=j<=16 else .1 if j in [2,3,17,18] else 1.
                vals += [x[j]-step,x[j]+step]
                if j in [15,16]:vals=list(range(21))
                if j==19:vals=list(range(-102,101))
                vals=[v for v in vals if m.bounds[j][0]<=v<=m.bounds[j][1]]
                trials=np.repeat(x[:,None],len(vals),axis=1);trials[j]=vals
                scores=fn(trials);ix=int(np.argmin(scores))
                if scores[ix]<float(fn(x)[0])-1e-7:x[j]=vals[ix];changed=True
            if not changed:break
        tie=x.copy();tie[17]=m.baseline[17]
        if abs(float(fn(tie)[0])-float(fn(x)[0]))<1e-7:x=tie
        winners.append(x)
    save('searches.json',traces)
    return winners


def main():
    assert (OUT/'work_log.md').exists() and not (OUT/'full_result.json').exists()
    m=ScenarioModel();cfgs=configs()
    budget=m.evaluate(m.baseline,cfgs[0],details=True,budget=True)
    observed=read(OUT/'latest/budget_income.json')['tables'][0]
    shown_profit=number(next(row[1] for row in observed if row and row[0]=='本回合利润'))
    budget_error=budget['periods'][0]['profit']-shown_profit
    save('budget_replay.json',dict(model=budget,display_profit=shown_profit,error_kusd=budget_error,
        scope='整套最新草稿预算复算，非独立留出或实际成绩；未用误差重新拟合任何参数'))
    print('budget replay',budget_error,flush=True)
    assert abs(budget_error)<10, 'Budget discrepancy must be explained before optimization'
    base=m.evaluate(m.baseline,cfgs[0],details=True)
    assert np.allclose(base['periods'][0]['demand'],m.share*m.totals*np.array([1.07,.95])[None,:])
    assert base['balance_error_max']<1e-6 and base['quantity_error_max']<1e-8
    batch=m.evaluate(np.column_stack([m.baseline,m.baseline]),cfgs[0])[0]
    assert np.allclose(batch,base['profit_5_to_6'])
    assert np.all(m.demand(m.baseline[:,None],cfgs[0],0)>0)
    trials=m.baseline.copy();trials[15]+=1
    assert abs(m.evaluate(trials,cfgs[0],True)['periods'][0]['capacity'][0]-base['periods'][0]['capacity'][0]-1)<1e-8
    winners=search(m,cfgs)
    comparisons=[]
    for name,x in [('最新基准',m.baseline),('中性利润候选',winners[0]),('稳健利润候选',winners[1])]:
        evaluations=[dict(name=c['name'],**m.evaluate(x,c,details=True)) for c in cfgs]
        comparisons.append(dict(name=name,x=x.tolist(),evaluations=evaluations))
        assert all(e['balance_error_max']<1e-6 and e['quantity_error_max']<1e-8 for e in evaluations)
    save('full_result.json',dict(status='CONDITIONAL_JOINT_OPTIMIZATION_WITH_FORWARD_RESPONSE',
        training_performed=False,application_version='t5v0b+explicit_assumptions',response_training_round=3,
        start_round=5,end_round=6,comparisons=comparisons,configs=cfgs))
    sensitivity(m,comparisons,cfgs)
    sources=[BUNDLE/'models_full.json',OLD/'models_full.json',INITIAL/'current_42_drafts_all_columns.json',
        INITIAL/'curves_original_chart_literals.json',Path(__file__)]+list((OUT/'latest').glob('*.json'))+list(set(m.price_sources))
    save('source_hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in sources})
    shutil.copy2(Path(__file__),OUT/Path(__file__).name)
    print('COMPLETE',str(OUT),flush=True)


def sensitivity(m,plans,cfgs):
    rows=[]
    for plan in plans[1:]:
        x=np.array(plan['x']);base=m.evaluate(x,cfgs[0],True)
        for f in m.fields:
            row=f['row'];overrides={};variants=[]
            if row in ROWS:
                j=ROWS.index(row);v=x[j]
                step=max(abs(v)*.1,1. if row in [9,10] else .1 if row in [13,14] else 100. if row==54 else 1. if row==46 else 1. if row==47 else 5. if row in [42,43] else 50.)
                if row in [46,47,54]:step=max(1.,round(step if row!=54 else step/100))
                if row==54:step=max(10.,round(abs(v)*.1))
                for sign in [-1,1]:
                    z=x.copy();value=float(np.clip(v+sign*step,*m.bounds[j]));z[j]=value
                    display=value*(20 if row==47 else 100 if row==54 else 1)
                    variants.append((display,z,{},'可控决策'))
            elif row in [34,35,37,38]:
                j=0 if row in [34,35] else 1;k=0 if row in [34,37] else 1
                priority=base['periods'][0]['priority'][j]
                v='第一' if priority==k else '第二';new='第二' if v=='第一' else '第一'
                variants=[(new,x,{row:new},'物流切换（两国排序联动）')]
            elif row in [11,15,27,31,41]:
                rows.append(dict(plan=plan['name'],key=f['key'],row=row,category='非可用控制',current=m.current[row],test='无招标／无可用分包控件',
                    delta_profit_5_to_6=None,delta_cash=None,status='N/A；不虚构开放投标或免费分包'))
                continue
            else:
                if row in [58,59,61,62]:
                    j=0 if row in [58,59] else 1;k=0 if row in [58,61] else 1
                    v=base['periods'][0]['demand'][j][k];step=v*.1
                elif row in [65,66,68,69]:v=7. if row in [65,68] else -5.;step=5.
                elif row in [72,73]:v=0.;step=5.
                elif row in [76,77]:v=base['periods'][0]['efficiency'][0 if row==76 else 1];step=v*.1
                elif row==79:v=base['periods'][0]['rate']*100;step=1.
                else:raise AssertionError(row)
                variants=[(v-step,x,{row:v-step},'预估/外生压力；不当作真实控制'),(v+step,x,{row:v+step},'预估/外生压力；不当作真实控制')]
            for display,z,override,category in variants:
                e=m.evaluate(z,cfgs[0],True,overrides=override)
                rows.append(dict(plan=plan['name'],key=f['key'],row=row,category=category,test=display,
                    delta_profit_5_to_6=e['profit_5_to_6']-base['profit_5_to_6'],
                    delta_cash=e['sampled_minimum_cash']-base['sampled_minimum_cash'],feasible=e['feasible'],
                    profit=e['profit_5_to_6'],status='单项变化，其余决策固定；不是重优化结果'))
        # Full legal discrete investment and finance sweeps test boundary/rounding failures.
        frontier=[]
        for j in [15,16,19]:
            for v in range(int(m.bounds[j][0]),int(m.bounds[j][1])+1):
                z=x.copy();z[j]=v;e=m.evaluate(z,cfgs[0],True)
                frontier.append(dict(row=ROWS[j],value=v*(20 if j==16 else 100 if j==19 else 1),
                    profit=e['profit_5_to_6'],sampled_minimum_cash=e['sampled_minimum_cash'],feasible=e['feasible']))
        save(('neutral' if plan==plans[1] else 'robust')+'_discrete_frontier.json',frontier)
    assert all({r['key'] for r in rows if r['plan']==p['name']}=={f['key'] for f in m.fields} for p in plans[1:])
    save('sensitivity_all_fields.json',rows)
    with (OUT/'sensitivity_all_fields.csv').open('w',encoding='utf-8-sig',newline='') as f:
        columns=list(dict.fromkeys(k for row in rows for k in row));w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)


if __name__=='__main__':main()
