"""Let formal6 RD/operations vary independently, preserving frozen t5v2."""
import copy, hashlib, inspect, json, re, shutil, sys, textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'work')]
import numpy as np
from scipy.optimize import differential_evolution
import t5v2
import reoptimize_t5v2 as prior

SOURCE=prior.SOURCE
PREVIOUS=ROOT/'output/formal5_reoptimized_t5v2/20261015T205843819112+0800'
read=prior.read

def build_runtime(out):
    raw=textwrap.dedent(inspect.getsource(t5v2._BaseScenario.demand)).replace('def demand(', 'def demand_raw(')
    old="x[12+j] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.rdbase[j]"
    assert raw.count(old)==1
    raw=raw.replace(old,"cfg['_previous_rd'][j] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.rdbase[j]")
    evaluation=textwrap.dedent(inspect.getsource(t5v2._BaseScenario.evaluate))
    old="effective_investment(x[14], x[14] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.opsbase, self.investment_mapping['operations'])"
    assert evaluation.count(old)==1
    evaluation=evaluation.replace(old,"effective_investment(x[22] if t and cfg.get('future_mapping') != 'freeze_formal5' else x[14], x[14] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.opsbase, self.investment_mapping['operations'])")
    evaluation=evaluation.replace('spending = x[4:15].sum(axis=0)', 'spending = x[4:15].sum(axis=0) + (x[20:23].sum(axis=0) - x[12:15].sum(axis=0) if t else 0)')
    evaluation=evaluation.replace("periods[-1]['effective_rd_kusd'] = effective_investment(x[12:14], rd_previous, self.investment_mapping['rd'])[:, 0].tolist()", "periods[-1]['effective_rd_kusd'] = effective_investment(x[20:22] if t and cfg.get('future_mapping') != 'freeze_formal5' else x[12:14], rd_previous, self.investment_mapping['rd'])[:, 0].tolist()")
    evaluation=evaluation.replace("float(effective_investment(x[14], op_previous, self.investment_mapping['operations'])[0])", "float(effective_investment(x[22] if t and cfg.get('future_mapping') != 'freeze_formal5' else x[14], op_previous, self.investment_mapping['operations'])[0])")
    wrapper='''def demand(self, x, cfg, t):
    cfg = dict(cfg)
    cfg['_previous_rd'] = x[12:14]
    now = x[:20].copy()
    if t and cfg.get('future_mapping') != 'freeze_formal5':
        now[12:15] = x[20:23]
    mapping = cfg.pop('marketing_mapping', 'aggregate')
    cfg.pop('marketing_proxy', None)
    if mapping == 'aggregate':
        now[4:8] = x[4:8].sum(axis=0)
        now[8:12] = x[8:12].sum(axis=0)
    elif mapping == 'inferred_local':
        now[4:8] = x[4:8] * (self.general_total / self.local_general.ravel())[:, None]
        now[8:12] = x[8:12] * (self.designer_total / self.local_designer.ravel())[:, None]
    else:
        raise ValueError('Unknown marketing mapping')
    return demand_raw(self, now, cfg, t)
'''
    source='from t5v2 import *\n\n'+raw+'\n'+evaluation+'\n'+wrapper
    (out/'two_period_runtime.py').write_text(source,encoding='utf-8')
    ns=dict(vars(t5v2));exec(compile(source,str(out/'two_period_runtime.py'),'exec'),ns)
    return type('TwoPeriodModel',(t5v2.ApplicationModel,),{'evaluate':ns['evaluate'],'demand':ns['demand']})

