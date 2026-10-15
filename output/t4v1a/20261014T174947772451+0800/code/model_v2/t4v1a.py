"""Frozen t4v1 application: offline scenarios, never training or platform writes."""
import argparse
import ast
import copy
import csv
import hashlib
import json
import math
import shutil
import sys
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'dependencies'), str(ROOT/'work/python_packages'),
               str(ROOT/'code'), str(Path(__file__).parent)]
import numpy as np
import scipy
import core
import interest_rate_model as interest
import material_unit_cost_model as material
from stepwise_model import curve_value
from build_model_inputs import production_and_delivery
import connector_free_production as connector
import horizon

TZ = timezone(timedelta(hours=8))
BASE = ROOT/'output/t4v1_deduplicated/20261014T162452595723+0800'
ACTUAL = ROOT/'output/t4v1/20261014T153914569881+0800'
CANDIDATE = ROOT/'output/t4v1_connector_optimization/20261014T162353579815+0800'
INITIAL = ROOT/'output/round_close/20261013_formal3_close/formal4_initial'
PRODUCTS = ('复合梁', '连接件')
COUNTRIES = ('泰国', '印尼')
CURVE_KEYS = {'复合梁':'rd_beam', '连接件':'rd_connector', '运营':'operations_thailand'}
FORBIDDEN = {'fit', 'train', 'select', 'choose', 'least_squares', 'lsq_linear',
             'curve_fit', 'fit_points', 'fit_curves', 'efficiency_fit', 'demand_fit'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError('需要有限非负数；价格、效率与资产须为正数')
    return value


def missing(reason):
    return dict(status='SKIPPED_MISSING_EVIDENCE', reason=reason, value=None)


@contextmanager
def no_training():
    previous = sys.getprofile()
    def guard(frame, event, arg):
        if event == 'call' and frame.f_code.co_name in FORBIDDEN:
            raise RuntimeError('禁止重训/选参调用: '+frame.f_code.co_name)
    sys.setprofile(guard)
    try:
        yield
    finally:
        sys.setprofile(previous)


def curve_at(registry, key, context, effective_x):
    """Explicit effective coordinates only; spending-to-coordinate mapping is unknown."""
    c = registry['formal4_curves']['curves'][key]
    expected = dict(market_id=5, team_id=registry['target_team_id'], phase='formal', round=4,
                    previous_input=c['upstream_condition']['previous_value'], unit='千美元',
                    coordinate_kind='effective_investment_scenario')
    if context != expected:
        raise ValueError('曲线情境、历史条件或有效投入单位不匹配')
    x = number(effective_x)
    if not c['x_range'][0] <= x <= c['x_range'][1]:
        raise ValueError('有效投入超过已归档曲线范围')
    value = float(curve_value(x, c['parameters'], c['form']))
    number(value, True)
    return dict(status='CURVE_COORDINATE_SCENARIO_ONLY', effective_input_kusd=x, multiplier=value,
                context=context, source=c['source'], source_sha256=c['source_sha256'],
                spending_mapping_verified=False, historical_effect_added=False)


def demand_reference(registry, rows, totals, growth, model_name='SHARE', linear=False):
    """Hold formal3 response inputs/curves; apply round4 industry scenarios externally."""
    output, skipped = [], []
    if set(growth) != set(PRODUCTS):
        raise ValueError('需要两个产品的行业情景')
    for product in PRODUCTS:
        g = growth[product]
        if isinstance(g, bool) or not isinstance(g, (int, float)) or not math.isfinite(g) or g < -1:
            raise ValueError('行业变化率须为有限数且不低于-100%')
        pr = [r for r in rows if r['product'] == product]
        for country in COUNTRIES:
            pool = [r for r in pr if r['country'] == country]
            expected = registry['competition_teams']
            ids = [r['team_id'] for r in pool]
            if len(ids) != len(set(ids)) or set(ids) != set(expected):
                skipped.append(dict(product=product, country=country, **missing('竞争输入不完整或重复；不能按部分队伍重新归一化')))
                continue
            for r in pool:
                if (r['market_id'], r['phase'], r['round']) != (registry['application_market'], 'formal', 3):
                    raise ValueError('冻结竞争参考仅支持目标市场正式3实际输入')
                for name in ('price', 'initial_price', 'general', 'designer', 'rd', 'previous_rd'):
                    number(r[name], name in ('price', 'initial_price'))
            name = model_name if model_name == 'SHARE' else 'COUNTRY/'+country
            m = registry['demand'][product][name]
            config = m
            if linear and product == '连接件':
                candidate = registry['frozen_candidates']['connector_price']
                m, config = candidate['model'], candidate['config']
                if config['marketing_decay'] != 0:
                    raise ValueError('只接入已冻结的无营销延续价格候选')
            x = core.features(pool, registry['curves']['rd/'+product]['parameters'], config['rho'], config['piecewise'])
            if linear and product == '连接件':
                x[:, :2] = 0
                x[:, COUNTRIES.index(country)] = -np.array([r['price'] for r in pool])/100
            shares = core.predict(pool, x, m['beta'])
            total = number(totals[product][country])*(1+g)
            assert math.isclose(float(sum(shares)), 1, abs_tol=1e-12)
            records = [dict(product=product, country=country, team_id=r['team_id'], share=float(s),
                            demand_kunits=float(s*total), market_total_kunits=total,
                            model=('LINEAR_PRICE_CANDIDATE' if linear and product == '连接件' else name),
                            status='FROZEN_FORMAL3_RESPONSE_SCENARIO', response_round=3, scenario_round=4,
                            assumption='正式3响应、投入代理及曲线保持；不是已核验的回合4曲线响应') for r, s in zip(pool, shares)]
            assert math.isclose(sum(r['demand_kunits'] for r in records), total, abs_tol=1e-9)
            output.extend(records)
    return dict(status='INCOMPLETE_COMPETITION' if skipped else 'CONDITIONAL_SCENARIO',
                predictions=output, skipped=skipped, formal4_response_verified=False,
                units={'demand':'千单位', 'share':'小数'},
                assumptions=['两国分别按相同行业增长率缩放', '公司增长由份额与市场总量共同决定'])


def rate_scenario(registry, state, form='solvency_exponential', base_rate=None):
    if form != 'solvency_exponential':
        raise ValueError('杠杆幂函数仅作诊断，禁止进入应用路径')
    for key in ('equity', 'assets', 'long_debt', 'short_debt'):
        number(state[key], key in ('equity', 'assets'))
    features = interest.ratios(state)
    model = registry['risk'][form]
    if any(not model['ranges'][k][0] <= v <= model['ranges'][k][1] for k, v in features.items()):
        raise ValueError('财务状态超过冻结风险模型范围')
    base = registry['application_parameters']['base_rate']['value'] if base_rate is None else number(base_rate)
    rate = base+float(interest.premium(form, model['parameters'], [features])[0])
    if not math.isfinite(rate):
        raise ValueError('非有限利率')
    return dict(status='CONDITIONAL_STATE_SCENARIO', long_rate=rate,
                short_rate=rate+registry['application_parameters']['short_spread']['value'],
                features=features, state=state, base_rate=base, unit='小数',
                rate_timing_verified=False, full_financing_recommendation=False,
                limitation='给定状态关联；范围内也包含稀疏高风险区域，非前瞻验证')


def labor_cost(registry, plan, efficiency, wage=None):
    """Known rule on an explicit fixed-production scenario, no capacity investment timing."""
    p = registry['application_parameters']
    for key in ('capacity_kunits', 'production_kunits', 'previous_workers'):
        number(plan[key], key == 'capacity_kunits')
    e = number(efficiency, True)
    q, cap = plan['production_kunits'], plan['capacity_kunits']
    if q > cap:
        raise ValueError('产量超过情景产能')
    w = p['wage']['value'] if wage is None else number(wage)
    result = production_and_delivery(cap, 100*q/cap, e, [q,0], [0,1], w,
                p['second_shift']['value'], p['third_shift']['value'], plan['previous_workers'],
                p['attrition']['value'], p['severance']['value'])
    return dict(status='FIXED_PRODUCTION_RULE_SCENARIO', **result, wage_kusd_per_person=w,
                efficiency_kunits_per_person=e, units='产量千单位、人员人、工资与解聘费千美元',
                assumptions='给定产能、产量及上期人数；不推断投资生效时点或订单交付')


def apply_request(registry, request):
    if (request.get('version'), request.get('market_id'), request.get('phase'), request.get('round')) != ('t4v1a',5,'formal',4):
        raise ValueError('需要t4v1a／市场5／正式4情境')
    result = dict(version='t4v1a', complete_profit=None, full_profit_available=False,
                  deployment_enabled=False, remaining_profit_ranking=False)
    for name in ('growth', 'competitors', 'market_totals_kunits'):
        if name not in request:
            result['demand'] = missing('缺少必需输入: '+name)
            break
    else:
        if request.get('competition_assumption') != 'FORMAL3_ACTUAL_STRATEGY_HELD':
            raise ValueError('需要显式声明正式3策略保持情景')
        if request['market_totals_kunits'] != registry['formal3_market_totals_kunits']:
            raise ValueError('情景基准总量须匹配已归档正式3真实需求')
        result['demand'] = demand_reference(registry, request['competitors'], request['market_totals_kunits'], request['growth'])
        result['country_reference'] = demand_reference(registry, request['competitors'], request['market_totals_kunits'], request['growth'], 'COUNTRY')
        result['linear_price_candidate'] = demand_reference(registry, request['competitors'], request['market_totals_kunits'], request['growth'], linear=True)
    result['curves'] = {}
    for key,item in request.get('curve_coordinates', {}).items():
        absent=[k for k in ('context','effective_x_kusd') if k not in item]
        result['curves'][key]=missing('缺曲线坐标输入: '+','.join(absent)) if absent else curve_at(registry,key,item['context'],item['effective_x_kusd'])
    result['spending_to_curve'] = missing('未证实当期支出至有效投入映射；不自动加历史作用')
    result['labor'] = {}
    for product, plan in request.get('production', {}).items():
        if product not in PRODUCTS:
            raise ValueError('未知产品')
        absent=[k for k in ('capacity_kunits','production_kunits','previous_workers','efficiency_kunits_per_person') if k not in plan]
        if absent:
            result['labor'][product]=missing('缺生产输入: '+','.join(absent))
        elif plan.get('efficiency_basis') != 'EXPLICIT_SCENARIO':
            result['labor'][product] = missing('效率未给定为显式情景；回合4运营历史映射未核验')
        else:
            result['labor'][product] = labor_cost(registry, plan, plan['efficiency_kunits_per_person'])
    if not result['labor']:
        result['labor'] = missing('缺产能、产量、上期人数和显式效率；不使用未知状态')
    financial = request.get('financial')
    if financial is None:
        result['finance'] = missing('缺显式财务状态情景，计息与税亏状态未齐')
    elif 'state' not in financial or any(k not in financial['state'] for k in ('equity','assets','long_debt','short_debt')):
        result['finance']=missing('缺财务state或equity/assets/long_debt/short_debt字段')
    elif financial.get('state_basis') != 'FORMAL3_CLOSING_STATE_HELD':
        raise ValueError('财务例子只支持正式3期末状态保持的显式情景')
    else:
        state = financial['state']
        current = rate_scenario(registry, state, financial.get('form','solvency_exponential'))
        old = rate_scenario(registry, state, base_rate=.04)
        debt = state['long_debt']
        result['finance'] = dict(status='CONDITIONAL_FINANCE_SENSITIVITY', rate=current,
            base4_rate=old, rate_delta=current['long_rate']-old['long_rate'],
            long_interest_delta_kusd=debt*(current['long_rate']-old['long_rate']),
            cash_before_tax_delta_kusd=-debt*(current['long_rate']-old['long_rate']),
            closing_cash=None, assumptions='长债余额整期保持、税前利息直接付现；计息时点未经核验',
            missing=['完整税亏','订单收付款','实际计息状态及支付时点'])
    result['orders'] = missing('仅招标机会，缺中标与交付状态；不确认收入或预收现金')
    result['horizon'] = horizon.remaining_profit(4, [dict(round=r,profit=None,in_scope=False,end_state=None) for r in (4,5,6)])
    return result


def self_check(registry):
    checks = {}
    state = dict(equity=50., assets=100., long_debt=40., short_debt=10.)
    assert math.isclose(rate_scenario(registry,state)['long_rate']-rate_scenario(registry,state,base_rate=.04)['long_rate'],.01,abs_tol=1e-14)
    for state_bad in [dict(state,equity=0),dict(state,assets=float('nan')),dict(state,long_debt=-1),dict(state,equity=99),dict(state,short_debt=True)]:
        try: rate_scenario(registry,state_bad)
        except ValueError: pass
        else: raise AssertionError('Invalid risk input accepted')
    try: rate_scenario(registry,state,'leverage_power')
    except ValueError: pass
    else: raise AssertionError('Power model application accepted')
    checks['rate_shift_and_invalid_state_and_power_rejection'] = True
    for key,c in registry['formal4_curves']['curves'].items():
        context = dict(market_id=5,team_id=registry['target_team_id'],phase='formal',round=4,
                       previous_input=c['upstream_condition']['previous_value'],unit='千美元',
                       coordinate_kind='effective_investment_scenario')
        for x in (0,c['x_range'][1]): curve_at(registry,key,context,x)
        for ctx,x in [(context,c['x_range'][1]+1),(dict(context,round=3),0),
                      (dict(context,previous_input=-1),0),(dict(context,unit='美元'),0),
                      (dict(context,team_id='OTHER'),0)]:
            try: curve_at(registry,key,ctx,x)
            except ValueError: pass
            else: raise AssertionError('Invalid curve context accepted')
    checks['curve_context_zero_boundary_extrapolation_and_no_history_duplication'] = True
    for q in (0,10-1e-7,10+1e-7,20-1e-7,20+1e-7,30):
        plan=dict(capacity_kunits=30.,production_kunits=q,previous_workers=200.)
        a,b = labor_cost(registry,plan,.2,30),labor_cost(registry,plan,.2,33)
        for field in ('payroll','firing'):
            assert math.isclose(b[field],a[field]*1.1,abs_tol=1e-8)
        assert math.isclose(b['workers'],q/.2,abs_tol=1e-9)
    checks['wage_increase_shift_boundaries_workers_and_severance'] = True
    checks['connector_existing_rules'] = connector.self_check()
    checks['horizon_unknown_not_zero'] = horizon.self_check()
    lifecycle = dict(opening_inventory_book_value_kusd=0.,rd_kusd=0.,marketing_kusd=0.,
                     attributed_operations_kusd=0.,investment_kunits=0.,investment_unit_cost=1.,
                     capacity_decay_pct=15.,orders_due=[],orders_awarded=[])
    product=dict(capacity=100.,efficiency=10.,material_cost=14.2,demand={'泰国':0.,'印尼':0.},
                 prices={'泰国':27.,'印尼':27.},transport_costs={'泰国':.5,'印尼':2.})
    award=dict(status='CONFIRMED',quantity_kunits=10.,price=27.,advance_received_kusd=27.)
    plan=dict(allocation_pct=0.,opening_inventory_kunits=0.,holding_cost_per_unit=.6,
              country_priority=list(COUNTRIES),lifecycle=dict(lifecycle,orders_awarded=[award]))
    first=connector.project(product,plan,33.,[1.,1.65,2.56])
    second=connector.project(product,dict(plan,allocation_pct=10.,lifecycle=dict(lifecycle,orders_due=[award])),33.,[1.,1.65,2.56])
    assert first['order_revenue_kusd']==0 and first['order_cash_movement_kusd']==27
    assert second['order_revenue_kusd']==270 and second['order_balance_due_kusd']==243
    try: connector.project(product,dict(plan,lifecycle=dict(lifecycle,orders_awarded=[dict(award,status='TENDER')])),33.,[1.,1.65,2.56])
    except ValueError: pass
    else: raise AssertionError('Tender treated as confirmed order')
    checks['order_advance_revenue_balance_and_tender_rejection'] = True
    try:
        with no_training():
            def fit(): return None
            fit()
    except RuntimeError: checks['training_guard_rejects_fit'] = True
    else: raise AssertionError('Training guard failed')
    return checks


def snapshot_code(out):
    """Copy only the local import closure; imports do not execute training entrypoints."""
    queue=[Path(__file__), Path(__file__).with_name('verify_t4v1a.py')]; copied=set()
    paths=[ROOT/'code/model_v2',ROOT/'code']
    while queue:
        path=queue.pop()
        if path in copied: continue
        copied.add(path)
        dest=out/path.relative_to(ROOT)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,dest)
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
            for name in names:
                for directory in paths:
                    candidate=directory/(name.split('.')[0]+'.py')
                    if candidate.is_file(): queue.append(candidate); break
    return [p.relative_to(ROOT).as_posix() for p in sorted(copied)]


