"""Source-linked Cesim models, fits, forward validation and decision scenarios, in Python.
Run: python code/stepwise_model.py. Reads archives only; never writes browser decisions.
"""
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import least_squares, lsq_linear

from archive_and_report import number, table_rows, write_json
from audit_incremental import ROOT, cells, load
from build_model_inputs import production_and_delivery
from fit_demand import metrics

NS = {'s': 'http://www.w3.org/2000/svg'}
COUNTRIES = ['泰国', '印尼']
NAMES = ['泰国价格弹性', '印尼价格弹性', '合计一般营销代理', '合计设计师营销代理', '研发曲线作用']


def source(name, label, column=1, occurrence=0):
    rows = [r for r in table_rows(load(name)['snapshot']) if len(r['cells']) > column and r['cells'][0] == label]
    assert len(rows) > occurrence and len(rows[occurrence]['cells']) > column, (name, label, column, occurrence)
    row = rows[occurrence]
    return dict(value=number(row['cells'][column]), file='raw/'+name+'.json',
                line=row['line'], column=column, label=label, occurrence=occurrence)


def chart_points(svg):
    """Decode rendered line vertices against the rendered axes, without reading JS state."""
    tree = ET.fromstring(svg)
    texts = tree.findall('.//s:text', NS)
    x_ticks = [(float(t.attrib['x']), float(''.join(t.itertext()))) for t in texts
               if t.attrib.get('y') == '226' and re.fullmatch(r'\d+(\.\d+)?', ''.join(t.itertext()))]
    assert len(x_ticks) >= 8
    # shortcut: integer tick labels introduce sub-unit x error; replace with exported values if available.
    slope, intercept = np.polyfit(*np.array(x_ticks).T, 1)
    plot = next(e for e in tree.findall('.//s:rect', NS)
                if e.attrib.get('fill') == '#eeeeee' and float(e.attrib.get('width', 0)) > 500
                and float(e.attrib.get('height', 0)) > 100)
    top, height = float(plot.attrib['y']), float(plot.attrib['height'])
    y_max = max(float(''.join(t.itertext())) for t in texts
                if t.attrib.get('x') == '35.4' and re.fullmatch(r'\d+(\.\d+)?', ''.join(t.itertext())))
    path = next(p.attrib['d'] for p in tree.findall('.//s:path', NS)
                if p.attrib.get('stroke') == '#ffcd34' and len(p.attrib.get('d', '')) > 500)
    pairs = re.findall(r'[ML](-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', path)
    points = np.array([(slope*float(x)+intercept, (top+height-float(y))/height*y_max)
                       for x, y in pairs if float(x) >= float(plot.attrib['x'])])
    assert len(points) == 200 and np.all(np.diff(points[:, 0]) > 0)
    points[0, 0] = 0
    assert np.all(points >= 0) and np.all(np.diff(points[:, 1]) >= 0)
    return points, dict(x_tick_rounding='±0.5千美元/刻度，坐标线性标定', ymax=y_max,
                        axis_max=float(points[-1, 0]), representation='rendered SVG vertices, not independent experiments')


def curve_value(x, params, form):
    x = np.maximum(np.asarray(x), 0)
    if form == 'power':
        a, b, c, d = params
        return a + b*(x+c)**d
    a, b, c = params
    return a + b*x/(c+x)


def fit_curves():
    archive = '20261011_model_v2_round1_production_svg'
    graphs = load(archive)['graphs']
    result = {}
    for label, keyword, form in [('rd', '需求乘数', 'power'), ('operations', '效率乘数', 'saturation')]:
        svg = next(s for s in graphs if keyword in s)
        points, axes = chart_points(svg)
        x, y = points.T
        train, test = np.arange(0, len(x), 2), np.arange(1, len(x), 2)
        bounds = ([-2,0,.0001,.001],[2,10,1000,1]) if form=='power' else ([0,0,.001],[2,3,100000])
        initial = [.1,.2,.5,.2] if form == 'power' else [.45, .8, 300]
        fit = least_squares(lambda p: curve_value(x[train], p, form)-y[train], initial,
                            bounds=bounds, max_nfev=5000, xtol=1e-12, ftol=1e-12, gtol=1e-12)
        assert fit.success
        final = least_squares(lambda p: curve_value(x, p, form)-y, fit.x, bounds=bounds,
                              max_nfev=5000, xtol=1e-12, ftol=1e-12, gtol=1e-12)
        result[label] = dict(form=form, parameters=final.x.tolist(), axes=axes,
                             held_vertex_mae=float(np.mean(abs(curve_value(x[test], fit.x, form)-y[test]))),
                             held_vertex_max_error=float(max(abs(curve_value(x[test], fit.x, form)-y[test]))),
                             formula='a+b*(x+c)**d' if form == 'power' else 'a+b*x/(c+x)',
                             source='raw/'+archive+'.json', points=points.tolist(),
                             limit='同一条可见曲线上的交错顶点检验，只验证近似公式，不是外部需求验证')
    return result


def demand_features(rows, curves):
    x = np.zeros((len(rows), len(NAMES)))
    for i, r in enumerate(rows):
        c = COUNTRIES.index(r['market'])
        x[i, c] = -np.log(r['price']/[1800, 2000][c])
        x[i, 2:4] = np.log1p(np.array([r['general'], r['designer']])/1000)
        # Prior initial0 RD is also known; unlike v1 it is not silently zeroed in round1.
        effective_rd = r['rd'] + .5*r['previous_rd']
        x[i, 4] = np.log(curve_value(effective_rd, curves['rd']['parameters'], 'power'))
    return x


def fit_share(rows, x, train, penalty):
    a, b = [], []
    for round_no in sorted({rows[i]['round'] for i in train}):
        for country in COUNTRIES:
            ids = [i for i in train if rows[i]['round'] == round_no and rows[i]['market'] == country]
            if len(ids) < 2:
                continue
            yy = np.log([rows[i]['demand'] for i in ids])
            # Group centering eliminates unobserved round/country intercepts using training labels only.
            a.extend(x[ids]-x[ids].mean(axis=0))
            b.extend(yy-yy.mean())
    assert len(a) > len(NAMES)
    result = lsq_linear(np.vstack([a, np.sqrt(penalty)*np.eye(len(NAMES))]),
                        np.r_[b, np.zeros(len(NAMES))], bounds=(0, np.inf), tol=1e-12)
    assert result.success
    return result.x


def shares(x, beta):
    utility = x@beta
    weight = np.exp(utility-max(utility))
    return weight/sum(weight)


def share_cv(rows, x, train, penalty):
    errors = []
    for team in sorted({rows[i]['team'] for i in train}):
        fit_ids = [i for i in train if rows[i]['team'] != team]
        beta = fit_share(rows, x, fit_ids, penalty)
        for country in COUNTRIES:
            for rnd in sorted({rows[i]['round'] for i in train}):
                ids = [i for i in train if rows[i]['market'] == country and rows[i]['round'] == rnd]
                held = [j for j,i in enumerate(ids) if rows[i]['team'] == team]
                actual = np.array([rows[i]['demand'] for i in ids])
                prediction = shares(x[ids], beta)
                errors.extend(abs(actual[held]/sum(actual)-prediction[held]))
    return float(np.mean(errors))


