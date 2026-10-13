"""Build source-linked inputs and reconcile accounts; no network or decision writes."""
import csv
import hashlib
from datetime import datetime, timezone
from collections import defaultdict

from archive_and_report import table_rows, number, write_json
from audit_incremental import ROOT, RAW, load, classify


def production_and_delivery(capacity, allocation, efficiency, demand, priority, wage,
                            second_shift, third_shift, previous_workers, attrition, severance):
    assert capacity > 0 and efficiency > 0 and 0 <= allocation <= 100
    assert len(demand) == 2 and all(d >= 0 for d in demand)
    assert sorted(priority) == [0, 1] and 0 <= attrition <= 1
    # shortcut: zero opening inventory and no bulk orders, extend when either appears.
    q = min(capacity * allocation / 100, sum(demand))
    bands = [min(q,capacity/3), min(max(q-capacity/3,0),capacity/3), max(q-2*capacity/3,0)]
    payroll = sum(a*b for a,b in zip(bands,[1,second_shift,third_shift])) / efficiency * wage
    workers = q / efficiency
    firing = max(previous_workers*(1-attrition)-workers,0)*wage*severance
    sales, remaining = [0,0], q
    for market in priority:
        sales[market] = min(demand[market],remaining)
        remaining -= sales[market]
    return dict(production=q, workers=workers, payroll=payroll, firing=firing, sales=sales)


