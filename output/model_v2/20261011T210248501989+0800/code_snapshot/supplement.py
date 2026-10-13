"""Read-only integration and remaining production/finance checks."""
from scipy.optimize import brentq
from core import *
from finance import accounts, parameters
from live_review import rows as live_rows, LIVE

COUNTRY_RUN = 'output/country_demand/20261011T205528470485+0800'


def country_review(rows):
    from country_demand import predict_country, validate
    result = read(COUNTRY_RUN+'/model.json')
    hashes = {COUNTRY_RUN+'/'+n: digest(ROOT/COUNTRY_RUN/n) for n in ['model.json','validation.json']}
    for source in result['sources']:
        assert digest(ROOT/source['file']) == source['sha256'], source['file']
        hashes[source['file']] = source['sha256']
    assert digest(ROOT/FROZEN) == result['frozen_curve_source']['sha256']
    # Verify only the dependencies actually used for replay, not unrelated report code.
    for name in ['country_demand.py','core.py','context.py','demand.py','cross_market_validation.py','stepwise_model.py','archive_and_report.py']:
        current = ROOT/'code/model_v2'/name
        if not current.exists(): current = ROOT/'code'/name
        assert digest(current) == result['code_hashes'][name], name
        hashes[current.relative_to(ROOT).as_posix()] = digest(current)
    params = read(FROZEN)['rd_curve_parameters']
    checks = validate(result['models'], rows, params)
    differences = []
    for name, model in result['models'].items():
        rr = [r for r in rows if r['context_id']==model['context_id'] and r['country']==model['country'] and r['context_fit_eligible']]
        assert [key(r) for r in rr] == model['training_keys']
        predictions = predict_country(rr, model, params)
        saved = [r for r in result['predictions'] if r['model']==name]
        assert len(saved)==len(rr)==10
        for r, s, p in zip(rr, saved, predictions):
            assert r['team_id']==s['team_id'] and r['demand']==s['actual']
            differences.append(abs(float(p)-s['predicted_share']))
    assert max(differences)<1e-12
    predictions = [dict(r, model='COUNTRY_DEMAND_V1/'+r['model']) for r in result['predictions']]
    return dict(source_run=COUNTRY_RUN, source_hashes=hashes, models=result['models'], predictions=predictions,
                checks=dict(checks, frozen_share_max_difference=max(differences), predictions_n=len(predictions)),
                assumptions=result['assumptions'], limitations=result['limitations'],
                external_validation=False, optimization_eligible=False,
                scope='四个国家/情境独立模型，只并列展示；仍为合计营销代理、样本内研究，不用于国别分配优化')