def fit_demand_v2(data, curves):
    history = {(r['round'], r['team']): r for r in data['history']}
    rows = []
    for m in data['markets']:
        if not m['usable_for_fit']:
            continue
        h = history[m['round'], m['team']]['fields']
        previous = history[m['round']-1, m['team']]['fields']
        rows.append(dict(team=m['team'], round=m['round'], market=m['market'],
                         price=m['price']['value'], demand=m['demand']['value'],
                         general=h['general_marketing']['value'], designer=h['designer_marketing']['value'],
                         rd=h['rd']['value'], previous_rd=previous['rd']['value'],
                         source=m['demand'], supply_limited=m['supply_limited']))
    assert len(rows) == 40
    x = demand_features(rows, curves)
    penalties = [.01, .1, 1, 10]
    train = [i for i,r in enumerate(rows) if r['round']==1]
    scores = {p: share_cv(rows, x, train, p) for p in penalties}
    penalty = min(scores, key=scores.get)
    beta = fit_share(rows, x, train, penalty)
    records, totals = [], {}
    for country in COUNTRIES:
        initial = sum(m['demand']['value'] for m in data['markets'] if m['round']==0 and m['market']==country)
        prior = sum(r['demand'] for r in rows if r['round']==1 and r['market']==country)
        forecast_total = prior*(prior/initial)
        ids = [i for i,r in enumerate(rows) if r['round']==2 and r['market']==country]
        observed_total = sum(rows[i]['demand'] for i in ids)
        prediction = shares(x[ids], beta)
        totals[country] = dict(previous=prior, forecast=forecast_total, observed=observed_total,
                               formula='M1*(M1/M0)，仅一个已知历史增长率的朴素延续，非官方函数')
        for i,s in zip(ids,prediction):
            records.append(dict(team=rows[i]['team'], market=country, actual=rows[i]['demand'],
                                predicted=float(s*forecast_total), conditional_oracle_total_prediction=float(s*observed_total),
                                share=float(s), actual_share=rows[i]['demand']/observed_total,
                                baseline=forecast_total/len(ids), source=rows[i]['source']))
    y = np.array([r['actual'] for r in records])
    p = np.array([r['predicted'] for r in records])
    oracle = np.array([r['conditional_oracle_total_prediction'] for r in records])
    all_ids = list(range(len(rows)))
    full_scores = {p: share_cv(rows, x, all_ids, p) for p in penalties}
    full_penalty = min(full_scores,key=full_scores.get)
    full_beta = fit_share(rows,x,all_ids,full_penalty)
    nested = []
    for team in sorted({r['team'] for r in rows}):
        ids = [i for i,r in enumerate(rows) if r['team'] != team]
        inner = {p:share_cv(rows,x,ids,p) for p in penalties}
        chosen = min(inner,key=inner.get)
        bb = fit_share(rows,x,ids,chosen)
        for rnd in [1,2]:
            for country in COUNTRIES:
                group = [i for i,r in enumerate(rows) if r['round']==rnd and r['market']==country]
                pos = next(j for j,i in enumerate(group) if rows[i]['team']==team)
                actual_share = rows[group[pos]]['demand']/sum(rows[i]['demand'] for i in group)
                predicted_share = float(shares(x[group],bb)[pos])
                nested.append(dict(team=team,round=rnd,market=country,actual_share=actual_share,
                                   predicted_share=predicted_share,penalty=chosen))
    return dict(formula='u=-e_country*log(P/P0)+bg*log1p(Gtotal/1000)+bd*log1p(Dtotal/1000)+br*log(f_rd(R+0.5*Rprev)); share=exp(u)/sum(exp(u)); demand=M*share',
                coefficient_names=NAMES, frozen_round1_beta=beta.tolist(), selected_penalty=penalty,
                inner_training_share_mae=scores, all_practice_beta=full_beta.tolist(),full_penalty=full_penalty,
                forward=dict(model=metrics(y,p),baseline=metrics(y,np.array([r['baseline'] for r in records])),
                             conditional_oracle_total_only=metrics(y,oracle),records=records,market_totals=totals),
                nested_team_share_mae=float(np.mean([abs(r['actual_share']-r['predicted_share']) for r in nested])),
                nested_team_share_records=nested, input_rows=rows,
                limits=['国别营销缺失，合计投入仍是代理；不支持国别营销因果优化',
                        '验证使用回合结束后竞争者策略作为条件，正式竞争策略必须给定情景',
                        '真实市场总量未知；主验证用上期增长外推，不用验证期总量',
                        'oracle项使用验证期真实总量，只有份额诊断意义，不是可实现的预测误差',
                        '新特征和公式已受已知练习2资料启发；前向结果是回溯验证，未来正式结果才是外部验证',
                        '研发0.5延续为假设，曲线横轴有效投资到真实存量的映射未识别',
                        'softmax份额守恒是建模约束，不证明平台内部用softmax'])


def historical_accounts(data):
    records = []
    for h in data['history']:
        if h['round']==0:
            continue
        rnd, team = h['round'], h['team']
        col = next(m['demand']['column'] for m in data['markets'] if m['round']==rnd and m['team']==team)
        name = f'practice{rnd}_printable'
        previous = 'initial0_printable' if rnd==1 else 'practice1_printable'
        f = lambda label,occ=0: source(name,label,col,occ)
        prev = lambda label,occ=0: source(previous,label,col,occ)
        fields = {k:f(label,occ) for k,label,occ in [
            ('materials','原材料购买',0),('payroll','生产人员成本',0),('firing','解雇成本',0),
            ('revenue','净销售额',0),('ebitda','税息折旧及摊销前利润（EBITDA）',0),
            ('tax','直接税',0),('pretax','税前利润',0),('equity','股东权益合计',0),
            ('long_debt','长期贷款',0),('short_debt','短期贷款',0),('assets','资产总计',0),
            ('long_rate','长期贷款利率，%',0),('long_interest','长期贷款利息',0),
            ('short_interest','短期贷款利息',0),('cash_interest','利息收入',0),
            ('ar','应收帐款',0),('ap','应付账款',0),('cash','现金及现金等价物',1),
            ('building_depreciation','厂房',0),('machine_depreciation','机器',0),
            ('building_book','厂房',1),('machine_book','机器',1),
            ('building_capex','厂房',2),('machine_capex','机器',2)]}
        fields.update({k:prev(label,occ) for k,label,occ in [
            ('previous_workers','生产线人工数量',0),('previous_cash','现金及现金等价物',1),
            ('previous_ar','应收帐款',0),('previous_ap','应付账款',0),
            ('previous_building','厂房',1),('previous_machine','机器',1),
            ('previous_long','长期贷款',0),('previous_short','短期贷款',0),
            ('previous_equity','股东权益合计',0),('previous_pretax','税前利润',0)]})
        fields.update(h['fields'])
        fields['allocation_capacity'] = f('生产能力, 千单位')
        record = dict(round=rnd,team=team,fields=fields)
        records.append(record)
    return records


