"""Neutral and maximin joint formal5/6 policies with frozen t5v2 coefficients."""
import copy, csv, json, re, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'work')]
import numpy as np
from scipy.optimize import differential_evolution
import optimize_t5v2_two_period as two
import reoptimize_t5v2 as prior
import t5v2

SOURCE=prior.SOURCE
PREVIOUS=ROOT/'output/formal5_two_period_t5v2/20261015T213516664688+0800'
read=prior.read

def solve(m,cfgs,bounds,start,objective_indices,out):
    def score(x):
        ev=[m.evaluate(x,c) for c in cfgs[:3]]
        return -np.min([ev[i][0] for i in objective_indices],axis=0)+np.max([e[2] for e in ev],axis=0)
    def round_decision(x):
        x=x.copy();x[:2]=np.round(x[:2]);x[2:4]=np.round(x[2:4],1)
        x[4:17]=np.round(x[4:17]);x[17:19]=np.round(x[17:19],1);x[19:]=np.round(x[19:])
        return x
    def future_score(v):
        x=np.broadcast_to(start[:,None],(23,v.shape[1])).copy();x[20:23]=v
        return score(x)
    z=differential_evolution(future_score,bounds[20:23],seed=101,popsize=12,maxiter=500,tol=.00001,atol=.02,
        polish=False,vectorized=True,updating='deferred')
    warm=start.copy();warm[20:23]=np.round(z.x)
    candidates=[start,warm];trace=[]
    for seed in [101,137]:
        z=differential_evolution(score,bounds,seed=seed,popsize=14,maxiter=1600,tol=.00002,atol=.03,polish=False,
            vectorized=True,updating='deferred',integrality=[False]*15+[True,True,False,False,True]+[False]*3,x0=warm)
        candidates.append(round_decision(z.x));trace.append(dict(seed=seed,iterations=z.nit,converged=bool(z.success),score=-float(z.fun),x=z.x.tolist()))
        print('SEARCH',objective_indices,seed,z.nit,z.success,-float(z.fun),flush=True)
    x=min(candidates,key=lambda v:float(score(v)[0])).copy()
    for _ in range(25):
        changed=False
        for j,(lo,hi) in enumerate(bounds):
            if lo==hi:continue
            step=.1 if j in [2,3,17,18] else 1
            vals=[x[j],lo,hi]+[x[j]+s*step for s in [-100,-10,-1,1,10,100]]
            if j in [15,16,19]:vals=list(range(int(lo),int(hi)+1))
            vals=sorted(set(v for v in vals if lo<=v<=hi))
            trials=np.repeat(x[:,None],len(vals),axis=1);trials[j]=vals;scores=score(trials);ix=int(np.argmin(scores))
            if scores[ix]<float(score(x)[0])-1e-8:x[j]=vals[ix];changed=True
        if not changed:break
    tie=x.copy();tie[17]=start[17]
    if abs(float(score(tie)[0])-float(score(x)[0]))<1e-8:x=tie
    assert float(score(x)[0])<=float(score(start)[0])+1e-7
    x=round_decision(x)
    x[4:8]=prior.distribute(int(sum(x[4:8])),m.local_general.ravel())
    x[8:12]=prior.distribute(int(sum(x[8:12])),m.local_designer.ravel())
    assert all(m.evaluate(x,c,True)['feasible'] for c in cfgs[:3])
    return x,trace

