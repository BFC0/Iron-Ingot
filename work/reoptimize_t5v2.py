"""Re-search frozen t5v2 decisions; never edits source bundles or platform inputs."""
import copy, csv, hashlib, json, re, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2')]
import numpy as np
from scipy.optimize import differential_evolution
import t5v2

SOURCE = ROOT/'output/t5v2/20261015_effective_investment'
ORDER = [65,66,58,59,68,69,61,62,72,73,46,47,41,42,43,76,77,51,52,49,9,18,25,13,21,29,10,19,26,14,22,30,11,27,15,31,34,35,37,38,54,79]
ROWS = [9,10,13,14,18,19,21,22,25,26,29,30,51,52,49,46,47,42,43,54]
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def distribute(total, weights):
    raw = total*weights/weights.sum()
    values = np.floor(raw).astype(int)
    for i in np.argsort(-(raw-values))[:int(round(total-values.sum()))]:
        values[i] += 1
    assert values.sum() == total and np.all(values >= 0)
    return values

def main():
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out = ROOT/'output/formal5_reoptimized_t5v2'/stamp
    out.mkdir(parents=True, exist_ok=False)
    print('OUTPUT', out, flush=True)
    log = out/'work_log.md'
    log.write_text(f'# 正式5 t5v2重新优化\n\n开始：{stamp}，北京时间。进行中。\n用户要求：依据t5v2及回合5已知数据和曲线重新计算，取消名义投入完全有效假设，采用新的有效投资映射。只作本地计算，不填写或提交平台。复用19:11个人PYT基准（19:46恢复核验）、既有前景和曲线；未实时核对平台，不重复采集教程。保留全部历史和未提交修改。\n', encoding='utf-8')
    save = lambda name, value: (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    preserved = {p.relative_to(ROOT).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    preserved['code/model_v2/t5v2.py'] = sha(ROOT/'code/model_v2/t5v2.py')
    save('source_hashes.json', preserved)
    reg = read(SOURCE/'models_full.json')
    m = t5v2.ApplicationModel()
    m.__dict__.update(t5v2.decode(reg['application_state']))
    m.r = {'risk':reg['risk']}
    m.current = {int(k):v for k,v in m.current.items()}
    cfgs = reg['scenario_configs']
    old = read(SOURCE/'full_result.json')
    bounds = copy.deepcopy(m.bounds)
    # Only marketing totals are identified by t5v2; fixed-zero slots remove equivalent copies.
    for i in [5,6,7,9,10,11]: bounds[i] = [0,0]
    def aggregate(x):
        x = np.array(x, float).copy()
        x[4:8] = [sum(x[4:8]),0,0,0]
        x[8:12] = [sum(x[8:12]),0,0,0]
        return x
    def restore(x):
        x = x.copy()
        x[4:8] = distribute(int(round(sum(x[4:8]))), m.local_general.ravel())
        x[8:12] = distribute(int(round(sum(x[8:12]))), m.local_designer.ravel())
        return x
    def rounded(x):
        x = x.copy()
        x[:2] = np.round(x[:2]); x[2:4] = np.round(x[2:4],1)
        x[4:17] = np.round(x[4:17]); x[17:19] = np.round(x[17:19],1); x[19] = round(x[19])
        return x
    traces, winners = [], []
    for obj, target in [('中性', [0]), ('COUNTRY', [1]), ('稳健', [0,1,2])]:
        def score(x):
            ev = [m.evaluate(x,c) for c in cfgs[:3]]
            return -np.min([ev[i][0] for i in target], axis=0) + np.max([e[2] for e in ev], axis=0)
        incumbent = aggregate(old['comparisons'][1+len(winners)]['x'])
        candidates = [incumbent]
        for seed in [43,71]:
            z = differential_evolution(score,bounds,popsize=12,maxiter=1100,tol=.00003,atol=.05,
                polish=False,seed=seed,vectorized=True,updating='deferred',
                integrality=[False]*15+[True,True,False,False,True],x0=incumbent)
            traces.append(dict(objective=obj,seed=seed,converged=bool(z.success),iterations=z.nit,score=-float(z.fun),x=z.x.tolist()))
            candidates.append(rounded(z.x))
            save('searches.json',traces)
            print('SEARCH',obj,seed,z.nit,z.success,-float(z.fun),flush=True)
        x = min(candidates, key=lambda v:float(score(v)[0])).copy()
        # Check large coordinate moves as well as every machine and financing grid value.
        for iteration in range(15):
            changed = False
            for j in range(20):
                lo,hi = bounds[j]
                if lo == hi: continue
                step = .1 if j in [2,3,17,18] else 1.
                vals = [x[j],lo,hi]
                vals += [x[j]+s*step for s in [-100,-10,-1,1,10,100]]
                if j in [15,16,19]: vals = list(range(int(lo),int(hi)+1))
                vals = sorted(set(v for v in vals if lo<=v<=hi))
                trials = np.repeat(x[:,None],len(vals),axis=1); trials[j] = vals
                scores = score(trials); k = int(np.argmin(scores))
                if scores[k] < float(score(x)[0])-1e-8:
                    x[j] = vals[k]; changed = True
            if not changed: break
        tie = x.copy(); tie[17] = m.baseline[17]
        if abs(float(score(tie)[0])-float(score(x)[0]))<1e-8: x = tie
        assert float(score(x)[0])<=float(score(incumbent)[0])+1e-7
        x = restore(x)
        assert all(m.evaluate(x,c,True)['feasible'] for c in cfgs[:3])
        winners.append(x)
        save('winners.json',[v.tolist() for v in winners])
        print('WINNER',obj,-float(score(x)[0]),x.tolist(),flush=True)
    plans = []
    for name,x in zip(['归档当前基准','中性利润候选','COUNTRY利润候选','稳健利润候选'],[m.baseline,*winners]):
        evaluations = [dict(name=c['name'],**m.evaluate(x,c,True)) for c in cfgs]
        plans.append(dict(name=name,x=x.tolist(),evaluations=evaluations))
    result = dict(version='t5v2',reoptimization=True,source_bundle=SOURCE.relative_to(ROOT).as_posix(),
        start_round=5,end_round=6,full_global_optimum=False,configs=cfgs,comparisons=plans)
    save('full_result.json',result)
    finish(out, reg, m, result, old, save, preserved)

def finish(out, reg, m, result, old, save, preserved):
    delivery(out, reg, m, result, old, save)
    assert all(sha(ROOT/p)==h for p,h in preserved.items())
    shutil.copy2(Path(__file__),out/Path(__file__).name)
    # Update the existing status paragraph, preserving all current on-disk edits.
    doc = ROOT/'README.md'; shutil.copy2(doc,out/'README_before.md')
    before = sha(doc); text = doc.read_text(encoding='utf-8')
    a = text.index('正式5最新决策分析：'); b = text.index('\n\n',a)
    text = text[:a]+'正式5最新决策分析：[t5v2重新优化与42字段建议]('+out.relative_to(ROOT).as_posix()+'/report.md)。采用新的研发/运营有效投资映射，以旧候选为保底重新搜索；统一比较正式5—6条件收益、现金和压力情景。未实时核验或填写平台，营销细分、招标及分包仍有未求解项；不能宣称全参数最优。'+text[b:]
    doc.write_text(text,encoding='utf-8')
    save('document_changes.json',{'README.md':{'before':before,'after':sha(doc)}})
    assert (ROOT/re.search(r'正式5最新决策分析：\[[^]]+\]\(([^)]+)\)',text)[1]).exists()
    with (out/'work_log.md').open('a',encoding='utf-8') as f:
        f.write('\n完成：六次新随机种子搜索及离散步长检查，旧候选保底。126字段、64情景回放、有效投资轨迹、预算复现、财务及数量等式、链接、原模型哈希验收通过。报告完整列出假设与未求解项。未访问或写入平台；未独立验证正式6及缺失机制。\n')
    save('manifest.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'})
    print('COMPLETE',out,flush=True)

def delivery(out,reg,m,result,old,save):
    plans = result['comparisons']; cfgs = result['configs']
    source_fields = {r['row']:r for r in read(SOURCE/'decisions.json') if r['plan']=='稳健利润候选'}
    records = []
    for plan,ref in zip(plans[1:],[0,1,0]):
        x = plan['x']; p = plan['evaluations'][ref]['periods'][0]
        values = {row:x[j]*(20 if row==47 else 100 if row==54 else 1) for j,row in enumerate(ROWS)}
        values.update({58:p['demand'][0][0],59:p['demand'][0][1],61:p['demand'][1][0],62:p['demand'][1][1],
            65:7,66:-5,68:7,69:-5,72:(cfgs[ref]['future_growth'][0]-1)*100,73:(cfgs[ref]['future_growth'][1]-1)*100,
            76:p['efficiency'][0],77:p['efficiency'][1],79:p['rate']*100})
        for j,rows in enumerate([[34,35],[37,38]]):
            for k,row in enumerate(rows): values[row] = '第一' if p['priority'][j]==k else '第二'
        for row in ORDER:
            f = copy.deepcopy(source_fields[row]); v = values.get(row,m.current[row])
            if row in [58,59,61,62]: v = round(v,2)
            if row in [76,77]: v = round(v,6)
            if row==79: v = round(v,2)
            f.update(plan=plan['name'],current=m.current[row],suggested=v,changed=v!=m.current[row])
            if row in [18,19,21,22,25,26,29,30]:
                f.update(status='合计求解／细分未识别',reason='两类营销总额联合优化，按当前构成分摊；不是国别产品细分最优。不同分摊仅在主模型等价')
            elif row in [11,15,27,31,41]:
                f.update(status='未求解／保留归档值',reason='归档无新招标；分包机制缺失，收益与产能影响未知，不能将FALSE或零证明为最优')
            elif row in [51,52]: f['reason']='E=0.75×当期＋0.50×上期，费用计当期名义投入；研发与其余经营变量联合重搜'
            elif row==49: f['reason']='E=当期＋0.35×上期，效率由曲线重算；费用计当期名义投入'
            if row in [65,66,68,69,72,73]: f['status']='外生情景假设'
            records.append(f)
    assert len(records)==126
    for plan in plans[1:]: assert [r['row'] for r in records if r['plan']==plan['name']]==ORDER
    save('decisions.json',records)
    with (out/'decisions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    checks=0
    for plan in plans:
        x=np.array(plan['x'])
        for cfg,expected in zip(cfgs,plan['evaluations']):
            actual=t5v2.apply_request(reg,dict(version='t5v2',market_id=5,phase='formal',round=5,decision_vector=plan['x'],scenario=cfg['name']))
            assert abs(actual['profit_5_to_6']-expected['profit_5_to_6'])<1e-8
            assert actual['balance_error_max']<1e-7 and actual['quantity_error_max']<1e-8
            p=actual['periods'][0]
            assert np.allclose(p['effective_rd_kusd'],.75*x[12:14]+[450,650])
            assert abs(p['effective_operations_kusd']-(x[14]+262.5))<1e-8
            checks+=1
        batch=m.evaluate(np.column_stack([x,x]),cfgs[0])[0]
        assert np.allclose(batch,plan['evaluations'][0]['profit_5_to_6'])
    budget=m.evaluate(m.baseline,cfgs[0],True,budget=True)
    assert abs(budget['periods'][0]['profit']-5232)<10
    save('budget_replay.json',budget)
    fmt=lambda v: f'{v:,.6f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)
    lines=['# 正式5：t5v2重新优化决策','',
        '推荐将下表稳健候选用于个人预算核验。它在三核心情景中最低利润最高；仍有亏损风险，仅是已识别机制及既定范围内的部分优化候选。未填写或提交平台。',
        '', '数据基准：市场5、正式5、PYT；个人输入取2026-10-15 19:11归档，19:46已恢复核验。此次未实时访问平台，“当前”均指该归档值。前景、参数及600个曲线点复用既有正式5归档。', '',
        '研发有效投资＝0.75×本期支出＋0.50×上期支出（上期梁900、连接件1300）；运营有效投资＝本期支出＋0.35×上期750。曲线使用有效投资，费用只计本期名义支出。取消名义支出直接作为有效投资的路径。系数与网页试验区间兼容，非服务端源码定律。', '',
        '## 完整填写建议', '',
        '按正式5归档子页顺序逐项列出。各候选的需求、效率和利率随经营方案一致重算；外生增长不作为可操纵利润的变量。中性与稳健预估按中性情景、COUNTRY预估按国别情景。金额单位千美元，价格美元，数量千单位。', '']
    byplan=[{r['row']:r for r in records if r['plan']==p['name']} for p in plans[1:]]
    for title,rows in [('需求',ORDER[:10]),('生产：投资与计划',ORDER[10:20]),('销售：泰国、印尼与大客户',ORDER[20:36]),('物流',ORDER[36:40]),('财务',ORDER[40:])]:
        lines += ['### '+title,'','| 字段／产品／国家 | 单位 | 归档当前 | 中性 | COUNTRY | 稳健（建议） | 稳健是否调整 | 优化状态及依据 |','| --- | --- | ---: | ---: | ---: | ---: | --- | --- |']
        for row in rows:
            a,b,c=[p[row] for p in byplan]
            label='／'.join(str(c[k]) for k in ['section','product','label'] if c[k])
            lines.append(f'| {label} | {c["unit"]} | {fmt(c["current"])} | {fmt(a["suggested"])} | {fmt(b["suggested"])} | {fmt(c["suggested"])} | {"是" if c["changed"] else "否"} | {c["status"]}：{c["reason"]} |')
        lines.append('')
    lines += ['[逐方案是否调整、状态及依据JSON](decisions.json) · [填写CSV](decisions.csv)','',
        '## 统一期限与收益风险比较','','所有数字是模型条件预测，非已实现利润或已核平台候选预算。比较正式5—6新增税后利润；正式1—4已实现收益是共同常数，不补零。各候选均约束三核心情景采样最低现金≥3000、长贷非负、权益正、权益比率在0.25—0.97及营销合计限额。', '',
        '| 方案 | 中性利润 | 较当前增加 | COUNTRY利润 | 联合不利利润 | 不利较当前增加 | 三核心最低现金 | 贷款变化 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for plan in plans:
        ev=plan['evaluations'];baseline=plans[0]['evaluations']
        lines.append(f'| {plan["name"]} | {ev[0]["profit_5_to_6"]:,.2f} | {ev[0]["profit_5_to_6"]-baseline[0]["profit_5_to_6"]:+,.2f} | {ev[1]["profit_5_to_6"]:,.2f} | {ev[2]["profit_5_to_6"]:,.2f} | {ev[2]["profit_5_to_6"]-baseline[2]["profit_5_to_6"]:+,.2f} | {min(e["sampled_minimum_cash"] for e in ev[:3]):,.2f} | {plan["x"][19]*100:,.0f} |')
    lines += ['', '稳健最大化三核心最低利润，适用于优先降低联合不利损失；中性最大化SHARE利润；COUNTRY最大化国别模型利润。三者使用相同现金约束、边界和未来政策。国别模型得分高不等于模型更准确；三个情景没有已校准概率，不把中性当作期望收益。', '',
        '| 方案 | 第5回合利润：中性／不利 | 第6回合利润：中性／不利 | 第5回合末库存：梁／连接件（中性） | 第6回合末库存：梁／连接件（中性） |',
        '| --- | ---: | ---: | ---: | ---: |']
    for plan in plans:
        a,b=plan['evaluations'][0]['periods']; c,d=plan['evaluations'][2]['periods']
        pair=lambda v:'／'.join(f'{z:,.2f}' for z in v)
        lines.append(f'| {plan["name"]} | {pair([a["profit"],c["profit"]])} | {pair([b["profit"],d["profit"]])} | {pair(a["closing_inventory"])} | {pair(b["closing_inventory"])} |')
    lines += ['', '## 与上一批t5v2候选比较','','同模型、同情景与边界，旧候选参与保底，以下改善来自重新搜索，未重训或修改模型。', '',
        '| 候选 | 原目标利润 | 新目标利润 | 改善 |','| --- | ---: | ---: | ---: |']
    for i,plan in enumerate(plans[1:]):
        ix=0 if i==0 else 1 if i==1 else 2
        before=old['comparisons'][i+1]['evaluations'][ix]['profit_5_to_6'];after=plan['evaluations'][ix]['profit_5_to_6']
        assert after>=before-1e-7
        lines.append(f'| {plan["name"]} | {before:,.4f} | {after:,.4f} | {after-before:+,.4f} |')
    lines += ['', '## 有效投资轨迹与全部压力情景','','| 方案 | 正式5研发：梁／连接件 | 正式5运营 | 正式6研发：梁／连接件 | 正式6运营 |','| --- | ---: | ---: | ---: | ---: |']
    for plan in plans:
        a,b=plan['evaluations'][0]['periods']
        pair=lambda v:'／'.join(f'{z:,.2f}' for z in v)
        lines.append(f'| {plan["name"]} | {pair(a["effective_rd_kusd"])} | {a["effective_operations_kusd"]:,.2f} | {pair(b["effective_rd_kusd"])} | {b["effective_operations_kusd"]:,.2f} |')
    lines += ['','| 情景 | 当前利润 | 中性候选 | COUNTRY候选 | 稳健候选 | 稳健最低现金 | 稳健约束通过 |','| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for i,cfg in enumerate(cfgs):
        ev=[p['evaluations'][i] for p in plans]
        lines.append('| '+cfg['name']+' | '+' | '.join(f'{e["profit_5_to_6"]:,.2f}' for e in ev)+f' | {ev[-1]["sampled_minimum_cash"]:,.2f} | {ev[-1]["feasible"]} |')
    lines += ['', '仅前三个情景进入现金硬约束；其余为压力检查，未全部要求可行。最低现金只覆盖年末及投资融资后检查点，不能代表全过程流动性。', '',
        '## 每套方案共同假设与未求解项','',
        '- 模型t5v2冻结。正式5泰国+7%、印尼−5%，竞争吸引力基准不变；联合不利为市场×0.9、竞争吸引力×1.25、效率×0.9、材料×1.1、正式6两产品需求×0.9/0.95、工资×1.1、应收60天及期初债务计息。COUNTRY仅切换国别需求响应。',
        '- 正式6价格、营销、研发及运营延续正式5；同曲线、映射权重、基础需求规模不变为假设。生产可在观察需求后调整，不新增机器或融资；这不是完整第6回合决策树优化。单列冻结正式5有效投资情景。',
        '- 研发分母锚点E=1.25×上期投入，运营E=1.35×上期投入，是t5v2反事实归一化，未独立识别正式4真实有效存量；本次仅应用新映射，不解决旧需求系数中的代理误差。正式5投入映射有网页区间证据，历史权重解释及正式6迁移未独立识别。',
        '- 机器当期生效，正式6产能衰减15%；现有库存梁0、连接件202.40及账面3516沿用归档。材料比例迁移、工资43.5及班次1/1.65/2.56、运输、库存计价、税29%、固定成本、应收应付和风险利率均沿用t5v2。财务期初值来自已有状态推导，税亏/订单/自动短贷时序不完整；未知状态并未被证明为零，所得利润只在这些假设下成立。',
        '- 营销仅两类合计可识别，8个细分保留原构成比例，未任意默认固定合计。4个招标字段缺新机会机制，分包字段缺数量成本关系，暂保留归档值；缺口可能改变需求、产能及利润，补齐真实可选项和支付规则后需重算。物流按净售价推导排序；运营、研发、投资、配比、融资及四个价格均纳入联合搜索。',
        '- 分析支持域沿用t5v2，并非官方上下限：价格为正式4实际正价范围；一般营销合计≤2700，设计师≤3840；研发0—2600，运营0—1620；机器梁0—20、连接件0—400（步长20）；长贷变化−10200至10000（步长100）；配比0—100%。超出支持域的最优性未证明。',
        '- 对名义投入0/1200/2600及0/381/2600验证研发映射，运营0/900/1200；更高运营、未来回合及超出原图有效投资域均属外推。达到支持边界仅说明该范围内倾向，不能解释为平台最优。', '',
        '| 方案 | 到达分析边界的数值字段 |','| --- | --- |']
    for plan in plans[1:]:
        hits=[]
        for j,v in enumerate(plan['x']):
            lo,hi=m.bounds[j]
            if abs(v-lo)<1e-7 or abs(v-hi)<1e-7: hits.append(source_fields[ROWS[j]]['key'])
        lines.append('| '+plan['name']+' | '+'；'.join(hits).replace('|','／')+' |')
    lines += ['', '## 搜索与验收','','每个目标运行新种子43、71的差分进化（种群系数12、最多1100代），以原候选保底，再按显示精度检查局部大小步长和全部机器、贷款档位。折合14个可识别搜索自由度；未穷举所有经营组合，算法收敛不是全局最优证明。', '',
        f'已通过{checks}组冻结接口回放、批量与标量一致、126条字段顺序/唯一性、有效投资坐标检查、财务及数量恒等式；归档预算5232的本地复现误差{budget["periods"][0]["profit"]-5232:.4f}千美元。预算复现只核旧基准，三候选尚未平台预算核验。', '',
        '[完整计算结果](full_result.json) · [搜索记录](searches.json) · [验收](validation.json) · [原模型及归档哈希](source_hashes.json) · [原t5v2报告](../../t5v2/20261015_effective_investment/report.md) · [冻结注册表](../../t5v2/20261015_effective_investment/models_full.json)', '',
        '未访问平台、未采集教程、未改原模型；未完成营销细分、招标分包及正式6独立验证。各方案均可能亏损，不宣称全参数最优。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    width=None
    for line in lines:
        if line.startswith('|'):
            n=len(line.split('|'));assert width is None or width==n; width=n
        else: width=None
    save('validation.json',dict(status='PASS',frozen_replays=checks,fields=126,source_runtime_unchanged=True,
        effective_mapping_used=True,scalar_batch_parity=True,financial_and_quantity_balances=True,
        baseline_budget_error=budget['periods'][0]['profit']-5232,platform_accessed=False,global_optimum_proven=False))
    for link in re.findall(r'\]\(([^)]+)\)',(out/'report.md').read_text(encoding='utf-8')):
        assert (out/link).resolve().exists(),link

if __name__=='__main__':
    if len(sys.argv)==1:
        main()
    else:
        out=Path(sys.argv[1]).resolve()
        assert out.parent==ROOT/'output/formal5_reoptimized_t5v2'
        reg=read(SOURCE/'models_full.json')
        m=t5v2.ApplicationModel();m.__dict__.update(t5v2.decode(reg['application_state']))
        m.r={'risk':reg['risk']};m.current={int(k):v for k,v in m.current.items()}
        save=lambda name,value:(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        with (out/'work_log.md').open('a',encoding='utf-8') as f:
            f.write('\n交付检查更正：边界字段键包含竖线，触发表格列宽检查；已将展示分隔符改为斜线。复用已保存搜索结果继续验收，不重复搜索、不改模型。\n')
        finish(out,reg,m,read(out/'full_result.json'),read(SOURCE/'full_result.json'),save,read(out/'source_hashes.json'))