def finance_fits(accounts):
    checks = []
    def check(record,key,formula,predicted,tolerance):
        s = record['fields'][key]
        checks.append(dict(round=record['round'],team=record['team'],metric=key,formula=formula,
                           predicted=float(predicted),observed=s['value'],error=float(predicted-s['value']),
                           tolerance=tolerance,passed=abs(predicted-s['value'])<=tolerance,source=s))
    risk_train, risk_test = [], []
    for r in accounts:
        f = {k:v['value'] for k,v in r['fields'].items()}
        q, cap, workers = f['production'],f['capacity'],f['workers']
        e = q/workers
        output = production_and_delivery(cap,q/cap*100,e,[q,0],[0,1],28,1.65,2.56,
                                         f['previous_workers'],.1,.35)
        check(r,'payroll','分班次产量 / (q/工人数) * 28 * 班次系数',output['payroll'],6)
        check(r,'firing','max(上期人数*0.9-本期人数,0)*28*0.35',output['firing'],.7)
        check(r,'ar','收入*30/365',f['revenue']*30/365,.6)
        check(r,'ap','原材料*30/365',f['materials']*30/365,.6)
        check(r,'building_depreciation','期初厂房账面值*7%',f['previous_building']*.07,.6)
        check(r,'machine_depreciation','(期初机器账面值+本期投资)*15%',(f['previous_machine']+f['machine_capex'])*.15,.6)
        check(r,'building_book','期初厂房+800-折旧',f['previous_building']+800-f['building_depreciation'],1.1)
        check(r,'machine_book','期初机器+投资-折旧',f['previous_machine']+f['machine_capex']-f['machine_depreciation'],1.1)
        check(r,'long_interest','(期初长期贷款+期末长期贷款)/2*年利率',
              (f['previous_long']+f['long_debt'])/2*f['long_rate']/100,1.2)
        check(r,'cash_interest','(期初现金+期末现金)/2*1%',(f['previous_cash']+f['cash'])/2*.01,.6)
        previous_capacity = source('initial0_printable' if r['round']==1 else 'practice1_printable',
                                   '生产能力, 千单位',r['fields']['capacity']['column'])['value']
        check(r,'capacity','期初产能*85%+本期机器投资/100',previous_capacity*.85+f['machine_capex']/100,.011)
        loss = max(-f['previous_pretax'],0) if r['round']==2 else 0
        # Integer pretax/tax display adds at most 0.5*0.29+0.5=0.645 in profitable no-loss cases.
        check(r,'tax','max(本期税前利润-已知累计税亏,0)*29%',max(f['pretax']-loss,0)*.29,.65)
        # Initial phase0 is identical across firms; never count it as ten independent experiments.
        state = dict(team=r['team'],round=r['round'],equity_ratio=f['equity']/f['assets'],
                     leverage=(f['long_debt']+f['short_debt'])/f['equity'],
                     premium=f['long_rate']/100-[0,.03,.025][r['round']],source=r['fields']['long_rate'])
        (risk_train if r['round']==1 else risk_test).append(state)
    candidates = []
    for form in ['leverage_power','solvency_exponential']:
        def predict(p, rows):
            if form=='leverage_power':
                return p[0]*np.array([r['leverage'] for r in rows])**p[1]
            return p[0]*np.exp(-p[1]*np.array([r['equity_ratio'] for r in rows]))
        target = np.array([r['premium'] for r in risk_train])
        initial = [.002,2] if form=='leverage_power' else [.3,10]
        fit = least_squares(lambda p:predict(p,risk_train)-target,initial,bounds=([0,0],[10,30]),
                            xtol=1e-12,ftol=1e-12,gtol=1e-12)
        test_prediction = predict(fit.x,risk_test)
        candidates.append(dict(form=form,parameters=fit.x.tolist(),
                               training_mae_basis_points=float(np.mean(abs(predict(fit.x,risk_train)-target))*10000),
                               forward_mae_basis_points=float(np.mean(abs(test_prediction-np.array([r['premium'] for r in risk_test])))*10000),
                               test_records=[dict(r,predicted_premium=float(p)) for r,p in zip(risk_test,test_prediction)],
                               limit='期末权益/资产本身取决于利润，实际预测必须联立；此处是已知状态条件诊断'))
    train = [r for r in accounts if r['round']==1]
    uplift = np.median([r['fields']['materials']['value']/r['fields']['production']['value']-900 for r in train])
    material_records = []
    for r in accounts:
        f = {k:v['value'] for k,v in r['fields'].items()}
        base = 900 if r['round']==1 else 1053
        predicted = f['production']*(base+uplift)
        material_records.append(dict(round=r['round'],team=r['team'],predicted=predicted,
                                     observed=f['materials'],error=predicted-f['materials'],source=r['fields']['materials']))
    return dict(checks=checks,failed=[c for c in checks if not c['passed']],risk_candidates=candidates,
                materials=dict(uplift_usd_per_unit=float(uplift),formula='q*(公布原料单价+练习1估计的单位差额)',
                               records=material_records,forward_mae_kusd=float(np.mean([abs(r['error']) for r in material_records if r['round']==2])),
                               limit='差额为经验校准，不解释其内部组成；显示产量舍入误差约每条±5美元量级'),
                limits=['工资以实际q/工人数校验，不是独立生产效率预测',
                        '厂房自动投资800和折旧7%为当前场景经验关系，未进行平台投资扰动',
                        '税亏只覆盖两回合，没有亏后转盈样本；递延机制不能由零税证实',
                        '短贷非零只有营销团队练习2一条，无法唯一识别计息时点',
                        '风险拟合是给定期末状态的诊断，不用实际期末状态冒充可实现前瞻预测'])


def efficiency_fit(data,curves):
    history = {(r['round'],r['team']):r for r in data['history']}
    rows = []
    for h in data['history']:
        if h['round']==0:
            continue
        f = h['fields']
        previous = history[h['round']-1,h['team']]['fields']
        rows.append(dict(round=h['round'],team=h['team'],operations=f['operations']['value'],
                         previous_operations=previous['operations']['value'],
                         effective_observed=f['production']['value']/f['workers']['value'],
                         source=dict(production=f['production'],workers=f['workers'])))
    candidates = []
    for rho in [0,.5,1]:
        train = [r for r in rows if r['round']==1]
        ratio = [r['effective_observed']/curve_value(r['operations']+rho*r['previous_operations'],
                                                  curves['operations']['parameters'],'saturation') for r in train]
        technology = float(np.mean(ratio))
        observed = np.array([r['effective_observed'] for r in train])
        predicted = technology*curve_value(np.array([r['operations']+rho*r['previous_operations'] for r in train]),
                                          curves['operations']['parameters'],'saturation')
        test = [r for r in rows if r['round']==2]
        p = technology*curve_value(np.array([r['operations']+rho*r['previous_operations'] for r in test]),
                                  curves['operations']['parameters'],'saturation')
        candidates.append(dict(rho=rho,technology_scale=technology,training_mae=float(np.mean(abs(predicted-observed))),
                               forward_mae=float(np.mean(abs(p-np.array([r['effective_observed'] for r in test])))),
                               records=[dict(r,predicted=float(v)) for r,v in zip(test,p)]))
    # Freeze the previously specified 0.5 carry assumption, not the best hindsight forward score.
    return dict(formula='efficiency = technology_scale * f_operations(O+rho*Oprev)',rho=.5,
                selected=next(c for c in candidates if c['rho']==.5),sensitivity=candidates,input_rows=rows,
                limit='基底技术趋势与累积投资尚不可分离，正式1采用练习1技术尺度；正式以后不得自动恒定外推')


def accounts_from_state(state, decision, demand, efficiency, parameters, material_uplift):
    """Independent financial computation for the archived no-inventory/no-bulk scope."""
    assert state['inventory']==0 and state['short_debt']==0 and state['equity']>0
    assert all(v>=0 for v in demand) and all(p>0 for p in decision['prices'])
    assert decision['machine_investment']>=0 and decision['long_change']>=-state['long_debt']
    cap = state['capacity']*.85+decision['machine_investment']
    production = production_and_delivery(cap,decision['allocation'],efficiency,demand,decision['priority'],28,
                                         1.65,2.56,state['workers'],.1,.35)
    revenue = sum(s*p for s,p in zip(production['sales'],decision['prices']))
    materials = production['production']*(parameters['material_cost']+material_uplift)
    transport = sum(s*c for s,c in zip(production['sales'],[30,120]))
    marketing = sum(decision['general'])+sum(decision['designer'])+50
    overhead = 4000+production['firing']+decision['rd']+decision['operations']
    ebitda = revenue-materials-production['payroll']-transport-marketing-overhead
    machine_capex = decision['machine_investment']*100
    building_capex = 800
    machine_dep = (state['machine_book']+machine_capex)*.15
    building_dep = state['building_book']*.07
    ebit = ebitda-machine_dep-building_dep
    ar,ap = revenue*30/365,materials*30/365
    long_end = state['long_debt']+decision['long_change']
    long_interest = (state['long_debt']+long_end)/2*decision['long_rate']/100
    cash_before_interest = state['cash']+ebitda-long_interest+(state['ar']-ar)+(ap-state['ap'])\
                           -machine_capex-building_capex+decision['long_change']
    # Solve cash interest and income tax simultaneously with end cash; no actual future balance is used.
    cash_interest = state['cash']*.01
    for _ in range(100):
        pretax = ebit+cash_interest-long_interest
        tax = max(pretax-state['tax_loss'],0)*.29
        cash = cash_before_interest+cash_interest-tax
        updated = max((state['cash']+cash)/2,0)*.01
        if abs(updated-cash_interest)<1e-10:
            break
        cash_interest=updated
    assert abs(updated-cash_interest)<1e-8
    profit = pretax-tax
    short_needed = max(2000-cash,0)
    equity = state['equity']+profit
    assets = state['machine_book']+machine_capex-machine_dep+state['building_book']+building_capex-building_dep+ar+cash
    liabilities_equity = long_end+ap+equity
    assert abs(assets-liabilities_equity)<1e-6
    return dict(production=production,capacity=cap,sales=production['sales'],efficiency=efficiency,revenue=revenue,
                materials=materials,transport=transport,marketing=marketing,overhead=overhead,ebitda=ebitda,
                machine_capex=machine_capex,building_capex=building_capex,machine_depreciation=machine_dep,
                building_depreciation=building_dep,ebit=ebit,long_interest=long_interest,cash_interest=cash_interest,
                pretax=pretax,tax=tax,profit=profit,ar=ar,ap=ap,cash=cash,long_debt=long_end,
                short_debt_needed_before_unidentified_short_interest=short_needed,equity=equity,assets=assets,
                balance_error=assets-liabilities_equity,tax_loss_end=max(state['tax_loss']-max(pretax,0),0)+max(-pretax,0),
                fully_computed_in_scope=short_needed==0,
                limit='若现金低于2000，短贷计息未识别，该结果不是完整融资后利润；库存和大客户非零需扩展')