def decision_records(m,plan,fields):
    x=plan['x'];p=plan['evaluations'][0]['periods'][0]
    values={row:x[j]*(20 if row==47 else 100 if row==54 else 1) for j,row in enumerate(prior.ROWS)}
    values.update({58:p['demand'][0][0],59:p['demand'][0][1],61:p['demand'][1][0],62:p['demand'][1][1],65:7,66:-5,68:7,69:-5,72:0,73:0,76:p['efficiency'][0],77:p['efficiency'][1],79:p['rate']*100})
    for j,rows in enumerate([[34,35],[37,38]]):
        for k,row in enumerate(rows):values[row]='第一' if p['priority'][j]==k else '第二'
    records=[]
    for row in prior.ORDER:
        f=copy.deepcopy(fields[row]);v=values.get(row,m.current[row])
        if row in [58,59,61,62,79]:v=round(v,2)
        if row in [76,77]:v=round(v,6)
        f.update(plan=plan['name'],current=m.current[row],suggested=v,changed=v!=m.current[row])
        f.pop('previous_recommendation',None)
        if row in [51,52]:f.update(status='两期联合求解',reason='E5=0.75R5+0.50R4；E6=0.75R6+0.50R5；两期研发分别求解，费用分期计入')
        elif row==49:f.update(status='两期联合求解',reason='E5=O5+0.35O4；E6=O6+0.35O5；两期运营分别求解，费用分期计入')
        elif row in [34,35,37,38]:f['reason']='按本方案两国净售价排序，较高者优先；供应不足时影响实际销售'
        elif row in [76,77,79,58,59,61,62]:f['reason']='使用本方案决策和中性情景一致重算，预估值不作为利润优化变量'
        records.append(f)
    return records