def build_bundle(output=None):
    out = output or ROOT/'output/t4v1a'/datetime.now(TZ).strftime('%Y%m%dT%H%M%S%f%z')
    if out.exists() and set(p.name for p in out.iterdir()) != {'work_log.md'}:
        raise FileExistsError('输出目录已含交付，拒绝覆盖')
    out.mkdir(parents=True,exist_ok=True)
    log=out/'work_log.md'
    with log.open('a',encoding='utf-8') as f:
        f.write('\n\n开始：'+datetime.now(TZ).isoformat()+'。仅本地冻结参数应用；不重训、不选参。不要输出真名，姓名统一用首字母替代。\n')
    protected={p:sha(p) for directory in (BASE,ACTUAL,CANDIDATE) for p in directory.rglob('*') if p.is_file()}
    original=read(BASE/'models_full.json')
    data=read(ACTUAL/'dataset.json')
    curves=read(ACTUAL/'formal4_curves/formal4_curves.json')
    candidates=read(CANDIDATE/'results.json')
    efficiency_results=read(CANDIDATE/'efficiency_results.json')
    history=read(CANDIDATE/'history.json')
    known=read(INITIAL/'verification/20261014T002441/known_conditions.json')
    sources={}
    def refs(value):
        if isinstance(value,dict):
            path=value.get('source')
            digest=value.get('sha256',value.get('source_sha256'))
            if isinstance(path,str) and isinstance(digest,str) and len(digest)==64:
                file=ROOT/path
                if not file.is_file(): file=INITIAL.parent/path
                if not file.is_file():
                    raise FileNotFoundError('带哈希的源引用缺失: '+path)
                if file not in protected: protected[file]=sha(file)
                assert protected[file]==digest, '来源哈希变化: '+str(file)
                sources[file.relative_to(ROOT).as_posix()]=digest
            for v in value.values(): refs(v)
        elif isinstance(value,list):
            for v in value: refs(v)
    for value in (original,data,curves,history,known): refs(value)
    for path in (INITIAL/'verification/20261014T002441/known_conditions.json',
                 INITIAL/'carryover_classification/20261014T005023/addendum_report.md',
                 ROOT/'output/t4v1_interest_diagnosis/20261014T161010990317+0800/report.md'):
        protected[path]=sha(path)
        sources[path.relative_to(ROOT).as_posix()]=protected[path]
    own=data['own_final_decision_rows'][0]['team_id']
    teams=sorted({r['team_id'] for r in data['state_pairs'] if r['market_id']==5})
    assert len(teams)==10
    def published(label,expected,unit,occurrence=0,factor=1):
        items=[p for p in known['parameters'] if p['label']==label]
        ref=items[occurrence]
        value=float(ref['current'].replace('\u00a0','').replace(' ',''))*factor
        assert math.isclose(value,expected,abs_tol=1e-12)
        return dict(value=value,unit=unit,source=ref,phase='formal',round=4,category='PUBLISHED_FORMAL4_PARAMETER')
    parameters=dict(base_rate=published('基准利率',.05,'小数',factor=.01),
        short_spread=published('高于基准的短期利率溢价',.03,'小数',factor=.01),
        wage=published('泰国',33,'千美元/人'),second_shift=published('两班倒',1.65,'乘数'),
        third_shift=published('三班倒',2.56,'乘数'),
        attrition=published('年人员离职率（without costs），%',.1,'小数',factor=.01),
        severance=published('裁员成本，占薪资%',.35,'小数',factor=.01))
    for product,capex,base_price in [('复合梁',58,1053),('连接件',1,14.2)]:
        parameters['machine/'+product]=published('机器, '+product,capex,'美元/单位')
        parameters['material/'+product]=published(product,base_price,'美元/单位')
    industry=read(ACTUAL/'industry.json')
    totals={p:{c:next(r['actual_total_kunits'] for r in industry if (r['market'],r['product'],r['country'])==(5,p,c)) for c in COUNTRIES} for p in PRODUCTS}
    rows=[r for pr in data['competitive_rows_by_product'].values() for r in pr if r['market_id']==5]
    for p in PRODUCTS:
        for c in COUNTRIES:
            pool=[r for r in rows if (r['product'],r['country'])==(p,c)]
            assert len(pool)==10 and math.isclose(sum(r['demand'] for r in pool),totals[p][c],abs_tol=1e-9)
    competitors=[{k:r[k] for k in ('market_id','team_id','phase','round','product','country','price','initial_price','general','designer','rd','previous_rd')} for r in rows]
    registry=copy.deepcopy(original)
    registry.update(version='t4v1a',base_version='t4v1',application_round=4,application_market=5,
        target_team_id=own,competition_teams=teams,formal3_market_totals_kunits=totals,
        application_parameters=parameters,formal4_curves=curves,
        frozen_candidates=dict(operations={p:efficiency_results[p]['full_history']['fit'] for p in PRODUCTS},
            connector_price={k:candidates['demand']['final_candidate'][k] for k in ('config','model')}),
        application_policy=dict(primary='SHARE',country='separate reference',ABS='diagnostic only',
            power_risk='diagnostic only',curve_spending_mapping='BLOCKED',full_profit='BLOCKED'),
        deployment_enabled=False)
    (out/'evidence').mkdir()
    actions={}
    adjusted={'TOTAL','BASELINE','GROWTH','INTEREST','RISK_EXP','FINANCE','LABOR','OPERATING','MATERIAL','MATERIAL_PROP'}
    compared={'SHARE','COUNTRY','EFF','RISK_POWER','ABS','CONNECTOR','CONNECTOR_V2','JOINT_ALLOCATION'}
    blocked={'RD','OPS','CAPACITY','HORIZON'}
    for name,item in registry['model_inventory'].items():
        action='应用调整' if name in adjusted else '候选对照' if name in compared else '缺数据跳过' if name in blocked else '沿用'
        actions[name]=dict(action=action,original_status=item['status'],deployment_enabled=False)
        src=(BASE/item['artifact']).resolve()
        if src==BASE/'models_full.json':
            item['artifact']='models_full.json'
        else:
            dest=out/'evidence'/src.name
            if dest.exists() and sha(dest)!=sha(src):
                dest=out/'evidence'/(sha(src)[:12]+'_'+src.name)
            if src.suffix not in ('.json','.csv','.md'):
                raise ValueError('不复制HTML或原始网页证据: '+str(src))
            shutil.copy2(src,dest)
            item['artifact']=dest.relative_to(out).as_posix()
        item['application_action']=action
    assert len(actions)==29
    save(out/'models_full.json',registry)
    save(out/'baseline_models_full.json',original)
    save(out/'model_inventory.json',dict(count=29,models=actions,missing_not_zero=True))
    save(out/'application_parameters.json',parameters)
    save(out/'formal4_curves.json',curves)
    save(out/'inputs.json',dict(competitors=competitors,formal3_market_totals_kunits=totals,
        industry_actual=industry,source_rows=rows,history=history,
        financial_state_pairs=data['state_pairs'],efficiency_results=efficiency_results))
    save(out/'source_manifest.json',dict(raw_sources=sources,
        protected_hashes={p.relative_to(ROOT).as_posix():h for p,h in protected.items()},
        raw_files_copied=False,training_cutoff='formal3_actual',application_period='formal4'))
    skipped=[dict(model='RD/OPS/EFF_FORWARD',reason='曲线来源及上期投入已核实；当期支出→有效横轴映射、完整存量未证实'),
        dict(model='SHARE/COUNTRY_REAL_INPUTS',reason='99队产品/国家分配缺失；本组曲线不可推广其他队'),
        dict(model='CAPACITY',reason='投资生效时点冲突；仅更新机器单价，不排名投资收益'),
        dict(model='FINANCE',reason='期初/期末/平均风险状态与计息时点未识别；税亏、完整现金链缺失'),
        dict(model='CONNECTOR_V2',reason='机会不是确认订单；中标、交付及实际预收余款状态缺失'),
        dict(model='MATERIAL_TRANSFER',reason='缺新基价实际标签；只作固定参数敏感性'),
        dict(model='HORIZON',reason='正式4→5→6前景及完整结转状态缺失，不计算剩余利润排名'),
        dict(model='NESTED_DEMAND_COEFFICIENT_REPLAY',reason='旧嵌套留出只保存配置和预测，未保存每折系数；只核验保存预测的指标，不重训恢复系数')]
    save(out/'skipped.json',skipped)
    save(out/'tender_opportunities.json',dict(round=4,status='TENDER_OPPORTUNITY_ONLY',
        opportunities=[dict(product='连接件',quantity_kunits=200),dict(product='复合梁',quantity_kunits=3)],
        confirmed_revenue=None,confirmed_advance=None,source_text=known['five_sections']['大客户订单'],
        source=dict(file='output/round_close/20261013_formal3_close/formal4_initial/raw/market5_formal4_outlook.json',
            sha256=sha(INITIAL/'raw/market5_formal4_outlook.json'),section='大客户订单')))
    state=next(r['closing']['values'] for r in data['state_pairs'] if (r['market_id'],r['team_id'])==(5,own))
    request=dict(version='t4v1a',market_id=5,phase='formal',round=4,
        growth={'复合梁':-.175,'连接件':.05},competition_assumption='FORMAL3_ACTUAL_STRATEGY_HELD',
        competitors=competitors,market_totals_kunits=totals,production={},
        financial=dict(state_basis='FORMAL3_CLOSING_STATE_HELD',state={k:state[k] for k in ('equity','assets','long_debt','short_debt')}))
    save(out/'example_request.json',request)
    comparisons=[]
    historical=[]
    efficiency_comparison=[]
    material_sensitivity=[]
    replay_count=0
    with no_training():
        checks=self_check(registry)
        for product,pr in data['competitive_rows_by_product'].items():
            for name in ('SHARE','COUNTRY/泰国','COUNTRY/印尼'):
                pool=pr if name=='SHARE' else [r for r in pr if r['country']==name.split('/')[1]]
                m=original['demand'][product][name]
                x=core.features(pool,original['curves']['rd/'+product]['parameters'],m['rho'],m['piecewise'])
                old_pred=core.predict(pool,x,m['beta'])
                new_model=registry['demand'][product][name]
                assert np.array_equal(old_pred,core.predict(pool,x,new_model['beta']))
                assert math.isclose(core.score(pool,old_pred)*100,m['training_mae_pp'],abs_tol=1e-9)
                replay_count+=len(pool)
                historical.extend(dict(product=product,model=name,market=r['market_id'],team=r['team_id'],country=r['country'],predicted_share=float(v)) for r,v in zip(pool,old_pred))
                for fold in m['nested_validation']['folds']:
                    selected=fold['selected']
                    held=fold['held_markets']
                    te=[r for r in pool if r['market_id'] in held]
                    saved={tuple(r['key']):r['predicted_share'] for r in m['nested_validation']['predictions']}
                    predictions=np.array([saved[tuple(core.key(r))] for r in te])
                    assert math.isclose(core.score(te,predictions)*100,fold['mae_pp'],abs_tol=1e-9)
                    assert not set(tuple(k) for k in fold['training_keys']) & set(tuple(k) for k in fold['test_keys'])
        for delta in (-.15,-.175,-.2):
            scenario=copy.deepcopy(request);scenario['growth']['复合梁']=delta
            value=apply_request(registry,scenario)
            for step,growth in [('总量前参考',dict.fromkeys(PRODUCTS,0.)),('总量情景',scenario['growth'])]:
                pred=demand_reference(registry,competitors,totals,growth)
                for r in pred['predictions']:
                    if r['team_id']==own:
                        comparisons.append(dict(step=step,beam_growth=delta,product=r['product'],country=r['country'],
                            baseline_demand_kunits=r['demand_kunits'],t4v1a_demand_kunits=r['demand_kunits'],
                            market_total_kunits=r['market_total_kunits'],share=r['share'],
                            explanation='两版同输入同冻结响应；总量前后差异单列，曲线映射未通过故无响应替换'))
            save(out/f'scenario_{abs(delta):.3f}.json',value)
        incomplete=competitors[:-1]
        assert demand_reference(registry,incomplete,totals,request['growth'])['skipped']
        checks['incomplete_competition_rejected_without_renormalization']=True
        curves_diagnostics={}
        for key,c in curves['curves'].items():
            ctx=dict(market_id=5,team_id=own,phase='formal',round=4,previous_input=c['upstream_condition']['previous_value'],unit='千美元',coordinate_kind='effective_investment_scenario')
            assert ctx['previous_input']=={'rd_beam':1000,'rd_connector':400,'operations_thailand':600}[key]
            curves_diagnostics[key]=[curve_at(registry,key,ctx,x) for x in (0,c['x_range'][1]/2,c['x_range'][1])]
        save(out/'curve_coordinate_diagnostics.json',curves_diagnostics)
        for product in PRODUCTS:
            params=original['curves']['operations/泰国']['parameters']
            erows=original['efficiency'][product]['rows']
            hrows={(r['market_id'],r['team_id']):r for r in history}
            for variant in ('original_replay','full_history'):
                archive=efficiency_results[product][variant]
                saved={(r['market'],r['team']):r['predicted'] for r in archive['predictions']}
                for row in erows:
                    fold=next(f for f in archive['folds'] if f['market']==row['market_id'])
                    model=fold['fit']
                    earlier=hrows[row['market_id'],row['team_id']]['refs']['operations'][0]['value']
                    x=row['operations']+model['rho']*row['previous_operations']+(model['rho']**2*earlier if variant=='full_history' else 0)
                    predicted=model['theta']*float(curve_value(x,params,'saturation'))
                    assert math.isclose(predicted,saved[row['market_id'],row['team_id']],rel_tol=1e-12)
            row=next(r for r in erows if r['team_id']==own)
            source=ROOT/row['source']['production']['source'];doc=read(source)
            col=row['source']['production']['column']
            cells=next((ti,ri,r) for ti,table in enumerate(doc['tables']) for ri,r in enumerate(table) if r and r[0]=='机器产能, '+product+', 千单位')
            cap=float(cells[2][col].replace('\u00a0','').replace(' ',''))
            plan=dict(capacity_kunits=cap,production_kunits=row['source']['production']['value'],previous_workers=row['source']['workers']['value'])
            for name,model in [('t4v1',original['efficiency'][product]['chosen']),('t4v1a_history_candidate',registry['frozen_candidates']['operations'][product])]:
                earlier=hrows[5,own]['refs']['operations'][0]['value']
                x=row['operations']+model['rho']*row['previous_operations']+(model['rho']**2*earlier if name!='t4v1' else 0)
                e=model['theta']*float(curve_value(x,params,'saturation'))
                costs=labor_cost(registry,plan,e)
                selected=original['materials'][product]['selected']
                mat=material.predict(original['materials'][product]['models'][selected],parameters['material/'+product]['value'],plan['production_kunits'])
                efficiency_comparison.append(dict(product=product,variant=name,effective_operations_kusd=x,efficiency=e,
                    payroll_kusd=costs['payroll'],firing_kusd=costs['firing'],workers=costs['workers'],
                    material_cost_kusd=mat['material_cost_kusd'],cost_kusd=costs['payroll']+costs['firing']+mat['material_cost_kusd'],
                    status='FORMAL3_RESPONSE_FIXED_PRODUCTION_FORMAL4_WAGE_SCENARIO',
                    capacity_source=dict(source=str(source.relative_to(ROOT)),table=cells[0],row=cells[1],column=col),
                    note='历史效率保持的成本敏感性；不是回合4曲线映射或效率预测，未扣研发/运营等费用'))
            for scale in (1.,.9,1.1):
                for form,m in original['materials'][product]['models'].items():
                    material_sensitivity.append(dict(product=product,base_scale=scale,form=form,
                        **material.predict(m,parameters['material/'+product]['value']*scale,plan['production_kunits']),
                        status='CURRENT_BASE_PRICE' if scale==1 else 'FUTURE_BASE_SENSITIVITY_ONLY'))
        price_response=[]
        for delta in (0.,-.05,-.1):
            for product in PRODUCTS:
                for country in COUNTRIES:
                    probe=copy.deepcopy(competitors)
                    for r in probe:
                        if (r['team_id'],r['product'],r['country'])==(own,product,country): r['price']*=1+delta
                    for linear in ((False,True) if product=='连接件' else (False,)):
                        result=demand_reference(registry,probe,totals,request['growth'],linear=linear)
                        row=next(r for r in result['predictions'] if (r['team_id'],r['product'],r['country'])==(own,product,country))
                        price_response.append(dict(product=product,country=country,price_delta=delta,linear_candidate=linear,
                            share=row['share'],demand_kunits=row['demand_kunits'],status='FROZEN_RESPONSE_PRICE_SCENARIO'))
        for form in interest.FORMS:
            old=interest.premium(form,original['risk'][form]['parameters'],data['risk'])
            new=interest.premium(form,registry['risk'][form]['parameters'],data['risk'])
            assert np.array_equal(old,new)
        for product in PRODUCTS:
            assert registry['frozen_candidates']['operations'][product]==efficiency_results[product]['full_history']['fit']
        checks.update(no_training_or_selection_calls=True,unchanged_fitted_parameters=True,
            frozen_demand_replay_records=replay_count,nested_saved_prediction_metrics_verified=True,
            saved_efficiency_holdout_predictions_replayed=True,share_and_market_total_conservation=True,
            formal4_curve_parameters_unchanged=True,history_condition_1000_400_600_verified=True,
            original_archived_rate_parameters_replayed=True,unknown_profit_and_horizon_not_ranked=True)
    save(out/'historical_replay.json',dict(scope='正式3同期条件复算，非回合4成绩',predictions=historical))
    save(out/'comparison.json',dict(demand=comparisons,efficiency_cost=efficiency_comparison,
        price_response=price_response,material_sensitivity=material_sensitivity,
        finance=apply_request(registry,request)['finance'],
        staged_status=[dict(step='总量',status='APPLIED'),dict(step='曲线映射',status='SKIPPED_MISSING_EVIDENCE'),
            dict(step='运营历史',status='HISTORICAL_COST_SCENARIO_ONLY'),dict(step='利率保护',status='CONDITIONAL_SCENARIO')],
        combined_scope='总量+冻结响应+利率保护；曲线与运营历史前向映射未证实，不合成为完整利润'))
    for name,records in [('comparison',comparisons),('efficiency_cost_comparison',efficiency_comparison),('price_response',price_response),('material_sensitivity',material_sensitivity)]:
        with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    checks['source_and_original_archives_unchanged']=all(sha(p)==h for p,h in protected.items())
    assert checks['source_and_original_archives_unchanged']
    code_files=snapshot_code(out)
    # shortcut: ship the existing Windows CPython 3.12 SciPy binaries; other platforms use the version lock.
    for name in ('scipy','scipy.libs','scipy-1.18.1.dist-info'):
        shutil.copytree(ROOT/'work/python_packages'/name,out/'dependencies'/name)
    save(out/'dependencies.json',dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,
        platform=sys.platform,local_code=code_files,bundled_scipy='Windows CPython 3.12',
        non_windows_install='python -m pip install -r requirements.txt'))
    (out/'requirements.txt').write_text(f'numpy=={np.__version__}\nscipy=={scipy.__version__}\n',encoding='utf-8')
    lines=['# t4v1a 非重训优化与对照', '', '不要输出真名，姓名统一用首字母替代。', '',
        '独立保留29类模型及冻结候选；训练回合3，应用情景回合4。未重训、未选参、未采集或修改平台，t4v1保留。', '',
        '## 已应用与对照', '',
        '- 正式4参数：基准利率5%、短贷溢价3个百分点、工资33千美元/人；机器58／1美元/单位；材料1053／14.20美元/单位。',
        '- 行业情景：复合梁−15%／−17.5%／−20%，连接件+5%；两国分别缩放真实需求总量。',
        '- 主份额保持SHARE；COUNTRY与连接件线性价格候选分列；ABS仍仅诊断，没有默认平均。',
        '- 三条回合4曲线冻结保存，上期投入1000／400／600、情境与范围核验；有效坐标求值开放，但自动支出映射跳过。',
        '- 运营历史候选仅用冻结参数复算，并在历史效率保持、固定产量和当期工资下比较人员、工资、解聘费及材料成本。',
        '- 杠杆幂函数禁止应用；指数函数仅限范围内显式状态情景，5%与4%利率差及税前现金敏感性单列。', '',
        '## 同输入对照', '', '| 产品 | 国家 | 正式3真实需求总量 | −17.5%／+5%情景总量 | 本组SHARE情景需求 |', '|---|---|---:|---:|---:|']
    central=read(out/'scenario_0.175.json')
    for r in central['demand']['predictions']:
        if r['team_id']==own:
            lines.append(f"| {r['product']} | {r['country']} | {totals[r['product']][r['country']]:.6f} | {r['market_total_kunits']:.6f} | {r['demand_kunits']:.6f} |")
    lines+=['', '单位均为千单位。两版在相同当期参数及冻结响应下需求一致；总量改变单列，不冒称系数优化。上述仍假设正式3策略和响应保持。', '',
        '| 产品 | 版本 | 效率（千单位/人） | 工资（千美元） | 解聘费（千美元） |', '|---|---|---:|---:|---:|']
    for r in efficiency_comparison:
        lines.append(f"| {r['product']} | {r['variant']} | {r['efficiency']:.8f} | {r['payroll_kusd']:.6f} | {r['firing_kusd']:.6f} |")
    finance=central['finance']
    lines+=['', '这些是正式3曲线响应保持的成本情景，不是回合4效率预测，不含完整经营费用或利润。', '',
        f"固定正式3期末风险状态及长债整期保持时，基准4%→5%使长贷利率增加{finance['rate_delta']*100:.6f}个百分点，税前利息增加{finance['long_interest_delta_kusd']:.6f}千美元；计息时点及现金终值未识别。", '',
        '## 缺数据跳过', '']+[f"- {r['model']}：{r['reason']}。" for r in skipped]
    lines+=['', '## 验收与复现', '',
        f'冻结需求训练预测{replay_count}条复算及保存的嵌套留出预测指标核验；双产品效率保存留出预测、两风险函数冻结参数复算通过。',
        '份额与市场总量守恒、缺竞争输入拒绝、曲线情境/边界、工资10%上涨、班次/人员/解聘、利率保护、确认订单预收与余款规则、未知利润与期限检查通过。',
        '完整检查见acceptance.json；历史验证只作已有结果复算，不是新增回合4成绩。', '',
        '在此交付目录使用Python 3.12和锁定NumPy运行：', '',
        '```powershell', 'python code/model_v2/t4v1a.py --bundle . --self-check',
        'python code/model_v2/t4v1a.py --bundle . --request example_request.json', '```', '',
        '已保存本地导入闭包、SciPy依赖副本与版本锁；原始网页及人员表头不复制。输入、参数、曲线与必要证据均随交付保存。',
        '接口缺输入返回具体缺口；非法数值/情境拒绝。请求可填写显式有效曲线坐标及固定生产效率情景；这些输入不自动升级为已核实状态。', '',
        '跳过补采、重训、完整利润和剩余回合搜索。风险：前向历史映射、实际计息机制和订单状态未齐，不能据此推荐完整决策或宣称六回合最优。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    checks['report_table_numbers_match_json']=all(f"{r['payroll_kusd']:.6f}" in (out/'report.md').read_text(encoding='utf-8') for r in efficiency_comparison)
    save(out/'acceptance.json',checks)
    with log.open('a',encoding='utf-8') as f:
        f.write('\n完成：'+datetime.now(TZ).isoformat()+'。29类完整保存；全部冻结复算与规则检查通过，原模型及原件哈希未变。曲线前向映射、投资时序、完整利润/订单及HORIZON缺数据跳过。\n')
    save(out/'manifest.json',dict(version='t4v1a',status='FROZEN_APPLICATION_WITH_EXPLICIT_GAPS',
        generated_at=datetime.now(TZ).isoformat(),training_performed=False,deployment_enabled=False,
        output_hashes={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    index=ROOT/'output/t4v1a/README.md'
    index.write_text('# t4v1a\n\n独立非重训应用版，t4v1保留。\n\n[报告]('+out.name+'/report.md)、[模型]('+out.name+'/models_full.json)、[验收]('+out.name+'/acceptance.json)。\n',encoding='utf-8')
    print(json.dumps(dict(output=str(out),checks=checks),ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--bundle',type=Path,help='Read an existing self-contained t4v1a bundle')
    parser.add_argument('--request',type=Path,help='Evaluate request; print JSON without modifying the bundle')
    parser.add_argument('--self-check',action='store_true')
    args=parser.parse_args()
    if args.bundle:
        registry=read(args.bundle/'models_full.json')
        with no_training():
            result=self_check(registry) if args.self_check else apply_request(registry,read(args.request or args.bundle/'example_request.json'))
        print(json.dumps(result,ensure_ascii=False,allow_nan=False)); return
    if args.request:
        parser.error('--request requires --bundle')
    if args.self_check:
        parser.error('--self-check requires --bundle (read-only checks on a saved version)')
    build_bundle(args.output)


if __name__ == '__main__':
    main()