def current_state(data):
    name = 'initial0_printable'
    col = 6
    return {key:source(name,label,col,occ)['value'] for key,label,occ in [
        ('capacity','生产能力, 千单位',0),('workers','生产线人工数量',0),
        ('inventory','复合梁',0),('cash','现金及现金等价物',1),('ar','应收帐款',0),
        ('ap','应付账款',0),('machine_book','机器',1),('building_book','厂房',1),
        ('long_debt','长期贷款',0),('short_debt','短期贷款',0),('equity','股东权益合计',0)]} | {'tax_loss':0}


def live_decision():
    name = '20261011_model_v2_round1_checklist'
    personal=5
    decision = dict(prices=[source(name,c+', 美元',personal)['value'] for c in COUNTRIES],
                    general=[source(name,c,personal,0)['value'] for c in COUNTRIES],
                    designer=[source(name,c,personal,1)['value'] for c in COUNTRIES],
                    rd=source(name,'复合梁',personal,1)['value'],
                    operations=source(name,'泰国',personal,3)['value'],
                    allocation=source(name,'复合梁',personal,0)['value'],
                    machine_investment=source(name,'机器, 复合梁',personal)['value'],priority=[0,1],
                    long_change=source(name,'长期贷款变化(增加 + / 减少 -), 千 美元',personal)['value'],
                    long_rate=source(name,'长期贷款利率, %',personal)['value'])
    demand = [source(name,c,personal,occ)['value'] for c,occ in zip(COUNTRIES,[4,3])]
    efficiency = source(name,'复合梁',personal,3)['value']
    assert decision['prices']==[3000,2000] and demand==[2.5,11] and efficiency==.15
    return decision,demand,efficiency


def risk_linked_accounts(state,decision,demand,efficiency,parameters,uplift,risk):
    """Forecast the interest rate jointly with forecast end-state, without future actual inputs."""
    linked=dict(decision)
    rate=decision['long_rate']/100
    a,b=risk['parameters']
    for _ in range(100):
        linked['long_rate']=rate*100
        out=accounts_from_state(state,linked,demand,efficiency,parameters,uplift)
        if out['equity']<=0 or not out['fully_computed_in_scope']:
            return dict(status='OUTSIDE_IDENTIFIED_SCOPE',output=out)
        risk_premium=a*np.exp(-b*out['equity']/out['assets']) if risk['form']=='solvency_exponential' else a*(out['long_debt']/out['equity'])**b
        target=.03+risk_premium
        if abs(target-rate)<1e-10:
            break
        rate=(rate+target)/2
    assert abs(target-rate)<1e-8
    return dict(status='CONDITIONAL_FORECAST',predicted_long_rate_percent=float(rate*100),output=out,
                formula=risk['form'],limit='采用练习1训练的风险模型与预测期末状态联立，未经正式结果验证')


def field_registry():
    # Every visible input has an explicit computation path or an explicit identification limit.
    rows = [
        ('泰国/印尼市场增长预测','%','总市场需求→公司需求',
         'M_next/M_previous-1；仅以已知增长外推/前景情景给定','SCENARIO_NOT_IDENTIFIED','只有两练习回合；行业价格与经济趋势不能分离'),
        ('泰国/印尼公司需求预测','千单位','价格/营销/研发→份额→公司需求',
         'M*softmax(相对策略效用)','FITTED_CONDITIONAL','竞争者正式策略未知，营销只有合计代理'),
        ('下回合需求增长预测','%','市场增长→竞争份额→下回合需求',
         'D_next/D_current-1；市场规模与竞争情景传播','SCENARIO_NOT_IDENTIFIED','不直接沿用截图50%，正式2前景未开放'),
        ('生产效率预测','千单位/人','运营投入→效率乘数→人均产出',
         'tech*f_operations(O+0.5*Oprev)','FITTED_CONDITIONAL','科技基底与完整投资存量尚不可分离'),
        ('长期贷款利率预测','%','经营决策→期末权益/资产→风险溢价→利率',
         '基准3%+练习1拟合风险溢价，与Python财务联立','FITTED_CONDITIONAL','有条件拟合不是平台官方公式；短贷分支未识别'),
        ('泰国/印尼售价','美元/单位','价格→份额/销量→收入/利润',
         '候选价格网格→需求→生产销售→财务→情景比较','MODELED_SCENARIOS','训练范围内关联效应；没有六回合最优证明'),
        ('泰国/印尼一般营销','千美元','营销→需求效用，同时计入费用',
         '合计营销的log1p代理；费用按两国求和','PARTIALLY_IDENTIFIED','两国分配未识别，不分别优化国别营销'),
        ('泰国/印尼设计师营销','千美元','客户投入→需求效用，同时计入费用',
         '合计设计师营销的log1p代理；费用按两国求和','PARTIALLY_IDENTIFIED','两国分配与延续效应未识别'),
        ('大客户报价/设计师营销','美元/单位；千美元','中标→下一回合交付→利润/约束',
         '正式1可投标量0，因此当前不参与；未来评分仅保留价格/研发/营销候选结构',
         'CURRENT_ZERO_ORDER','无中标样本，不能拟合门槛或权重'),
        ('交货优先级','次序','可售供给→按优先级分配销量',
         '依次min(需求,剩余供给)；候选按价格减运输排序','CALIBRATED_CURRENT','零初库存/零大客户的两国范围'),
        ('产能分配','%','需求与产能→产量→班次/用工',
         'q=min(C*allocation/100,sum(D))；allocation候选=min(sum(D)/C,1)*100',
         'CALIBRATED_CURRENT','本批价格下各班次边际贡献为正；其他价格须重新算边际利润'),
        ('机器投资','千单位','投资→当期产能/资产→折旧→现金→下期产能',
         'C=0.85*Cprev+I；capex=100*I；机器折旧=15%*(账面期初+capex)',
         'HISTORICALLY_VALIDATED','未来利用率/行业机器价格未知，不能独立求六回合投资最优'),
        ('运营改进','千美元','即时/累积效率提升→工人/工资，同时计入费用',
         '0.45+0.75*x/(400.106+x)，x=O+rho*Oprev为假设','CURVE_AND_HISTORY_FIT','可见曲线有效投资映射未独立识别'),
        ('研发','千美元','即时/累积需求乘数→份额，同时计入费用',
         '拟合平移幂曲线；有效投入R+rho*Rprev为假设','CURVE_AND_SHARE_FIT','对真实需求的国别权重与未来效应未完全识别'),
        ('长期贷款增减','千美元','融资→长期余额/利息→现金→风险',
         'L_end=L_start+change；利息=平均余额*利率；不足现金触发短贷待识别',
         'CALIBRATED_LONG_ONLY','低于最低现金的融资后完整利润不输出为确定值'),
    ]
    return [dict(field=f,unit=u,steps=s,formula=e,status=st,limit=l) for f,u,s,e,st,l in rows]