def main():
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out=ROOT/'output/formal5_two_period_t5v2'/stamp;out.mkdir(parents=True,exist_ok=False)
    print('OUTPUT',out,flush=True)
    save=lambda name,v:(out/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (out/'work_log.md').write_text(f'# 正式5—6研发运营独立优化\n\n开始{stamp}，北京时间。进行中。用户要求考虑第6回合仍有研发和运营投入以及第5回合滞后作用。本次增加第6回合三项投入独立决策，重新联合求解第5回合全部已识别数值决策。复用归档，不访问或提交平台，不重采教程。继承未知机制限制。\n',encoding='utf-8')
    preserved={p.relative_to(ROOT).as_posix():prior.sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    preserved['code/model_v2/t5v2.py']=prior.sha(ROOT/'code/model_v2/t5v2.py');save('source_hashes.json',preserved)
    reg=read(SOURCE/'models_full.json');old=read(PREVIOUS/'full_result.json')
    cls=build_runtime(out);m=cls();m.__dict__.update(t5v2.decode(reg['application_state']));m.r={'risk':reg['risk']};m.current={int(k):v for k,v in m.current.items()}
    cfgs=reg['scenario_configs'];oldx=np.array(old['comparisons'][3]['x'])
    extended=lambda x:np.r_[x,x[12:15]]
    # Equality with the old policy must hold before searching the larger policy space.
    for p in old['comparisons']:
        for c,e in zip(cfgs,p['evaluations']):
            a=m.evaluate(extended(np.array(p['x'])),c,True)
            assert abs(a['profit_5_to_6']-e['profit_5_to_6'])<1e-8
    x0=extended(oldx);x0[4:8]=[sum(oldx[4:8]),0,0,0];x0[8:12]=[sum(oldx[8:12]),0,0,0]
    bounds=copy.deepcopy(m.bounds)+copy.deepcopy(m.bounds[12:15])
    for j in [5,6,7,9,10,11]:bounds[j]=[0,0]
    def objective(x):
        ev=[m.evaluate(x,c) for c in cfgs[:3]]
        return -np.min([e[0] for e in ev],axis=0)+np.max([e[2] for e in ev],axis=0)
    # First isolate future-policy improvement, keeping the prior formal5 decisions unchanged.
    def future_score(v):
        x=np.broadcast_to(x0[:,None],(23,v.shape[1])).copy();x[20:23]=v
        return objective(x)
    z=differential_evolution(future_score,bounds[20:23],seed=43,popsize=12,maxiter=500,tol=.00001,atol=.02,polish=False,vectorized=True,updating='deferred')
    fixed=x0.copy();fixed[20:23]=np.round(z.x)
    candidates=[x0,fixed];traces=[]
    for seed in [43,71]:
        z=differential_evolution(objective,bounds,seed=seed,popsize=12,maxiter=1400,tol=.00003,atol=.05,
            polish=False,vectorized=True,updating='deferred',integrality=[False]*15+[True,True,False,False,True]+[False]*3,x0=fixed)
        traces.append(dict(seed=seed,iterations=z.nit,converged=bool(z.success),score=-float(z.fun)))
        x=z.x.copy();x[:2]=np.round(x[:2]);x[2:4]=np.round(x[2:4],1);x[4:17]=np.round(x[4:17]);x[17:19]=np.round(x[17:19],1);x[19:]=np.round(x[19:]);candidates.append(x)
        save('searches.json',traces);print('SEARCH',seed,z.nit,z.success,-float(z.fun),flush=True)
    x=min(candidates,key=lambda v:float(objective(v)[0])).copy()
    for _ in range(20):
        changed=False
        for j,(lo,hi) in enumerate(bounds):
            if lo==hi:continue
            step=.1 if j in [2,3,17,18] else 1
            vals=[x[j],lo,hi]+[x[j]+s*step for s in [-100,-10,-1,1,10,100]]
            if j in [15,16,19]: vals=list(range(int(lo),int(hi)+1))
            vals=sorted(set(v for v in vals if lo<=v<=hi));trials=np.repeat(x[:,None],len(vals),axis=1);trials[j]=vals
            scores=objective(trials);ix=int(np.argmin(scores))
            if scores[ix]<float(objective(x)[0])-1e-8:x[j]=vals[ix];changed=True
        if not changed:break
    tie=x.copy();tie[17]=oldx[17]
    if abs(float(objective(tie)[0])-float(objective(x)[0]))<1e-8:x=tie
    assert float(objective(x)[0])<=float(objective(x0)[0])+1e-7
    for v in [x,fixed]:
        v[4:8]=prior.distribute(int(sum(v[4:8])),m.local_general.ravel());v[8:12]=prior.distribute(int(sum(v[8:12])),m.local_designer.ravel())
    plans=[]
    for name,v in [('原稳健：两期同投入',extended(oldx)),('原本期方案：仅优化下期投入',fixed),('两期联合稳健候选',x)]:
        ev=[dict(name=c['name'],**m.evaluate(v,c,True)) for c in cfgs]
        assert all(e['feasible'] for e in ev[:3])
        plans.append(dict(name=name,x=v.tolist(),evaluations=ev))
    save('full_result.json',dict(version='t5v2_two_period_policy',configs=cfgs,comparisons=plans,full_global_optimum=False))
    checks=0
    for plan in plans:
        v=np.array(plan['x'])
        for c,e in zip(cfgs,plan['evaluations']):
            assert e['balance_error_max']<1e-7 and e['quantity_error_max']<1e-8
            a,b=e['periods']
            assert np.allclose(a['effective_rd_kusd'],.75*v[12:14]+[450,650])
            if c.get('future_mapping')!='freeze_formal5':
                assert np.allclose(b['effective_rd_kusd'],.75*v[20:22]+.5*v[12:14])
                assert abs(b['effective_operations_kusd']-(v[22]+.35*v[14]))<1e-8
            assert abs(b['spending']-(sum(v[4:12])+sum(v[20:23])))<1e-8
            batch=m.evaluate(np.column_stack([v,v]),c)
            assert np.allclose(batch[0],e['profit_5_to_6']);checks+=1
    # An extra dollar in period6 must not alter period5, and period5 must carry to period6.
    test=x.copy();test[20]+=1
    a=m.evaluate(x,cfgs[0],True);b=m.evaluate(test,cfgs[0],True)
    assert a['periods'][0]==b['periods'][0]
    assert abs(b['periods'][1]['effective_rd_kusd'][0]-a['periods'][1]['effective_rd_kusd'][0]-.75)<1e-8
    test=x.copy();test[12]-=1;b=m.evaluate(test,cfgs[0],True)
    assert abs(b['periods'][1]['effective_rd_kusd'][0]-a['periods'][1]['effective_rd_kusd'][0]+.5)<1e-8
    save('validation.json',dict(status='PASS',old_policy_replays=64,new_policy_replays=checks,causal_carryover=True,period_costs_separate=True,scalar_batch_parity=True,platform_accessed=False))
    report(out,m,plans,cfgs,save)
    assert all(prior.sha(ROOT/p)==h for p,h in preserved.items())
    shutil.copy2(Path(__file__),out/Path(__file__).name)
    doc=ROOT/'README.md';shutil.copy2(doc,out/'README_before.md');before=prior.sha(doc);s=doc.read_text(encoding='utf-8');a=s.index('正式5最新决策分析：');b=s.index('\n\n',a)
    s=s[:a]+'正式5最新决策分析：[t5v2两期研发运营独立优化]('+out.relative_to(ROOT).as_posix()+'/report.md)。正式6研发两产品及运营独立求解，正式5投入按新有效投资映射影响正式6，重新联合优化本期已识别决策。原同投入策略保留为对照；仍为条件候选，未实时核对或填写平台。'+s[b:];doc.write_text(s,encoding='utf-8');save('document_changes.json',dict(before=before,after=prior.sha(doc)))
    with (out/'work_log.md').open('a',encoding='utf-8') as f:f.write('\n完成：两期三项投入独立搜索；64次原策略退化一致，48次新策略回放、跨期因果及分期费用自检、42字段顺序、财务数量恒等式、链接与源哈希通过。未验证回合6新曲线及历史存量，未提交平台。\n')
    save('manifest.json',{p.name:prior.sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'})
    print('COMPLETE',out,flush=True)
    print(json.dumps(plans[-1],ensure_ascii=False)[:1100],flush=True)

def report(out,m,plans,cfgs,save):
    fmt=lambda v:f'{v:,.6f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)
    oldfields={r['row']:r for r in read(PREVIOUS/'decisions.json') if r['plan']=='稳健利润候选'}
    plan=plans[-1];x=plan['x'];p=plan['evaluations'][0]['periods'][0]
    values={row:x[j]*(20 if row==47 else 100 if row==54 else 1) for j,row in enumerate(prior.ROWS)}
    values.update({58:p['demand'][0][0],59:p['demand'][0][1],61:p['demand'][1][0],62:p['demand'][1][1],65:7,66:-5,68:7,69:-5,72:0,73:0,76:p['efficiency'][0],77:p['efficiency'][1],79:p['rate']*100})
    for j,rows in enumerate([[34,35],[37,38]]):
        for k,row in enumerate(rows):values[row]='第一' if p['priority'][j]==k else '第二'
    records=[]
    for row in prior.ORDER:
        f=copy.deepcopy(oldfields[row]);v=values.get(row,m.current[row])
        if row in [58,59,61,62,79]:v=round(v,2)
        if row in [76,77]:v=round(v,6)
        f.update(plan=plan['name'],suggested=v,previous_recommendation=oldfields[row]['suggested'],changed=v!=m.current[row])
        if row in [51,52,49]:f['reason']='本期与下期投入分别求解；本期有效投资含历史项，下期有效投资含本期滞后项；名义费用分期计入'
        records.append(f)
    assert len(records)==42 and [r['row'] for r in records]==prior.ORDER;save('decisions.json',records)
    lines=['# t5v2：回合5和6的研发运营分别优化','',
        '应调整：原方案考虑了第5回合投入的下期作用，但把第6回合投入锁定为与本期相同。现在解除这三个等式，同时重新优化第5回合其他已识别经营变量。推荐以下两期联合稳健候选，仍是给定未来情景与范围内的部分优化结果。','',
        '当前值取2026-10-15 19:11市场5、正式5、个人PYT归档（19:46恢复核验）；本次不访问平台。原曲线及参数复用t5v2，无新训练。', '',
        '## 回合5完整填写建议','','推荐表按归档页面顺序列出。单独列出上一批稳健建议，供检查此次调整；归档当前不代表实时草稿。', '']
    byrow={r['row']:r for r in records}
    for title,rows in [('需求',prior.ORDER[:10]),('生产：投资与计划',prior.ORDER[10:20]),('销售：泰国、印尼与大客户',prior.ORDER[20:36]),('物流',prior.ORDER[36:40]),('财务',prior.ORDER[40:])]:
        lines+=['### '+title,'','| 字段／产品／国家 | 单位 | 归档当前 | 原稳健建议 | 两期联合建议 | 较当前调整 | 状态及依据 |','| --- | --- | ---: | ---: | ---: | --- | --- |']
        for row in rows:
            f=byrow[row];label='／'.join(str(f[k]) for k in ['section','product','label'] if f[k])
            lines.append(f'| {label} | {f["unit"]} | {fmt(f["current"])} | {fmt(f["previous_recommendation"])} | {fmt(f["suggested"])} | {"是" if f["changed"] else "否"} | {f["status"]}：{f["reason"]} |')
        lines.append('')
    lines+=['## 两期投入与有效投资','','单位千美元；第6回合计划在当前假设下求得，到时需用新曲线和实际状态重算。','',
        '| 项目 | 回合5实际支出 | 回合5有效投资 | 回合6实际支出计划 | 回合6有效投资 |','| --- | ---: | ---: | ---: | ---: |']
    a,b=plan['evaluations'][0]['periods']
    for j,name in enumerate(['复合梁研发','连接件研发','运营改进']):
        e5=a['effective_rd_kusd'][j] if j<2 else a['effective_operations_kusd'];e6=b['effective_rd_kusd'][j] if j<2 else b['effective_operations_kusd']
        lines.append(f'| {name} | {x[12+j]:,.0f} | {e5:,.2f} | {x[20+j]:,.0f} | {e6:,.2f} |')
    lines+=['','研发：E5=0.75R5+0.50R4，E6=0.75R6+0.50R5；运营：E5=O5+0.35O4，E6=O6+0.35O5。R4=900/1300，O4=750。第5回合支出既影响本期，也影响第6回合；第6回合支出只计剩余期限内效应，模型不赋予回合7收益。并非把第6回合投入机械设为零。','',
        '## 同期限对照','','金额千美元，正式5—6新增条件税后利润；三方案使用相同情景、边界和三核心最低现金3000约束。旧方案是同投入策略；中间方案只放开第6回合三项投入；新方案同时重新求解第5回合已识别决策。','','| 策略 | 中性利润 | COUNTRY利润 | 联合不利利润 | 三核心最低现金 | 本期贷款变化 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for q in plans:
        e=q['evaluations'];lines.append(f'| {q["name"]} | {e[0]["profit_5_to_6"]:,.2f} | {e[1]["profit_5_to_6"]:,.2f} | {e[2]["profit_5_to_6"]:,.2f} | {min(v["sampled_minimum_cash"] for v in e[:3]):,.2f} | {q["x"][19]*100:,.0f} |')
    lines+=['','推荐新方案的依据是三核心最低利润；得分差是模型条件结果，不代表实际收益保证。未计概率，故中性并非期望收益。','',
        '| 策略 | 回合5利润：中性／不利 | 回合6利润：中性／不利 | 回合5末库存梁／连接件（中性） | 回合6末库存梁／连接件（中性） |','| --- | ---: | ---: | ---: | ---: |']
    pair=lambda v:'／'.join(f'{z:,.2f}' for z in v)
    for q in plans:
        a,b=q['evaluations'][0]['periods'];c,d=q['evaluations'][2]['periods']
        lines.append(f'| {q["name"]} | {pair([a["profit"],c["profit"]])} | {pair([b["profit"],d["profit"]])} | {pair(a["closing_inventory"])} | {pair(b["closing_inventory"])} |')
    lines+=['','## 假设和未求解范围','',
        '- 三方案均使用t5v2冻结需求、效率及财务模型，正式5泰国+7%、印尼−5%；未来同曲线、同映射权重和历史归一化为假设。下期实际曲线和竞争变化未知。联合不利仍为市场0.9、竞争吸引力1.25、效率0.9、材料1.1、下期市场0.9/0.95、工资1.1及应收60天等。',
        '- 新增的仅是回合6两产品研发与运营三个独立控制，回合6其他价格和营销延续本期，生产仍观察需求后调整，机器和融资不新增。回合5的四个价格、两类营销合计、研发、运营、机器、配比及融资均重新搜索，物流按净价推导；不是完整回合6策略树最优。',
        '- 回合6研发和运营费用分别按其真实计划金额计入，未重复扣除历史投入。真实库存订单、税亏、财务期初及时点、自动短贷尚有机制缺口，沿用原条件模型；条件利润不能解释为已核真实净利润。',
        '- 营销8项细分仅识别两类合计，按现有构成分摊；招标4项和分包1项仍未求解、保留归档值，可能影响需求、成本、产能和利润。完整字段展示不等于全参数已求解。',
        '- 支持域沿用原版：研发每产品每期0—2600、运营每期0—1620；机器梁0—20、连接件0—400步长20；贷款−10200至10000步长100；一般营销合计≤2700、设计师≤3840；配比0—100%；价格在正式4正价历史支持域。触边不能解释为官方约束或全局最优。',
        '- 新有效投资映射仅与网页试验区间兼容；研发历史权重、运营历史截距及更早存量未独立识别。回合6采用新权重仍属迁移假设。机器本期生效、下期15%衰减，财务/成本公式同冻结版。最低现金只检查年末和投资融资后，不保证任意时点现金。', '',
        '## 全部压力情景','','| 情景 | 原同投入利润 | 仅调下期利润 | 两期联合利润 | 两期联合最低现金 | 约束通过 |','| --- | ---: | ---: | ---: | ---: | --- |']
    for i,c in enumerate(cfgs):
        ev=[q['evaluations'][i] for q in plans]
        lines.append('| '+c['name']+' | '+' | '.join(f'{e["profit_5_to_6"]:,.2f}' for e in ev)+f' | {ev[-1]["sampled_minimum_cash"]:,.2f} | {ev[-1]["feasible"]} |')
    lines+=['','仅前三核心情景进入约束；其余用于压力检查。冻结正式5有效投资情景将回合6响应固定在正式5坐标，但仍计回合6计划支出，是刻意的响应失效压力，不是基础映射。','',
        '## 验收与复现','','64组旧策略退化回放一致；48组新策略批量/标量、财务数量等式、费用分期、有效投资坐标检查通过。回合6投入变化不改变回合5；回合5研发每少1，下期有效投资减少0.5的因果检查通过。两新种子搜索及机器/融资离散档位局部检查通过，未穷举全局。运行：`python work/optimize_t5v2_two_period.py`。','',
        '[完整结果](full_result.json) · [42项决策](decisions.json) · [验收](validation.json) · [搜索](searches.json) · [两期运行代码](two_period_runtime.py) · [上版报告](../../formal5_reoptimized_t5v2/20261015T205843819112+0800/report.md)','',
        '未访问或填写平台；回合6曲线、营销细分及招标分包仍未独立验证。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    width=None
    for line in lines:
        if line.startswith('|'):
            n=len(line.split('|'));assert width is None or width==n; width=n
        else:width=None
    for link in re.findall(r'\]\(([^)]+)\)', '\n'.join(lines)):assert (out/link).resolve().exists(),link

if __name__=='__main__':main()