def main():
    inputs, reports, checks, markets, sources = [], {}, [], [], {}
    for path in sorted(RAW.glob('*.json')):
        data = load(path.stem)
        if 'snapshot' not in data:
            continue
        phase, round_no, kind = classify(path.stem)
        sources['raw/'+path.name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            captured_at=data.get('captured_at'), phase=phase, round=round_no, kind=kind)
        occurrences = defaultdict(int)
        parsed = table_rows(data['snapshot'])
        for row in parsed:
            if not row['cells']:
                continue
            label = row['cells'][0]
            occurrence = occurrences[label]
            occurrences[label] += 1
            inputs.append(dict(file='raw/' + path.name, line=row['line'], label=label,
                               occurrence=occurrence, cells=row['cells'], phase=phase,
                               round=round_no, kind=kind, captured_at=data.get('captured_at'),
                               source_url=data.get('source_url')))
        reports[path.stem] = parsed

    def field(name, label, column, occurrence=0):
        matches = [r for r in reports[name] if len(r['cells']) > column and r['cells'][0] == label]
        assert len(matches) > occurrence, (name, label, occurrence)
        row = matches[occurrence]
        assert len(row['cells']) > column, (name, label, column)
        return dict(value=number(row['cells'][column]), file='raw/' + name + '.json',
                    line=row['line'], column=column, label=label, occurrence=occurrence)

    def reconcile(case, metric, formula, terms, expected, tolerance):
        error = expected['value'] - formula(*[t['value'] for t in terms])
        checks.append(dict(case=case, metric=metric, calculated=expected['value']-error,
                           observed=expected['value'], error=error, tolerance=tolerance,
                           passed=abs(error) <= tolerance, inputs=terms, target=expected))

    teams = None
    history = []
    for name in ['initial0_printable', 'practice1_printable', 'practice2_printable']:
        headers = [r['cells'] for r in reports[name] if len(r['cells']) == 10 and '营销团队' in r['cells']]
        assert headers and all(h == headers[0] for h in headers), name
        if teams is None:
            teams = headers[0]
        assert teams == headers[0] and len(set(teams)) == 10
        phase, round_no, _ = classify(name)
        for col, team in enumerate(teams, 1):
            f = lambda label, occurrence=0: field(name, label, col, occurrence)
            case = name + '/' + team
            record = dict(phase=phase, round=round_no, team=team, kind='actual_result', fields={})
            for key, label, occurrence in [
                ('production', '生产规模, 千单位', 0), ('capacity', '生产能力, 千单位', 0),
                ('efficiency', '生产效率, 千单位/人', 0), ('workers', '生产线人工数量', 0),
                ('wage', '生产工资合计, 千 美元', 0), ('general_marketing', '一般营销', 0),
                ('designer_marketing', '设计师营销', 0), ('rd', '研发', 0),
                ('operations', '运营改进', 0), ('profit', '本回合利润, 千 美元', 0),
                ('cumulative_profit', '累计收益, 千 美元', 0), ('cash', '现金及现金等价物', 0),
                ('short_debt', '短期贷款', 0), ('inventory', '复合梁', 0),
                ('building_capex', '厂房', 2), ('machine_capex', '机器', 2)]:
                record['fields'][key] = f(label, occurrence)
            history.append(record)
            sales, prices = [], []
            for country in ['泰国', '印尼']:
                sale, demand, price = f(country, 0), f(country, 1), f(country + ', 美元')
                sales.append(sale)
                prices.append(price)
                markets.append(dict(phase=phase, round=round_no, team=team, market=country,
                                    usable_for_fit=phase == 'practice', price=price,
                                    sales=sale, demand=demand, unmet=f(country, 2),
                                    quantity_unit='千单位', price_unit='美元/单位',
                                    supply_limited=demand['value']-sale['value'] > .015))
                assert sale['value'] <= demand['value'] + .015
                reconcile(case, country+'需求守恒', lambda d, s: d-s,
                          [demand, sale], f(country, 2), .015)
            revenue_tolerance = sum(p['value'] * .005 for p in prices) + .51
            reconcile(case, '销售收入', lambda a,b,p,q:a*p+b*q,
                      sales+prices, f('净销售额'), revenue_tolerance)
            reconcile(case, '数量守恒', lambda a,b,c:a+b+c,
                      sales+[f('大客户订单')], f('生产规模, 千单位'), .025)
            reconcile(case, '毛利', lambda r,c:r-c,
                      [f('净销售额'), f('可变成本总和')], f('毛利', 1), 1.01)
            reconcile(case, 'EBITDA', lambda g,m,o:g-m-o,
                      [f('毛利', 1), f('营销和销售成本总和'), f('杂费成本总和')],
                      f('税息折旧及摊销前利润（EBITDA）'), 2.01)
            reconcile(case, 'EBIT', lambda e,b,m:e-b-m,
                      [f('税息折旧及摊销前利润（EBITDA）'), f('厂房',0), f('机器',0)],
                      f('息税前利润（EBIT）'), 2.01)
            reconcile(case, '税前利润', lambda e,i,l,s:e+i-l-s,
                      [f('息税前利润（EBIT）'), f('利息收入'), f('长期贷款利息'), f('短期贷款利息')],
                      f('税前利润'), 2.01)
            reconcile(case, '税后利润', lambda p,t:p-t,
                      [f('税前利润'), f('直接税')], f('本回合利润, 千 美元'), 1.01)
            reconcile(case, '资产负债平衡', lambda a:a,
                      [f('资产总计')], f('负债与所有者权益总计'), .01)
            reconcile(case, '期末现金', lambda c,o,k,l,s:c+o-k+l+s,
                      [f('1月1日的流动资产'), f('经营活动现金流'), f('资本支出总计'),
                       f('长期贷款变化(增加 + / 减少 -)'), f('短期贷款变化(增加 + / 减少 -)')],
                      f('12月31日的流动资产'), 2.01)

    for name in ['round1_budget_income', '20261011_user_probe_B_budget_income']:
        f = lambda label: field(name, label, 1)
        reconcile(name, '预算EBITDA', lambda r,c,m,o:r-c-m-o,
                  [f('净销售额'), f('可变成本总和'), f('营销和销售成本总和'), f('杂费成本总和')],
                  f('税息折旧及摊销前利润（EBITDA）'), 2.01)
        reconcile(name, '预算EBIT', lambda e,b,m:e-b-m,
                  [f('税息折旧及摊销前利润（EBITDA）'), f('厂房'), f('机器')], f('运营利润 (EBIT)'), 2.01)
        reconcile(name, '预算税前利润', lambda e,i,l,s:e+i-l-s,
                  [f('运营利润 (EBIT)'), f('利息收入'), f('长期贷款利息'), f('短期贷款利息')],
                  f('税前利润'), 2.01)

    for round_no in [1,2]:
        name = '20261011_practice'+str(round_no)+'_checklist'
        actual = next(r for r in history if r['phase']=='practice' and r['round']==round_no and r['team']=='营销团队')
        actual['executed_group_decisions'] = [r for r in inputs if r['file']=='raw/'+name+'.json']
        actual['decision_column'] = 1
        for label, key, occurrence in [('泰国, 美元',None,0), ('印尼, 美元',None,0),
                                       ('复合梁','rd',1), ('泰国','operations',3)]:
            value = field(name,label,1,occurrence)
            if key:
                target = actual['fields'][key]
            else:
                target = next(m['price'] for m in markets if m['phase']=='practice' and m['round']==round_no and m['team']=='营销团队' and m['market']==label.split(',')[0])
            reconcile(name, '已执行小组策略配对/'+label, lambda x:x, [value], target, .01)

    for team in teams:
        previous = next(r for r in history if r['team']==team and r['round']==0)
        for round_no in [1,2]:
            current = next(r for r in history if r['team']==team and r['round']==round_no)
            reconcile('practice'+str(round_no)+'/'+team, '累计收益递推', lambda a,b:a+b,
                      [previous['fields']['cumulative_profit'], current['fields']['profit']],
                      current['fields']['cumulative_profit'], 1.01)
            previous = current

    assert production_and_delivery(18,100,.2,[20,20],[1,0],28,1.65,2.56,0,.1,.35)['sales'] == [0,18]
    assert abs(production_and_delivery(18,100,.2,[20,20],[0,1],28,1.65,2.56,0,.1,.35)['payroll'] - 4376.4) < 1e-8
    assert production_and_delivery(18,100,.2,[1,1],[0,1],28,1.65,2.56,0,.1,.35)['production'] == 2
    assert production_and_delivery(18,0,.2,[1,1],[0,1],28,1.65,2.56,0,.1,.35)['production'] == 0
    invalid_rejected = False
    try:
        production_and_delivery(18,101,.2,[1,1],[0,1],28,1.65,2.56,0,.1,.35)
    except AssertionError:
        invalid_rejected = True
    assert invalid_rejected

    def parameter(label):
        return field('round1_outlook',label,1)

    mechanistic = []
    for demand_file, income in [('round1_demand','round1_budget_income'),
                                ('20261011_user_probe_B_demand','20261011_user_probe_B_budget_income')]:
        sources = [field('round1_production','产能, 千单位',1),
                   field('round1_production','产能分配, %',1),
                   field('round1_production','生产效率, 千单位/人',1),
                   field('initial0_printable','生产线人工数量',6)]
        pars = [parameter(label) for label in ['泰国','两班倒','三班倒',
                '年人员离职率（without costs），%','裁员成本，占薪资%',
                '复合梁','泰国 -> 泰国','泰国 -> 印尼']]
        ds = [field(demand_file,country,4) for country in ['泰国','印尼']]
        ps = [field('round1_sales_'+country,'每单位价格, 美元',1) for country in ['thailand','indonesia']]
        demand = [d['value'] for d in ds]
        result = production_and_delivery(*[s['value'] for s in sources[:3]],demand,[0,1],
                *[p['value'] for p in pars[:3]],sources[3]['value'],
                pars[3]['value']/100,pars[4]['value']/100)
        sources += pars + ds + ps
        for metric, predicted, label, tolerance in [
            ('工资公式',result['payroll'],'工厂员工成本',.51),
            ('解聘公式',result['firing'],'解聘费',.55),
            ('物流分配收入',sum(s*p['value'] for s,p in zip(result['sales'],ps)),'净销售额',.51),
            ('物流分配运输',sum(s*p['value'] for s,p in zip(result['sales'],pars[6:])),'运输',.51)]:
            observed = field(income,label,1)
            reconcile(income,metric,lambda:predicted,[],observed,tolerance)
            checks[-1]['inputs'] = sources
        mechanistic.append(dict(case=income, demand=demand, output=result,
                               raw_material_base_cost=result['production']*pars[5]['value'],
                               reported_materials=field(income,'原材料购买',1),
                               material_residual=field(income,'原材料购买',1)['value']-result['production']*pars[5]['value']))

    failures = [c for c in checks if not c['passed']]
    write_json(ROOT/'结构化模型输入.json', dict(generated_at=datetime.now(timezone.utc).isoformat(),
        live_state_verified=False, history=history, markets=markets, source_rows=inputs, sources=sources,
        units=dict(finance='千美元', quantity='千单位', price='美元/单位', efficiency='千单位/人'),
        limitations=['预算不作为实际需求标签', '初始0不作为独立训练样本',
                     '竞争者国别营销缺失；总营销不得冒充国别营销',
                     '正式1重置初始状态，不延续练习2资金与亏损', '本脚本离线运行，输入取原件采集时点；网页核对见最新试验记录']))
    write_json(ROOT/'模型回算核验.json', dict(check_count=len(checks), failed_count=len(failures),
        checks=checks, production_delivery_model=mechanistic,
        limitations=['财务恒等式回算使用报表成本，不等于独立预测所有成本',
                     '工资与解聘公式仅在两个同产量预算上验证，跨班次尚未平台验证',
                     '原材料基础公式少4千美元，不能将900改成反推系数后称官方参数',
                     '利息、风险溢价、税亏与投资折旧机制仍需单独校准']))
    with (ROOT/'历史市场建模样本.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['阶段','回合','团队','市场','可拟合','价格_美元','需求_千单位','销量_千单位','缺货', '源文件','需求行','价格行'])
        writer.writerows([m['phase'],m['round'],m['team'],m['market'],m['usable_for_fit'],
                          m['price']['value'],m['demand']['value'],m['sales']['value'],m['supply_limited'],
                          m['demand']['file'],m['demand']['line'],m['price']['line']] for m in markets)
    assert len(history)==30 and len(markets)==60
    assert len([m for m in markets if m['usable_for_fit']])==40
    assert not failures, failures
    print(f'{len(history)} team-rounds, {len(markets)} market rows; {len(checks)} checks passed')


if __name__ == '__main__':
    main()
