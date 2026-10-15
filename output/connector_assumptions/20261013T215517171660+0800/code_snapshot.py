"""Explicit connector scenarios; no platform writes or formal4 model claims."""
import copy
import csv
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2')]
import numpy as np
from scipy.optimize import differential_evolution
import t3v1 as model
from connector_free_production import project

VERSION=ROOT/'output/connector_model_update/20261013T200914882448+0800'
OLD=ROOT/'output/t3v1/20261013T193815695205+0800'
OUT=ROOT/'output/connector_assumptions'/datetime.now(model.nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
C=list(model.COUNTRIES)
TARGET='M05-05014677bb16a61e'


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def save(name,data):
    with (OUT/name).open('x',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)


def run():
    OUT.mkdir(parents=True,exist_ok=False)
    (OUT/'work_log.md').write_text('用户授权：在假设前提下输出连接件数据，文档标清。进行中；离线计算，不修改平台。不要输出真名，姓名统一用首字母替代。\n',encoding='utf-8')
    reg,p=read(VERSION/'models.json'),read(VERSION/'published_parameters.json')
    request=read(OLD/'example_request.json')
    dataset=read(OLD/'dataset.json')
    sources=[VERSION/'models.json',VERSION/'published_parameters.json',OLD/'example_request.json',OLD/'dataset.json',model.base.CURRENT/'tables.json',Path(__file__)]
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}
    # Existing example supplies only synthetic rival connector behavior, never this company's real capacity.
    rows=copy.deepcopy(request['competitors'])
    for r in rows:
        if r['product']=='复合梁':
            r['previous_rd']=r['rd']
        else:
            r['rd']=min(r['rd'],reg['observed_connector_rd']['x_range'][1])
    bounds=[(24.,40.5),(24.,40.5),(0.,2500.),(0.,4300.),(0.,1600.)]
    totals={'5':{'复合梁':{'泰国':55.37,'印尼':142.44},'连接件':{'泰国':250.,'印尼':150.}}}

    def demand(x,scale=1.,rival_price=1.,rival_marketing=1.,rd_mode='tied'):
        trial=copy.deepcopy(rows)
        for r in trial:
            if r['product']!='连接件': continue
            if r['team_id']==TARGET:
                r.update(price=float(x[C.index(r['country'])]),general=float(x[2]),designer=float(x[3]),rd=float(x[4]),previous_rd=0.)
            else:
                r.update(price=r['price']*rival_price,general=r['general']*rival_marketing,previous_rd=0.)
                r['designer']*=rival_marketing
        t=copy.deepcopy(totals)
        t['5']['连接件']={c:v*scale for c,v in totals['5']['连接件'].items()}
        predictions=model.predict_demand(trial,reg,t,rd_mode)
        return {c:next(r['demand_kunits'] for r in predictions if r['product']=='连接件' and r['country']==c and r['team_id']==TARGET) for c in C}

    def product(x,d,capacity,efficiency=16.7,material_scale=1.):
        return dict(capacity=float(capacity),efficiency=efficiency,material_cost=p['material_cost']*material_scale,
                    demand=d,prices=dict(zip(C,map(float,x[:2]))),transport_costs=p['transport_costs'])

    def plan(x,allocation,investment=0.,due=None):
        return dict(allocation_pct=float(allocation),opening_inventory_kunits=0.,holding_cost_per_unit=p['holding_cost_per_unit'],
                    country_priority=sorted(C,key=lambda c:-(x[C.index(c)]-p['transport_costs'][c])),
                    lifecycle=dict(opening_inventory_book_value_kusd=0.,orders_due=due or [],orders_awarded=[],
                    rd_kusd=float(x[4]),marketing_kusd=float(x[2]+x[3]),attributed_operations_kusd=0.,investment_kunits=float(investment),
                    investment_unit_cost=p['investment_unit_cost'],capacity_decay_pct=p['capacity_decay_pct'],environment_per_unit=p['environment_per_unit']))

    def choose(x,options=None):
        options=options or {}
        d=demand(x,**options)
        order=sorted(C,key=lambda c:-(x[C.index(c)]-p['transport_costs'][c]))
        candidates=[]
        for n in range(0,401,20):
            q=min(sum(d.values()),n)
            available=q; revenue=0.; freight=0.
            for c in order:
                sold=min(available,d[c]);available-=sold
                revenue+=sold*x[C.index(c)];freight+=sold*p['transport_costs'][c]
            bands=[min(q,n/3),min(max(q-n/3,0),n/3),max(q-2*n/3,0)]
            payroll=sum(a*b for a,b in zip(bands,p['shift_multipliers']))*p['wage_kusd']/16.7
            operating=revenue-freight-q*p['material_cost']-payroll-sum(x[2:])
            candidates.append((operating-n*p['investment_unit_cost'],n,q))
        score,n,q=max(candidates)
        out=project(product(x,d,n),plan(x,100*q/n if n else 0),p['wage_kusd'],p['shift_multipliers'])
        assert abs(score-(out['contribution_kusd']-n*p['investment_unit_cost']))<1e-8
        return dict(category='ASSUMED_FORMAL4_FROZEN_FORMAL3_CONDITIONS',parameters=list(map(float,x)),demand_kunits=d,
                    investment_formal3_kunits=n,investment_formal3_kusd=n*p['investment_unit_cost'],
                    incremental_operating_contribution_formal4_kusd=out['operating_contribution_kusd'],
                    one_year_contribution_less_prior_capex_kusd=float(score),projection=out)

    base=np.array([27.,27.,0.,0.,0.])
    baseline=choose(base)
    solvers=[]
    for seed in [31,53]:
        fit=differential_evolution(lambda x:-choose(x)['one_year_contribution_less_prior_capex_kusd'],bounds,seed=seed,popsize=10,maxiter=180,tol=1e-7,polish=True)
        solvers.append(dict(seed=seed,parameters=fit.x.tolist(),score=-float(fit.fun),converged=bool(fit.success)))
    best=max(solvers,key=lambda s:s['score'])
    x=np.array([round(v,2) for v in best['parameters']])
    best_plan=choose(x)
    fixed_price=[choose(np.array([v,v,0.,0.,0.])) for v in [24.,27.,30.]]
    stress=[]
    cases=[('行业需求减半',dict(scale=.5)),('行业需求翻倍',dict(scale=2.)),('250/150按每队解读：行业规模10倍',dict(scale=10.)),
           ('对手降价10%',dict(rival_price=.9)),('对手营销增加50%',dict(rival_marketing=1.5)),
           ('改用连接件独立研发图线',dict(rd_mode='observed_sensitivity'))]
    for label,options in cases:
        d=demand(x,**options)
        out=project(product(x,d,best_plan['investment_formal3_kunits']),plan(x,best_plan['projection']['capacity_allocation_pct']),p['wage_kusd'],p['shift_multipliers'])
        stress.append(dict(label=label,category='ASSUMED_FIXED_FREE_PRODUCTION_PLAN',assumptions=options,demand_kunits=d,
                          one_year_contribution_less_prior_capex_kusd=out['contribution_kusd']-best_plan['investment_formal3_kusd'],projection=out))
    for efficiency in [16.,18.]:
        out=project(product(x,best_plan['demand_kunits'],best_plan['investment_formal3_kunits'],efficiency=efficiency),plan(x,best_plan['projection']['capacity_allocation_pct']),p['wage_kusd'],p['shift_multipliers'])
        stress.append(dict(label=f'效率{efficiency}',category='ASSUMED_FIXED_FREE_PRODUCTION_PLAN',assumptions={'efficiency':efficiency},
                          one_year_contribution_less_prior_capex_kusd=out['contribution_kusd']-best_plan['investment_formal3_kusd'],projection=out))
    scale_sizing=[dict(scale=scale,**choose(x,dict(scale=scale))) for scale in [.5,1.,2.,10.]]
    capacity_comparison=[]
    for n in [20,40,80,120,200,400]:
        q=min(sum(best_plan['demand_kunits'].values()),n)
        out=project(product(x,best_plan['demand_kunits'],n),plan(x,q/n*100),p['wage_kusd'],p['shift_multipliers'])
        capacity_comparison.append(dict(capacity_kunits=n,capex_kusd=n*1.1,one_year_contribution_less_prior_capex_kusd=out['contribution_kusd']-n*1.1,projection=out))
    tender_price=26.; tender_quantity=350.
    due=[dict(status='CONFIRMED',quantity_kunits=tender_quantity,price=tender_price,advance_received_kusd=tender_quantity*tender_price*.1)]
    d=demand(base); q=min(400.,350.+sum(d.values()))
    tender_out=project(product(base,d,400.),plan(base,q/400*100,due=due),p['wage_kusd'],p['shift_multipliers'])
    tender=dict(category='HYPOTHETICAL_CONFIRMED_AWARD_NOT_FORECAST',assumptions='假设全部350千单位中标、合同26美元、正式4交付、正式3新增400千单位产能；运输/违约及竞争中标模型未识别',
                advance_cash_formal3_kusd=910.,capex_formal3_kusd=440.,one_year_contribution_less_prior_capex_kusd=tender_out['contribution_kusd']-440.,projection=tender_out)
    no_entry=project(product(base,dict.fromkeys(C,0.),0.),plan(base,0.),p['wage_kusd'],p['shift_multipliers'])
    assert no_entry['production_kunits']==no_entry['contribution_kusd']==0.
    assert abs(solvers[0]['score']-solvers[1]['score'])<.1
    assert math.isclose(sum(best_plan['projection']['sales_kunits'].values()),best_plan['projection']['production_kunits'],abs_tol=1e-8)
    half=stress[0]['projection']
    assert half['closing_inventory_kunits']>0 and math.isclose(half['production_kunits'],best_plan['projection']['production_kunits'])
    assert tender_out['orders_delivered_kunits']==350. and tender_out['order_balance_due_kusd']==8190.
    assumptions=[
        dict(id='A1',classification='市场规模口径假设',statement='250/150千单位暂解释为10队竞争市场的两国行业总需求，不是本队需求；规模0.5/2/10倍另算'),
        dict(id='A2',classification='竞争行为假设',statement='连接件对手售价按正式2复合梁价格/原参考价×27；营销沿用正式2复合梁投入，研发暂取该投入与1600的较小值（人为情景上限，非平台限额），连接件上期研发为0'),
        dict(id='A3',classification='产品迁移假设',statement='基准共用复合梁价格/营销/研发行为系数与正式3复合梁研发曲线；连接件独立图线仅作敏感性，真实训练标签0条'),
        dict(id='A4',classification='未来条件冻结假设',statement='先在正式3条件下预测连接件需求，再假设正式4需求、曲线和公布成本不变；没有调用或训练正式4需求模型'),
        dict(id='A5',classification='成本及人员假设',statement='正式4效率16.7、材料14.2、工资30、运费0.5/2，直接延用正式3；不额外归属共同运营/管理費，无硬性用工上限，招聘/解聘及学习影响未计'),
        dict(id='A6',classification='无订单假设',statement='基准无确认订单；350千单位招标不加入基准需求或收入；确认中标情景明确假设合同26美元而非预测报价'),
        dict(id='A7',classification='投资与生产情景',statement='正式3投资在正式4生效，机器选择0–400千单位、20千单位步长；连接件独立自由生产，基准按预估销量设置比例；敏感性保持计划产量，需求下跌结转库存'),
        dict(id='A8',classification='目标与边界',statement='比较正式4增量经营资源贡献减正式3机器购置支出，非会计净利润、NPV或完整现金流；未计正式5/6及机器残值、利息、税和零售收付时点'),
        dict(id='A9',classification='搜索边界假设',statement='两国售价各24–40.5美元，一般/设计师营销总额0–2500/4300千美元，研发0–1600；营销按总额入模，国别分配未识别')]
    result=dict(status='EXPLICIT_ASSUMPTION_SCENARIOS_NOT_ACTUAL_FORECAST',market=5,account='PYT',known_formal3=dict(capacity_kunits=0.,opening_inventory_kunits=0.,deliverable_kunits=0.,published_parameters=p),
                assumptions=assumptions,baseline=baseline,conditional_candidate=best_plan,solvers=solvers,fixed_price_comparison=fixed_price,
                sensitivity=stress,scale_sizing=scale_sizing,capacity_comparison=capacity_comparison,hypothetical_tender=tender,
                decision_formal3='基准保留连接件零生产；机器投资是待审阅条件候选，不自动填写平台；正式3营销/研发不据正式4假设自动改动',
                sources=hashes,checks=dict(two_seed_score_gap=abs(solvers[0]['score']-solvers[1]['score']),fixed_production_inventory=True,quantity_conservation=True,confirmed_order_balance=True,zero_capacity=True))
    save('result.json',result)
    (OUT/'code_snapshot.py').write_bytes(Path(__file__).read_bytes())
    flat=[]
    for label,r in [('27美元零投入基准',baseline),('条件搜索候选',best_plan)]+[(r['label'],r) for r in stress]:
        o=r['projection']; flat.append(dict(category=r['category'],scenario=label,production_kunits=o['production_kunits'],sales_thailand=o['sales_kunits']['泰国'],sales_indonesia=o['sales_kunits']['印尼'],inventory_kunits=o['closing_inventory_kunits'],workers=o['workers'],resource_contribution_kusd=o['contribution_kusd'],after_prior_capex_kusd=r['one_year_contribution_less_prior_capex_kusd']))
    with (OUT/'连接件情景数据.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    o=best_plan['projection']
    lines=['# 连接件假设预估与正式3决策补充','', '**全文数值均为假设情景计算，不是平台实际结果、平台预算或已验证的正式4预测。**',
           '', '市场5、PYT。已知条件截止于2026-10-13下午归档；未实时核验当前页面。不要输出真名，姓名统一用首字母替代。',
           '', '## 先区分本期事实与未来情景','',
           '正式3归档：连接件本期机器产能0、期初库存0，因此基准本期生产和交付均为0。新增机器下期生效沿用已建模型的投资情景。下面的需求是正式3条件迁移计算；产销和收益是假设正式4沿用这些条件后计算，不能写成正式3本期收入。',
           '', '## 假设清单','', '| 编号 | 性质 | 明确前提 |','|---|---|---|']
    lines += [f'| {a["id"]} | {a["classification"]} | {a["statement"]} |' for a in assumptions]
    lines += ['', '## 基准与条件候选','',
              f'在上述假设及搜索边界内，候选泰国/印尼售价 {x[0]:.2f}/{x[1]:.2f}美元；一般营销总额{x[2]:.2f}、设计师营销总额{x[3]:.2f}、研发{x[4]:.2f}千美元。国别营销比例未优化。',
              f'模型条件需求泰国{best_plan["demand_kunits"]["泰国"]:.3f}、印尼{best_plan["demand_kunits"]["印尼"]:.3f}千单位。正式3新增机器候选{best_plan["investment_formal3_kunits"]}千单位，购置{best_plan["investment_formal3_kusd"]:.2f}千美元；正式4自由生产比例{o["capacity_allocation_pct"]:.3f}%，产量{o["production_kunits"]:.3f}千单位，用工{o["workers"]:.3f}人。',
              f'正式4增量经营贡献{o["operating_contribution_kusd"]:.2f}千美元，扣正式3机器购置后跨两期比较值{best_plan["one_year_contribution_less_prior_capex_kusd"]:.2f}千美元。机器支出单列，不冒充正式4经营费用。',
              '这一结果仅适用于独立连接件增量比较；共同管理费已在复合梁主报告中列示，不重复扣给连接件。没有计算公司整体净利润或最低现金约束。',
              '', '| 情景 | 两国售价 | 两国条件需求，千单位 | 新增产能，千单位 | 购置，千美元 | 次期贡献减购置，千美元 |','|---|---|---|---:|---:|---:|']
    for r in fixed_price+[best_plan]:
        lines.append(f'| {"固定售价零投入" if r in fixed_price else "条件搜索候选"} | {r["parameters"][0]:.2f}/{r["parameters"][1]:.2f} | {r["demand_kunits"]["泰国"]:.3f}/{r["demand_kunits"]["印尼"]:.3f} | {r["investment_formal3_kunits"]} | {r["investment_formal3_kusd"]:.2f} | {r["one_year_contribution_less_prior_capex_kusd"]:.2f} |')
    lines += ['', '## 敏感性：保持候选自由生产计划，不把滞销产量自动删掉','', '| 假设情景 | 两国销量，千单位 | 期末库存，千单位 | 经营资源贡献减前期购置，千美元 |','|---|---:|---:|---:|']
    for r in stress:
        a=r['projection'];lines.append(f'| {r["label"]} | {a["sales_kunits"]["泰国"]:.3f}/{a["sales_kunits"]["印尼"]:.3f} | {a["closing_inventory_kunits"]:.3f} | {r["one_year_contribution_less_prior_capex_kusd"]:.2f} |')
    lines += ['', '库存按加权平均成本结转，持有费0.6美元/单位；表中资源贡献扣全部本期生产支出，不把未售库存当已实现收入。经营贡献与资源贡献差额等于新增库存账面成本，详见JSON。',
              '', '## 市场规模口径改变后，重新选择机器和生产比例','', '| 行业规模倍数 | 泰国需求 | 印尼需求 | 新增产能 | 生产比例 | 贡献减购置，千美元 |','|---|---:|---:|---:|---:|---:|']
    lines += [f'| {r["scale"]} | {r["demand_kunits"]["泰国"]:.3f} | {r["demand_kunits"]["印尼"]:.3f} | {r["investment_formal3_kunits"]} | {r["projection"]["capacity_allocation_pct"]:.2f}% | {r["one_year_contribution_less_prior_capex_kusd"]:.2f} |' for r in scale_sizing]
    lines += ['', '此表固定候选价格和投入，只重新选择机器及生产比例；不是每个规模下重新优化全部决策。10倍情景仅展示“每队需求”解读会造成的差异，没有确认该解读。',
              '', '## 招标单列：假设中标不等于预测中标','',
              f'仅假设350千单位全部中标、合同26美元、正式4交付且正式3购入400千单位产能：购置440千美元；正式3预收910千美元作为合同负债，不算收入；正式4订单收入9100千美元、余款8190千美元。连同零售，正式4产量{q:.3f}千单位，贡献减前期购置{tender["one_year_contribution_less_prior_capex_kusd"]:.2f}千美元。',
              '中标概率、对手报价、订单运输、履约处罚和终局价值未知，此情景不用于推荐投标报价或实际融资；订单运输成本缺失，不能视为完整订单利润。',
              '', '## 计算核验及使用边界','',
              f'两种随机种子搜索值差{result["checks"]["two_seed_score_gap"]:.8f}千美元；公共连接件V2计算回放、数量/库存成本守恒、零产能、固定计划滞销结存、确认订单余款及来源哈希检查通过。数值搜索不证明全局最优。',
              '正式3投资候选与正式4生产候选须分期开列。正式3连接件价格/营销/研发不因本报告而自动改动；未来费用只在未来情景中扣除一次。已有复合梁主报告保留原范围，本补充不宣布完整双产品或六回合最优。',
              '完整输入、优化参数、21档机器比较、环境影响与库存/订单明细见result.json；主情景另存CSV。未改模型、未重训、未修改平台；正式4已知条件发布后应重新计算。']
    (OUT/'连接件假设预估.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert all(hashlib.sha256(f.read_bytes()).hexdigest()==hashes[str(f.relative_to(ROOT))] for f in sources)
    with (OUT/'work_log.md').open('a',encoding='utf-8') as f:
        f.write('完成：基准、条件候选、固定生产敏感性、规模口径、确认订单假设均已交付；检查通过。原件及注册表哈希不变；未改平台，未验证实际或完整跨期最优。\n')
    print(json.dumps(dict(output=str(OUT),baseline=baseline['one_year_contribution_less_prior_capex_kusd'],parameters=x.tolist(),demand=best_plan['demand_kunits'],capacity=best_plan['investment_formal3_kunits'],capex=best_plan['investment_formal3_kusd'],allocation=o['capacity_allocation_pct'],score=best_plan['one_year_contribution_less_prior_capex_kusd'],half_scale=stress[0]['one_year_contribution_less_prior_capex_kusd']),ensure_ascii=False))


if __name__=='__main__':
    run()
