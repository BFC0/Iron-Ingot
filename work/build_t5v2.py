"""Freeze t5v2 from t5v1, fit interval-censored investment mappings, and rerun decisions."""
import copy, csv, hashlib, inspect, json, re, shutil, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'work')]
import numpy as np
from scipy.optimize import linprog
import t5v1
import solve_formal5_full as base

SOURCE=ROOT/'output/t5v1/20261015T171355804'
PROBE=ROOT/'output/effective_investment/20261015_code_probe'
OUT=ROOT/'output/t5v2/20261015_effective_investment'
ORDER=[65,66,58,59,68,69,61,62,72,73,46,47,41,42,43,76,77,51,52,49,9,18,25,13,21,29,10,19,26,14,22,30,11,27,15,31,34,35,37,38,54,79]
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,v):
    (OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def mapping_fit(samples):
    records=[]
    for sample in samples:
        values=[base.number(v['value']) for v in sample['inputs']]
        for chart in sample['charts']:
            for series in chart['markers']:
                product=series['name'].split(', ')[1]
                key='operations' if chart['id']=='cost.efficiency.chart' else 'rd_beam' if product=='复合梁' else 'rd_connector'
                pos={'rd_beam':4,'rd_connector':5,'operations':6}[key]
                xmax=float(chart['curveEndpoints'][0]['xmax']);step=xmax/199
                point=series['points'][0];i=point['i']
                # The marker is the first grid point at or above investment, not an exact coordinate.
                records.append(dict(key=key,input=values[pos],lower=max(0,(i-1)*step-.5),upper=i*step+.5,
                    plotted_label=float(point['x']),grid_index=i,grid_step=step,multiplier=point['y'],at=sample['at']))
    models={}
    for key,previous,canonical in [('rd_beam',900,[.75,.5]),('rd_connector',1300,[.75,.5]),('operations',750,[1.,.35])]:
        rows=[r for r in records if r['key']==key]
        unique={r['input']:r for r in rows}
        assert len(unique)>=3
        # Hold the original input out of calibration; use zero and the other endpoint.
        original={'rd_beam':2600,'rd_connector':381,'operations':900}[key]
        train=[r for r in rows if r['input']!=original]
        A=np.array([[r['input'],previous] for r in train]);lo=np.array([r['lower'] for r in train]);hi=np.array([r['upper'] for r in train])
        bounds=[]
        for j in range(2):
            c=np.eye(2)[j]
            low=linprog(c,A_ub=np.r_[A,-A],b_ub=np.r_[hi,-lo],bounds=[(0,None)]*2,method='highs')
            high=linprog(-c,A_ub=np.r_[A,-A],b_ub=np.r_[hi,-lo],bounds=[(0,None)]*2,method='highs')
            assert low.success and high.success
            bounds.append([float(low.fun),float(-high.fun)])
        assert all(r['lower']-1e-8<=canonical[0]*r['input']+canonical[1]*previous<=r['upper']+1e-8 for r in rows)
        models[key]=dict(current_weight=canonical[0],previous_weight=canonical[1],previous_input=previous,
            coefficient_intervals=bounds,distinct_inputs=sorted(unique),held_input=original,
            status='SIMPLE_COEFFICIENTS_COMPATIBLE_WITH_INTERVALS_NOT_SOURCE_CODE',
            historic_weight_scope='one fixed prior state; dependence on previous input is not independently identified')
    return dict(models=models,records=records,grid_rule='ceil(E/(xmax/199)); labels ±0.5; inferred from all trials',
        source_function_found=False,curve_parameters_retrained=False)

def runtime_source():
    text=(ROOT/'code/model_v2/t5v1.py').read_text(encoding='utf-8')
    text=text.replace('t5v1','t5v2').replace("('t5v2','t5v0b',5)","('t5v2','t5v1',5)").replace("base_version='t5v0b'","base_version='t5v1'")
    text=text.replace('基线t5v0b','基线t5v1')
    addition='''def effective_investment(current, previous, item):
    return item['current_weight'] * current + item['previous_weight'] * previous


'''
    text=text.replace('class _BaseScenario:',addition+'class _BaseScenario:')
    old='rdlog = np.array([np.log(curve(x[12 + j], self.rdcurves[j]) / curve(self.rdbase[j], self.rdcurves[j])) for j in range(2)])'
    new="rdlog = np.array([np.log(curve(effective_investment(x[12+j], x[12+j] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.rdbase[j], self.investment_mapping['rd']), self.rdcurves[j]) / curve(effective_investment(self.rdbase[j], self.rdbase[j], self.investment_mapping['rd']), self.rdcurves[j])) for j in range(2)])"
    assert text.count(old)==1;text=text.replace(old,new)
    needle='            cash, ar, ap, machine, building, debt, equity, assets = (newcash, newar, newap, newmachine, newbuilding, newdebt, newequity, newassets)'
    trace="""            if details:
                rd_previous = x[12:14] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.rdbase[:, None]
                op_previous = x[14] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.opsbase
                periods[-1]['effective_rd_kusd'] = effective_investment(x[12:14], rd_previous, self.investment_mapping['rd'])[:, 0].tolist()
                periods[-1]['effective_operations_kusd'] = float(effective_investment(x[14], op_previous, self.investment_mapping['operations'])[0])
                periods[-1]['future_mapping_assumption'] = bool(t)
"""
    assert text.count(needle)==1;text=text.replace(needle,trace+needle)
    old="ef = self.effbase[:, None] * curve(x[14], self.opcurve) / curve(self.opsbase, self.opcurve) * cfg.get('efficiency_scale', 1.0)"
    new="ef = self.effbase[:, None] * curve(effective_investment(x[14], x[14] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.opsbase, self.investment_mapping['operations']), self.opcurve) / curve(effective_investment(self.opsbase, self.opsbase, self.investment_mapping['operations']), self.opcurve) * cfg.get('efficiency_scale', 1.0)"
    assert text.count(old)==1;text=text.replace(old,new)
    text=text.replace("result.update(version='t5v2',", "result.update(investment_mapping_status=registry['investment_mapping']['status'], version='t5v2',")
    text=text.replace('正式6同价同投入及同曲线为情景','正式6同价同投入、同曲线及投入滞后权重为情景；基准为同投入反事实归一化，非历史有效存量已识别')
    return text

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    (OUT/'code_snapshot').mkdir();(OUT/'sources').mkdir()
    (OUT/'work_log.md').write_text('# t5v2工作日志\n\n2026-10-15，北京时间。按用户要求以t5v1接入投入→有效投资映射，整体独立保存。不要输出真名，姓名统一用首字母替代。网页采集与失败尝试详见sources/probe/work_log.md；不提交小组方案。进行中。\n',encoding='utf-8')
    preservation={str(p.relative_to(ROOT)):sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    preservation['code/model_v2/t5v1.py']=sha(ROOT/'code/model_v2/t5v1.py')
    save('t5v1_before_hashes.json',preservation)
    shutil.copytree(PROBE,OUT/'sources/probe')
    shutil.copy2(SOURCE/'models_full.json',OUT/'sources/t5v1_models_full.json')
    samples=read(PROBE/'samples_partial.json')
    mapping=mapping_fit(samples);save('effective_investment_models.json',mapping)
    before=read(PROBE/'checklist_before.json');after=read(PROBE/'checklist_final_restored.json')
    assert before==after, 'Final own/team rows must equal the original snapshot'
    code=ROOT/'code/model_v2/t5v2.py'
    with code.open('x',encoding='utf-8') as f:f.write(runtime_source())
    shutil.copy2(code,OUT/'code_snapshot/t5v2.py');shutil.copy2(Path(__file__),OUT/'code_snapshot/build_t5v2.py')
    import t5v2
    registry=copy.deepcopy(read(SOURCE/'models_full.json'))
    registry.update(version='t5v2',base_version='t5v1',investment_mapping=dict(status='FORMAL5_INTERVAL_VALIDATED_FORMAL6_ASSUMED',**mapping))
    state=t5v2.decode(registry['application_state'])
    oldrows=read(SOURCE/'decisions.json');fields={r['row']:r for r in oldrows if r['plan']=='稳健利润候选'}
    assert len(fields)==42
    current={row:(values[-1] if values[-1] in ['第一','第二','FALSE','TRUE'] else base.number(values[-1])) for row,values in zip(sorted(fields),before[2:])}
    assert len(current)==42
    state['current']=current
    baseline=np.array([current[r]/(20 if r==47 else 100 if r==54 else 1) for r in base.ROWS])
    state['baseline']=baseline
    state['investment_mapping']={'rd':{'current_weight':.75,'previous_weight':.5},'operations':{'current_weight':1.,'previous_weight':.35}}
    m=t5v2.ApplicationModel();m.__dict__.update(state);m.r={'risk':registry['risk']}
    m.fields=[dict(row=r,key=f['key'],section=f['section'],product_or_location=f['product'],label=f['label'],unit=f['unit']) for r,f in fields.items()]
    cfgs=copy.deepcopy(registry['scenario_configs'])
    cfgs.append(dict(cfgs[0],name='正式6冻结正式5有效投资',future_mapping='freeze_formal5'))
    registry['scenario_configs']=cfgs
    def encode(v):
        if isinstance(v,np.ndarray):return {'__ndarray__':v.tolist()}
        if isinstance(v,dict):return {k:encode(x) for k,x in v.items()}
        if isinstance(v,list):return [encode(x) for x in v]
        return v
    registry['application_state']=encode(state)
    # Reuse the original search, with COUNTRY as a third explicit objective.
    base.OUT=OUT
    search_source=inspect.getsource(base.search).replace("['中性','稳健']","['中性','COUNTRY','稳健']").replace("active=cfgs[:1] if objective=='中性' else cfgs[:3]","active=cfgs[:1] if objective=='中性' else cfgs[1:2] if objective=='COUNTRY' else cfgs[:3]")
    (OUT/'code_snapshot/search.py').write_text(search_source,encoding='utf-8')
    ns=dict(vars(base));exec(compile(search_source,'t5v2_search','exec'),ns)
    actual_bounds=copy.deepcopy(m.bounds)
    m.baseline=baseline.copy();m.baseline[4:8]=[sum(baseline[4:8]),0,0,0];m.baseline[8:12]=[sum(baseline[8:12]),0,0,0]
    for j in [5,6,7,9,10,11]:m.bounds[j]=[0,0]
    winners=ns['search'](m,cfgs)
    m.bounds=actual_bounds;m.baseline=baseline
    def distribute(total,weights):
        raw=total*weights/weights.sum();v=np.floor(raw).astype(int)
        for i in np.argsort(-(raw-v))[:int(round(total-v.sum()))]:v[i]+=1
        return v
    for x in winners:
        x[4:8]=distribute(int(sum(x[4:8])),m.local_general.ravel());x[8:12]=distribute(int(sum(x[8:12])),m.local_designer.ravel())
    comparisons=[]
    for name,x in zip(['最新网页基准','中性利润候选','COUNTRY利润候选','稳健利润候选'],[baseline,*winners]):
        ev=[dict(name=c['name'],**m.evaluate(x,c,True)) for c in cfgs]
        assert all(e['balance_error_max']<1e-7 and e['quantity_error_max']<1e-8 for e in ev)
        if name!='最新网页基准':assert all(e['feasible'] for e in ev[:3])
        comparisons.append(dict(name=name,x=x.tolist(),evaluations=ev))
    registry['saved_plans']=[dict(name=p['name'],x=p['x']) for p in comparisons]
    save('models_full.json',registry)
    result=dict(version='t5v2',base_version='t5v1',configs=cfgs,comparisons=comparisons,start_round=5,end_round=6,full_global_optimum=False)
    save('full_result.json',result)
    # Recompute the old plans under the new mapping to isolate model changes from reoptimization.
    oldresult=read(SOURCE/'full_result.json')
    save('t5v1_plan_replay.json',[dict(name=p['name'],old=p['evaluations'][:3],new=[dict(name=c['name'],**m.evaluate(p['x'],c,True)) for c in cfgs[:3]]) for p in oldresult['comparisons']])
    save('budget_replay.json',m.evaluate(baseline,cfgs[0],True,budget=True))
    make_delivery(m,registry,result,fields,t5v2,preservation)

def make_delivery(m,registry,result,fields,runtime,preservation):
    plans=result['comparisons'];cfgs=result['configs'];decisions=[];sens=[]
    fmt=lambda v:f'{v:,.4f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)
    def predicted(row,e,c):
        p=e['periods'][0]
        if row in [58,59,61,62]:return p['demand'][0 if row in [58,59] else 1][0 if row in [58,61] else 1]
        if row in [76,77]:return p['efficiency'][0 if row==76 else 1]
        if row==79:return p['rate']*100
        if row in [65,68]:return 7.
        if row in [66,69]:return -5.
        return (c['future_growth'][0 if row==72 else 1]-1)*100
    for plan,ref in zip(plans[1:],[0,1,0]):
        x=np.array(plan['x']);ev=plan['evaluations'];p=ev[ref]['periods'][0]
        values={row:x[j]*(20 if row==47 else 100 if row==54 else 1) for j,row in enumerate(base.ROWS)}
        for row in [58,59,61,62,65,66,68,69,72,73,76,77,79]:values[row]=predicted(row,ev[ref],cfgs[ref])
        for j,rr in enumerate([[34,35],[37,38]]):
            for k,row in enumerate(rr):values[row]='第一' if p['priority'][j]==k else '第二'
        for row in ORDER:
            f=copy.deepcopy(fields[row]);v=values.get(row,m.current[row]);v=v.item() if isinstance(v,np.generic) else v
            if row in [58,59,61,62]:v=round(v,2)
            if row in [76,77]:v=round(v,6)
            if row==79:v=round(v,2)
            status='联合求解' if row in base.ROWS else '净价推导' if row in [34,35,37,38] else '未求解／不适用' if row in [11,15,27,31,41] else '情景重算'
            reason='沿用t5v1需求、生产与财务假设；统一三核心情景现金≥3000'
            if row in [51,52]:reason='支出先经0.75×当期＋0.50×上期映射，再进入研发需求曲线；正式6权重延用为假设'
            elif row==49:reason='支出先经当期＋0.35×上期映射，再进入效率曲线；费用仍仅计当期支出'
            elif row in [18,19,21,22,25,26,29,30]:reason='两类营销合计联合求解，按现有构成分摊；细分最优未识别'
            elif row in [11,15,27,31,41]:reason='无新招标／分包机制未识别，不虚构可解决策'
            elif row not in base.ROWS:reason='与本候选及其参考情景一致重算；外生增长不是可控收益'
            f.update(plan=plan['name'],current=m.current[row],suggested=v,changed=v!=m.current[row],status=status,reason=reason)
            decisions.append(f)
            common=dict(plan=plan['name'],row=row,key=f['key'],reference=cfgs[ref]['name'],unit=f['unit'])
            if row in [11,15,27,31,41]:
                sens.append(dict(common,direction='不适用',test=None,delta_profit=None,delta_worst=None,minimum_cash=None,core_feasible=None,status='未求解／不适用'));continue
            for sign in [-1,1]:
                z=x.copy();overrides=[{} for _ in range(3)];clipped=False
                if row in base.ROWS:
                    j=base.ROWS.index(row);scale=20 if row==47 else 100 if row==54 else 1
                    start=x[j]*scale
                    step=abs(start)*.1 if row in [9,10,13,14] else 5. if row in [42,43] else max(1.,round(abs(start)*.1)) if row==46 else max(20.,round(abs(start)*.1/20)*20) if row==47 else max(1000.,round(abs(start)*.1/100)*100) if row==54 else max(50.,abs(start)*.1)
                    wanted=round(start+sign*step,1 if row in [13,14,42,43] else 0)
                    lo,hi=[float(q)*scale for q in m.bounds[j]]
                    if row in [18,19,21,22]:hi=min(hi,2700-sum(x[4:8])+x[j])
                    if row in [25,26,29,30]:hi=min(hi,3840-sum(x[8:12])+x[j])
                    test=float(np.clip(wanted,lo,hi));clipped=abs(wanted-test)>1e-8;z[j]=test/scale
                elif row in [34,35,37,38]:
                    if sign==1:continue
                    test='第二' if v=='第一' else '第一';overrides=[{row:test} for _ in range(3)]
                else:
                    test=predicted(row,ev[ref],cfgs[ref])*(1+sign*.1) if row in [58,59,61,62,76,77] else predicted(row,ev[ref],cfgs[ref])+sign*(1 if row==79 else 5)
                    overrides=[{row:predicted(row,e,c)*(1+sign*.1) if row in [58,59,61,62,76,77] else predicted(row,e,c)+sign*(1 if row==79 else 5)} for e,c in zip(ev[:3],cfgs[:3])]
                changed=[m.evaluate(z,c,True,overrides=o) for c,o in zip(cfgs[:3],overrides)]
                assert all(e['balance_error_max']<1e-7 and e['quantity_error_max']<1e-8 for e in changed)
                sens.append(dict(common,direction='减少／切换' if sign<0 else '增加',test=test,
                    delta_profit=changed[ref]['profit_5_to_6']-ev[ref]['profit_5_to_6'],
                    delta_worst=min(e['profit_5_to_6'] for e in changed)-min(e['profit_5_to_6'] for e in ev[:3]),
                    minimum_cash=min(e['sampled_minimum_cash'] for e in changed),core_feasible=all(e['feasible'] for e in changed),status='边界截断' if clipped else '已计算'))
    for name,rows in [('decisions',decisions),('sensitivity_all_candidates',sens)]:
        save(name+'.json',rows)
        with (OUT/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            columns=list(dict.fromkeys(k for r in rows for k in r));w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
    for plan in plans[1:]:assert {r['row'] for r in decisions if r['plan']==plan['name']}==set(ORDER) and {r['row'] for r in sens if r['plan']==plan['name']}==set(ORDER)
    # Frozen runtime equality, scalar/batch parity, rejection, and forward response checks.
    request=dict(version='t5v2',market_id=5,phase='formal',round=5,plan='稳健利润候选',scenario='中性SHARE')
    save('example_request.json',request);save('example_result.json',runtime.apply_request(registry,request))
    for plan in plans:
        for c,expected in zip(cfgs,plan['evaluations']):
            actual=runtime.apply_request(registry,dict(request,plan=plan['name'],scenario=c['name']))
            assert abs(actual['profit_5_to_6']-expected['profit_5_to_6'])<1e-8
    x=np.array(plans[-1]['x']);batch=m.evaluate(np.column_stack([x,x]),cfgs[0])[0]
    assert np.allclose(batch,plans[-1]['evaluations'][0]['profit_5_to_6'])
    for bad in [dict(request,version='t5v1'),dict(request,decision_vector=[float('nan')]*20),dict(request,round=6)]:
        try:runtime.apply_request(registry,bad)
        except ValueError:pass
        else:raise AssertionError('Invalid request accepted')
    for j in [12,13,14]:
        low=x.copy();low[j]=0;high=x.copy();high[j]=min(m.bounds[j][1],1200)
        a=m.evaluate(low,cfgs[0],True)['periods'][0];b=m.evaluate(high,cfgs[0],True)['periods'][0]
        assert sum(b['demand'][j-12])>sum(a['demand'][j-12]) if j<14 else min(np.array(b['efficiency'])-a['efficiency'])>0
    budget=read(OUT/'budget_replay.json');budget_error=budget['periods'][0]['profit']-5232
    assert abs(budget_error)<10, budget_error
    preserved=all(sha(ROOT/p)==h for p,h in preservation.items());assert preserved
    validation=dict(status='PASS',version='t5v2',t5v1_files_preserved=len(preservation),t5v1_unchanged=preserved,
        platform_restored=True,current_fields=42,candidate_decisions=126,sensitivity_fields_each=42,
        frozen_replays=len(plans)*len(cfgs),budget_profit_display=5232,budget_replay_error=budget_error,
        scalar_batch_parity=True,invalid_requests_rejected=True,forward_response_checks=True,
        investment_mapping_interval_validation=True,independent_business_validation=False)
    save('validation.json',validation)
    lines=['# t5v2：有效投资映射接入及完整条件决策','',
        '以t5v1为基线，研发和运营先转换为有效投资，再进入原需求与效率曲线，随后重算生产、利润、现金及正式6情景。t5v1源代码及全部归档哈希不变。建议优先将稳健候选用于预算复核，仍存在联合不利情景亏损风险。','',
        '市场5、正式5、个人PYT。试验前基准2026-10-15 19:11（北京时间），最终恢复约19:46；截止当日22:00。三项已恢复2600／381／900，42项个人输入及小组列与试验前一致。未提交小组方案。不要输出真名，姓名统一用首字母替代。','',
        '## 新映射及识别边界','',
        '| 对象 | 本次采用的有效投资E（千美元） | 上期输入 | 当前网页基准E |','| --- | --- | ---: | ---: |',
        '| 复合梁研发 | 0.75×R＋0.50×R上期 | 900 | 2400 |','| 连接件研发 | 0.75×R＋0.50×R上期 | 1300 | 935.75 |','| 运营 | O＋0.35×O上期 | 750 | 1162.5 |','',
        '公开内联脚本和5份业务脚本未发现转换函数：change事件通过Wicket POST送服务端，图表收到计算完成的JSON。上述系数是兼容网页试验区间的简洁关系，不能称为源码公式或唯一精确参数。每种机制至少3个不同投入；原输入作为留出点。历史输入始终固定，因此只识别本期斜率与历史截距，0.50及0.35是截距除以上期投入的解释，尚不能排除更早历史状态。','',
        '回合效果点按200点绘图网格向上落点；连接件381未变时，改复合梁后标记从946变为941，说明显示点并非精确有效投资。校准保留每个点的相邻网格区间和标签±0.5误差；参数兼容区间、全部乘数与验证点见[映射模型](effective_investment_models.json)。既有曲线参数不重训，营销、价格、材料与风险系数沿用t5v1。','',
        '研发和运营费用只按当期名义支出进入成本及现金。为保持t5v1的反事实需求/效率锚定方式，分母也使用同一映射后的基准：研发基准E=1.25×上期支出，运营基准E=1.35×上期支出。这是归一化情景，未识别正式4真实有效存量；不能将归一化处理说成独立历史验证。正式6同投入、同曲线且沿用本次权重，使用本次正式5投入作上期；另列冻结正式5有效投资的压力情景。','',
        '## 统一情景与推荐理由','',
        '金额千美元，期限正式5—6新增税后利润；既往利润为共同常数。中性、COUNTRY分别最大化对应模型利润；稳健最大化三核心最低利润。三候选均约束三核心采样最低现金≥3000，保持相同搜索域和未来政策。','',
        '| 方案 | 中性利润 | COUNTRY利润 | 联合不利利润 | 三核心最低现金 | 贷款变化 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for plan in plans:
        e=plan['evaluations'];lines.append(f'| {plan["name"]} | {e[0]["profit_5_to_6"]:,.2f} | {e[1]["profit_5_to_6"]:,.2f} | {e[2]["profit_5_to_6"]:,.2f} | {min(z["sampled_minimum_cash"] for z in e[:3]):,.2f} | {plan["x"][19]*100:,.0f} |')
    lines+=['','稳健候选以不利情景利润为目标；中性和COUNTRY候选按各自模型得分，较高的模型利润不能证明更准确。现金仅检查年末及回合初投资融资后，不保证任意时点现金。正式6仍用观察需求后的生产调整政策，不代表完整未来策略已优化。','',
        '## 全部42字段（按网页子页顺序）','',
        '20项数值决策表示折合14个可识别自由度，另推导两产品物流排序；营销细分按当前构成分摊，同合计在主模型内等价。无新招标4项和不可用分包1项标记未求解；13项预估按对应方案重算或列外生假设，不能宣称全参数全局最优。','']
    byplan=[{r['row']:r for r in decisions if r['plan']==p['name']} for p in plans[1:]]
    sections=[('需求',ORDER[:10]),('生产',ORDER[10:20]),('销售',ORDER[20:36]),('物流',ORDER[36:40]),('财务',ORDER[40:])]
    for title,rr in sections:
        lines += [f'### {title}','','| 参数 | 单位 | 当前 | 中性 | COUNTRY | 稳健（建议） | 优化状态及依据 |','| --- | --- | ---: | ---: | ---: | ---: | --- |']
        for row in rr:
            a,b,c=[r[row] for r in byplan];label='／'.join(str(c[k]) for k in ['section','product','label'] if c[k])
            lines.append(f'| {label} | {c["unit"]} | {fmt(c["current"])} | {fmt(a["suggested"])} | {fmt(b["suggested"])} | {fmt(c["suggested"])} | {c["status"]}：{c["reason"]} |')
        lines.append('')
    lines+=['[完整决策CSV](decisions.csv) · [JSON](decisions.json)。','',
        '## 三候选全部42字段敏感性','',
        '中性/稳健列参考中性，COUNTRY列参考COUNTRY。每格“测试值：Δ利润／Δ三核心最低利润；三核心最低现金”，金额千美元。▲表示任一核心情景约束失效。一次改一个字段，其余不重优化。价格±10%；营销/研发/运营±10%且至少50；产能配比±5个百分点；机器按原档位、贷款±10%且至少1000；外生增长±5个百分点；需求/效率误差±10%；利率±1个百分点。越界截断，零变化不代表不敏感。','',
        '| 字段 | 中性：减少／增加 | COUNTRY：减少／增加 | 稳健：减少／增加 |','| --- | --- | --- | --- |']
    for row in ORDER:
        cells=[]
        for plan in plans[1:]:
            tests=[r for r in sens if r['row']==row and r['plan']==plan['name']]
            cells.append('；'.join('N/A未求解' if r['delta_profit'] is None else f'{fmt(r["test"])}：{r["delta_profit"]:+,.1f}／{r["delta_worst"]:+,.1f}；现{r["minimum_cash"]:,.1f}'+('▲' if not r['core_feasible'] else '')+('（边界）' if r['status']=='边界截断' else '') for r in tests))
        f=fields[row];lines.append('| '+'／'.join(str(f[k]) for k in ['section','product','label'] if f[k])+' | '+' | '.join(cells)+' |')
    lines+=['','[敏感性CSV](sensitivity_all_candidates.csv) · [JSON](sensitivity_all_candidates.json)。','',
        '## 全部假设压力比较','', '| 情景 | 当前基准利润 | 中性 | COUNTRY | 稳健 | 稳健最低现金 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for i,c in enumerate(cfgs):
        ev=[p['evaluations'][i] for p in plans];lines.append(f'| {c["name"]} | '+' | '.join(f'{e["profit_5_to_6"]:,.2f}' for e in ev)+f' | {ev[-1]["sampled_minimum_cash"]:,.2f} |')
    lines+=['','## 继承条件、验证及复现','',
        '- 两产品泰国+7%、印尼−5%；机器本期立即生效、正式6容量衰减15%；班次工资1/1.65/2.56、工资43.5。材料比例迁移、运输、库存、税29%、利息、应收应付、固定资产及解聘等完整公式沿用t5v1。主情景无新增招标和分包，未来无新机器/融资。研发与运营均按实际支出计成本；历史有效存量不重复支出。',
        '- 售价沿用正式4正价支持域；一般营销合计≤2700、设计师≤3840；研发0—2600、运营0—1620；机器梁0—20、连接件0—400且步长20；长贷变化−10200至10000且步长100；配比0—100%。这些是分析支持范围，不能当作官方全部约束。',
        '- 新研发关系实测0/1200/2600及0/381/2600；运营0/900/1200。运营1200以上及跨回合均有映射外推；曲线有效坐标超过原曲线支持域同样属于外推。本版不因拟合图形良好而宣称经营预测准确。',
        '- 本次只拟合投入映射，没有重训历史需求或效率技术尺度。保留t5v1营销合计代理、需求重要性迁移、未来市场及曲线、税亏/订单/自动短贷机制限制。费用代理及历史横轴使用误差没有因本次接线自动消失，旧需求系数并非已修复的无偏估计。',
        f'- 校验：{validation["frozen_replays"]}组独立运行回放、标量/批量一致、非法输入拒绝、研发/运营响应方向、数量与财务恒等式通过；当前网页预算5232与本地复算差{budget_error:.4f}千美元，仅为财务复现，不代表候选预算获平台验证。',
        '- 源码检查未找到服务端转换函数；试验失败的DOM填值未参与校准。最终恢复证据及全部个人/小组数值见sources/probe；原始前端业务代码为只读下载，不执行。',
        '', '[运行说明](../../../code/model_v2/t5v2_README.md) · [注册表](models_full.json) · [完整结果](full_result.json) · [旧方案同模型回放](t5v1_plan_replay.json) · [验收](validation.json) · [版本清单](version_manifest.json)。','',
        '![三项投入恢复后页面](sources/probe/restored.png)']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    readme=ROOT/'code/model_v2/t5v2_README.md'
    if not readme.exists():
        with readme.open('x',encoding='utf-8') as f:f.write('# t5v2独立冻结应用\n\n以t5v1为基线，新增网页区间验证的投入→有效投资映射，连接原需求、效率、生产及财务链。原版只读保留。\n\n[完整报告](../../'+OUT.relative_to(ROOT).as_posix()+'/report.md) · [映射参数](../../'+OUT.relative_to(ROOT).as_posix()+'/effective_investment_models.json)。\n\n```powershell\npython code/model_v2/t5v2.py --bundle '+OUT.relative_to(ROOT).as_posix()+'\n```\n\n可用`--request`传入与example_request.json同结构的请求。仅依赖NumPy，不访问平台、不训练。正式6及历史有效存量归一化仍为显式情景，营销细分、招标、分包未完全求解。\n')
    docs=['README.md','code/model_v2/README.md'];(OUT/'documents_before').mkdir(exist_ok=True)
    changes={}
    for name in docs:
        path=ROOT/name;backup=OUT/'documents_before'/name.replace('/','__')
        if (OUT/'document_changes.json').exists():
            prior=read(OUT/'document_changes.json')
            if name in prior and sha(path)==prior[name]['after']:
                changes[name]=prior[name];continue
        if not backup.exists():shutil.copy2(path,backup)
        assert sha(path)==sha(backup), 'Shared index changed since backup'
        old=path.read_text(encoding='utf-8');changes[name]={'before':sha(path)}
        if name=='README.md':
            marker='| 最新条件优化版本 | **t5v1**：'
            assert marker in old
            old=old.replace(marker,'| 最新条件优化版本 | **t5v2**：[完整建议与敏感性]('+OUT.relative_to(ROOT).as_posix()+'/report.md)、[运行说明](code/model_v2/t5v2_README.md) | 正式5研发/运营投入→有效投资区间验证后接入完整计算链；三候选重新求解、42字段敏感性重算。正式6及历史基准归一化仍属情景，t5v1原版哈希不变。 |\n| 前一条件优化版本 | **t5v1**:',1)
            start=old.index('正式5最新决策分析：');end=old.index('\n\n',start)
            old=old[:start]+'正式5最新决策分析：[t5v2有效投资映射与完整条件决策]('+OUT.relative_to(ROOT).as_posix()+'/report.md)。研发采用0.75×当期＋0.50×上期、运营采用当期＋0.35×上期，来源为网页区间验证而非服务端源码。三候选、需求效率及现金一致重算；正式6映射与历史归一化仍有假设。t5v1及历史结果保留。'+old[end:]
        else:old=old.replace('## 当前工作入口\n','## 当前工作入口\n\n- [t5v2有效投资接入](t5v2_README.md)：t5v1基础上新增研发/运营映射，三候选及42字段敏感性独立重算。\n',1)
        path.write_text(old,encoding='utf-8');changes[name]['after']=sha(path)
    save('document_changes.json',changes)
    for filename in ['report.md']:
        text=(OUT/filename).read_text(encoding='utf-8');width=None
        for line in text.splitlines():
            if line.startswith('|'):
                n=len(line.split('|'));assert width is None or n==width,(filename,line);width=n
            else:width=None
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if link!='version_manifest.json':assert (OUT/link).resolve().exists(),link
    assert all(sha(ROOT/p)==h for p,h in preservation.items())
    with (OUT/'work_log.md').open('a',encoding='utf-8') as f:f.write('\n\n完成：3条映射与留出区间检查通过，三候选×42字段、全部情景、冻结回放及预算核验通过。网页三项已恢复，个人和小组数值与初始一致。t5v1原版哈希不变。DOM fill未保存尝试排除，原生输入后失焦保存成功；一次额外图表读取超时后补读成功。独立业务预测验证未完成，正式6与历史归一化假设保留。\n')
    save('version_manifest.json',dict(version='t5v2',base_version='t5v1',outputs={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='version_manifest.json'},runtime={'code/model_v2/t5v2.py':sha(ROOT/'code/model_v2/t5v2.py')},documents=changes))
    (ROOT/'work/t5v2_active_run.txt').write_text(OUT.relative_to(ROOT).as_posix(),encoding='utf-8')
    print(json.dumps(validation,ensure_ascii=False),flush=True)
    print('COMPLETE',OUT,flush=True)

if __name__=='__main__':
    if '--finish' in sys.argv:
        import t5v2
        registry=read(OUT/'models_full.json');m=t5v2.ApplicationModel();m.__dict__.update(t5v2.decode(registry['application_state']));m.r={'risk':registry['risk']};m.current={int(k):v for k,v in m.current.items()}
        fields={r['row']:r for r in read(SOURCE/'decisions.json') if r['plan']=='稳健利润候选'}
        shutil.copy2(Path(__file__),OUT/'code_snapshot/build_t5v2.py')
        make_delivery(m,registry,read(OUT/'full_result.json'),fields,t5v2,read(OUT/'t5v1_before_hashes.json'))
    else:main()
