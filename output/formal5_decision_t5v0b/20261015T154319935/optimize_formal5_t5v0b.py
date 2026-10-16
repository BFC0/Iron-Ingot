"""Auditable partial formal5 search using frozen t5v0b; no platform writes."""
import csv
import hashlib
import itertools
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
import numpy as np
import t5v0b as model
from verify_t5v0b import verify

OUT = ROOT/(ROOT/'work/formal5_decision_active.txt').read_text(encoding='utf-8-sig').strip()
BUNDLE = ROOT/'output/t5v0b/20261015T153107587428+0800'
INITIAL = ROOT/'output/round_close/20261014_formal4_close/formal5_initial'
P, C = list(model.PRODUCTS), list(model.COUNTRIES)
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
save = lambda p,v: p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
fmt = lambda v: f'{v:,.2f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)


def main():
    assert (OUT/'work_log.md').is_file() and not (OUT/'result.json').exists()
    r = read(BUNDLE/'models_full.json')
    fields = [x for x in read(INITIAL/'current_42_drafts_all_columns.json') if x['column_identity']=='PYT']
    group = read(INITIAL/'current_group_42_draft.json')
    assert len(fields)==42 and len({x['key'] for x in fields})==42
    current = {x['row']:x['value'] for x in fields}
    assert all(x['value']==current[x['row']] for x in group)
    pars = {k:v['value'] for k,v in r['application_parameters'].items()}
    dataset_path = ROOT/'output/t5v0/20261015T085218049188+0800/dataset.json'
    dataset = read(dataset_path)
    team = dataset['own_final_decision_rows'][0]['team_id']
    closing = next(x for x in dataset['state_pairs'] if x['market_id']==5 and x['team_id']==team)['closing']
    state = {k:closing['values'][k] for k in ('equity','assets','long_debt','short_debt')}
    header = dict(version='t5v0b',market_id=5,phase='formal',round=5)
    with model.app.no_training():
        acceptance = verify(BUNDLE)
        held_result = model.apply_request(r,dict(header,demand_basis='FORMAL4_OWN_SHARE_HELD',financial_state=state,
            investments_kunits=dict.fromkeys(P,0)))
    save(OUT/'model_acceptance.json',acceptance)
    held = held_result['demand']['demand_kunits']
    caps = [41.67,412.25]
    efficiency = [current[76],current[77]]
    workers = [r['efficiency'][p]['workers']['value'] for p in P]
    inventories = [r['opening_inventory_kunits'][p] for p in P]
    prices = [[current[i] for i in rows] for rows in ([9,10],[13,14])]
    transport = [[30.,90.],[.5,2.]]
    # shortcut: unknown responses keep price/spending/finance unresolved; add them only after their forward mechanisms are identified.
    for row in dataset['own_final_decision_rows']:
        j,k=P.index(row['product']),C.index(row['country'])
        assert row['price']==prices[j][k]
    costs = [{f:v['unit_cost_usd'] for f,v in model.prior.material_scenarios(r,p,0).items()} for p in P]
    base_demand = [[held[p][c] for c in C] for p in P]
    draft_demand = [[current[i] for i in rows] for rows in ([58,59],[61,62])]
    scenarios=[]
    for name,dem in [('份额保持×0.8',[[v*.8 for v in row] for row in base_demand]),
                     ('份额保持',base_demand),('份额保持×1.25',[[v*1.25 for v in row] for row in base_demand]),
                     ('原草稿高需求',draft_demand)]:
        for material_form,eff_scale in itertools.product(costs[0],[.9,1.,1.1]):
            scenarios.append(dict(name=name,demands=dem,material_form=material_form,efficiency_scale=eff_scale))

    def evaluate(j,allocation,priority,s):
        demand=s['demands'][j]
        q=caps[j]*allocation/100
        if j==0:
            q=min(q,sum(demand))
        eff=efficiency[j]*s['efficiency_scale']
        labor=model.app.labor_cost(r,dict(capacity_kunits=caps[j],production_kunits=q,previous_workers=workers[j]),eff)
        available=inventories[j]+q
        sales=[0.,0.]
        for k in priority:
            sales[k]=min(demand[k],available)
            available-=sales[k]
        revenue=sum(sales[k]*prices[j][k] for k in range(2))
        freight=sum(sales[k]*transport[j][k] for k in range(2))
        materials=q*costs[j][s['material_form']]
        holding=available*pars['holding']
        contribution=revenue-freight-materials-labor['payroll']-labor['firing']-holding
        assert math.isclose(inventories[j]+q,sum(sales)+available,abs_tol=1e-8)
        assert all(0<=sales[k]<=demand[k]+1e-8 for k in range(2))
        return dict(production=q,sales=sales,demand=demand,inventory=available,
            unmet=sum(demand)-sum(sales),workers=labor['workers'],revenue=revenue,
            freight=freight,materials=materials,payroll=labor['payroll'],severance=labor['firing'],
            holding=holding,contribution=contribution,
            production_spending=materials+labor['payroll']+labor['firing'])

    grid=[i/10 for i in range(1001)]
    arrays=[]; ideal=[]; priorities=[]; searches=[]
    for j in range(2):
        rows=[]; choices=[]
        for order in ([0,1],[1,0]):
            rows += [[evaluate(j,a,order,s)['contribution'] for s in scenarios] for a in grid]
            choices += [(a,list(order)) for a in grid]
        arr=np.array(rows); best=arr.max(axis=0)
        arrays.append(arr);ideal.append(best);priorities.append(choices)
        worst=(best-arr).max(axis=1)
        idxs=np.flatnonzero(worst<=worst.min()+1e-8)
        idx=min(idxs,key=lambda i:abs(choices[i][0]-current[42+j]))
        searches.append(dict(product=P[j],minimax_regret_choice=choices[int(idx)],worst_regret=float(worst[idx]),
            allocations_tested=len(grid),priorities_tested=2,scenarios=len(scenarios)))
    nominal_idx=next(i for i,s in enumerate(scenarios) if s['name']=='份额保持' and s['material_form']=='published' and s['efficiency_scale']==1)
    low=[]
    for j in range(2):
        arr=arrays[j][:,nominal_idx]
        idxs=np.flatnonzero(arr>=arr.max()-1e-8)
        idx=min(idxs,key=lambda i:abs(priorities[j][i][0]-current[42+j]))
        low.append(priorities[j][int(idx)])
    robust=[s['minimax_regret_choice'] for s in searches]
    baseline=[(current[42],[1,0]),(current[43],[0,1])]
    # Beam demand-driven capacity has a flat optimum in all tested scenarios; retain the existing allocation.
    assert low[0][0]==robust[0][0]==70.
    plans=[]
    for name,policy in [('归档基准',baseline),('A 按份额保持补产',low),('B 限制缺货后悔值（建议）',robust)]:
        evaluations=[]
        for s in scenarios:
            products=[evaluate(j,*policy[j],s) for j in range(2)]
            evaluations.append(dict(scenario=s,products=products,contribution=sum(x['contribution'] for x in products)))
        plan=dict(name=name,policy=policy,evaluations=evaluations,nominal=evaluations[nominal_idx],
            worst_regret=max(float(ideal[0][i]+ideal[1][i])-e['contribution'] for i,e in enumerate(evaluations)),
            round5_net_profit=None,round5_to_6_profit=None,minimum_cash=None,financing_feasible=None)
        plans.append(plan)
    assert plans[2]['worst_regret']<plans[0]['worst_regret']
    # The beam is scenario-wise optimal; therefore the connector minimax search also minimizes joint regret.
    beam_scores=np.array([evaluate(0,*robust[0],s)['contribution'] for s in scenarios])
    assert np.allclose(beam_scores,ideal[0],atol=1e-8)
    rate=round(held_result['finance']['long_rate']*100,2)
    records=[]
    for plan in plans[1:]:
        updates={42:plan['policy'][0][0],43:plan['policy'][1][0],65:7.,66:-5.,68:7.,69:-5.,72:0.,73:0.,79:rate}
        for j,rows in enumerate(([58,59],[61,62])):
            for k,i in enumerate(rows):updates[i]=round(base_demand[j][k],2)
        for j,rows in enumerate(([34,35],[37,38])):
            for k,i in enumerate(rows):updates[i]='第一' if plan['policy'][j][1][0]==k else '第二'
        for field in fields:
            i=field['row'];v=updates.get(i,current[i])
            status='未求解／临时保留';reason='缺价格与营销前向响应，保留与正式4需求锚点相同的策略；不能把需求固定后清零营销或提高售价'
            if i in [42,43]:status='条件网格搜索';reason='0—100%，步长0.1%；A最大化份额保持情景贡献，B最小化36情景最大后悔值；研发、营销等仍未求解'
            elif i in [34,35,37,38]:status='物流推导';reason='两种优先级均比较；复合梁印尼净价2090>泰国1830，连接件泰国35.5>印尼30'
            elif i in [11,15,27,31]:status='本期无新招标／非有效控制';reason='正式5订单机会0且四个投标控件禁用，保留0；不把它解释为历史合同已验证为空'
            elif i==41:reason='列表为FALSE，个人生产页未发现可用分包控件，成本与交付机制未解，暂不分包'
            elif i in [46,47]:reason='所有36情景无投资容量足够，暂取0；机器单价已核78/1.10，立即可用仅有指南规则，正式6收益和现金时序缺失'
            elif i in [49,51,52]:reason='正式5曲线存在，支出到有效横轴/历史存量映射未核，保留750/900/1300及需求锚点，不伪造投入优化'
            elif i==54:reason='正式5期初现金链未核，保留贷款变化0；不可把正式4现金12202直接当已核正式5可支用现金'
            elif i in [58,59,61,62]:status='份额保持情景重算';reason='正式4本组真实需求×本国1.07/0.95；非竞争需求预测；B安全库存不冒充需求增长'
            elif i in [65,66,68,69]:status='t5v0b外生假设';reason='泰国7%／印尼−5%，不作为可优化的真实需求旋钮'
            elif i in [72,73]:status='未知／中性占位';reason='正式6前景缺失，暂0%且不用于剩余收益排名；需新前景和情景重算'
            elif i in [76,77]:status='条件效率预估／未校准';reason='沿用0.17/17作为显式效率情景，±10%压力；运营支出未变不代表效率跨期已验证'
            elif i==79:status='历史财务状态条件预估';reason='t5v0b风险模型+正式5基准5%；沿用正式4期末权益/资产/债务作条件状态，非已核计息利率'
            records.append(dict(plan=plan['name'],key=field['key'],row=i,section=field['section'],
                product=field['product_or_location'],label=field['label'],unit=field['unit'],
                current=current[i],suggested=v,changed=v!=current[i],estimate=field['estimate_attribute'],status=status,reason=reason))
    assert len(records)==84 and all(len({x['key'] for x in records if x['plan']==p['name']})==42 for p in plans[1:])
    save(OUT/'decisions.json',records)
    with (OUT/'decisions.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    sources=[BUNDLE/'models_full.json',dataset_path,INITIAL/'current_42_drafts_all_columns.json',
        INITIAL/'current_group_42_draft.json',INITIAL/'current_personal_controls.json',INITIAL/'source_manifest.json',
        INITIAL/'published_parameters.json',INITIAL/'carryover_comparison.json',ROOT/'sources/决策指南_逐页文本.txt',Path(__file__)]
    for source in read(INITIAL/'source_manifest.json'):
        assert sha(ROOT/source['path'])==source['sha256']
    for value in r['efficiency'].values():
        for key in ['workers','production']:
            ref=value[key];assert sha(ROOT/ref['source'])==ref['sha256']
    save(OUT/'sources.json',{str(p.relative_to(ROOT)):sha(p) for p in sources})
    save(OUT/'inputs.json',dict(version='t5v0b',capacity=caps,efficiency=efficiency,previous_workers=workers,
        opening_inventory=inventories,prices=prices,freight=transport,material_unit_costs=costs,
        formal4_closing_state_scenario=state,held_request=dict(header,demand_basis='FORMAL4_OWN_SHARE_HELD'),held_result=held_result,
        live_readback=False,live_issue='浏览器创建与绑定页面两次各30秒超时；不能读取当前本人列，使用2026-10-14 23:28—23:33北京时间归档基准'))
    result=dict(status='PARTIAL_OPTIMIZATION_NOT_ALL_PARAMETER_OPTIMUM',version='t5v0b',market_id=5,round=5,
        full_profit_available=False,training_performed=False,platform_written=False,searches=searches,plans=plans,
        objective='收入−本期全部生产材料支出−工资−解聘−运费−期末库存持有费；仅可比经营资源贡献，非利润或现金流',
        regret='同一情景下知道需求/成本后的最佳生产贡献减本计划贡献；非概率期望或收益置信区间')
    save(OUT/'result.json',result)
    render(r,fields,records,plans,scenarios,searches,rate,costs)
    print(json.dumps(dict(output=str(OUT),searches=searches,plans=[dict(name=p['name'],allocation=p['policy'],
        contribution=p['nominal']['contribution'],worst_regret=p['worst_regret'],
        products=p['nominal']['products']) for p in plans]),ensure_ascii=False,indent=2))