def financial_review():
    inp = read('分步模型拟合与验证.json')['decisions']['current_inputs']
    state, p = inp['state'], parameters()
    records, identities, boundary = [], [], []
    def cell(file, label):
        matches = [(i,r) for i,r in enumerate(live_rows(file)) if len(r)>1 and r[0]==label and r[1].strip()]
        assert len(matches)==1, (file,label)
        i,r = matches[0]
        return old.numeric(r[1]), dict(file=LIVE+'/'+file+'.json', table_row_index=i, column=1, label=label, text=r[1])
    for prefix, inv in [('baseline',0),('machine1',1)]:
        decision = dict(inp['decision'], machine_investment=inv, long_rate=inp['decision']['long_rate']/100)
        a = accounts(state,decision,inp['demand'],inp['efficiency'],p)
        bal, cf = prefix+'_balance', prefix+'_cashflow'
        mapping = {
            bal: {'厂房':state['building_book']+a['building_capex']-a['building_depreciation'],
                  '机器':state['machine_book']+a['machine_capex']-a['machine_depreciation'],
                  '应收帐款':a['ar'],'现金及现金等价物':a['cash'],'资产总和':a['assets'],
                  '本回合利润':a['profit'],'股东权益合计':a['equity'],'长期贷款':a['long_debt'],'应付账款':a['ap']},
            cf: {'税息折旧及摊销前利润（EBITDA）':a['ebitda'],
                 '财务收入和支出':a['cash_interest']-a['long_interest'], '直接税':-a['tax'],
                 '应收帐变化(增 - / 减 +)':state['ar']-a['ar'],
                 '应付账变化(增 + / 减 -)':a['ap']-state['ap'],
                 '资本支出总计':-a['machine_capex']-a['building_capex'],
                 '流动资产变动':a['cash']-state['cash'],'流动资产 12月31日':a['cash']}}
        for file, fields in mapping.items():
            for label, value in fields.items():
                observed, source = cell(file,label)
                records.append(dict(case=prefix,metric=label,source=source,actual=observed,predicted=value,
                    residual=value-observed,unit='千美元',target_display_half_width=.5,
                    nominal_prediction_inside_target_display_interval=abs(value-observed)<=.5,
                    interpretation='仅与目标整数显示区间比较；未传播期初/材料/周转及经验参数误差，超区间不作独立机制拒绝'))
        for file,target,terms in [
            (bal,'资产总和',['固定资产总和','流动资产总额']),
            (bal,'股东权益和负债总计',['股东权益合计','负债合计']),
            (cf,'经营活动现金流',['营运资金总计','净营运资本变化总计']),
            (cf,'流动资产 12月31日',['流动资产 1月1日','流动资产变动'])]:
            target_value, target_source = cell(file,target)
            parts = [cell(file,label) for label in terms]
            error = sum(v for v,_ in parts)-target_value
            tolerance = .5*(len(terms)+1)
            assert abs(error)<=tolerance
            identities.append(dict(case=prefix,target=target,display_identity_error=error,
                rounding_tolerance=tolerance,sources=[target_source]+[s for _,s in parts],passed=True,
                scope='仅显示数的会计恒等式，不是独立预测验证'))
    baseline = dict(inp['decision'],long_rate=inp['decision']['long_rate']/100)
    def loan_result(change):
        return accounts(state,dict(baseline,long_change=change),inp['demand'],inp['efficiency'],p)
    if (loan_result(-state['long_debt'])['cash']-p['minimum_cash'])*(loan_result(0)['cash']-p['minimum_cash'])<0:
        crossing = brentq(lambda change:loan_result(change)['cash']-p['minimum_cash'], -state['long_debt'], 0, xtol=1e-8)
        for delta in [-1,0,1]:
            a=loan_result(crossing+delta)
            boundary.append(dict(long_change=crossing+delta,cash=a['cash'],profit=a['profit'],
                short_debt_needed=a['short_debt_needed_before_unidentified_short_interest'],
                complete=a['fully_computed_in_scope'],balance_error=a['balance_error']))
        assert abs(boundary[1]['cash']-p['minimum_cash'])<1e-6
        assert boundary[1]['complete'] and boundary[1]['short_debt_needed']==0
        assert boundary[0]['short_debt_needed']>0 and boundary[2]['short_debt_needed']==0
    invalid = []
    for field,value in [('allocation',101),('long_rate',3),('long_change',-state['long_debt']-1),('machine_investment',-1)]:
        try: accounts(state,dict(baseline,**{field:value}),inp['demand'],inp['efficiency'],p)
        except AssertionError: invalid.append(field)
        else: raise AssertionError('Invalid financial input accepted: '+field)
    return dict(records=records,display_identities=identities,loan_cash_boundary=boundary,invalid_inputs_rejected=invalid,
        summary=dict(comparison_n=len(records),target_display_interval_matches=sum(r['nominal_prediction_inside_target_display_interval'] for r in records),
                     accounting_identities_n=len(identities)),
        source_hashes={LIVE+'/'+prefix+'_'+table+'.json':digest(ROOT/LIVE/(prefix+'_'+table+'.json'))
                      for prefix in ['baseline','machine1'] for table in ['balance','cashflow']},
        gate_passed=False, live_mutations=0,
        limitations=['并发变化样本只作参考，不拟合；完整独立保留验证套件尚缺',
                     '贷款现金边界只是固定手填利率/需求下的数学分支，网页贷款步长与风险联动未核验',
                     '短贷利息、库存、大客户、未来前景和状态结转仍未识别'])