def counterfactuals(data,curves,demand_fit,efficiency_model,finance):
    """One-input-at-a-time model sensitivity, explicitly not live platform experiments."""
    state=current_state(data)
    baseline,_,_=live_decision()
    rivals=[]
    history={(h['round'],h['team']):h for h in data['history']}
    for m in data['markets']:
        if m['round']!=0 or m['team']=='营销团队':
            continue
        f=history[0,m['team']]['fields']
        rivals.append(dict(team=m['team'],market=m['market'],price=m['price']['value'],
                           general=f['general_marketing']['value'],designer=f['designer_marketing']['value'],
                           rd=f['rd']['value'],previous_rd=600))
    variations=[('基准',baseline)]
    for key,values in [('rd',[0,400,800,1200]),('operations',[0,400,1000,1400]),
                       ('machine_investment',[5,10,20]),('allocation',[40,60,80,100]),
                       ('long_change',[-5000,5000])]:
        variations.extend((f'{key}={value}',dict(baseline,**{key:value})) for value in values)
    variations.append(('印尼优先',dict(baseline,priority=[1,0])))
    for key in ['general','designer']:
        variations.extend((f'{key}两国同比例={factor}',dict(baseline,**{key:[v*factor for v in baseline[key]]}))
                          for factor in [.5,2])
    risk=min(finance['risk_candidates'],key=lambda r:r['training_mae_basis_points'])
    outputs=[]
    for label,decision in variations:
        demand=[]
        for country,total,price in zip(COUNTRIES,[43.22,121.94],decision['prices']):
            own=dict(team='营销团队',market=country,price=price,general=sum(decision['general']),
                     designer=sum(decision['designer']),rd=decision['rd'],previous_rd=600)
            group=[r for r in rivals if r['market']==country]+[own]
            demand.append(float(shares(demand_features(group,curves),np.array(demand_fit['frozen_round1_beta']))[-1]*total))
        efficiency=efficiency_model['selected']['technology_scale']*float(curve_value(
            decision['operations']+.5*700,curves['operations']['parameters'],'saturation'))
        out=accounts_from_state(state,decision,demand,efficiency,dict(material_cost=900),finance['materials']['uplift_usd_per_unit'])
        outputs.append(dict(label=label,decision=decision,demand=demand,efficiency=efficiency,
                            output=out,risk_linked_forecast=risk_linked_accounts(state,decision,demand,efficiency,
                            dict(material_cost=900),finance['materials']['uplift_usd_per_unit'],risk),
                            classification='MODEL_COUNTERFACTUAL_NOT_PLATFORM_PROBE',
                            limit='其他输入固定；研发/运营/机器投资的未来收益未计入，投入代理不是因果回报'))
    return outputs


def next_round_forecasts(data,curves,demand_fit,efficiency_model):
    """Forecast every demand input through two stages under explicit future assumptions."""
    baseline,_,_=live_decision()
    history={(h['round'],h['team']):h for h in data['history']}
    totals={rnd:np.array([sum(m['demand']['value'] for m in data['markets'] if m['round']==rnd and m['market']==c)
                         for c in COUNTRIES]) for rnd in [0,1,2]}
    growth1=totals[1]/totals[0]-1
    growth2=totals[2]/totals[1]-1
    results=[]
    for rival_round in [0,1]:
        rivals=[]
        for m in data['markets']:
            if m['round']!=rival_round or m['team']=='营销团队':
                continue
            f=history[rival_round,m['team']]['fields']
            rivals.append(dict(team=m['team'],market=m['market'],price=m['price']['value'],
                               general=f['general_marketing']['value'],designer=f['designer_marketing']['value'],
                               rd=f['rd']['value'],previous_rd=600))
        for growth in [np.zeros(2),growth1]:
            current_totals=np.array([43.22,121.94])*(1+growth)
            current_demand=[]
            for c,p,total in zip(COUNTRIES,baseline['prices'],current_totals):
                group=[r for r in rivals if r['market']==c]+[dict(team='营销团队',market=c,price=p,
                         general=sum(baseline['general']),designer=sum(baseline['designer']),rd=baseline['rd'],previous_rd=600)]
                current_demand.append(float(shares(demand_features(group,curves),np.array(demand_fit['frozen_round1_beta']))[-1]*total))
            for future_growth in [np.zeros(2),np.full(2,.05),np.full(2,.1),growth2]:
                future_demand=[]
                for c,p,total in zip(COUNTRIES,baseline['prices'],current_totals*(1+future_growth)):
                    # Keep rivals' decisions constant, carry their known scenario RD into next period.
                    group=[dict(r,previous_rd=r['rd']) for r in rivals if r['market']==c]+[dict(
                        team='营销团队',market=c,price=p,general=sum(baseline['general']),
                        designer=sum(baseline['designer']),rd=baseline['rd'],previous_rd=baseline['rd'])]
                    future_demand.append(float(shares(demand_features(group,curves),np.array(demand_fit['frozen_round1_beta']))[-1]*total))
                results.append(dict(rival_scenario=f'采用{rival_round}回合策略并保持不变',
                                    current_market_growth_percent=(growth*100).tolist(),current_demand=current_demand,
                                    future_market_growth_percent=(future_growth*100).tolist(),future_demand=future_demand,
                                    next_total_demand_growth_percent=float((sum(future_demand)/sum(current_demand)-1)*100),
                                    current_efficiency=efficiency_model['selected']['technology_scale']*float(curve_value(
                                        baseline['operations']+.5*700,curves['operations']['parameters'],'saturation')),
                                    classification='CONDITIONAL_FORECAST_NOT_KNOWN',
                                    limit='正式2未来增长/竞争/技术未知；0/5/10%及历史增长均为情景，不是已知正式前景'))
    return results


def decision_scenarios(data,curves,demand_fit,efficiency_model,finance):
    state=current_state(data)
    decision,input_demand,input_efficiency=live_decision()
    parameters=dict(material_cost=900)
    current=accounts_from_state(state,decision,input_demand,input_efficiency,parameters,finance['materials']['uplift_usd_per_unit'])
    observations=[]
    for key,label,tolerance in [('revenue','净销售额',.6),('materials','原材料购买',.6),
                                ('transport','运输',.6),('long_interest','长期贷款利息',.6),
                                ('cash_interest','利息收入',.6),('profit','本回合利润',3),
                                ('machine_depreciation','机器',.6),('building_depreciation','厂房',.6)]:
        s=source('20261011_model_v2_round1_budget_income',label)
        observations.append(dict(metric=key,predicted=current[key],observed=s['value'],
                                  error=current[key]-s['value'],passed=abs(current[key]-s['value'])<=tolerance,source=s))
    for key,label,tolerance in [('cash','现金及现金等价物',3),('ar','应收帐款',.6),('ap','应付账款',.6)]:
        s=source('20261011_model_v2_round1_budget_balance',label)
        observations.append(dict(metric=key,predicted=current[key],observed=s['value'],
                                  error=current[key]-s['value'],passed=abs(current[key]-s['value'])<=tolerance,source=s))
    scenarios=[]
    history={(r['round'],r['team']):r for r in data['history']}
    own='营销团队'
    for rival_round in [0,1]:
        rivals=[]
        for c in COUNTRIES:
            for m in data['markets']:
                if m['round']!=rival_round or m['market']!=c or m['team']==own:
                    continue
                f=history[rival_round,m['team']]['fields']
                rivals.append(dict(team=m['team'],market=c,price=m['price']['value'],
                                   general=f['general_marketing']['value'],designer=f['designer_marketing']['value'],
                                   rd=f['rd']['value'],previous_rd=600))
        historical_growth=tuple(sum(m['demand']['value'] for m in data['markets'] if m['round']==1 and m['market']==c)
                                /sum(m['demand']['value'] for m in data['markets'] if m['round']==0 and m['market']==c)-1
                                for c in COUNTRIES)
        for growth in [(0,0),historical_growth]:
            # These are explicit assumptions: no future formal market size or rival strategy is observed.
            market_totals=np.array([43.22,121.94])*(1+np.array(growth))
            for th_price in [1790,1800,1900,2000,2200,2500,3000,4000]:
                for in_price in [1888,2000,2200,2400,2500,2600,2800,2900]:
                    candidate=dict(decision,prices=[th_price,in_price])
                    own_rows=[dict(team=own,market=c,price=p,general=sum(candidate['general']),
                                   designer=sum(candidate['designer']),rd=candidate['rd'],previous_rd=600)
                              for c,p in zip(COUNTRIES,candidate['prices'])]
                    demand=[]
                    for c,total in zip(COUNTRIES,market_totals):
                        group=[r for r in rivals+own_rows if r['market']==c]
                        s=shares(demand_features(group,curves),np.array(demand_fit['frozen_round1_beta']))
                        demand.append(float(s[-1]*total))
                    efficiency=efficiency_model['selected']['technology_scale']*float(curve_value(
                        candidate['operations']+.5*700,curves['operations']['parameters'],'saturation'))
                    cap=state['capacity']*.85
                    candidate['allocation']=min(sum(demand)/cap*100,100)
                    margins=np.array(candidate['prices'])-np.array([30,120])
                    candidate['priority']=np.argsort(-margins).tolist()
                    out=accounts_from_state(state,candidate,demand,efficiency,parameters,finance['materials']['uplift_usd_per_unit'])
                    # Select on training fit only; forward risk scores are diagnostics, not selection inputs.
                    risk=min(finance['risk_candidates'],key=lambda r:r['training_mae_basis_points'])
                    linked=risk_linked_accounts(state,candidate,demand,efficiency,parameters,
                                                finance['materials']['uplift_usd_per_unit'],risk)
                    scenarios.append(dict(rival_scenario='初始0策略' if rival_round==0 else '练习1策略',
                                          market_growth_percent=(np.array(growth)*100).tolist(),
                                          decision=candidate,demand=demand,output=out,risk_linked_forecast=linked))
    groups={}
    for r in scenarios:
        key=tuple(r['decision']['prices'])
        groups.setdefault(key,[]).append(r)
    ranking=[dict(prices=list(key),min_profit=min(r['output']['profit'] for r in group),
                  max_profit=max(r['output']['profit'] for r in group),
                  all_in_finance_scope=all(r['output']['fully_computed_in_scope'] for r in group))
             for key,group in groups.items()]
    ranking.sort(key=lambda r:r['min_profit'],reverse=True)
    return dict(current_budget_replay=current,current_replay_checks=observations,
                current_inputs=dict(decision=decision,demand=input_demand,efficiency=input_efficiency,state=state),
                scenario_ranking=ranking,scenario_records=scenarios,
                limit='只比较给定营销/研发/运营/零投资/固定3%利率下的价格、产能和物流；非全面或六回合最优，经验代理不可解释为营销因果收益')