def render(r,fields,records,plans,scenarios,searches,rate,costs):
    a,b=plans[1:];selected=[x for x in records if x['plan']==b['name']]
    byrow={x['row']:x for x in selected};arow={x['row']:x for x in records if x['plan']==a['name']}
    lines=['# 正式5决策建议：t5v0b全项审查与部分优化','',
        '不要输出真名，姓名统一用首字母替代。','',
        '**推荐B作为暂行生产与库存方案。全部42项已覆盖，但价格、营销、研发、运营、投资、分包和融资存在未求解项，不能称全参数最优。** 未填写或提交平台。',
        f'B连接件产能分配建议 **{fmt(b["policy"][1][0])}%**，A为 **{fmt(a["policy"][1][0])}%**；两方案复合梁均保留70%产能上限。B在下述36个明确情景中最小化生产策略的最大后悔值，覆盖需求不确定性，代价是份额保持情景下多留库存。',
        '','当前值来自2026-10-14 23:28—23:33（北京时间）的市场5／正式5／PYT归档草稿，小组42项当时与PYT一致；非实时基准。2026-10-15此次尝试实时创建和绑定决策列表均30秒超时。不得覆盖用户之后的新值。',
        '','## 建议表：按正式5子页与字段顺序','',
        'A：按正式4本组份额保持的需求补产。B：在份额偏低、偏高和原草稿高需求之间限制最坏缺货/积压机会损失。两方案的需求预估使用同一份额保持值，安全库存没有混进需求预估。下回合0%只是未知值占位，不是模型预测。']
    sections=[('需求：复合梁',[65,66,58,59]),('需求：连接件',[68,69,61,62]),
        ('生产／投资：下回合需求与机器',[72,73,46,47]),('生产／计划：生产与效率',[41,42,43,76,77]),
        ('生产／计划：研发与运营',[51,52,49]),('销售／泰国：复合梁',[9,18,25]),
        ('销售／泰国：连接件',[13,21,29]),('销售／印尼：复合梁',[10,19,26]),
        ('销售／印尼：连接件',[14,22,30]),('销售／大客户订单：复合梁',[11,27]),
        ('销售／大客户订单：连接件',[15,31]),('物流：复合梁',[34,35]),
        ('物流：连接件',[37,38]),('财务',[54,79])]
    order=[i for _,rows in sections for i in rows]
    assert len(order)==42 and set(order)==set(byrow)
    for title,rows in sections:
        lines += ['',f'### {title}','','| 参数／产品／国家 | 单位 | 归档当前 | A建议 | B建议 | B调整 | 状态、依据与约束 |',
            '| --- | --- | ---: | ---: | ---: | --- | --- |']
        for i in rows:
            x=byrow[i];label=' / '.join(v for v in [x['product'],x['label']] if v)
            lines.append(f'| {label} | {x["unit"]} | {fmt(x["current"])} | {fmt(arow[i]["suggested"])} | {fmt(x["suggested"])} | {"是" if x["changed"] else "否"} | {x["status"]}：{x["reason"]} |')
    lines += ['','正式5实际控件顺序按归档9个子页逐项核对；分包FALSE只在列表存在，未发现可用个人控件，单独保留为未求解项。物流每产品两行是同一优先级选择的两国结果；四项禁用投标输入仍列全，不误计为有效优化变量。完整唯一键、状态及理由：[CSV](decisions.csv)、[JSON](decisions.json)。',
        '','## 同基准比较（千美元、千单位）','',
        '**以下贡献扣除全部新生产资源支出，不回加未售库存价值，也未扣期初库存的历史成本；这是资源占用比较，不能称净利润、平台预算或现金节省。** 各方案都从同一202.40千单位连接件库存出发；共同支出和期初库存不能忽略后就称完整经营收益。',
        '','| 方案 | 份额保持贡献 | 对基准增量 | 连接件产量 | 连接件销量 | 连接件期末库存 | 最大后悔值 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for p in plans:
        n=p['nominal'];z=n['products'][1]
        lines.append(f'| {p["name"]} | {n["contribution"]:,.2f} | {n["contribution"]-plans[0]["nominal"]["contribution"]:,.2f} | {z["production"]:.4f} | {sum(z["sales"]):.4f} | {z["inventory"]:.4f} | {p["worst_regret"]:,.2f} |')
    lines += ['','| 同一需求情景（公布材料价、效率中值） | 基准贡献 | A贡献／连接件缺货 | B贡献／连接件缺货 |',
        '| --- | ---: | ---: | ---: |']
    for name in ['份额保持×0.8','份额保持','份额保持×1.25','原草稿高需求']:
        ix=next(i for i,s in enumerate(scenarios) if s['name']==name and s['material_form']=='published' and s['efficiency_scale']==1)
        es=[p['evaluations'][ix] for p in plans]
        lines.append(f'| {name} | {es[0]["contribution"]:,.2f} | {es[1]["contribution"]:,.2f} / {es[1]["products"][1]["unmet"]:.4f} | {es[2]["contribution"]:,.2f} / {es[2]["products"][1]["unmet"]:.4f} |')
    lines += ['','| 财务／期限指标 | 基准 | A | B |','| --- | --- | --- | --- |',
        '| 正式5净利润、正式5—6新增利润 | 未求解 | 未求解 | 未求解 |',
        '| 最低现金（公布下限2000千美元） | 未验证 | 未验证 | 未验证 |',
        '| 长期贷款变化 | 0（归档） | 0（临时） | 0（临时） |',
        '| 自动短贷及融资可行性 | 未验证 | 未验证 | 未验证 |',
        '| 正式6期末库存、残值、剩余收益排名 | 未求解 | 未求解 | 未求解 |',
        '','### 为什么选B','',
        'A以需求保持份额为单一基准，材料支出和积压最少，但需求恢复时会缺连接件。B同时考虑历史份额需求偏差与草稿中425千单位的高需求，避免直接把需求腰斩当作确定事实；以可核算的机会损失折中产量。高需求草稿不是独立预测，这项风险偏好是本次分析选择，若确认其已无依据，应采用A。B仍可能缺货，不能称安全供给保证；也可能积压。',
        '','复合梁是需求驱动，70%是产能上限而非必产29.169千单位；各测试需求均小于该上限。把上限改到约37%会在需求好转时人为限制供应，而基准情景下没有已验证的成本节省，因此两方案保留70%。此结论基于现有模型需求驱动规则，实际执行仍需平台预算核验。',
        '','### 名义情景资源明细','',
        '| 方案／产品 | 产量 | 人员 | 材料支出 | 工资 | 解聘 | 运费 | 持有费 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for p in plans:
        for j,z in enumerate(p['nominal']['products']):
            lines.append(f'| {p["name"]}／{P[j]} | {z["production"]:.4f} | {z["workers"]:.2f} | {z["materials"]:,.2f} | {z["payroll"]:,.2f} | {z["severance"]:,.2f} | {z["freight"]:,.2f} | {z["holding"]:,.2f} |')
    lines += ['','## 假设、边界与搜索范围','',
        '- 模型：冻结t5v0b，训练回合4、应用回合5；三条正式5曲线及29类状态不改、不重训、不调用旧需求响应冒充正式5预测。市场5／正式5／PYT；剩余期限5—6，但仅正式5可比资源贡献可计算，不以单回合贡献替代剩余净利润。',
        '- 需求：两产品泰国+7%、印尼−5%来自t5v0b用户假设；本组份额保持是额外分析假设。正式4真实需求分别3.54/12.24与108.23/116.17，乘国别比例得3.7878/11.628及115.8061/110.3615千单位。竞争队行为和份额变化未验证；份额保持不代表对手已建模。',
        '- 需求场景：上述需求×0.8、×1、×1.25，以及原草稿4.47/12.20、285/140；它们是有限压力集合，无概率含义。每个需求组合再取三材料形式和效率×0.9/1/1.1，合计36个情景。价格、八项营销、研发和运营保持正式4最终方案同值，只是为了不破坏需求锚点，未证明其最优。',
        '- 数量与生产：正式5零投资容量41.67/412.25，期初库存0/202.40；前期人员92.84/25.10来自正式4实际。工资43.5千美元/人、班次1/1.65/2.56、离职10%、解聘35%使用公布参数；绝对效率0.17/17为显式条件，非t5v0b新增预测。机器共同为0，不虚构正式6容量与收益。',
        '- 全参数范围：42个清单字段全覆盖；生产配比分别0—100%、步长0.1%及两种物流优先级穷举，每产品2002项选择。各产品分开计算；复合梁选择在每个情景均达到该情景最优，因此连接件的最小最大后悔值亦为此固定策略下的两产品联合结果。不是所有经营变量联合最优。',
        '- 材料：公布价、固定加价、比例迁移三种路径都测试，跨期迁移仍未验证。物流费复合梁30/90、连接件0.5/2美元/单位；持有费按期末数量×0.6美元/单位，库存计价和正式6残值未解。',
        f'- 融资：按正式4期末权益27102、资产39169、长贷10200、短贷0给定条件算长期利率{rate:.2f}%；这是风险状态情景，不能宣称正式5实际计息利率。正式5期初现金、周转、税亏、借款计息时点与最低现金约束未接通，因此不做还贷最优值。',
        '- 订单：正式5无新招标是已核事实；正式4公开下期订单0与未独立核验的正式5合同状态区分。计算在无额外到期订单占用的条件下；若发现到期合同，须先扣交付承诺再重算。',
        '- 预估一致性：增长、需求、物流、人员和成本按同一方案重算。表中需求按页面两位小数显示，计算保留未舍入值；取整误差小于0.01千单位，不作为额外需求。正式6增长0只作占位，正式6收益/利润留空。',
        '','## 未求解项及补齐方法','',
        '| 范围 | 临时处理 | 缺口与影响 | 补齐方法 |','| --- | --- | --- | --- |',
        '| 4国别价格、8项营销 | 保留1860/2180、36/32及现投入 | 缺竞争最终输入与前向份额响应，不能排名提价/降价和增减营销 | 补竞争输入、真实产品/国别分配与独立需求验证，再联合搜索 |',
        '| 两项研发、运营 | 保留900/1300/750 | 当期支出到有效横轴及持续存量未知，影响需求、效率及正式6 | 用可恢复单字段试验和历史投入确定映射，留出验证 |',
        '| 两机器投资 | 暂0 | 容量在本次需求范围非瓶颈；但正式6需求、现金/计价时序未知，不能完整评估两期价值 | 核对投资时序、正式6需求/容量及现金后重算 |',
        '| 分包 | FALSE | 可用性、成本和交付未核，未知不设成免费供给 | 核对当回合控件与指南、预算联动 |',
        '| 长贷变化、短贷与最低现金 | 暂0变化 | 未验证偿债后现金和计息，不推荐直接还款10200 | 配对最新财务预算、期初状态与还贷扰动，恢复后核验 |',
        '| 正式6增长、效率、真实利率 | 条件占位 | 不应当成已知外生状态或人为改善预算 | 更新前景、状态及映射后重新生成预估 |',
        '','本报告已做模型继承验收、来源哈希、数量守恒、销量上界、网格目标、唯一字段及表序核验；未做实时平台预算回读。此前4435千美元是旧需求预估下的平台预算，未拿来作本报告利润或比较基准。',
        '','## 可复现文件','',
        '[计算结果](result.json) · [输入与模型输出](inputs.json) · [来源哈希](sources.json) · [模型验收](model_acceptance.json) · [工作日志](work_log.md) · [计算脚本](optimize_formal5_t5v0b.py)',
        '','运行：使用项目Python3.12执行 `work/optimize_formal5_t5v0b.py`；输出目录由 `work/formal5_decision_active.txt` 指定，拒绝覆盖已有结果。脚本依赖原项目模型及来源档案。']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    shutil.copy2(Path(__file__),OUT/Path(__file__).name)
    # Back up the current on-disk README, including earlier uncommitted work, before the focused status update.
    before=ROOT/'README.md';backup=OUT/'before';backup.mkdir(exist_ok=False)
    shutil.copy2(before,backup/'README.md');old=sha(before)
    content=before.read_text(encoding='utf-8')
    marker='## 研究诊断与条件比较'
    entry=(f'正式5最新决策分析：[t5v0b全项建议与部分优化]({OUT.relative_to(ROOT).as_posix()}/report.md)。'
        f'42项按子页输出，连接件A {a["policy"][1][0]:g}%／B {b["policy"][1][0]:g}%（有限压力情景建议），'
        '复合梁需求驱动上限70%；价格、营销、投入及完整财务仍有未求解项，不是全参数最优。实时回读超时，未填写或提交。\n\n')
    assert marker in content
    before.write_text(content.replace(marker,entry+marker,1),encoding='utf-8')
    save(OUT/'document_hashes.json',dict(README=dict(before=old,after=sha(before),backup=str((backup/'README.md').relative_to(ROOT)))))
    checks=[]
    for path in [before,OUT/'report.md']:
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):continue
            dest=target.split('#')[0]
            valid=(path.parent/dest).exists()
            checks.append(dict(document=str(path.relative_to(ROOT)),target=target,exists=valid))
    save(OUT/'link_checks.json',checks)
    assert all(x['exists'] for x in checks),[x for x in checks if not x['exists']]
    stamp=datetime.now(timezone(timedelta(hours=8))).isoformat()
    with (OUT/'work_log.md').open('a',encoding='utf-8') as f:
        f.write(f'\n验收完成：{stamp}。42项×2方案逐页覆盖；生产/优先级每产品2002选择×36情景；模型来源与继承验收通过，数量守恒、目标、字段完整性和链接通过。\n'
            '实时页面两次各30秒超时，使用已归档本人/小组基准，未重复采集教程，未重训、未填写、未提交。完整净利润和现金约束仍未求解。README改前磁盘备份及改前/改后哈希已保存；未回退已有修改。\n')


if __name__=='__main__':
    main()
