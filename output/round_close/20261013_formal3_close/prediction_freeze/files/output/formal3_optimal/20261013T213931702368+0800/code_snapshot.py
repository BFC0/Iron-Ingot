"""Append-only formal3 conditional optimization using the frozen t3v1 registry."""
import copy
import csv
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2')]
import numpy as np
from scipy.optimize import differential_evolution
import t3v1 as model
import material_unit_cost_model as material_model

REG = ROOT/'output/connector_model_update/20261013T200914882448+0800/models.json'
DATA = ROOT/'output/t3v1/20261013T193815695205+0800/dataset.json'
CURRENT = model.base.CURRENT
C = list(model.COUNTRIES)
TARGET = 'M05-05014677bb16a61e'
OUT = ROOT/'output/formal3_optimal'/datetime.now(model.nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def save(name, value):
    with (OUT/name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def run():
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT/'work_log.md').write_text('用户授权：按最新模型和正式3已知条件输出决策及敏感性分析。\n进行中；仅离线分析。不要输出真名，姓名统一用首字母替代。\n', encoding='utf-8')
    registry, dataset = read(REG), read(DATA)
    personal, tables = read(CURRENT/'personal_rows.json'), read(CURRENT/'tables.json')
    current = {r['row_index']: r for r in personal}
    number = lambda i: float(current[i]['value'].replace('\xa0','').replace(' ',''))
    pair = next(p for p in dataset['state_pairs'] if p['market_id']==5 and p['team_id']==TARGET)
    state = pair['closing']['values']
    own = [r for r in dataset['rows'] if r['market_id']==5 and r['team_id']==TARGET]
    assert len(own)==2 and state['rd']==800 and state['operations']==750
    published = tables['outlook']['tables'][-1]
    def field(section, label):
        start = next(i for i,r in enumerate(published) if r==[section])
        row = next(r for r in published[start+1:] if r[0]==label)
        return float(row[1].replace('\xa0','').replace(' ',''))
    wage = field('生产工资, 千 美元','泰国')
    published_materials = field('原材料成本','复合梁')
    material_fit = registry['mechanisms']['materials'][registry['mechanisms']['material_selection']['form']]
    materials = material_model.predict(material_fit,published_materials,1.)['unit_cost_usd']
    transport = [field('运输成本, 复合梁','泰国 -> '+c) for c in C]
    shifts = [1.,field('工资乘数','两班倒'),field('工资乘数','三班倒')]
    plan_rows = next(t for t in tables['productionplanning']['tables'] if ['生产决策'] in t)
    cap = float(next(r[1] for r in plan_rows if r[0]=='产能, 千单位'))
    assert cap==21.5 and float(next(r[2] for r in plan_rows if r[0]=='产能, 千单位'))==0
    assert abs(state['capacity']*.85-cap)<.01
    assert next(r for t in tables['logistics']['tables'] for r in t if r[0]=='期初库存')[1]=='0.00'
    fit = registry['mechanisms']['efficiency']['chosen']
    op_curve = registry['response_curves']['3']['operations']['parameters']
    rd_curve = registry['response_curves']['3']['rd']['parameters']
    retained = state['workers']*.9
    pools = {c:[{k:r[k] for k in ('market_id','phase','round','team_id','country','price','initial_price','general','designer','rd','previous_rd')}
                for r in dataset['rows'] if r['market_id']==5 and r['country']==c] for c in C}
    for pool in pools.values():
        for r in pool:
            r.update(round=3, previous_rd=r['rd'])
    baseline = np.array([number(9),number(10),number(18)+number(19),number(25)+number(26),number(51),number(49)])
    # shortcut: frozen formal2 price reference and aggregate marketing retain the estimator's training semantics; country effects need independent data.
    bounds = []
    for c in C:
        rows = [r for r in dataset['rows'] if r['country']==c]
        ref = next(r['initial_price'] for r in own if r['country']==c)
        bounds.append((min(r['price']/r['initial_price'] for r in rows)*ref,max(r['price']/r['initial_price'] for r in rows)*ref))
    bounds += [(0,2500),(0,4300),(0,1600-max(registry['demand']['COUNTRY/'+c]['rho']*state['rd'] for c in C)),
               (0,1620-fit['rho']*state['operations'])]
    totals0 = np.array([55.37,142.44])  # Archived demand-page last-year totals, not this year's player forecast.

    def demand(x, rival_price=1., rival_marketing=1., total_scale=1., price_reference='frozen'):
        result=[]
        for j,c in enumerate(C):
            pool=copy.deepcopy(pools[c])
            for r in pool:
                if price_reference=='formal2': r['initial_price']=r['price']
                if r['team_id']==TARGET:
                    r.update(price=float(x[j]),general=float(x[2]),designer=float(x[3]),rd=float(x[4]),previous_rd=state['rd'])
                else:
                    r.update(price=r['price']*rival_price,general=r['general']*rival_marketing,designer=r['designer']*rival_marketing)
            m=registry['demand']['COUNTRY/'+c]
            shares=model.core.predict(pool,model.core.features(pool,rd_curve,m['rho'],m['piecewise']),m['beta'])
            result.append(float(shares[next(i for i,r in enumerate(pool) if r['team_id']==TARGET)]*totals0[j]*total_scale))
        return np.array(result)

    def evaluate(x, total_scale=1., rival_price=1., rival_marketing=1., efficiency_scale=1., material_scale=1., wage_scale=1., current_plan=False, allocation_limit_pct=100., price_reference='frozen'):
        d=demand(x,rival_price,rival_marketing,total_scale,price_reference)
        a,b,c=op_curve
        effective=x[5]+fit['rho']*state['operations']
        eff=fit['theta']*(a+b*effective/(c+effective))*efficiency_scale
        prices=x[:2]
        net=prices-np.array(transport)
        order=[1,0] if current_plan else list(np.argsort(-net))
        limit=cap*(number(42) if current_plan else allocation_limit_pct)/100
        upper=min(limit,float(sum(d)))
        def calc(q):
            sales=np.zeros(2); remaining=q
            for j in order:
                sales[j]=min(remaining,d[j]); remaining-=sales[j]
            bands=np.array([min(q,cap/3),min(max(q-cap/3,0),cap/3),max(q-2*cap/3,0)])
            payroll=float(bands@np.array(shifts))*wage*wage_scale/eff
            firing=max(retained-q/eff,0)*wage*.35
            variable=float(sales@net)-q*materials*material_scale-payroll-firing
            return variable,sales,payroll,firing,bands
        # Piecewise linear production objective: demand, shift and severance breakpoints suffice.
        candidates=[0.,upper,*[min(upper,v) for v in [cap/3,2*cap/3,retained*eff,d[order[0]]]]]
        q=max(candidates,key=lambda q:calc(q)[0]) if not current_plan else upper
        value,sales,payroll,firing,bands=calc(q)
        score=value-x[2]-x[3]-x[4]-x[5]-6050
        return dict(score_kusd=float(score),variable_contribution_after_severance_kusd=float(value),demand_kunits=d.tolist(),
                    sales_kunits=sales.tolist(),production_kunits=float(q),allocation_pct=float(q/cap*100),efficiency=float(eff),
                    workers=float(q/eff),payroll_kusd=payroll,severance_kusd=firing,shift_production_kunits=bands.tolist(),priority=[C[j] for j in order])

    def optimize(options, seeds=(11,29), search_bounds=None):
        results=[]
        for seed in seeds:
            result=differential_evolution(lambda x:-evaluate(x,**options)['score_kusd'],search_bounds or bounds,seed=seed,popsize=12,maxiter=220,tol=1e-7,polish=True)
            results.append(dict(seed=seed,x=result.x.tolist(),score=-float(result.fun),success=bool(result.success),message=str(result.message),evaluations=result.nfev))
        best=max(results,key=lambda r:r['score'])
        return dict(parameters=best['x'],metrics=evaluate(np.array(best['x']),**options),solvers=results)

    base=evaluate(baseline,current_plan=True)
    best=optimize({})
    x=np.array(best['parameters'])
    rounded=np.array([round(x[0]),round(x[1]),round(x[2]),round(x[3]),round(x[4]),round(x[5])],float)
    rounded=np.array([max(lo,min(hi,v)) for v,(lo,hi) in zip(rounded,bounds)])
    candidate=evaluate(rounded)
    print('baseline/candidate',base['score_kusd'],candidate['score_kusd'],'parameters',rounded.tolist(),flush=True)
    scenarios=[('总需求−30%',dict(total_scale=.7)),('总需求−15%',dict(total_scale=.85)),('总需求+7.5%（玩家增长预估）',dict(total_scale=1.075)),
               ('总需求+30%',dict(total_scale=1.3)),('对手降价10%',dict(rival_price=.9)),('对手提价10%',dict(rival_price=1.1)),
               ('对手营销+50%',dict(rival_marketing=1.5)),('效率−10%',dict(efficiency_scale=.9)),('效率+10%',dict(efficiency_scale=1.1)),
               ('材料+10%',dict(material_scale=1.1)),('工资+7%',dict(wage_scale=1.07)),('价格参考改为正式2实际',dict(price_reference='formal2')),
               ('联合不利',dict(total_scale=.7,rival_price=.9,rival_marketing=1.5,efficiency_scale=.9,material_scale=1.1))]
    sensitivity=[]
    for label,options in scenarios:
        value=evaluate(rounded,allocation_limit_pct=candidate['allocation_pct'],**options)
        sensitivity.append(dict(label=label,assumptions=options,**value,delta_kusd=value['score_kusd']-candidate['score_kusd']))
    reoptimized=[]
    for label,options in [scenarios[0],scenarios[4],scenarios[-1]]:
        reoptimized.append(dict(label=label,assumptions=options,**optimize(options,seeds=(17,))))
    boundary_analysis=optimize({},seeds=(23,),search_bounds=bounds[:2]+[(0,5000),(0,8600)]+bounds[4:])
    anchor_analysis=optimize(dict(price_reference='formal2'),seeds=(23,))
    local=[]
    for i,name in enumerate(['泰国售价','印尼售价','一般营销总额','设计师营销总额','研发','运营']):
        for change in [-.1,.1]:
            z=rounded.copy(); z[i]*=1+change
            if bounds[i][0]<=z[i]<=bounds[i][1]:
                m=evaluate(z); local.append(dict(parameter=name,change_pct=change*100,value=float(z[i]),delta_kusd=m['score_kusd']-candidate['score_kusd']))
    # Exact production allocation must agree with the existing public model when severance is zero.
    prod={'复合梁':dict(capacity=cap,efficiency=candidate['efficiency'],material_cost=materials,demand=dict(zip(C,candidate['demand_kunits'])),prices=dict(zip(C,rounded[:2])),transport_costs=dict(zip(C,transport))),
          '连接件':dict(capacity=0.,efficiency=number(78),material_cost=14.2,demand=dict.fromkeys(C,0.),prices=dict.fromkeys(C,27.),transport_costs=dict(zip(C,[.5,2.]))) }
    allocation=model.allocate(prod,None,wage,shifts)
    assert candidate['severance_kusd']==0 and abs(allocation['contribution_kusd']-candidate['variable_contribution_after_severance_kusd'])<1e-6
    assert abs(sum(candidate['sales_kunits'])-candidate['production_kunits'])<1e-8
    assert candidate['score_kusd']>=base['score_kusd']
    assert len(personal)==44 and len({r['row_index'] for r in personal})==44
    # Archived manual-input budget arithmetic is checked separately from the demand forecast.
    budget_sales=np.array([3.4,13.8]); budget_q=17.2
    bands=np.array([cap/3,cap/3,budget_q-2*cap/3])
    manual_payroll=float(bands@np.array(shifts))*wage/number(77)
    manual_ebitda=float(budget_sales@(baseline[:2]-np.array(transport)))-budget_q*materials-manual_payroll-sum(baseline[2:])-6050
    budget_tolerance=.005*(sum(baseline[:2])+materials)+manual_payroll*.005/(number(77)-.005)+3.
    assert abs(manual_ebitda-8570)<budget_tolerance
    assert abs(best['solvers'][0]['score']-best['solvers'][1]['score'])<1.
    updates={9:rounded[0],10:rounded[1],18:round(rounded[2]*number(18)/(number(18)+number(19))),
             25:round(rounded[3]*number(25)/(number(25)+number(26))),49:rounded[5],51:rounded[4],
             42:math.ceil(candidate['allocation_pct']*10)/10,34:'第一' if candidate['priority'][0]=='泰国' else '第二',35:'第一' if candidate['priority'][0]=='印尼' else '第二',
             58:candidate['demand_kunits'][0],59:candidate['demand_kunits'][1],77:candidate['efficiency']}
    updates[19]=rounded[2]-updates[18]; updates[26]=rounded[3]-updates[25]
    decisions=[]
    reasons={9:'当期条件搜索',10:'当期条件搜索',18:'总营销优化；国别比例沿用当前，未识别国别边际作用',19:'总营销优化；国别比例沿用当前，未识别国别边际作用',25:'总营销优化；国别比例沿用当前',26:'总营销优化；国别比例沿用当前',
             49:'当期效率代理收益减运营费用；不含后续作用',51:'当期需求作用减研发费用；不含后续作用',42:'按需求、班次与边际贡献求解',34:'单位售价减运费排序',35:'单位售价减运费排序',58:'条件需求预测',59:'条件需求预测',77:'正式2技术尺度与正式3运营曲线迁移'}
    section=''; product=''
    for r in personal[2:]:
        i=r['row_index']
        # Archived context is cumulative; use row transitions to keep unique field semantics.
        if i in [9,13,18,21,25,29,34,37,41,42,46,49,51,54,58,61,65,69,73,77,80]:
            section={9:'售价',13:'售价',18:'一般营销',21:'一般营销',25:'设计师营销',29:'设计师营销',34:'物流',37:'物流',41:'产能分配',42:'产能分配',46:'投资',49:'运营',51:'研发',54:'融资',58:'需求预估',61:'需求预估',65:'市场增长预估',69:'连接件总市场需求预估',73:'下期需求增长预估',77:'效率预估',80:'利率预估'}[i]
        product=('连接件' if i in [13,14,15,21,22,29,30,31,37,38,43,47,52,61,62,69,70,74,78] else '复合梁' if i in [9,10,11,18,19,25,26,27,34,35,42,46,51,58,59,65,66,73,77] else '共同')
        value=updates.get(i,r['value'])
        try: changed=not math.isclose(float(value),number(i),abs_tol=1e-8)
        except (ValueError,TypeError): changed=str(value)!=r['value']
        unit='美元/单位' if section=='售价' else '千美元' if section in ['一般营销','设计师营销','研发','运营','融资'] else '千单位' if section in ['需求预估','投资','连接件总市场需求预估'] else '千单位/人' if section=='效率预估' else '%' if '增长' in section or section in ['产能分配','利率预估'] else '选择'
        reason=reasons.get(i,'保留当前值／未优化；跨期、现金流或对应机制未完整识别')
        if product=='连接件': reason='本期产能及库存为零，保持当前；投资下期生效，另列门槛情景'
        decisions.append(dict(key=f'row_{i}',section=section,product=product,label=r['label'],unit=unit,current=r['value'],suggested=value,changed=changed,reason=reason))
    assert len(decisions)==42 and len({r['key'] for r in decisions})==42
    connector=[]
    for efficiency in [16.,16.7,18.]:
        for shift in [1.,1.65,2.56]:
            for country,freight in zip(C,[.5,2.]):
                margin=27-14.2-freight-wage*shift/efficiency
                connector.append(dict(efficiency=efficiency,shift_multiplier=shift,country=country,unit_margin=margin,
                                      one_year_break_even_sellthrough_pct=100*1.1/margin))
    sources=[REG,DATA,CURRENT/'personal_rows.json',CURRENT/'tables.json',CURRENT/'verification.json',Path(__file__)]
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (OUT/'code_snapshot.py').write_bytes(Path(__file__).read_bytes())
    result=dict(status='FORMAL3_CONDITIONAL_NUMERICAL_CANDIDATE_NOT_SIX_ROUND_OPTIMUM',market=5,account='PYT',phase='formal',round=3,
                model='t3v1 + CONNECTOR_LIFECYCLE_V2',objective='当期收入−材料−工资−运费−裁员−研发−运营−营销−6050固定费，非净利润',
                parameter_names=['泰国售价','印尼售价','一般营销总额','设计师营销总额','研发','运营'],bounds=bounds,
                assumptions=['对手复用正式2价格和营销，previous_rd更新为正式2实际研发；本人上期研发800、运营750',
                             '复合梁行业总需求采用归档上期55.37/142.44，增长0%；7.5%是玩家预估，仅列敏感性',
                             '价格归一化沿用训练和t3v1示例的正式1参考价；营销是两国总额，国别比例未识别',
                             '无硬性用工上限，允许招聘；10%自然流失后多余员工按35%基础年薪裁员',
                             '正式2效率theta/rho迁移至正式3；运营及研发限正式3曲线范围；材料使用最新注册表选中的additive模型及正式3公布价',
                             '连接件本期零产能/零库存/零确认订单；投资下期生效；未据招标推定中标'],
                opening_state=state,current_parameters=baseline.tolist(),baseline=base,continuous_candidate=best,
                suggested_parameters=rounded.tolist(),candidate=candidate,sensitivity=sensitivity,reoptimized=reoptimized,
                local_sensitivity=local,decisions=decisions,connector_investment_threshold=connector,
                boundary_analysis=boundary_analysis,price_reference_analysis=anchor_analysis,material_unit_cost_usd=materials,
                budget_replay=dict(archived_budget_profit_kusd=4513,archived_budget_ebitda_kusd=8570,manual_ebitda_replay_kusd=manual_ebitda,display_rounding_tolerance_kusd=budget_tolerance,
                                  category='PLAYER_INPUT_CONDITIONAL_BUDGET_NOT_MODEL_FORECAST'),
                checks=dict(allocation_replay=True,production_conservation=True,field_count=42,two_seed_score_gap=abs(best['solvers'][0]['score']-best['solvers'][1]['score'])),
                sources=source_hashes,
                limits=['无正式3实际验证、无连接件真实标签；数值搜索不证明全局最优',
                        '未优化投资、融资、大客户投标及正式3至6累计利润；未来价格/需求/订单/终局价值未知',
                        '未算折旧、税、利息、营运资金及最低现金约束；不能据贡献决定还贷',
                        '未实时核验个人最新值或平台回合；未写入平台；历史预算4513不能与贡献直接相减'])
    save('result.json',result)
    with (OUT/'完整决策.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(decisions[0])); w.writeheader(); w.writerows(decisions)
    lines=['# 正式3条件最优候选与敏感性分析','',f'市场5、PYT；归档基准：2026-10-13 16:28至16:42，北京时间。运行：{OUT.name}。',
           '不要输出真名，姓名统一用首字母替代。未修改平台。',
           '', '**这是最新模型下、明确假设与搜索边界内的当期数值最优候选；不是正式3至6累计净利润最优。**',
           '',f'建议复合梁售价泰国 {rounded[0]:.0f}、印尼 {rounded[1]:.0f} 美元/单位；一般营销总额 {rounded[2]:.0f}、设计师营销总额 {rounded[3]:.0f}、研发 {rounded[4]:.0f}、运营 {rounded[5]:.0f} 千美元。',
           f'产能比例填写 {updates[42]:.1f}%（需求驱动下实际利用率 {candidate["allocation_pct"]:.3f}%）；优先 {candidate["priority"][0]}。模型需求 {candidate["demand_kunits"][0]:.3f}/{candidate["demand_kunits"][1]:.3f} 千单位；效率 {candidate["efficiency"]:.6f} 千单位/人。',
           '',f'同口径归档方案贡献 {base["score_kusd"]:.2f} → 候选 {candidate["score_kusd"]:.2f} 千美元，改善 {candidate["score_kusd"]-base["score_kusd"]:.2f}。此口径已扣研发、运营、营销、裁员、固定费6050，未扣折旧、税、利息，非完整净利润或现金流。',
           '',f'归档预算净利润4513千美元来自手填需求5.2/13.8、效率0.17，不能作为模型预测成绩。独立预算EBITDA回放 {manual_ebitda:.2f}，与显示8570的差额在由数量及成本显示精度计算的±{budget_tolerance:.2f}千美元容差内。',
           '', '当前连接件机器产能0、期初库存0。本期产量保持0；新增机器下期生效，不可把旧演示的80千单位当本队事实。',
           '', '## 完整42项输入（另2项预算摘要不作为决策）','', '| 分区 | 产品 | 字段 | 单位 | 当前 | 建议 | 调整 | 依据 |','|---|---|---|---|---:|---:|---|---|']
    for d in decisions:
        value=f'{d["suggested"]:.6g}' if isinstance(d['suggested'],(int,float)) else str(d['suggested'])
        lines.append(f'| {d["section"]} | {d["product"]} | {d["label"]} | {d["unit"]} | {d["current"]} | {value} | {"是" if d["changed"] else "否"} | {d["reason"]} |')
    lines+=['','## 敏感性：固定建议售价、投入及产能比例，每种情景按需求驱动重算产量和物流','',
            '| 情景 | 当期贡献，千美元 | 相对基准变化 | 产量，千单位 | 产能比例 |','|---|---:|---:|---:|---:|']
    lines += [f'| {r["label"]} | {r["score_kusd"]:.2f} | {r["delta_kusd"]:+.2f} | {r["production_kunits"]:.3f} | {r["allocation_pct"]:.2f}% |' for r in sensitivity]
    lines+=['','## 情景下重新优化','', '| 情景 | 泰国价格 | 印尼价格 | 一般营销 | 设计师营销 | 研发 | 运营 | 贡献，千美元 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    lines += ['| '+r['label']+' | '+' | '.join(f'{v:.1f}' for v in r['parameters'])+f' | {r["metrics"]["score_kusd"]:.2f} |' for r in reoptimized]
    lines+=['','## 解释与边界','', *['- '+a for a in result['assumptions']],
            '',f'售价搜索范围泰国{bounds[0][0]:.0f}–{bounds[0][1]:.0f}、印尼{bounds[1][0]:.0f}–{bounds[1][1]:.0f}，由正式2全部样本归一化范围确定。当前泰国6600超出该范围，基准按模型外推评分，需慎读。',
            f'一般/设计师营销总额上界2500/4300；研发上界{bounds[4][1]:.0f}，运营上界{bounds[5][1]:.2f}由有效投入曲线域约束。两个独立随机种子的最优值差{result["checks"]["two_seed_score_gap"]:.6f}千美元。',
            f'材料单价使用最新选中的additive经验模型：1053+{material_fit["parameter"]:.6f}={materials:.6f}美元；正式3迁移仍未经实际验证。',
            f'营销搜索上界扩为5000/8600的外推诊断：参数{[round(v,2) for v in boundary_analysis["parameters"]]}，贡献{boundary_analysis["metrics"]["score_kusd"]:.2f}千美元。此项超出训练范围，不替代推荐；证明主候选依赖已明确的边界。',
            f'把价格归一化参考改为正式2实际价格并重新搜索：参数{[round(v,2) for v in anchor_analysis["parameters"]]}，贡献{anchor_analysis["metrics"]["score_kusd"]:.2f}千美元。价格参考转换尚未正式3验证，此项作为结构敏感性。',
            '优化是条件目标下的数值搜索；当前投入的未来收益未计入，因此低研发/运营方案不自动适合四回合累计收益。营销按总额入模，不能把国别分配比例称为最优。',
            '', '## 连接件下期投资门槛','',
            '按售价27、材料14.2、工资30、效率16–18、三种班次测算；订单350千单位属于招标，不是确认销售。下表只给一年度经营毛贡献覆盖机器购置1.10的售出比例，假设可用销量等于新增产能×售出比例；未计营销、研发、融资、库存、税及机器残值。它不是投资推荐或完整回收期。',
            '', '| 国家 | 效率 | 班次乘数 | 单位边际贡献，美元 | 售出比例门槛 |','|---|---:|---:|---:|---:|']
    lines += [f'| {r["country"]} | {r["efficiency"]} | {r["shift_multiplier"]} | {r["unit_margin"]:.3f} | {r["one_year_break_even_sellthrough_pct"]:.2f}% |' for r in connector]
    lines += ['', *['- '+v for v in result['limits']], '', '来源哈希、连续解、整值方案、逐变量±10%敏感性及检查均保存在result.json；完整决策另存CSV。复现：项目Python运行work/optimize_formal3_known.py，每次创建新目录。']
    (OUT/'决策与敏感性分析.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==source_hashes[str(p.relative_to(ROOT))] for p in sources)
    with (OUT/'work_log.md').open('a',encoding='utf-8') as f:
        f.write('\n完成：读取最新冻结注册表、正式3完整个人列与产能/物流、正式2状态；条件优化及压力分析完成。公共分配回放、42字段完整性、预算算术及双种子检查通过。未修改原件、模型或平台；完整跨期最优未完成。\n')
    print(str(OUT),flush=True)


if __name__=='__main__':
    run()