def main():
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out=ROOT/'output/formal5_two_policies_t5v2'/stamp;out.mkdir(parents=True,exist_ok=False)
    print('OUTPUT',out,flush=True)
    save=lambda name,v:(out/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    log=out/'work_log.md';log.write_text(f'# 中性与稳健两期联合求解\n\n开始{stamp}（北京时间），进行中。用户要求基于两期研发运营独立投入生成中性、稳健建议。授权范围为本地计算与报告，不填写或提交平台。训练数据无新增，本次冻结模型系数、重新联合优化控制参数，不冒称统计重训。复用市场5正式5 19:11归档、19:46恢复核验及已有600点曲线；未实时核对回合或本人输入，不重复采集教程。\n',encoding='utf-8')
    source_hashes={p.relative_to(ROOT).as_posix():prior.sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    for file in ['code/model_v2/t5v2.py','work/optimize_t5v2_two_period.py']:
        source_hashes[file]=prior.sha(ROOT/file)
    save('source_hashes.json',source_hashes)
    reg=read(SOURCE/'models_full.json');old=read(prior.ROOT/'output/formal5_reoptimized_t5v2/20261015T205843819112+0800/full_result.json')
    previous=read(PREVIOUS/'full_result.json')
    cls=two.build_runtime(out);m=cls();m.__dict__.update(t5v2.decode(reg['application_state']));m.r={'risk':reg['risk']};m.current={int(k):v for k,v in m.current.items()}
    cfgs=reg['scenario_configs'];bounds=copy.deepcopy(m.bounds)+copy.deepcopy(m.bounds[12:15])
    for j in [5,6,7,9,10,11]:bounds[j]=[0,0]
    for p in previous['comparisons']:
        for c,e in zip(cfgs,p['evaluations']):assert abs(m.evaluate(p['x'],c,True)['profit_5_to_6']-e['profit_5_to_6'])<1e-8
    traces=[];new=[]
    for name,indices,initial in [('中性联合候选',[0],np.r_[old['comparisons'][1]['x'],old['comparisons'][1]['x'][12:15]]),
                                  ('稳健联合候选',[0,1,2],np.array(previous['comparisons'][-1]['x']))]:
        initial[4:8]=[sum(initial[4:8]),0,0,0];initial[8:12]=[sum(initial[8:12]),0,0,0]
        x,trace=solve(m,cfgs,bounds,initial,indices,out)
        traces.extend([dict(objective=name,**v) for v in trace]);save('searches.json',traces)
        new.append(dict(name=name,x=x.tolist(),evaluations=[dict(name=c['name'],**m.evaluate(x,c,True)) for c in cfgs]))
        save('candidates.json',new);print('WINNER',name,x.tolist(),flush=True)
    baseline=np.r_[m.baseline,m.baseline[12:15]]
    base=dict(name='归档当前／下期同投入',x=baseline.tolist(),evaluations=[dict(name=c['name'],**m.evaluate(baseline,c,True)) for c in cfgs])
    plans=[base,*new]
    save('full_result.json',dict(version='t5v2_two_policies',coefficient_training=False,decision_parameters_reoptimized=True,
        start_round=5,end_round=6,configs=cfgs,comparisons=plans,search_bounds=bounds,full_global_optimum=False))
    fields={r['row']:r for r in read(PREVIOUS/'decisions.json')}
    records=[r for p in new for r in decision_records(m,p,fields)]
    assert len(records)==84
    for p in new:
        rr=[r for r in records if r['plan']==p['name']]
        assert [r['row'] for r in rr]==prior.ORDER and len({r['key'] for r in rr})==42
    save('decisions.json',records)
    with (out/'decisions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    checks=0
    for plan in plans:
        x=np.array(plan['x'])
        for c,e in zip(cfgs,plan['evaluations']):
            assert e['balance_error_max']<1e-7 and e['quantity_error_max']<1e-8
            a,b=e['periods'];assert np.allclose(a['effective_rd_kusd'],.75*x[12:14]+[450,650])
            assert abs(a['effective_operations_kusd']-x[14]-262.5)<1e-8
            if c.get('future_mapping')!='freeze_formal5':
                assert np.allclose(b['effective_rd_kusd'],.75*x[20:22]+.5*x[12:14])
                assert abs(b['effective_operations_kusd']-x[22]-.35*x[14])<1e-8
            assert abs(a['spending']-sum(x[4:15]))<1e-8
            assert abs(b['spending']-sum(x[4:12])-sum(x[20:23]))<1e-8
            assert np.allclose(m.evaluate(np.column_stack([x,x]),c)[0],e['profit_5_to_6']);checks+=1
        for j,carry in [(12,.5),(13,.5),(14,.35)]:
            z=x.copy();z[j]-=1;e=m.evaluate(z,cfgs[0],True)
            a=m.evaluate(x,cfgs[0],True)['periods'][1];b=e['periods'][1]
            av=a['effective_rd_kusd'][j-12] if j<14 else a['effective_operations_kusd'];bv=b['effective_rd_kusd'][j-12] if j<14 else b['effective_operations_kusd']
            assert abs(av-bv-carry)<1e-8
        z=x.copy();z[20]+=1;assert m.evaluate(z,cfgs[0],True)['periods'][0]==m.evaluate(x,cfgs[0],True)['periods'][0]
    assert new[0]['evaluations'][0]['profit_5_to_6']>=old['comparisons'][1]['evaluations'][0]['profit_5_to_6']-1e-7
    assert min(e['profit_5_to_6'] for e in new[1]['evaluations'][:3])>=min(e['profit_5_to_6'] for e in previous['comparisons'][-1]['evaluations'][:3])-1e-7
    save('validation.json',dict(status='PASS',old_policy_replays=48,new_policy_replays=checks,decision_fields=84,
        scalar_batch_parity=True,causal_carryover=True,separate_period_costs=True,both_core_feasible=True,
        coefficient_training=False,platform_accessed=False,full_global_optimum=False))
    report(out,m,plans,cfgs,records,old,previous)
    assert all(prior.sha(ROOT/p)==h for p,h in source_hashes.items())
    shutil.copy2(Path(__file__),out/Path(__file__).name)
    doc=ROOT/'README.md';shutil.copy2(doc,out/'README_before.md');before=prior.sha(doc);text=doc.read_text(encoding='utf-8');a=text.index('正式5最新决策分析：');b=text.index('\n\n',a)
    text=text[:a]+'正式5最新决策分析：[t5v2两期联合中性与稳健建议]('+out.relative_to(ROOT).as_posix()+'/report.md)。本期已识别经营决策与下期研发、运营独立联合求解，输出中性和稳健两套各42项建议，统一比较5—6条件收益、现金与压力。冻结统计模型系数，无新增训练标签；正式6迁移及未求解机制仍有假设，未填写平台。'+text[b:]
    doc.write_text(text,encoding='utf-8');save('document_changes.json',{'README.md':dict(before=before,after=prior.sha(doc))})
    assert (ROOT/re.search(r'正式5最新决策分析：\[[^]]+\]\(([^)]+)\)',text)[1]).exists()
    with log.open('a',encoding='utf-8') as f:f.write('\n完成：中性及稳健各两随机种子搜索、显示步长及机器贷款离散检查；84字段、48旧策略/48新策略回放、跨期因果、费用分期、批量标量、财务数量恒等式、链接及源哈希验收通过。两期投入单独决策，未重训统计系数，未访问平台。未求解营销细分、招标分包及完整第6回合策略。\n')
    save('manifest.json',{p.name:prior.sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'})
    print('COMPLETE',out,flush=True)

def report(out,m,plans,cfgs,records,old,previous):
    fmt=lambda v:f'{v:,.6f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)
    lines=['# 正式5—6：中性与稳健两期联合建议','',
        '本报告分别求解中性与稳健两套决策。两期研发、运营投入独立，第5回合已识别经营变量同时重搜；使用新的投入→有效投资映射。推荐优先用稳健候选作平台预算核验，仍存在联合不利亏损。','',
        '此次“联合训练”落实为控制参数联合优化。没有新增实际训练标签，需求、效率、材料及风险模型系数继续冻结t5v2，不将重新搜索冒称为统计模型重训。','',
        '数据基准：市场5、正式5、个人PYT，当前取2026-10-15 19:11归档、19:46恢复核验；本次未实时访问或填写平台。前景、参数与600个曲线点沿用正式5归档。','',
        '## 回合5完整填写建议','','按归档决策页顺序列出。两套方案的需求、效率、利率都按各自决策及中性情景重算；稳健优化的三核心压力另表，不靠修改预估美化预算。','']
    maps=[{r['row']:r for r in records if r['plan']==p['name']} for p in plans[1:]]
    for title,rows in [('需求',prior.ORDER[:10]),('生产：投资与计划',prior.ORDER[10:20]),('销售：泰国、印尼与大客户',prior.ORDER[20:36]),('物流',prior.ORDER[36:40]),('财务',prior.ORDER[40:])]:
        lines+=['### '+title,'','| 字段／产品／国家 | 单位 | 归档当前 | 中性建议 | 稳健建议 | 调整：中性／稳健 | 状态及依据 |','| --- | --- | ---: | ---: | ---: | --- | --- |']
        for row in rows:
            a,b=[d[row] for d in maps];label='／'.join(str(b[k]) for k in ['section','product','label'] if b[k])
            lines.append(f'| {label} | {b["unit"]} | {fmt(b["current"])} | {fmt(a["suggested"])} | {fmt(b["suggested"])} | {"是" if a["changed"] else "否"}／{"是" if b["changed"] else "否"} | {b["status"]}：{b["reason"]} |')
        lines.append('')
    lines+=['[各方案完整字段与依据JSON](decisions.json) · [填写CSV](decisions.csv)','',
        '## 两期研发与运营计划','','金额千美元。第6回合金额为当前假设下的预案，不能提前当作已核平台决策。','',
        '| 项目 | 中性：第5回合 | 中性：第6回合 | 稳健：第5回合 | 稳健：第6回合 |','| --- | ---: | ---: | ---: | ---: |']
    a,b=[p['x'] for p in plans[1:]]
    for j,name in enumerate(['复合梁研发','连接件研发','运营改进']):lines.append(f'| {name} | {a[12+j]:,.0f} | {a[20+j]:,.0f} | {b[12+j]:,.0f} | {b[20+j]:,.0f} |')
    lines+=['','研发E5=0.75R5+0.50R4，E6=0.75R6+0.50R5；运营E5=O5+0.35O4，E6=O6+0.35O5。R4为900/1300、O4为750。成本现金各期只扣本期实际支出，不重复扣历史投入；截止第6回合，不赋予第7回合收益。','',
        '| 方案 | 第5回合有效研发梁／连接件 | 第5回合有效运营 | 第6回合有效研发梁／连接件 | 第6回合有效运营 |','| --- | ---: | ---: | ---: | ---: |']
    pair=lambda v:'／'.join(f'{z:,.2f}' for z in v)
    for p in plans[1:]:
        a,b=p['evaluations'][0]['periods'];lines.append(f'| {p["name"]} | {pair(a["effective_rd_kusd"])} | {a["effective_operations_kusd"]:,.2f} | {pair(b["effective_rd_kusd"])} | {b["effective_operations_kusd"]:,.2f} |')
    lines+=['','## 统一期限与情景比较','','单位千美元；均比较正式5—6新增条件税后利润，历史已实现收益为共同常数。中性目标最大化SHARE中性利润；稳健目标最大化中性、COUNTRY和联合不利的最低利润。两者都约束三核心采样最低现金≥3000、长贷非负、权益正、权益比率0.25—0.97及营销限额。','',
        '| 方案 | 中性利润 | 较当前增加 | COUNTRY利润 | 联合不利利润 | 不利较当前增加 | 三核心最低现金 | 本期贷款变化 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for p in plans:
        e=p['evaluations'];base=plans[0]['evaluations']
        lines.append(f'| {p["name"]} | {e[0]["profit_5_to_6"]:,.2f} | {e[0]["profit_5_to_6"]-base[0]["profit_5_to_6"]:+,.2f} | {e[1]["profit_5_to_6"]:,.2f} | {e[2]["profit_5_to_6"]:,.2f} | {e[2]["profit_5_to_6"]-base[2]["profit_5_to_6"]:+,.2f} | {min(v["sampled_minimum_cash"] for v in e[:3]):,.2f} | {p["x"][19]*100:,.0f} |')
    lines+=['','优先降低联合不利损失时推荐稳健候选；愿意承担较大不利损失以提高中性模型得分时选中性候选。三情景没有校准概率，中性利润不是期望收益，模型得分不代表实际保证。最低现金仅是采样时点，贴近3000表示可用余量小。','',
        '| 方案 | 第5回合利润：中性／不利 | 第6回合利润：中性／不利 | 第5回合末库存梁／连接件（中性） | 第6回合末库存梁／连接件（中性） |','| --- | ---: | ---: | ---: | ---: |']
    for p in plans:
        a,b=p['evaluations'][0]['periods'];c,d=p['evaluations'][2]['periods']
        lines.append(f'| {p["name"]} | {pair([a["profit"],c["profit"]])} | {pair([b["profit"],d["profit"]])} | {pair(a["closing_inventory"])} | {pair(b["closing_inventory"])} |')
    lines+=['','## 前一候选对照','','模型与情景一致。中性旧方案来自两期同投入搜索，稳健旧方案来自上一批两期独立搜索，不能把两行改善都解释为释放下期投入的纯因果效应。','','| 目标 | 原候选目标利润 | 新候选目标利润 | 改善 |','| --- | ---: | ---: | ---: |']
    for name,before,after in [('中性',old['comparisons'][1]['evaluations'][0]['profit_5_to_6'],plans[1]['evaluations'][0]['profit_5_to_6']),('稳健',previous['comparisons'][-1]['evaluations'][2]['profit_5_to_6'],plans[2]['evaluations'][2]['profit_5_to_6'])]:
        lines.append(f'| {name} | {before:,.4f} | {after:,.4f} | {after-before:+,.4f} |')
    lines+=['','## 两套方案的假设、范围和未求解项','',
        '| 项目 | 中性候选 | 稳健候选 |','| --- | --- | --- |',
        '| 目标与期限 | 最大化正式5—6中性利润 | 最大化正式5—6三核心最低利润 |',
        '| 外生与竞争 | 正式5泰国+7%、印尼−5%，中性竞争吸引力不变；另接受核心约束及压力检查 | 相同，另将联合不利利润纳入最差目标 |',
        '| 正式6政策 | 独立研发与运营，其他价格营销延用第5回合，生产可观察需求后调整，无新增机器融资 | 相同未来政策类，并非完整第6回合策略树优化 |',
        '| 投入曲线 | 两期用正式5曲线、沿用新有效投资权重；正式6响应与历史归一化为假设 | 相同，另列映射冻结压力 |',
        '| 财务约束 | 三核心最低现金3000及债务/权益/比例边界；税亏和时点采用原条件模型 | 相同；没有额外放宽现金条件 |',
        '| 未求解项 | 营销8项仅两类合计可识别；招标4项、分包1项保留归档值并标未求解 | 相同，不能以稳健名称消除机制缺口 |','',
        '- 联合不利：市场规模×0.9、竞争吸引力×1.25、效率×0.9、材料×1.1，正式6市场×0.9/0.95、工资×1.1，应收60天及期初债务计息。核心之外的情景不强制可行。',
        '- 研发/运营映射为兼容网页试验区间的关系，不是已取得的服务端函数。历史权重和更早存量未独立识别。研发归一化分母E=1.25×历史投入，运营E=1.35×历史投入，沿用t5v2反事实锚点；旧系数代理误差未因新映射自动消除。',
        '- 机器本期生效、下期产能15%衰减；期初库存梁0、连接件202.40及账面3516；材料比例迁移、工资43.5、班次系数1/1.65/2.56、运输、库存计价、税29%、应收应付、固定资产和风险利率均沿用t5v2。期初财务为已有状态推导；订单、税亏和自动短贷时序未完整核验，未知项不能解释成已证零。',
        '- 价格支持域为正式4实际正价范围；一般营销合计≤2700、设计师≤3840；研发各产品各期0—2600、运营各期0—1620；机器梁0—20、连接件0—400步长20；长贷变化−10200至10000步长100；配比0—100%。这些是分析支持域，不是已证明的官方全部约束。',
        '- 营销合计重新优化，细分按当前构成分摊，在主模型中同合计等价；缺真实细分响应不能称细分最优。无新招标机会证据和分包成本产量机制，暂保留0/FALSE，影响未知；补齐后需重算。',
        '- 本期全部已识别数值决策纳入联合搜索，物流由净价推导。两期共17个可识别自由度；两新种子差分进化、旧候选保底、显示精度及机器融资离散局部检查，不是全参数或全局最优证明。','',
        '| 方案 | 触及分析边界的本期字段 |','| --- | --- |']
    fields={r['row']:r for r in records[:42]}
    for p in plans[1:]:
        hits=[fields[prior.ROWS[j]]['key'].replace('|','／') for j,v in enumerate(p['x'][:20]) if abs(v-m.bounds[j][0])<1e-7 or abs(v-m.bounds[j][1])<1e-7]
        lines.append('| '+p['name']+' | '+'；'.join(hits)+' |')
    lines+=['','## 全部压力情景','','| 情景 | 当前利润 | 中性建议利润 | 稳健建议利润 | 中性最低现金 | 稳健最低现金 | 中性／稳健约束通过 |','| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for i,c in enumerate(cfgs):
        a,b,d=[p['evaluations'][i] for p in plans]
        lines.append(f'| {c["name"]} | {a["profit_5_to_6"]:,.2f} | {b["profit_5_to_6"]:,.2f} | {d["profit_5_to_6"]:,.2f} | {b["sampled_minimum_cash"]:,.2f} | {d["sampled_minimum_cash"]:,.2f} | {b["feasible"]}／{d["feasible"]} |')
    lines+=['','冻结正式5有效投资压力把回合6响应固定在正式5坐标，但仍扣回合6计划支出，是刻意的响应失效检查。','',
        '## 验收和复现','','48组原两期策略回放一致；48组本批策略通过有效投资轨迹、两期费用、批量与标量、财务与数量等式。研发和运营滞后因果检查通过，第6回合投入变化不改变第5回合。84条决策字段按唯一键及顺序核对通过；三核心约束均通过。未独立验证经营预测。运行：`python work/solve_t5v2_two_policies.py`。','',
        '[完整计算结果](full_result.json) · [搜索](searches.json) · [验收](validation.json) · [运行代码](two_period_runtime.py) · [源文件哈希](source_hashes.json) · [前一两期稳健报告](../../formal5_two_period_t5v2/20261015T213516664688+0800/report.md)','',
        '未填写或提交平台；未新增统计训练标签，未完成营销细分、招标分包及正式6实际条件验证。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    width=None
    for line in lines:
        if line.startswith('|'):
            n=len(line.split('|'));assert width is None or width==n; width=n
        else:width=None
    for link in re.findall(r'\]\(([^)]+)\)','\n'.join(lines)):assert (out/link).resolve().exists(),link

if __name__=='__main__':main()