def self_check(curves):
    assert abs(sum(shares(np.zeros((10,5)),np.ones(5)))-1)<1e-12
    assert np.allclose(shares(np.zeros((10,5)),np.ones(5)),.1)
    assert float(curve_value(800,curves['rd']['parameters'],'power'))>float(curve_value(400,curves['rd']['parameters'],'power'))
    for curve in curves.values():
        p=np.array(curve['points'])
        assert curve['held_vertex_max_error']<.02
        assert np.all(np.diff(p[:,1])>=0)
    dummy=dict(capacity=20,workers=100,inventory=0,cash=15000,ar=2000,ap=1000,
               machine_book=8000,building_book=13000,long_debt=17000,short_debt=0,equity=20000,tax_loss=0)
    # The balance self-check requires a consistent starting balance sheet.
    dummy['equity']=dummy['machine_book']+dummy['building_book']+dummy['ar']+dummy['cash']-dummy['ap']-dummy['long_debt']
    decision=dict(prices=[2000,2200],general=[200,200],designer=[150,150],rd=600,operations=700,
                  allocation=100,machine_investment=0,priority=[1,0],long_change=0,long_rate=3)
    a=accounts_from_state(dummy,decision,[4,8],.17,dict(material_cost=900),1.25)
    assert a['sales']==[4,8] and abs(a['balance_error'])<1e-8
    b=accounts_from_state(dummy,dict(decision,long_change=1000),[4,8],.17,dict(material_cost=900),1.25)
    assert b['long_interest']>a['long_interest'] and b['cash']>a['cash']
    loss=accounts_from_state(dummy,dict(decision,prices=[100,100]),[4,8],.17,dict(material_cost=900),1.25)
    assert loss['tax']==0 and loss['tax_loss_end']>0


