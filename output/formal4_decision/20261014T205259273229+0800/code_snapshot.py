"""Formal4 conditional price/production search; frozen t4v1a, no platform writes."""
import copy
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
import numpy as np
from scipy.optimize import differential_evolution
import t4v1a as model
import material_unit_cost_model as material

BUNDLE = ROOT/'output/t4v1a/20261014T175143627079+0800'
INITIAL = ROOT/'output/round_close/20261013_formal3_close/formal4_initial/verification/20261014T002441'
OUT = ROOT/'output/formal4_decision'/datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f%z')
C = ['泰国', '印尼']
P = ['复合梁', '连接件']


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT/'work_log.md').write_text('用户授权：基于t4v1a给出正式4决策。\n进行中：离线条件搜索，未填写或提交平台。\n不要输出真名，姓名统一用首字母替代。\n', encoding='utf-8')
    r = model.read(BUNDLE/'models_full.json')
    request = model.read(BUNDLE/'example_request.json')
    rows = request['competitors']
    pars = {k:v['value'] for k,v in r['application_parameters'].items()}
    with (INITIAL/'formal4_current_checklist.csv').open(encoding='utf-8-sig', newline='') as f:
        fields = list(csv.DictReader(f))[2:]
    assert len(fields) == 42 and len({x['key'] for x in fields}) == 42
    val = {int(x['source_row']):x['PYT_value'] for x in fields}
    num = lambda i:float(val[i].replace('\xa0','').replace(' ',''))
    rawpath = ROOT/'output/round_close/20261014_full_archive/raw/formal4_decisionchecklist.json'
    latest = model.read(rawpath)
    table = latest['tables'][1]
    assert all(table[int(x['source_row'])+1][5] == x['PYT_value'] for x in fields)
    prodpath = ROOT/'output/round_close/20261014_resume_verified/raw/market5_formal3_productiondetails.json'
    actual = model.read(prodpath)['tables'][0]
    workers = [float(actual[i][6]) for i in [7,14]]
    cap, eff = [31.03,85.], [num(76),num(77)]
    freight = [[30.,90.],[.5,2.]]
    costs = [material.predict(r['materials'][p]['models'][r['materials'][p]['selected']],pars['material/'+p],1.)['unit_cost_usd'] for p in P]
    bounds, own = [], []
    for p in P:
        pool = [x for x in rows if x['product']==p]
        own.append([x for x in pool if x['team_id']==r['target_team_id']])
        bounds.append([(min(x['price'] for x in pool if x['country']==c),max(x['price'] for x in pool if x['country']==c)) for c in C])
    fixed = sum(num(i) for i in [18,19,21,22,25,26,29,30,49,51,52])

    def demand(j, prices, growth=None, rival=.0, marketing=1., variant='SHARE'):
        pool = copy.deepcopy([x for x in rows if x['product']==P[j]])
        for x in pool:
            if x['team_id']==r['target_team_id']:
                x['price'] = float(prices[C.index(x['country'])])
            else:
                x['price'] *= 1+rival
                x['general'] *= marketing
                x['designer'] *= marketing
        # shortcut: retain formal3 aggregate input proxies and response curves; replace after forward mapping is verified.
        data = model.demand_reference(r, pool+[copy.deepcopy(x) for x in rows if x['product']!=P[j]], request['market_totals_kunits'],
            {'复合梁':-.175 if growth is None else growth,'连接件':.05}, model_name='COUNTRY' if variant=='COUNTRY' else 'SHARE', linear=variant=='LINEAR')
        out = [next(x['demand_kunits'] for x in data['predictions'] if x['team_id']==r['target_team_id'] and x['product']==P[j] and x['country']==c) for c in C]
        return np.array(out)

    def evaluate(j, prices, limit=None, growth=None, rival=0., marketing=1., efficiency=.0, material_scale=1., variant='SHARE', priority=None):
        d = demand(j, prices, growth, rival, marketing, variant)
        e = eff[j]*(1+efficiency)
        net = np.asarray(prices)-freight[j]
        order = list(np.argsort(-net)) if priority is None else priority
        def at(q):
            if j==0: q=min(q,float(sum(d)))
            sales=np.zeros(2); remaining=q
            for k in order:
                sales[k]=min(remaining,d[k]);remaining-=sales[k]
            labor=model.labor_cost(r,dict(capacity_kunits=cap[j],production_kunits=q,previous_workers=workers[j]),e)
            inventory=q-float(sum(sales))
            score=float(sales@net)-q*costs[j]*material_scale-labor['payroll']-labor['firing']-.6*inventory
            return dict(score_kusd=score, demand_kunits=d.tolist(),sales_kunits=sales.tolist(),production_kunits=q,
                closing_inventory_kunits=inventory,workers=labor['workers'],payroll_kusd=labor['payroll'],severance_kusd=labor['firing'],priority=[C[k] for k in order])
        if limit is None:
            upper=min(cap[j],float(sum(d)))
            options=[0.,upper,cap[j]/3,cap[j]*2/3,workers[j]*.9*e,float(d[order[0]])]
            best=max((at(q) for q in options if 0<=q<=upper),key=lambda z:z['score_kusd'])
        else:
            best=at(cap[j]*limit/100)
        best['allocation_pct']=best['production_kunits']/cap[j]*100
        return best

    results=[]
    for j in range(2):
        searches=[]
        for seed in [11,29]:
            z=differential_evolution(lambda x:-evaluate(j,x)['score_kusd'],bounds[j],seed=seed,popsize=10,maxiter=100,tol=1e-8,polish=True)
            searches.append(dict(seed=seed,prices=z.x.tolist(),score=-float(z.fun),converged=bool(z.success)))
        best=max(searches,key=lambda x:x['score'])
        prices=[round(x,0 if j==0 else 1) for x in best['prices']]
        plan=evaluate(j,prices)
        allocation=math.ceil(plan['allocation_pct']*10-1e-10)/10
        plan=evaluate(j,prices,allocation)
        baseprices=[num(i) for i in ([9,10] if j==0 else [13,14])]
        baseline=evaluate(j,baseprices,num(42+j),priority=([1,0] if j==0 else [0,1]))
        assert abs(searches[0]['score']-searches[1]['score'])<1.
        assert plan['score_kusd']>=baseline['score_kusd']-1e-6
        assert 0<=plan['production_kunits']<=cap[j] and abs(sum(plan['sales_kunits'])+plan['closing_inventory_kunits']-plan['production_kunits'])<1e-9
        for k in range(2):
            for delta in [-1,1]:
                trial=prices.copy();trial[k]+=delta*(1 if j==0 else .1)
                assert evaluate(j,trial)['score_kusd']<=best['score']+1.
        scenarios=[]
        for name,opts in [('中性',{}),('复合梁行业−20%',{'growth':-.2}),('对手降价10%',{'rival':-.1}),('对手营销增加50%',{'marketing':1.5}),('效率下降10%',{'efficiency':-.1}),('材料上涨10%',{'material_scale':1.1}),('COUNTRY模型',{'variant':'COUNTRY'}),('连接件线性价格候选',{'variant':'LINEAR'}),('联合不利',{'growth':-.2,'rival':-.1,'marketing':1.5,'efficiency':-.1,'material_scale':1.1})]:
            a=evaluate(j,prices,allocation,**opts)
            b=evaluate(j,baseprices,num(42+j),priority=([1,0] if j==0 else [0,1]),**opts)
            scenarios.append(dict(name=name,candidate=a,baseline=b,delta_kusd=a['score_kusd']-b['score_kusd']))
        boundary=[C[k] for k in range(2) if min(abs(prices[k]-b) for b in bounds[j][k])<1e-6]
        results.append(dict(product=P[j],prices=prices,allocation=allocation,plan=plan,baseline=baseline,bounds=bounds[j],search_boundary_countries=boundary,searches=searches,scenarios=scenarios))
        print(P[j],prices,allocation,'demand',plan['demand_kunits'],'score delta',plan['score_kusd']-baseline['score_kusd'],flush=True)

    updates={9:results[0]['prices'][0],10:results[0]['prices'][1],13:results[1]['prices'][0],14:results[1]['prices'][1],42:results[0]['allocation'],43:results[1]['allocation'],65:-17.5,66:-17.5,68:5.,69:5.}
    reasons={i:'SHARE冻结响应与对手正式3策略保持下的价格/生产搜索' for i in [9,10,13,14,42,43]}
    for j in range(2):
        for k in range(2):
            i=([58,59] if j==0 else [61,62])[k]
            updates[i]=round(results[j]['plan']['demand_kunits'][k],2);reasons[i]='条件需求预测；预估不等于实际销量'
            i=([34,35] if j==0 else [37,38])[k]
            updates[i]='第一' if results[j]['plan']['priority'][0]==C[k] else '第二';reasons[i]='单位售价减运费排序'
    rate=model.rate_scenario(r,request['financial']['state'])
    updates[79]=round(rate['long_rate']*100,2);reasons[79]='正式3期末状态保持的利率情景；计息时点未识别'
    decisions=[]
    for x in fields:
        i=int(x['source_row']);suggested=updates.get(i,x['PYT_value'])
        try: changed=not math.isclose(float(suggested),num(i),abs_tol=1e-9)
        except ValueError:changed=str(suggested)!=x['PYT_value']
        section=x['section']
        unit='美元/单位' if section=='每单位价格' else '千美元' if any(w in section for w in ['营销','研发','运营','财务决策']) else '千单位/人' if '效率' in section else '千单位' if '千单位' in section else '%' if '%' in section or i==79 else '选择'
        if i==41:unit='选择'
        reason=reasons.get(i,'行业前景中性情景' if i in [65,66,68,69] else '保留归档值／未优化')
        if i in [72,73]:reason='保留玩家预估；正式5前景未知，未用于收益排名'
        decisions.append(dict(key=x['key'],section=section,product_or_location=x['subsection'],label=x['label'],unit=unit,current=x['PYT_value'],suggested=suggested,changed=changed,reason=reason))
    assert {x['key'] for x in decisions}=={x['key'] for x in fields}
    with (OUT/'decisions.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(decisions[0]));w.writeheader();w.writerows(decisions)
    sources=[BUNDLE/'models_full.json',BUNDLE/'example_request.json',INITIAL/'formal4_current_checklist.csv',rawpath,prodpath,Path(__file__)]
    result=dict(status='CONDITIONAL_PRICE_PRODUCTION_CANDIDATE_NOT_FULL_OPTIMUM',version='t4v1a',market=5,round=4,account='PYT',live_readback=False,
        baseline_timestamp=latest['captured_at'],products=results,decisions=decisions,rate_scenario=rate,fixed_retained_spending_kusd=fixed,
        score_definition='销售收入−全部生产材料支出−工资−解聘−运费−未售库存持有费；不含库存价值回加、固定费用、折旧、利息、税及跨期作用，不是利润',
        assumptions=['正式3需求曲线及研发、合计营销代理保持；未推断正式4投入有效横轴','效率固定为个人归档预估0.17/16.77，不称模型前向预测','零投资、零期初库存；未证实合同不确认收入或现金','复合梁需求驱动，连接件自由生产；压力测试保留已选产能分配和物流顺序','价格搜索限市场5正式3同产品同国家已见价格范围，未证明全局或跨期最优'],
        source_sha256={str(p.relative_to(ROOT)):model.sha(p) for p in sources},checks=dict(unique_complete_fields=42,two_seed_agreement=True,production_conservation=True,baseline_improvement=True,local_price_checks=True))
    model.save(OUT/'result.json',result)
    (OUT/'code_snapshot.py').write_bytes(Path(__file__).read_bytes())
    lines=['# 正式回合4条件决策候选（t4v1a）','', '不要输出真名，姓名统一用首字母替代。','',
        '这是固定营销、研发、运营、投资、融资和效率条件下的售价与生产候选，不是正式4—6完整利润最优解。未填写或提交平台。',
        f'个人基准：市场5、PYT，归档时间{latest["captured_at"]}（UTC）；未实时回读。正式4归档截止为2026-10-14 22:00（北京时间），须提交前核对。','',
        '## 核心结果','', '| 产品 | 泰国售价 | 印尼售价 | 产能分配 | 泰国需求 | 印尼需求 | 产量 | 可比贡献较基准增加（千美元） |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for a in results:
        v=a['plan'];lines.append(f'| {a["product"]} | {a["prices"][0]:g} | {a["prices"][1]:g} | {a["allocation"]:.1f}% | {v["demand_kunits"][0]:.3f} | {v["demand_kunits"][1]:.3f} | {v["production_kunits"]:.3f} | {v["score_kusd"]-a["baseline"]["score_kusd"]:.2f} |')
    lines+=['','售价为美元/单位；需求、产量为千单位。可比贡献定义：'+result['score_definition']+'。',f'保留营销、研发、运营合计{fixed:g}千美元；费用固定，未参与上述增量比较。',
        '复合梁印尼3000美元触及本次历史价格搜索上限，不证明更高价格无收益；连接件100%触及现有产能上限，未据此自动追加投资。连接件从原62%提高至100%，产量52.7→85千单位；提高价格使中性预测需求约85.124千单位，接近现有产能。',
        '归档基准用同一模型重新估计需求及生产，未使用玩家需求预估作为真实需求。归档平台预算利润1486千美元另属输入预估条件测算，与本报告可比贡献不可直接相减；候选平台预算未生成。',
        '', '## 不利情景与模型敏感性','', '| 情景 | 基准可比贡献 | 候选可比贡献 | 增量（千美元） |','|---|---:|---:|---:|']
    for i,s in enumerate(results[0]['scenarios']):
        a=sum(x['scenarios'][i]['baseline']['score_kusd'] for x in results);b=sum(x['scenarios'][i]['candidate']['score_kusd'] for x in results)
        lines.append(f'| {s["name"]} | {a:.2f} | {b:.2f} | {b-a:.2f} |')
    lines+=['','压力测试固定推荐产能分配；复合梁随需求下调产量，连接件仍按自由生产承担未售材料支出。库存未计可回收价值，因此有库存时此指标不是会计经营利润。未假设短缺转单。','', '## 完整输入表（42项，按决策列表顺序）','', '| 产品/地区 | 项目 | 单位 | 归档当前值 | 候选值 | 调整 | 依据 |','|---|---|---|---:|---:|---|---|']
    for x in decisions:lines.append(f'| {x["product_or_location"]} | {x["section"]} / {x["label"]} | {x["unit"]} | {x["current"]} | {x["suggested"]} | {"是" if x["changed"] else "否"} | {x["reason"]} |')
    lines+=['','## 假设、边界与复现','']+['- '+x for x in result['assumptions']]+['',
        '营销、研发、运营和投资未识别完整跨期边际收益，保留当前值不代表这些值最优。未投标的零值保持；机会不视作中标。长期贷款变化保持0，最低现金2000千美元约束尚未验证，不能据此确认可偿债额。',
        f'利率预估改为{updates[79]:.2f}%仅为给定正式3期末风险状态的模型情景；原3%低于公布基准5%，不可继续当作可信利率。',
        '正式5、6参数及完整结转状态未知，不计算剩余累计税后利润。未来增长7.5%/4%保留为玩家预估，不作为已知前景。',
        '两种随机种子搜索、局部价格扰动、产量销量库存守恒和42项唯一键覆盖检查通过；未重训。COUNTRY和线性候选仅用于敏感性，未替换SHARE。',
        '', '复现：在项目根目录用已配置Python运行 `work/optimize_formal4_t4v1a.py`，输出写入新的独立时间戳目录。',
        '', '[完整计算及输入哈希](result.json) · [完整决策CSV](decisions.csv) · [代码快照](code_snapshot.py)',
        '', '跳过平台填写、实时预算与现金链核验。风险：竞争策略变化及前向响应未识别，候选不能宣称完整经营或六回合最优。']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (OUT/'work_log.md').open('a',encoding='utf-8') as f:f.write('\n完成：双产品价格/生产条件搜索、9情景比较、42项完整决策输出，数值自检通过。无网页写入、无重训、无原件覆盖。\n')
    print('OUTPUT',OUT,flush=True)


if __name__=='__main__':
    main()
