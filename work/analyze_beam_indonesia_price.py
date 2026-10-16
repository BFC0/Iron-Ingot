"""Price profiles around 2759, preserving frozen two-period decision bundles."""
import copy, json, re, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'work')]
import numpy as np
import solve_t5v2_two_policies as q
import optimize_t5v2_two_period as two
import reoptimize_t5v2 as prior
import t5v2

BUNDLE=ROOT/'output/formal5_two_policies_t5v2/20261015T214235442505+0800'
read=prior.read

def main():
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out=ROOT/'output/beam_indonesia_price'/stamp;out.mkdir(parents=True,exist_ok=False)
    print('OUTPUT',out,flush=True)
    save=lambda name,v:(out/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    log=out/'work_log.md';log.write_text(f'# 印尼复合梁2759价格分析\n\n开始{stamp}，北京时间，进行中。用户要求分析2759是否过高。只读本地正式5数据和既有两期模型，不访问/填写平台、不重采教程。分别比较两期同价敏感性、仅第5回合调价及固定价格后其余决策重优化；未知机制保留。\n',encoding='utf-8')
    hashes={p.relative_to(ROOT).as_posix():prior.sha(p) for p in BUNDLE.rglob('*') if p.is_file()}
    hashes['code/model_v2/t5v2.py']=prior.sha(ROOT/'code/model_v2/t5v2.py');save('source_hashes.json',hashes)
    reg=read(prior.SOURCE/'models_full.json');result=read(BUNDLE/'full_result.json');cfgs=result['configs']
    cls=two.build_runtime(out);m=cls();m.__dict__.update(t5v2.decode(reg['application_state']));m.r={'risk':reg['risk']};m.current={int(k):v for k,v in m.current.items()}
    x=np.array(result['comparisons'][1]['x']);robust=np.array(result['comparisons'][2]['x'])
    for p in result['comparisons']:
        for c,e in zip(cfgs,p['evaluations']):assert abs(m.evaluate(p['x'],c,True)['profit_5_to_6']-e['profit_5_to_6'])<1e-8
    # Keep formal6 prices fixed when isolating a formal5-only price change.
    source=(out/'two_period_runtime.py').read_text(encoding='utf-8')
    assert source.count('    for t in range(2):')==1
    source=source.replace('    for t in range(2):',"    for t in range(2):\n        prices = np.broadcast_to(np.asarray(cfg['_future_prices'])[:, None], (4, n)).reshape(2, 2, n) if t and '_future_prices' in cfg else x[:4].reshape(2, 2, n)")
    source=source.replace('    now = x[:20].copy()',"    now = x[:20].copy()\n    if t and '_future_prices' in cfg:\n        now[:4] = np.asarray(cfg['_future_prices'])[:, None]")
    (out/'price_isolation_runtime.py').write_text(source,encoding='utf-8')
    ns=dict(vars(t5v2));exec(compile(source,str(out/'price_isolation_runtime.py'),'exec'),ns)
    isolate=type('PriceIsolation',(t5v2.ApplicationModel,),{'evaluate':ns['evaluate'],'demand':ns['demand']})()
    isolate.__dict__.update(m.__dict__)
    sweep=[]
    for price in [2180,2300,2400,2500,2600,2666,2700,2759,2800,2900,3000,3100]:
        z=x.copy();z[1]=price
        ev=[m.evaluate(z,c,True) for c in cfgs[:3]]
        one=isolate.evaluate(z,dict(cfgs[0],_future_prices=x[:4].tolist()),True)
        a,b=ev[0]['periods']
        row=dict(price=price,demand5_indonesia=a['demand'][0][1],sales5_indonesia=a['sales'][0][1],
            revenue5_indonesia=price*a['sales'][0][1],production5_beam=a['production'][0],
            profit5=a['profit'],profit6=b['profit'],profit56=ev[0]['profit_5_to_6'],
            profit_country=ev[1]['profit_5_to_6'],profit_adverse=ev[2]['profit_5_to_6'],
            minimum_core_cash=min(e['sampled_minimum_cash'] for e in ev),core_feasible=all(e['feasible'] for e in ev),
            profit56_only5_price=one['profit_5_to_6'],only5_period6_indonesia_price=2759)
        assert one['periods'][0]==ev[0]['periods'][0]
        sweep.append(row)
    save('price_sweep.json',sweep)
    # Dense profiles distinguish a sharp optimum from a flat, practically equivalent band.
    grid=np.arange(2200,3101,dtype=float);batch=np.repeat(x[:,None],len(grid),axis=1);batch[1]=grid
    profiles={}
    for c in [cfgs[0],cfgs[1],cfgs[2],dict(cfgs[0],price_elasticity=1.2,name='价格弹性增强20%')]:
        profits,cash,penalty=m.evaluate(batch,c)
        best=int(np.argmax(profits));valid=np.where(penalty<1e-6)[0]
        near=grid[profits>=profits[best]-10]
        profiles[c['name']]=dict(best_fixed_other_price=int(grid[best]),best_profit=float(profits[best]),
            within_10_kusd_range=[int(near[0]),int(near[-1])],
            best_feasible_price=int(grid[valid[np.argmax(profits[valid])]]) if len(valid) else None)
    save('dense_profiles.json',profiles)
    history=read(ROOT/'output/round_close/20261014_formal4_close/raw/market5_formal4_marketdetails.json')['tables'][0][4]
    historical=[float(str(v).replace('\xa0','').replace(' ','')) for v in history[1:] if str(v).strip()]
    c0=cfgs[0];a=m.evaluate(x,c0,True)['periods'][0]
    market_total=m.totals[0,1]*.95;share=a['demand'][0][1]/market_total
    elasticity=float(m.beta['SHARE'][0,1,1]*(1-share))
    plus=x.copy();minus=x.copy();plus[1]+=.1;minus[1]-=.1
    ep=m.evaluate(plus,c0,True)['periods'][0];em=m.evaluate(minus,c0,True)['periods'][0]
    numerical=-(np.log(ep['demand'][0][1])-np.log(em['demand'][0][1]))/(np.log(plus[1])-np.log(minus[1]))
    assert abs(elasticity-numerical)<1e-7
    history_info=dict(formal4_market5_indonesia_prices=historical,median=float(np.median(historical)),min=min(historical),max=max(historical),
        price_increase_vs_archived_current=2759/2180-1,price_increase_vs_historical_median=2759/float(np.median(historical))-1,
        formal5_competitor_prices_known=False,formal5_neutral_elasticity_at_2759=elasticity,
        model_high_price_kink=3000,model_price_support=m.bounds[1])
    save('historical_comparison.json',history_info)
    print('SWEEP',json.dumps(sweep,ensure_ascii=False),flush=True)
    alternatives=[];traces=[]
    for price in [2500,2666,2700,2800]:
        bounds=copy.deepcopy(result['search_bounds']);bounds[1]=[price,price]
        initial=x.copy();initial[1]=price;initial[4:8]=[sum(x[4:8]),0,0,0];initial[8:12]=[sum(x[8:12]),0,0,0]
        z,trace=q.solve(m,cfgs,bounds,initial,[0],out)
        alternatives.append(dict(name=f'固定印尼梁价格{price}条件中性候选',x=z.tolist(),evaluations=[dict(name=c['name'],**m.evaluate(z,c,True)) for c in cfgs]))
        traces.extend([dict(fixed_price=price,**r) for r in trace]);save('joint_price_profiles.json',alternatives);save('searches.json',traces)
        print('FIXED_PRICE_DONE',price,alternatives[-1]['evaluations'][0]['profit_5_to_6'],flush=True)
    fields={r['row']:r for r in read(BUNDLE/'decisions.json') if r['plan']=='中性联合候选'}
    records=[r for p in alternatives for r in q.decision_records(m,p,fields)]
    save('alternative_decisions.json',records)
    checks=0
    for p in alternatives:
        assert len({r['row'] for r in records if r['plan']==p['name']})==42
        for e in p['evaluations']:
            assert e['balance_error_max']<1e-7 and e['quantity_error_max']<1e-8;checks+=1
        assert all(e['feasible'] for e in p['evaluations'][:3])
    save('validation.json',dict(status='PASS',source_replays=48,alternative_replays=checks,alternative_fields=168,
        isolated_period5_sales_and_costs=True,analytical_numerical_elasticity_parity=True,platform_accessed=False))
    report(out,m,result,sweep,profiles,history_info,alternatives,records)
    assert all(prior.sha(ROOT/p)==h for p,h in hashes.items())
    shutil.copy2(Path(__file__),out/Path(__file__).name)
    with log.open('a',encoding='utf-8') as f:f.write('\n完成：12点两期同价与本期单独调价对照，901点价格剖面，4个价格约束下的其余变量联合搜索，168字段完整候选、数值导数、财务数量恒等式、链接和原模型哈希通过。未访问平台；本回合竞争队真实价格未知，弹性迁移及营销代理限制保留。\n')
    save('manifest.json',{p.name:prior.sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'})
    print('COMPLETE',out,flush=True)

def report(out,m,result,sweep,profiles,history,alternatives,records):
    base=next(r for r in sweep if r['price']==2759)
    lines=['# 印尼复合梁2759美元：价格风险与利润分析','',
        '2759在当前中性模型中接近利润最优，但相对本市场历史价格明显偏高，属于积极定价，不能据此认定实际市场一定接受。稳健候选2666提供风险偏好不同的参照，不应把它当作单独降价后仍保持其余中性决策的完整替代。','',
        '使用正式5 t5v2两期独立投入模型及已归档数据；个人PYT基准2026-10-15 19:11、19:46恢复核验。本次未实时读平台；当前正式5竞争队价格未知。以下均为条件预测，非实际成绩或已核平台预算。','',
        '## 价格位置和模型依据','',
        f'- 相对归档本人2180，提高{history["price_increase_vs_archived_current"]*100:.2f}%。正式4本市场10队印尼梁价格范围{history["min"]:,.0f}—{history["max"]:,.0f}，中位{history["median"]:,.0f}；2759较中位高{history["price_increase_vs_historical_median"]*100:.2f}%。这是历史参照，不是回合5实时竞价。',
        '- 全市场历史分析支持域为1888—6025，2759在全局支持域内，但超过本市场正式4的最高价；统计支持域不能证明本市场接受程度。',
        f'- 模型在2759附近估计印尼梁需求价格弹性约{history["formal5_neutral_elasticity_at_2759"]:.3f}：售价提高1%约减少{history["formal5_neutral_elasticity_at_2759"]:.2f}%需求（局部估计）。这是有弹性需求，不意味着涨价可无损增加收入。',
        '- 优化目标为利润而非销量/收入。降价增加需求，也增加材料、人工和运费；在两期投入、产能和库存约束下，较低售价未必增加净利润。模型还在印尼梁3000设置历史分段价格惩罚，2759低于此点；3000是拟合断点，不是官方最高价。','',
        '## 只改变该价格：其余中性经营决策保持不变','',
        '下表该售价同时用于第5和第6回合，与原优化政策一致；研发、运营、其他价格、营销、机器与贷款均保持中性方案，需求/效率/现金自动重算。利润为全公司正式5—6合计千美元，需求与销量千单位，价格美元。','',
        '| 印尼梁价格 | 第5回合印尼需求 | 第5回合印尼销量 | 印尼梁第5回合收入 | 两回合中性利润 | 较2759利润差 | 联合不利利润 | 三核心最低现金 | 约束通过 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for r in sweep:
        lines.append(f'| {r["price"]} | {r["demand5_indonesia"]:.3f} | {r["sales5_indonesia"]:.3f} | {r["revenue5_indonesia"]:,.2f} | {r["profit56"]:,.2f} | {r["profit56"]-base["profit56"]:+,.2f} | {r["profit_adverse"]:,.2f} | {r["minimum_core_cash"]:,.2f} | {r["core_feasible"]} |')
    lines+=['','低价导致约束失败时，不代表平台禁止该价格，而是原中性贷款及其他支出不配套，模型现金不满足3000要求；下节重优化会允许调整。','',
        '| 同一价格仅修改第5回合 | 两回合利润差：相对2759 |','| --- | ---: |']
    for r in sweep:
        lines.append(f'| {r["price"]} | {r["profit56_only5_price"]-base["profit56_only5_price"]:+,.2f} |')
    lines+=['','上表第6回合印尼售价固定2759，其余未来政策也保持原定。第5回合产销、现金及库存结转仍会影响第6回合，因此不是只计算当期售价差额。','',
        '## 固定该价格后，允许其他决策配合重优化','',
        '统一中性目标、正式5—6期限及三核心最低现金3000约束；两期研发运营独立，其他条件与原两期中性一致。结果是条件搜索候选，非价格本身的纯因果效应。','',
        '| 价格约束 | 两回合中性利润 | 较原2759方案 | 联合不利利润 | 三核心最低现金 | 第5回合贷款变化 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for p in alternatives:
        e=p['evaluations'];lines.append(f'| {p["x"][1]:,.0f} | {e[0]["profit_5_to_6"]:,.2f} | {e[0]["profit_5_to_6"]-base["profit56"]:+,.2f} | {e[2]["profit_5_to_6"]:,.2f} | {min(v["sampled_minimum_cash"] for v in e[:3]):,.2f} | {p["x"][19]*100:,.0f} |')
    lines+=['','## 弹性及模型选择风险','','下表只重算价格，仍用同一中性经营方案。各情景最优价格在2200—3100逐美元扫描，不是全方案再次求解。','',
        '| 响应情景 | 固定其他变量时最高利润价格 | 最高利润 | 距该情景最高利润不超过10千美元的价格区间 |','| --- | ---: | ---: | --- |']
    for name,p in profiles.items():lines.append(f'| {name} | {p["best_fixed_other_price"]} | {p["best_profit"]:,.2f} | {p["within_10_kusd_range"][0]}—{p["within_10_kusd_range"][1]} |')
    lines+=['','2759不是具有个位数精度的真实最优价格：不同需求响应、竞争和工资材料情景会改变它。正式4竞争队真实营销/研发细分缺失，需求锚定、公司费用代理和历史曲线归一化仍有误差；其他市场高价样本不能替代本市场的独立验证。','',
        '## 使用结论','','- 若沿用中性模型与整套中性方案，2759有模型依据；不宜仅因高于上期价格而直接判为错误。',
        '- 若更重视本市场历史价差与需求误差，应比较2666—2700附近的完整配套候选以及既有稳健方案；不能只换价格而沿用原需求预估、贷款及支出。',
        '- 未来竞争队真实定价未知，暂无法给出实际市场可接受最高价。现场预算仍依赖手填需求，不能将预算利润上升当作真实销量验证。','',
        '[原两类完整建议](../../formal5_two_policies_t5v2/20261015T214235442505+0800/report.md) · [原始价格对照](price_sweep.json) · [固定价格重优化结果](joint_price_profiles.json) · [全部条件候选字段](alternative_decisions.json) · [验收](validation.json)','',
        '## 条件候选完整字段（用于复核，不代表已选用新方案）','',
        '共同假设与边界同原两期报告：第6回合同价格营销、独立研发运营、同曲线和映射、无新机器融资；三核心现金≥3000。价格、材料、工资、库存、税、财务时序及终局政策均沿用t5v2条件模型，真实订单税亏等缺口未补齐。营销细分、招标及分包仍未求解。每个价格约束候选都比较中性利润而非稳健最差利润；物流按净价推导，全部预估按方案一致重算。','']
    fmt=lambda v:f'{v:,.6f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)
    for p in alternatives:
        byrow={r['row']:r for r in records if r['plan']==p['name']}
        lines+=['### '+p['name'],'']
        for title,rows in [('需求',prior.ORDER[:10]),('生产',prior.ORDER[10:20]),('销售',prior.ORDER[20:36]),('物流',prior.ORDER[36:40]),('财务',prior.ORDER[40:])]:
            lines+=['#### '+title,'','| 字段／产品／国家 | 单位 | 归档当前 | 条件建议 | 是否调整 | 状态及依据 |','| --- | --- | ---: | ---: | --- | --- |']
            for row in rows:
                f=byrow[row];label='／'.join(str(f[k]) for k in ['section','product','label'] if f[k]);status='给定价格条件' if row==10 else f['status']
                lines.append(f'| {label} | {f["unit"]} | {fmt(f["current"])} | {fmt(f["suggested"])} | {"是" if f["changed"] else "否"} | {status}：{f["reason"]} |')
            lines.append('')
        lines.append('第6回合研发梁／连接件、运营（千美元）：'+ '／'.join(fmt(v) for v in p['x'][20:23])+'。')
        lines.append('')
    lines+=['未访问或填写平台；未验证正式5实时竞争价格及正式6真实响应，不能称全参数最优。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    width=None
    for line in lines:
        if line.startswith('|'):
            n=len(line.split('|'));assert width is None or width==n;width=n
        else:width=None
    for link in re.findall(r'\]\(([^)]+)\)','\n'.join(lines)):assert (out/link).resolve().exists(),link

if __name__=='__main__':main()