def main():
    data=json.loads((ROOT/'结构化模型输入.json').read_text(encoding='utf-8'))
    curves=fit_curves()
    self_check(curves)
    demand=fit_demand_v2(data,curves)
    accounts=historical_accounts(data)
    finance=finance_fits(accounts)
    efficiency=efficiency_fit(data,curves)
    decisions=decision_scenarios(data,curves,demand,efficiency,finance)
    sensitivity=counterfactuals(data,curves,demand,efficiency,finance)
    forecasts=next_round_forecasts(data,curves,demand,efficiency)
    assert cells('20261011_model_v2_round1_checklist')==cells('20261011_model_v2_round1_checklist_final')
    assert cells('20261011_model_v2_round1_outlook')==cells('20261011_round1_outlook')
    assert not finance['failed'] and all(r['passed'] for r in decisions['current_replay_checks'])
    sources=['结构化模型输入.json','需求拟合与留出核验.json']+[str(p.relative_to(ROOT)).replace('\\','/')
             for p in (ROOT/'raw').glob('20261011_model_v2_*.json')]+['raw/initial0_printable.json','raw/practice1_printable.json','raw/practice2_printable.json']
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),status='STEPWISE_EXPLORATORY_WITH_EXPLICIT_UNIDENTIFIED_BRANCHES',
                units=dict(quantity='千单位',finance='千美元',price='美元/单位',efficiency='千单位/人'),
                source_hashes={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},
                field_registry=field_registry(),curves=curves,demand=demand,efficiency=efficiency,finance=finance,decisions=decisions,
                one_input_model_sensitivity=sensitivity,
                current_and_next_demand_forecast_scenarios=forecasts,
                checks=dict(self_checks='PASS',browser_decisions_modified=False,
                            initial_final_decision_cells_identical=True,live_outlook_matches_prior_archive=True,
                            current_budget_replay_failed=[r for r in decisions['current_replay_checks'] if not r['passed']],
                            historical_formula_failed_count=len(finance['failed'])))
    write_json(ROOT/'分步模型拟合与验证.json',result)
    with (ROOT/'预测与决策_分步模型清单.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['字段','单位','计算步骤','公式','识别状态','限制'])
        writer.writerows([r[k] for k in ['field','unit','steps','formula','status','limit']] for r in field_registry())
    with (ROOT/'分步模型_财务核验.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['回合','团队','指标','公式','模型值','观测值','误差','容差','通过','源文件','源行','源列'])
        for r in finance['checks']:
            writer.writerow([r['round'],r['team'],r['metric'],r['formula'],r['predicted'],r['observed'],r['error'],r['tolerance'],r['passed'],r['source']['file'],r['source']['line'],r['source']['column']])
    report(result)
    update_archive()
    print(json.dumps(dict(curves={k:{z:v[z] for z in ['parameters','held_vertex_mae','held_vertex_max_error']} for k,v in curves.items()},
                         forward=demand['forward']['model'],share_only=demand['forward']['conditional_oracle_total_only'],
                         demand_beta=demand['frozen_round1_beta'],efficiency_mae=efficiency['selected']['forward_mae'],
                         historical_failures=finance['failed'],current_replay=decisions['current_replay_checks'],
                         scenario_top=decisions['scenario_ranking'][:3]),ensure_ascii=False,indent=2))


def report(result):
    demand=result['demand']
    finance=result['finance']
    current=result['decisions']['current_budget_replay']
    old=json.loads((ROOT/'需求拟合与留出核验.json').read_text(encoding='utf-8'))
    old_forward=old['nested_forward_holdout']['model']
    rd=result['curves']['rd']
    op=result['curves']['operations']
    text=['# 正式1分步建模与隐藏函数拟合',
          '', '更新：2026-10-11（北京时间）。全部预测、拟合、情景和财务计算均由Python执行。', '',
          '已读取引用聊天的隐藏函数分析，并实时确认市场5、营销团队、正式1、PYT个人区域。'
          '当前个人需求2.5/11、小组5/11；网页采集前后每个表格单元格相同，没有修改或提交决策。', '',
          '本轮完成可识别部分的拟合与分步计算。对缺少可识别样本的分支明确保留未知，不能声称已还原全部平台隐藏函数。', '',
          '## 计算顺序', '',
          '```mermaid', 'flowchart LR', 'A[市场前景与行业总量情景] --> B[价格 营销 研发及竞争策略]',
          'B --> C[效用 份额 公司需求]', 'D[运营与技术基底] --> E[生产效率]',
          'F[期初产能与机器投资] --> G[产能和产量]', 'C --> G', 'E --> H[人数 班次工资 解聘]',
          'G --> H', 'G --> I[物流分配 销量 收入]', 'I --> J[成本 折旧 EBIT]', 'H --> J',
          'J --> K[利息 税 利润]', 'K --> L[周转资金 现金 资产负债]',
          'L --> M[风险溢价]', 'M --> K', 'L --> N[下回合状态与情景]', '```', '',
          '每个网页输入的公式、依赖和识别状态见 [分步模型清单](预测与决策_分步模型清单.csv)。'
          '清单覆盖市场增长、两国需求、下回合需求增长、效率、贷款利率、价格、两类营销、'
          '大客户、物流、产能分配、机器投资、运营、研发和融资。', '',
          '## 需求：从绝对数量回归改为竞争份额模型', '',
          '`utility = -e国*log(P/P0国) + bg*log1p(G合计/1000) + bd*log1p(M合计/1000) + br*log(f_rd(R+0.5*Rprev))`', '',
          '`share_i = exp(utility_i)/sum_j(exp(utility_j)); D_i = 行业总需求*share_i`', '',
          '行业规模与竞争份额分开计算；份额合计为1。训练只用实际需求，缺货销量不能替代需求。'
          '研发上期值补入初始0的600，不再把练习1上期投入默认为0。国别营销仍缺失，只使用合计代理。', '',
          '参数选择仅在练习1内部团队留出完成；验证采用练习1训练、练习2检验。'
          '公式设计已参考现有练习2资料，因此这仍是回溯验证。真实正式结果尚未发生，未来泛化需要独立验证。', '',
          '| 模型/检验 | MAE，千单位 | WAPE |', '| --- | ---: | ---: |',
          f'| 旧版冻结前向候选 | {old_forward["MAE"]:.3f} | {old_forward["WAPE"]:.2%} |',
          f'| 新版：上期行业增长外推+条件竞争策略 | {demand["forward"]["model"]["MAE"]:.3f} | {demand["forward"]["model"]["WAPE"]:.2%} |',
          f'| 新版等份额基线：同样行业规模预测 | {demand["forward"]["baseline"]["MAE"]:.3f} | {demand["forward"]["baseline"]["WAPE"]:.2%} |',
          f'| 新版份额诊断：给定验证期真实总量 | {demand["forward"]["conditional_oracle_total_only"]["MAE"]:.3f} | {demand["forward"]["conditional_oracle_total_only"]["WAPE"]:.2%} |', '',
          '**最后一行用到验证期实际总量，仅诊断份额模型，不是可实现的预测分数。**'
          '其他新版验证也以已实现的竞争者策略为条件。正式1竞争策略未知，必须给定情景；新旧对比不等于完全相同信息集的独立竞赛。', '',
          f'嵌套团队留出份额MAE为 {demand["nested_team_share_mae"]*100:.3f} 个百分点。'
          '参数与每条预测、来源行列均保存在JSON；系数表示关联，不能宣称平台真实价格弹性。', '',
          '| 冻结练习1系数 | 值 |', '| --- | ---: |']
    text.extend(f'| {k} | {v:.6f} |' for k,v in zip(NAMES,demand['frozen_round1_beta']))
    forecasts=result['current_and_next_demand_forecast_scenarios']
    text += ['', '### 当前各项预测的情景值', '',
             '下表固定当前价格与投入；竞争者使用初始0/练习1策略假设，行业规模取不增长/历史练习1增长。'
             '范围是情景端点，不是统计置信区间，也不是正式实际值。', '',
             '| 预测字段 | 当前手填值 | 模型情景 |', '| --- | ---: | --- |']
    for i,country in enumerate(COUNTRIES):
        lo=min(r['current_demand'][i] for r in forecasts)
        hi=max(r['current_demand'][i] for r in forecasts)
        text.append(f'| {country}公司需求，千单位 | {result["decisions"]["current_inputs"]["demand"][i]:.2f} | {lo:.3f}–{hi:.3f} |')
        hi_growth=max(r['current_market_growth_percent'][i] for r in forecasts)
        text.append(f'| {country}市场增长，% | 0.00 | 0.00–{hi_growth:.3f}，给定情景 |')
    text += [f'| 生产效率，千单位/人 | 0.15 | {forecasts[0]["current_efficiency"]:.6f}，条件点预测 |',
             f'| 下回合公司总需求增长，% | 0.00 | {min(r["next_total_demand_growth_percent"] for r in forecasts):.3f}–'
             f'{max(r["next_total_demand_growth_percent"] for r in forecasts):.3f}，未来情景传播 |',
             f'| 长期贷款利率，% | 3.00 | {result["one_input_model_sensitivity"][0]["risk_linked_forecast"]["predicted_long_rate_percent"]:.4f}，联立条件点预测 |', '',
             '下回合采用0/5/10%增长或历史练习1→2增长、竞争策略不变、研发跨期传递的明确假设。'
             '正式2前景未取得，这些未来假设不能当作已知信息。泰国当前手填需求明显高于模型情景值，'
             '应视为需要验证的偏差；此处没有修改输入。']
    text += ['', '行业总量仍是最薄弱环节：只有两个练习回合，不能同时识别宏观趋势、行业价格、营销和隐藏规模函数。'
             '验证期总量预测使用 `M1*(M1/M0)`；正式1情景使用初始规模不变与历史练习1增长两种假设。'
             '下回合需求增长必须从下回合行业/竞争情景推导，不能把截图50%或当前0%当作已知增长。', '',
             '## 研发与运营曲线', '',
             '本次从正式1生产页读取可见SVG线条和坐标轴，未读取平台内部模型状态。'
             '每条曲线200个顶点，以交错100个顶点拟合、另100个检验，随后用全曲线拟合最终参数。'
             '横轴刻度显示为整数，存在约±0.5千美元的标定误差；这些顶点不是200次独立实验。', '',
             f'研发：`f_rd(x) = {rd["parameters"][0]:.6f} + {rd["parameters"][1]:.6f}*(x+{rd["parameters"][2]:.6f})**{rd["parameters"][3]:.6f}`。', '',
             f'运营：`f_ops(x) = {op["parameters"][0]:.6f} + {op["parameters"][1]:.6f}*x/({op["parameters"][2]:.6f}+x)`。', '',
             f'曲线留点最大误差：研发 {rd["held_vertex_max_error"]:.6f}、运营 {op["held_vertex_max_error"]:.2e}（乘数单位）。'
             '仅说明可见曲线近似好；有效投资如何由历史投入累积而来、国别权重及实际需求效应仍需检验。', '',
             f'效率模型采用 `tech*f_ops(O+0.5*Oprev)`，练习1拟合技术尺度，练习2前向MAE为 '
             f'{result["efficiency"]["selected"]["forward_mae"]:.6f} 千单位/人。'
             '实际效率标签使用实际产量/工人数，避免把显示为0.17的两位小数当作精确效率。'
             'rho=0/0.5/1均保留为敏感性；0.5沿用事前假设，没有按验证误差挑选。', '',
             '## 生产、投资和财务链', '',
             '| 项目 | Python公式 | 核验范围 |', '| --- | --- | --- |',
             '| 当期产能 | 上期产能×0.85+机器投资千单位 | 两练习回合20队次，投资当回合生效 |',
             '| 产量 | min(产能×分配比例, 总需求) | 零期初库存/零大客户的需求驱动策略 |',
             '| 工人/工资 | q/效率；按产能的三个1/3班次，用1、1.65、2.56工资系数 | 历史校验使用实际人数，不冒充独立效率验证 |',
             '| 解聘 | max(上期人数×0.9−本期人数,0)×工资×0.35 | 20队次 |',
             '| 应收/应付 | 收入×30/365；原材料×30/365 | 20队次 |',
             '| 厂房折旧 | 期初账面值×7% | 当前场景经验拟合 |',
             '| 机器折旧 | (期初账面值+当期投资)×15% | 20队次，含投资变化 |',
             '| 厂房投资 | 800千美元 | 当前归档各队一致，未证明所有规模/回合恒定 |',
             '| 长期利息 | (期初贷款+期末贷款)/2×利率 | 给定实际利率的金额核验 |',
             '| 现金利息 | (期初现金+期末现金)/2×1% | 与现金和所得税联立，不引用未来实际现金 |',
             '| 税费 | max(税前利润−已知累计税亏,0)×29% | 只有盈利/亏损状态，没有亏后转盈样本 |',
             '| 资产负债 | 期末资产=权益+贷款+应付 | 独立计算链自检 |', '',
             f'原材料使用公布单价加练习1拟合单位差额 {finance["materials"]["uplift_usd_per_unit"]:.6f} 美元/单位；'
             f'练习2前向原材料总额MAE {finance["materials"]["forward_mae_kusd"]:.3f} 千美元。'
             '差额未解释，不把经验值改称官方原材料参数；数量显示舍入亦有影响。', '',
             f'历史公式核验共 {len(finance["checks"])} 项，{len(finance["failed"])} 项超过明示容差。'
             '这是多个单项关系核验，部分使用实际中间量，不是全部独立的财务前瞻预测。'
             '税费的0.65千美元容差来自税前/税额整数显示误差传播：0.5×29%+0.5=0.645。', '',
             '风险溢价分别拟合债务/权益幂函数与权益/资产指数函数。使用练习1拟合、练习2验证：', '',
             '| 候选 | 训练MAE，基点 | 前向MAE，基点 |', '| --- | ---: | ---: |']
    text.extend(f'| {r["form"]} | {r["training_mae_basis_points"]:.3f} | {r["forward_mae_basis_points"]:.3f} |' for r in finance['risk_candidates'])
    text += ['', '风险的条件验证使用实际期末资产/权益，仅用于诊断。情景预测另行联立预测利润、权益和利率，'
             '没有把未来实际财务状态输入预测。部署候选按练习1训练误差选择，不用练习2表现选型。'
             '短贷只有一条非零观测，不能唯一拟合计息时点；若预测现金不足2000，模型标记超出已识别范围。', '',
             '## 当前正式1预算的独立回算', '',
             '固定当前手填需求2.5/11、效率0.15、价格3000/2000、分配20%、其他个人输入不变。'
             '下表由期初状态和决策独立计算，原材料差额取练习1校准值；没有直接拿当前平台费用去拼利润。', '',
             '| 指标 | Python | 平台 | 误差，千美元 |', '| --- | ---: | ---: | ---: |']
    text.extend(f'| {r["metric"]} | {r["predicted"]:.3f} | {r["observed"]:.3f} | {r["error"]:+.3f} |'
                for r in result['decisions']['current_replay_checks'])
    text += ['', '所有11项在明示容差内通过。输入2.5/11只是当前玩家预测，预算回算成功不能证明真实需求正确。', '',
             '## 决策情景与单变量模型敏感性', '',
             f'本轮比较了 {len(result["decisions"]["scenario_records"])} 组价格/产能/物流情景；'
             f'另有 {len(result["one_input_model_sensitivity"])} 组单变量模型反事实，覆盖研发、运营、机器投资、产能、'
             '贷款、物流和合计营销。它们没有写入网页，不是平台扰动试验。', '',
             '保持当前营销、研发、运营、零机器投资和零贷款变化；两种竞争者策略假设×两种行业总量假设。'
             '效率由新模型预测；每组重新计算需求、产能分配与物流。下表按四种情景最小利润排序，仅表示有限网格内的条件结果。', '',
             '| 泰国价格 | 印尼价格 | 情景利润最小值，千美元 | 情景利润最大值，千美元 |',
             '| ---: | ---: | ---: | ---: |']
    text.extend(f'| {r["prices"][0]} | {r["prices"][1]} | {r["min_profit"]:.1f} | {r["max_profit"]:.1f} |'
                for r in result['decisions']['scenario_ranking'][:5])
    text += ['', '上述是固定3%预算利率的比较；JSON另保存预测风险利率联立结果。'
             '网格最优泰国价格靠近训练下界，不能继续向低价外推寻找极值。营销代理、竞争未知、市场规模未知、'
             '未来投入收益与机器价格变化都可能改变排序，因此没有据此填写推荐决策，也没有称其为正式6累计收益最优。', '',
             '## 仍未识别的内容', '',
             '- 正式与练习隐藏需求函数是否相同：正式实际结果未出现，不能判定。',
             '- 竞争者国别营销、营销延续、完整研发/运营存量：现有数据不能唯一分离。',
             '- 市场总量和宏观环境函数：只有两个时间点，不足以拟合独立趋势。',
             '- 大客户评分：正式1订单为0，无可用中标样本；当前不参与即可，未来报价模型仍待样本。',
             '- 短贷利息、亏后转盈税亏、非零库存：模型明确保留未识别分支，不输出确定的全流程利润。',
             '- 六回合累计收益优化：当前只有一步条件比较，未来前景和竞争策略仍须情景更新。', '',
             '## 复现与归档', '',
             '`python code/stepwise_model.py`', '',
             '- [Python代码](code/stepwise_model.py)', '- [全部拟合、预测、情景和核验JSON](分步模型拟合与验证.json)',
             '- [逐项历史财务核验](分步模型_财务核验.csv)', '- [每个预测与决策字段的模型清单](预测与决策_分步模型清单.csv)', '',
             '本轮新网页原件为 `raw/20261011_model_v2_round1_*.json`，含前景、投资、生产、SVG曲线、财务、需求、'
             '完整损益/资产负债/现金流预算以及采集前后的决策列表。已进入分组索引并更新SHA256清单。']
    (ROOT/'正式1分步建模报告.md').write_text('\n'.join(text)+'\n',encoding='utf-8')


def update_archive():
    from audit_incremental import classify
    paths=list((ROOT/'raw').glob('20261011_model_v2_*.json'))
    filenames={p.relative_to(ROOT).as_posix() for p in paths}
    index=json.loads((ROOT/'数据分组索引.json').read_text(encoding='utf-8'))
    index=[r for r in index if r['file'] not in filenames]
    added,grouped,plain=[],[],[]
    for p in paths:
        data=json.loads(p.read_text(encoding='utf-8'))
        phase,rnd,kind=classify(p.stem)
        item=dict(file=p.relative_to(ROOT).as_posix(),phase=phase,round=rnd,data_kind=kind,
                  captured_at=data['captured_at'],source_url=data['source_url'],market=5,usable_for_demand_fit=False,
                  usage='正式1实时基准/可见曲线/条件预算；不能作实际需求标签',
                  representation=data.get('representation','DOM snapshot'),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        added.append(item)
        if 'snapshot' in data:
            p.with_suffix('.txt').write_text(data['snapshot'],encoding='utf-8')
        for row in table_rows(data.get('snapshot','')):
            raw=json.dumps(row['cells'],ensure_ascii=False)
            grouped.append([item['file'],phase,rnd,kind,data['captured_at'],row['line'],row['row_text'],raw])
            plain.append([p.name,row['line'],row['row_text'],raw])
    write_json(ROOT/'数据分组索引.json',index+added)
    for name,new in [('分组表格行索引.csv',grouped),('全部表格行索引.csv',plain)]:
        with (ROOT/name).open(encoding='utf-8-sig',newline='') as stream:
            old=list(csv.reader(stream))
        old=[r for r in old if r[0] not in filenames and 'raw/'+r[0] not in filenames]
        with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as stream:
            csv.writer(stream).writerows(old+new)
    coverage=json.loads((ROOT/'归档覆盖与待办.json').read_text(encoding='utf-8'))
    coverage['files']=[r for r in coverage['files'] if r['file'] not in filenames]+added
    coverage['stepwise_model_v2']=dict(updated_at=datetime.now(timezone.utc).isoformat(),raw_files=len(paths),
                                     report='正式1分步建模报告.md',result='分步模型拟合与验证.json',decision_modified=False)
    write_json(ROOT/'归档覆盖与待办.json',coverage)
    manifest=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and p.name!='SHA256_manifest.json' and '__pycache__' not in p.parts and '.git' not in p.parts:
            manifest.append(dict(file=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    write_json(ROOT/'SHA256_manifest.json',manifest)


if __name__=='__main__':
    main()
