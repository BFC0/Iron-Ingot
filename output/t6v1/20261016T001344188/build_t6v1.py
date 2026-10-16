"""Build, verify and solve the isolated formal6 terminal application."""
import argparse
import hashlib
import itertools
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
import numpy as np
from scipy.optimize import differential_evolution
from fit_chart_json import fit_points
import core
import t6v1 as app

BASE = ROOT/'output/t6v0/20261015T235330003362+0800'
CLOSE = ROOT/'output/round_close/20261015_formal5_close'
INITIAL = CLOSE/'formal6_initial'
TZ = timezone(timedelta(hours=8))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
num = lambda v: float(re.sub(r'\s', '', str(v)))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def build(out):
    source = app.read(BASE/'models_full.json')
    assert source['version'] == 't6v0' and source['training_round'] == 5 and not source['deployment_enabled']
    fields = app.read(INITIAL/'current_group_draft.json')
    assert len(fields) == len({f['key'] for f in fields}) == 56
    values = {f['key']: f['value'] for f in fields}
    params = app.read(INITIAL/'published_parameters.json')
    for label, expected in [('企业所得税率, %', 29.), ('最低现金, 千 美元', 2000.), ('基准利率', 5.),
        ('高于基准的短期利率溢价', 3.5), ('基础成本', 12000.), ('市场调研', 50.),
        ('库存持有成本', .6), ('机器, 复合梁', 78.), ('机器, 连接件', 1.1), ('泰国', 43.5)]:
        matches = [v for v in params if v['label'] == label]
        assert len(matches) == 1 and num(matches[0]['current']) == expected, label
    sources = {p.relative_to(ROOT).as_posix(): sha(p) for p in BASE.rglob('*') if p.is_file()}
    for item in app.read(INITIAL/'source_manifest.json'):
        assert sha(ROOT/item['source']) == item['sha256']
        sources[item['source']] = item['sha256']
    for p in INITIAL.glob('*.json'):
        sources[p.relative_to(ROOT).as_posix()] = sha(p)
    for path, expected in app.read(BASE/'input_manifest.json')['input_hashes'].items():
        assert sha(ROOT/path) == expected, path
        sources[path] = expected
    for f in ['code/model_v2/t6v0.py', 'code/model_v2/t6v0_demand.py', 'code/model_v2/t6v1.py', 'work/build_t6v1.py']:
        sources[f] = sha(ROOT/f)
    curves = {}
    for chart in app.read(INITIAL/'curve_original_literals.json'):
        x = np.array([num(v['label']) for v in chart['data']['categories'][0]['category']])
        for series in chart['data']['dataset']:
            if not series['seriesname'].startswith('曲线,'):
                continue
            p = series['seriesname'].split(', ')[1]
            key = 'operations/泰国' if chart['id'] == 'cost.efficiency.chart' else 'rd/'+p
            form = 'saturation' if key.startswith('operations') else 'power'
            y = np.array([float(v['value']) for v in series['data']])
            assert len(x) == len(y) == 200 and np.isfinite(y).all()
            curves[key] = dict(fit_points(x, y, form), form=form, points=np.c_[x, y].tolist(),
                x_range=[float(x.min()), float(x.max())], application_round=6,
                source='formal6_initial/curve_original_literals.json', scope='图形拟合；不是新增经营训练标签')
    dataset = app.read(BASE/'dataset.json')
    ownid = dataset['own_final_decision_rows'][0]['team_id']
    pair = next(q for q in dataset['state_pairs'] if q['market_id'] == 5 and q['team_id'] == ownid)
    state = pair['closing']['values']
    competition = {}
    own_indices = {}
    rows = app.read(BASE/'demand_actual_rows.json')
    invalid = app.read(BASE/'demand_invalid_rows.json')
    for p in app.PRODUCTS:
        competition[p] = {}
        own_indices[p] = {}
        for c in app.COUNTRIES[:2]:
            rr = [q for q in rows[p]+[q for q in invalid if q['product'] == p] if q['market_id'] == 5 and q['country'] == c]
            rr.sort(key=lambda q: q['team_id'])
            assert len(rr) == len({q['team_id'] for q in rr}) == 10
            competition[p][c] = [{k: q[k] for k in ['team_id', 'price', 'general', 'designer', 'rd', 'previous_rd']} for q in rr]
            own_indices[p][c] = next(i for i, q in enumerate(rr) if q['team_id'] == ownid)
    totals = app.read(BASE/'industry.json')
    market = [[next(q['total'] for q in totals if q['market'] == 5 and q['product'] == p and q['country'] == c)*g for c, g in zip(app.COUNTRIES, [1.04, 1.05])]+[ph] for p, ph in zip(app.PRODUCTS, [5., 105.])]
    capdoc = app.read(CLOSE/'own_formal6_productioninvestments.json')
    capacity = [num(capdoc['tables'][3][i][2]) for i in [3, 4]]
    inv = [q['opening']['value'] for q in app.read(INITIAL/'carryover_comparison.json')[:2]]
    balance_path = CLOSE/'raw/market5_formal5_balancesheet.json'
    table = app.read(balance_path)['tables'][0]
    inventory_value = num(next(q[6] for q in table if len(q) > 6 and q[0] == '成品库存'))
    assert inv[0] == 0 and inv[1] > 0
    sources[balance_path.relative_to(ROOT).as_posix()] = sha(balance_path)
    mat = []
    for j, p in enumerate(app.PRODUCTS):
        m = source['materials'][p]
        chosen = m['models'][m['selected']]
        published = [720., 9.75][j]
        mat.append(published+chosen['parameter'] if m['selected'] == 'additive' else published*(1+chosen['parameter']) if m['selected'] == 'proportional' else published)
    baseline = []
    for section in ['每单位价格', '一般营销, 千 美元', '设计师营销, 千 美元']:
        for j, p in enumerate(app.PRODUCTS):
            for c in app.COUNTRIES:
                v = values[f'{section}|{p}|{c}'+(', 美元' if section == '每单位价格' else '')]
                baseline.append([1600., 23.][j] if section == '每单位价格' and c == '菲律宾' else v)
    baseline += [values['研发, 千 美元||'+p] for p in app.PRODUCTS]
    baseline += [values['运营改进, 千 美元||泰国'], 0., 0., 0., 0.]
    baseline += [values['产能分配, %|泰国|'+p] for p in app.PRODUCTS]
    baseline += [values['财务决策||长期贷款变化(增加 + / 减少 -), 千 美元']/100]
    # Analysis bounds are not platform constraints; report any boundary optimum.
    bounds = [[500., 4000.]]*3+[[10., 50.]]*3+[[0., 3000.]]*6+[[0., 4000.]]*6+[[0., 2600.]]*2+[[0., 1200.]]+[[0., 20.]]*4+[[0., 100.]]*2+[[-state['long_debt']/100, 100.]]
    scenarios = [dict(name='中性'), dict(name='菲律宾价格弹性-20%', ph_price=.8), dict(name='菲律宾价格弹性+20%', ph_price=1.2),
        dict(name='菲律宾营销响应-20%', ph_marketing=.8), dict(name='菲律宾营销响应+20%', ph_marketing=1.2),
        dict(name='联合不利', market_scale=.9, rival_scale=1.2, efficiency_scale=.9, material_scale=1.05, ar_days=60.),
        dict(name='印尼投产前不折旧', indo_depreciation=0.), dict(name='期初税亏919情景', tax_loss_assumption=919.),
        dict(name='无新增厂房支出情景', building_capex=0.)]
    reg = dict(version='t6v1', base_version='t6v0', application_round=6, training_round=5, state=state,
        state_basis='正式5期末实际结转假设；15项缺独立期初核验，非已核全部期初状态',
        unknown_opening_state=app.read(INITIAL/'carryover_comparison.json'),
        demand=source['demand'], training_curves=source['curves'], curves=curves, risk=source['risk'],
        competition=competition, own_indices=own_indices, market_totals=market, guide_prices=[1600., 23.],
        baseline=baseline, bounds=bounds, variable_names=app.NAMES, integer_indices=app.INTEGER,
        inventory=inv, inventory_book=[0., inventory_value], capacity=capacity,
        other_assets=state['assets']-sum(state[k] for k in ['cash', 'ar', 'machine_book', 'building_book'])-inventory_value,
        efficiency=[source['efficiency'][p]['production']['value']/source['efficiency'][p]['workers']['value'] for p in app.PRODUCTS],
        previous_workers=[source['efficiency'][p]['workers']['value'] for p in app.PRODUCTS],
        previous_rd=[2600., 231.], previous_ops=754.,
        investment_mapping=dict(rd_current=.75, rd_previous=.5, ops_previous=.35,
            status='正式5映射迁移及同投入归一化假设；未在正式6独立识别'),
        material_cost=mat, machine_prices=[78., 1.1], machine_depreciation=.15,
        freight=[[30., 120., 170.], [.5, 2., 2.2]], wage=43.5, shift2=1.65, shift3=2.56,
        holding=.6, fixed_cost=12050., building_capex_assumption=800., minimum_cash=2000.,
        base_rate=.05, short_spread=.035, general_limit=3000., designer_limit=4000., scenarios=scenarios,
        deployment_enabled=False, full_global_optimum=False, training_performed=False,
        marketing_scope='公司合计费用代理；12项细分分配不可识别，优化合计并明确标为部分求解',
        unresolved=['投标中标概率及交付收款机制：四项报价/营销未求解，暂不投标', '分包价格、产量及支付机制缺失：未求解，暂关闭',
            '期初税亏、完整历史投入存量、现金时点及15项独立期初状态', '营销细分及研发产品分配响应未作因果识别',
            '印尼投资当期折旧未核：同时计算0%和15%；不影响产量为0', '建造支出800、厂房折旧7%、30天收付账期和平均计息沿用旧应用假设'])
    save(out/'models_full.json', reg)
    save(out/'source_hashes.json', sources)
    save(out/'published_parameters.json', params)
    save(out/'current_fields.json', fields)
    return reg, fields


def self_check(m):
    x = m.baseline.copy()
    cfg = m.r['scenarios'][0]
    a = m.evaluate(x, cfg, True)
    assert a['round'] == a['start_round'] == a['end_round'] == 6
    assert a['production_indonesia'] == [0., 0.]
    assert np.max(abs(np.array(a['shares']).sum(axis=2)-1)) < 1e-12
    assert abs(a['balance_error']) < 1e-7 and a['quantity_error'] < 1e-8
    batch = m.evaluate(np.column_stack([x, x]), cfg)[0]
    assert np.allclose(batch, a['profit'])
    for i in [23, 24]:
        trial = x.copy(); trial[i] += 1
        for dep in [0., 1.]:
            base = m.evaluate(x, dict(indo_depreciation=dep), True)
            b = m.evaluate(trial, dict(indo_depreciation=dep), True)
            assert b['production_indonesia'] == [0., 0.] and b['production'] == base['production'] and b['capacity'] == base['capacity']
            assert b['indonesia_capex'] > base['indonesia_capex'] and b['cash'] < base['cash']
            delta = b['machine_depreciation']-base['machine_depreciation']
            assert abs(delta-(b['indonesia_capex']-base['indonesia_capex'])*.15*dep) < 1e-8
    trial = x.copy(); trial[21] += 1
    assert abs(m.evaluate(trial, cfg, True)['capacity'][0]-a['capacity'][0]-1) < 1e-8
    absent = m.evaluate(x, dict(disable_ph=True), True)
    assert np.all(np.array(absent['demand'])[:, 2] == 0)
    assert np.allclose(np.array(absent['demand'])[:, :2], np.array(a['demand'])[:, :2])
    # Independently replay the frozen feature recipe and ten-team softmax on the old countries.
    _, prediction = m.demand(x, dict(replay_training=True, disable_ph=True))
    for j, p in enumerate(app.PRODUCTS):
        for k, c in enumerate(app.COUNTRIES[:2]):
            rr = [dict(q, market_id=5, phase='formal', round=5, country=c, initial_price=1.) for q in m.r['competition'][p][c]]
            f = core.features(rr, m.r['training_curves']['rd/'+p]['parameters'], .5, False)
            expected = core.predict(rr, f, m.r['demand'][p]['COUNTRY/'+c]['beta'])
            assert np.allclose(expected, prediction[j, k, :, 0], atol=1e-12)
    assert max(m.evaluate(x, cfg, True, priorities=order)['profit'] for order in itertools.product(range(6), repeat=2)) <= a['profit']+1e-8
    for stressed in [x, np.r_[x[:21], [20., 20., 20., 20.], x[25:27], [-76.]]]:
        ev = m.evaluate(stressed, dict(market_scale=.5), True)
        assert abs(ev['balance_error']) < 1e-7
        assert ev['cash'] >= 2000-1e-7 and ev['short_debt'] >= 0
    ph = x.copy(); ph[:6] = np.tile(m.r['guide_prices'], (3, 1)).T.ravel()
    equal = dict(m.r)
    # Identical inputs must imply 1/10 in the new market, independent of the old own share.
    original = m.r['competition']
    m.r['competition'] = json.loads(json.dumps(original))
    for p in app.PRODUCTS:
        k = m.r['own_indices'][p]['印尼']
        for i in range(10):
            m.r['competition'][p]['印尼'][i].update({q: m.r['competition'][p]['印尼'][k][q] for q in ['general', 'designer', 'rd', 'previous_rd']})
    _, identical = m.demand(ph, dict(replay_training=True))
    assert np.allclose(identical[:, 2], .1)
    m.r['competition'] = original
    for bad in [np.full(28, np.nan), x[:-1], np.r_[[-1.], x[1:]], np.r_[x[:21], .5, x[22:]], [True]+x[1:].tolist()]:
        try:
            m.validate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid decision accepted')
    return dict(terminal_round_only=True, indonesia_zero_production=True, indonesia_cash_and_depreciation_scenarios=True,
        thailand_immediate_capacity=True, conservation=True, shares_normalized=True, vectorized_replay=True,
        philippines_disabled_old_countries_unchanged=True, independent_frozen_demand_replay=True,
        all_36_logistics_pairs_checked=True, invalid_inputs_rejected=True,
        short_debt_tax_cash_balance=True, equal_philippine_inputs_equal_share=True)


def rounded(x):
    x = x.copy()
    x[:3] = np.round(x[:3], 1)
    x[3:6] = np.round(x[3:6], 1)
    x[6:21] = np.round(x[6:21])
    x[21:25] = np.rint(x[21:25])
    x[25:27] = np.round(x[25:27], 1)
    x[27] = round(x[27])
    return x


def solve(m, out, iterations):
    integrality = [i in app.INTEGER for i in range(28)]
    traces = []
    candidates = []
    for name, scenarios in [('中性', m.r['scenarios'][:1]), ('稳健', m.r['scenarios'][:6])]:
        def score(x):
            values = [m.evaluate(x, c) for c in scenarios]
            return -np.min([v[0] for v in values], axis=0)+np.max([v[2] for v in values], axis=0)
        best = None
        for seed in [11, 29]:
            result = differential_evolution(score, m.bounds, seed=seed, popsize=7, maxiter=iterations,
                tol=.0005, atol=.5, polish=False, vectorized=True, updating='deferred',
                integrality=integrality, x0=m.baseline)
            traces.append(dict(plan=name, seed=seed, success=bool(result.success), iterations=result.nit, objective=float(result.fun)))
            print('SEARCH', name, seed, result.nit, -result.fun, flush=True)
            save(out/'search_trace.json', traces)
            if best is None or result.fun < best.fun:
                best = result
        x = rounded(best.x)
        for _ in range(4):
            changed = False
            for i in range(28):
                step = .1 if i < 6 or i in [25, 26] else 1.
                options = [x[i], x[i]-step, x[i]+step]
                if i in range(21, 25): options = list(range(21))
                if i == 27: options = list(range(int(m.bounds[i, 0]), int(m.bounds[i, 1])+1))
                if 6 <= i < 21: options += [0., max(0., x[i]*.9), x[i]*1.1]
                options = sorted({float(round(v, 1 if step == .1 else 0)) for v in options if m.bounds[i, 0] <= v <= m.bounds[i, 1]})
                trials = np.repeat(x[:, None], len(options), axis=1); trials[i] = options
                scores = score(trials); at = int(np.argmin(scores))
                if scores[at] < score(x)[0]-1e-7:
                    x[i] = options[at]; changed = True
            if not changed: break
        m.validate(x)
        # Aggregate proxies cannot identify splits; use a documented deterministic display allocation.
        before_split = score(x).copy()
        for start in [6, 12]:
            total = round(float(x[start:start+6].sum()))
            weights = m.baseline[start:start+6].reshape(2, 3).copy()
            weights[:, 2] = weights[:, :2].mean(axis=1)
            weights = weights.ravel()/weights.sum()
            split = np.floor(total*weights)
            split[np.argsort(total*weights-split)[::-1][:int(total-split.sum())]] += 1
            x[start:start+6] = split
        assert np.allclose(score(x), before_split)
        neutral = m.evaluate(x, m.r['scenarios'][0], True)
        fixed = [app.ORDERS.index(tuple(q)) for q in neutral['priorities']]
        evaluations = [dict(scenario=c['name'], **m.evaluate(x, c, True, priorities=fixed)) for c in m.r['scenarios']]
        candidates.append(dict(name=name, x=x.tolist(), evaluations=evaluations,
            boundary_variables=[app.NAMES[i] for i, v in enumerate(x) if abs(v-m.bounds[i, 0]) < 1e-7 or abs(v-m.bounds[i, 1]) < 1e-7]))
        save(out/'candidates_partial.json', candidates)
    return candidates


def field_page(f):
    s, p, label = f['section'], f['product'], f['label']
    if s in ['需求, 千单位', '预计市场增长，%', '总市场需求, 千单位']:
        j = app.PRODUCTS.index(p)
        return (0, j, 0 if s == '预计市场增长，%' else 1 if s == '总市场需求, 千单位' else 2, app.COUNTRIES.index(label))
    if s == '需求增长预估, %': return (1, 0, app.PRODUCTS.index(label), 0)
    if s == '投资决策, 千单位': return (1, 1+['泰国', '印尼'].index(p), app.PRODUCTS.index(label.replace('机器, ', '')), 0)
    if s == '产能分配, %': return (2, 0 if label == '分包制造' else 1, 0 if label == '分包制造' else app.PRODUCTS.index(label), 0)
    if s == '生产效率, 千单位/人': return (2, 2, app.PRODUCTS.index(label), 0)
    if s == '研发, 千 美元': return (2, 3, app.PRODUCTS.index(label), 0)
    if s == '运营改进, 千 美元': return (2, 4, 0, 0)
    if s in ['每单位价格', '一般营销, 千 美元', '设计师营销, 千 美元']:
        c = label.replace(', 美元', '')
        return (3+(['泰国', '印尼', '菲律宾', '大客户订单'].index(c)), app.PRODUCTS.index(p), ['每单位价格', '一般营销, 千 美元', '设计师营销, 千 美元'].index(s), 0)
    if s == '物流决策': return (7, app.PRODUCTS.index(p), app.COUNTRIES.index(label), 0)
    if s in ['财务决策', '财务']: return (8, 0 if s == '财务决策' else 1, 0, 0)
    raise ValueError(f['key'])


def field_value(f, candidate, r):
    s, p, c = f['section'], f['product'], f['label']
    x = candidate['x']; ev = candidate['evaluations'][0]
    if c.startswith('大客户订单') or c == '分包制造':
        return f['value'], '未求解', '机会不是确认订单；缺中标/分包机制，暂不投标或关闭；非优化结论'
    if s in ['每单位价格', '一般营销, 千 美元', '设计师营销, 千 美元']:
        i = app.PRODUCTS.index(p)*3+app.COUNTRIES.index(c.replace(', 美元', ''))
        offset = ['每单位价格', '一般营销, 千 美元', '设计师营销, 千 美元'].index(s)*6
        return x[offset+i], '条件求解' if offset == 0 else '合计求解；细分未识别', '价格范围及迁移假设' if offset == 0 else '公司合计费用代理；相同合计的不同分配不能区分，勿视为细分最优'
    if s == '物流决策':
        rank = ev['priorities'][app.PRODUCTS.index(p)].index(app.COUNTRIES.index(c))
        return ['第一', '第二', '第三'][rank], '六种顺序枚举', '候选内固定顺序跨情景回放'
    if s == '投资决策, 千单位':
        j = app.PRODUCTS.index(c.replace('机器, ', '')); index = (21 if p == '泰国' else 23)+j
        return x[index]*[1, 20][j], '离散条件求解', '泰国立即生效' if p == '泰国' else '本期产量0；比较支出、折旧和融资影响'
    if s == '产能分配, %': return x[25+app.PRODUCTS.index(c)], '条件求解', '复合梁需求驱动；连接件自由生产；分包关闭情景'
    if s == '研发, 千 美元': return x[18+app.PRODUCTS.index(c)], '条件求解', '本期响应；投入映射迁移假设，无第7回合收益'
    if s == '运营改进, 千 美元': return x[20], '条件求解', '回合6曲线与历史效率锚点归一化'
    if s == '财务决策': return x[27]*100, '条件求解', '100千美元搜索档位；采样现金约束，非完整时序'
    if s == '需求, 千单位': return ev['demand'][app.PRODUCTS.index(p)][app.COUNTRIES.index(c)], '随方案推导', '竞争需求，不使用手填预估驱动优化'
    if s == '预计市场增长，%': return 4. if c == '泰国' else 5., '前景情景', '两产品同国采用相同增长；非可控经营变量'
    if s == '总市场需求, 千单位': return [5., 105.][app.PRODUCTS.index(p)], '公布总量情景', '总市场规模，不是本组需求'
    if s == '需求增长预估, %': return 0., '终局停用', '仅界面占位，不构造第7回合需求或收益'
    if s == '生产效率, 千单位/人': return ev['efficiency'][app.PRODUCTS.index(c)], '随方案推导', '曲线条件映射，历史存量仍未识别'
    if s == '财务': return ev['rate']*100, '随方案推导', 't6v0风险模型给定状态条件应用，计息时点属假设'
    raise ValueError(f['key'])


def unit(f):
    if f['section'] == '物流决策' or f['label'] == '分包制造': return '选项'
    if f['section'] == '每单位价格': return '美元/单位'
    if f['section'] == '生产效率, 千单位/人': return '千单位/人'
    if '%' in f['section'] or '%' in f['label']: return '%'
    return '千单位' if '千单位' in f['section'] else '千美元'


def reports(m, out, fields, candidates, checks):
    headings = ['需求', '生产—投资', '生产—计划', '销售—泰国', '销售—印尼', '销售—菲律宾', '销售—大客户订单', '物流', '财务']
    ordered = sorted(fields, key=field_page)
    coverage = []
    lines = ['# t6v1 回合6终局条件方案', '',
        '状态：部分优化候选，非全参数最优。基于冻结t6v0，未重训、未填写平台。回合6为最终回合，印尼本期产量固定0。', '',
        '推荐：在本报告列明的有限情景与分析边界内优先考虑稳健候选；若更看重中性假设收益，可比较中性候选。投标、分包及营销细分机制仍未求解，不能直接称完整最优方案。', '',
        '## 完整字段建议（当前值来自归档小组草稿，非实时个人值）', '']
    previous = None
    for f in ordered:
        page = field_page(f)[0]
        if previous != page:
            lines += ['### '+headings[page], '', '| 参数 | 产品/国家 | 单位 | 当前值 | 中性建议 | 稳健建议 | 是否调整（中/稳） | 状态 | 依据与约束 |', '|---|---|---|---:|---:|---:|---|---|---|']
            previous = page
        a, status, reason = field_value(f, candidates[0], m.r)
        b, status2, reason2 = field_value(f, candidates[1], m.r)
        fmt = lambda v: f'{v:.4f}'.rstrip('0').rstrip('.') if isinstance(v, (int, float)) else str(v)
        changes = '/'.join('是' if isinstance(v, (int, float)) and isinstance(f['value'], (int, float)) and abs(v-f['value']) > 1e-6 or isinstance(v, str) and v != str(f['value']) else '否' for v in [a, b])
        lines.append('| '+' | '.join([f['section'], '/'.join(q for q in [f['product'], f['label']] if q), unit(f), fmt(f['value']), fmt(a), fmt(b), changes, status, reason])+' |')
        coverage.append(dict(key=f['key'], page=headings[page], current=f['value'], neutral=a, robust=b, status=status, reason=reason, unit=unit(f)))
    assert len(coverage) == len({q['key'] for q in coverage}) == 56
    save(out/'field_coverage.json', coverage)
    lines += ['', '## 同期限、同情景比较', '', '金额为千美元；利润仅正式6新增条件税后利润。现金为期末值，最低现金仅检查期初投资后及期末两个时点，不代表全期流动性已核。', '',
        '| 方案 | 情景 | 本期利润 | 期末现金 | 最低采样现金 | 期末短贷 | 投资前置缺口 | 约束通过 |', '|---|---|---:|---:|---:|---:|---:|---|']
    for q in candidates:
        for ev in q['evaluations']:
            lines.append(f"| {q['name']} | {ev['scenario']} | {ev['profit']:.2f} | {ev['cash']:.2f} | {ev['minimum_sampled_cash']:.2f} | {ev['short_debt']:.2f} | {ev['preoperation_bridge_need']:.2f} | {'是' if ev['feasible'] else '否'} |")
    lines += ['', '## 假设、来源与适用边界', '',
        '- 两候选采用同一模型、正式5结转及正式6期限；中性最大化中性利润，稳健最大化中性、菲律宾四种单项扰动及联合不利情景的最低利润。物流顺序在候选内固定，各情景不重新调参。',
        '- 泰国/印尼市场总量按正式5真实需求总量乘1.04/1.05；菲律宾5/105千单位。旧市场九组分别沿用各自正式5售价；菲律宾十队同以1600/23为基准价格，各队非价格投入代理沿用正式5。',
        '- 菲律宾沿用t6v0印尼国别系数，以指导价归一化，不继承本组印尼市场份额。价格弹性、营销响应分别±20%，不是置信区间。',
        '- t6v0公司合计费用代理保留。一般/设计师营销合计进入需求，细分金额虽列全且参与搜索，其配置效果不可识别；同合计重新分配不会改变本模型需求。展示分配采用旧草稿四项投入比例，菲律宾各产品权重取该产品两旧市场平均，再归一化并按整数余数分配；此为确定性展示约定，不是细分最优。研发按产品曲线与历史投入归一化迁移，因果作用未识别。',
        '- 研发有效投入0.75×本期+0.50×上期，运营本期+0.35×上期，沿用正式5试验解释并在本期曲线上归一化；更早历史存量未知。只计本期作用。',
        '- 材料使用t6v0选型参数迁移至720/9.75基价；工资43.5，班次倍率1.65/2.56，行政12000+调研50。库存加权平均计价，数量0/6.02、账面0/72来自正式5结转。',
        '- 泰国机器本期立即生效。印尼投资本期付现、产量始终为0；本期折旧分别按新增投资的15%和0%比较。采购额不直接当费用，未添加残值或第7回合收益。',
        '- 财务采用正式5期末实际作为条件期初，不等于15项独立期初缺口已关闭。基准税亏假设0，另列919情景；厂房支出800及7%折旧、应收/应付30天、平均贷款和现金计息均为继承情景，另列厂房支出0及回款60天压力。',
        '- 期末自动短贷以最低现金2000和基准+3.5个百分点计息作情景复现；前置投资现金缺口作为约束，未核全期支付顺序。风险利率使用给定期初融资状态的条件映射，非已验证前向预测。',
        '- 搜索范围：梁价500—4000，连接件10—50美元；一般营销合计≤3000、设计师合计≤4000千美元；研发各0—2600、运营0—1200；两地梁机器0—20千单位、连接件0—400且20一档；产能分配0—100%；贷款变动−7600至10000且100一档。以上是分析边界，不冒充平台上限。',
        '- 当前菲律宾价格0被替换为指导价后作为可运行参考基准，不能把该基准称为原草稿完整预算回放。',
        '', '### 每套候选触及的搜索边界', '']
    for q in candidates:
        lines.append('- '+q['name']+'：'+ '、'.join(q['boundary_variables'])+'。边界解仅表示本次分析范围结果。')
    lines += ['', '## 未求解及补齐方式', '']+[f'- {s}。' for s in m.r['unresolved']]
    lines += ['', '投标暂保留0报价/0营销、分包暂关闭，属于未求解占位，不是最优退出判断。应补中标、履约及收款规则和分包报价/产量接口后重求解；市场前景的订单规模不直接加入销量。', '',
        '## 验证与产物', '', f"{len(checks)}项机制检查通过；两候选56项字段无遗漏、重复；每产品枚举6种顺序，共36对。新增曲线各200点，仅验证图形拟合，不代表经营预测准确。", '',
        '[计算结果](result.json) · [模型与假设](models_full.json) · [56项字段](field_coverage.json) · [检查](checks.json) · [参数及来源](input_review.md) · [印尼投资影响](indonesia_investment_checks.json) · [搜索记录](search_trace.json) · [来源哈希](source_hashes.json)']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def finish(m, out, fields, candidates, checks):
    for q in candidates:
        for ev in q['evaluations']:
            assert abs(ev['balance_error']) < 1e-6 and ev['quantity_error'] < 1e-8
            assert ev['production_indonesia'] == [0., 0.]
    audit = []
    for candidate in candidates:
        x = np.array(candidate['x'])
        for location, indexes in [('泰国', [21, 22]), ('印尼', [23, 24])]:
            for index in indexes:
                for units in range(21):
                    trial = x.copy(); trial[index] = units
                    for dep in [0., 1.] if location == '印尼' else [1.]:
                        ev = m.evaluate(trial, dict(indo_depreciation=dep), True)
                        audit.append(dict(plan=candidate['name'], location=location, variable=app.NAMES[index], step=units,
                            depreciation_fraction=dep*.15, profit=ev['profit'], cash=ev['cash'],
                            short_debt=ev['short_debt'], depreciation=ev['machine_depreciation'], production_indonesia=ev['production_indonesia']))
    save(out/'indonesia_investment_checks.json', audit)
    sensitivity = []
    for candidate in candidates:
        x = np.array(candidate['x'])
        for i in range(28):
            options = {float(m.bounds[i, 0]), float(m.bounds[i, 1])}
            for direction in [-1, 1]:
                step = 1. if i in app.INTEGER else max(abs(x[i])*.1, .1 if i < 6 else 1.)
                options.add(float(np.clip(x[i]+direction*step, *m.bounds[i])))
            for value in sorted(options):
                trial = x.copy(); trial[i] = value
                if i in app.INTEGER: trial[i] = round(trial[i])
                ev = m.evaluate(trial, details=True)
                sensitivity.append(dict(plan=candidate['name'], variable=app.NAMES[i], trial=float(trial[i]), profit=ev['profit'], feasible=ev['feasible']))
    save(out/'sensitivity.json', sensitivity)
    save(out/'checks.json', dict(status='PASS_IMPLEMENTATION_CONDITIONAL_ONLY', mechanisms=checks, fields=56,
        source_hashes_unchanged=True, candidate_scenarios=len(candidates)*len(m.r['scenarios']),
        independent_forward_validation=False, full_global_optimum=False, platform_verified=False))
    save(out/'result.json', dict(version='t6v1', base_version='t6v0', start_round=6, end_round=6,
        status='PARTIAL_CONDITIONAL_OPTIMIZATION_WITH_UNSOLVED_MECHANISMS', candidates=candidates, baseline=m.evaluate(m.baseline, details=True)))
    save(out/'example_request.json', dict(version='t6v1', round=6, decision_vector=candidates[1]['x'], scenario='中性'))
    review = ['# 输入、参数及来源', '', '状态：完整字段已分类，期初状态仍有独立核验缺口。', '',
        '| 类别 | 处理 |', '|---|---|', '| 经营字段39项 | 28数值搜索变量＋6物流字段枚举＋5项投标/分包未求解 |',
        '| 预估与派生17项 | 6需求＋4增长＋2总量＋2终局停用项＋2效率＋1利率 |',
        '| 菲律宾原草稿价格0 | 运行基准替换为指导价1600/23，不称原预算回放 |',
        '| 正式5结转 | 现金10703、长贷7600、库存0/6.02及账面0/72；其余见模型state |',
        '| 泰国产能 | '+str(m.r['capacity'])+'千单位；当前0投资条件值 |',
        '| 印尼产能 | 本期固定0，下一回合显示值不引入 |', '',
        '全部公布参数见[published_parameters.json](published_parameters.json)，每项保留原件单元格及哈希；本模型使用的常数、情景及未知状态见[models_full.json](models_full.json)。', '',
        '公开参数以原归档为依据；本次未改写其值。应用公式与部分财务机制的假设不等于公布参数。', '',
        '| 曲线 | 点数 | 留点MAE | 最大留点误差 |', '|---|---:|---:|---:|']
    review += [f"| {k} | 200 | {v['held_mae']:.8g} | {v['held_max_error']:.8g} |" for k, v in m.r['curves'].items()]
    (out/'input_review.md').write_text('\n'.join(review)+'\n', encoding='utf-8')
    reports(m, out, fields, candidates, checks)
    for rel, expected in app.read(out/'source_hashes.json').items():
        assert sha(ROOT/rel) == expected, rel
    documents = {}
    link = out.relative_to(ROOT).as_posix()+'/report.md'
    for rel in ['README.md', 'code/model_v2/README.md', 'Cesim_任务要求与当前情况说明.md']:
        path = ROOT/rel
        backup = out/'documents_before'/rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        before = sha(path)
        text = path.read_text(encoding='utf-8-sig')
        prefix = '../../' if rel.startswith('code/model_v2/') else ''
        if rel == 'README.md':
            target = '| 最新需求竞争情景 |'
            entry = f'| 回合6终局条件应用 | **t6v1**：[56项建议与情景比较]({link})、[运行说明](code/model_v2/t6v1_README.md) | 基于冻结t6v0；菲律宾迁移印尼归一化；印尼本期产量0，投资财务影响双情景。中性/稳健为部分优化，投标、分包及细分营销未识别，未填写平台。 |\n'
            assert target in text
            text = text.replace(target, entry+target, 1)
            text = text.replace('正式6新增菲律宾需求及印尼投资机制尚未接入验证', '正式6新增菲律宾及印尼投资已在t6v1条件应用接入并做离线机制核验；仍缺平台及独立前向验证')
            text = text.replace('正式6新增菲律宾及印尼投资字段需适配', '正式6新增字段已由t6v1条件适配，投标/分包、细分投入及财务机制仍需补证')
        elif rel == 'code/model_v2/README.md':
            text = text.replace('## 当前工作入口', '## 当前工作入口\n\n- [t6v1终局应用](t6v1_README.md)：基于冻结t6v0扩充菲律宾；印尼本期产量0；[中性与稳健56项条件建议]('+prefix+link+')。缺口保留，非完整最优。', 1)
            text = text.replace('当前正式6的新增菲律宾需求、印尼投资及终局规则仍需适配', '当前正式6的新增菲律宾需求、印尼投资及终局规则已由t6v1作条件适配，独立前向验证及完整机制仍缺')
        else:
            heading = '### 决策全参数优化与方案输出（2026-10-15用户确认）'
            assert heading in text
            text = text.replace(heading, heading+'\n\n正式6终局口径（2026-10-16用户确认）：菲律宾迁移t6v0印尼国别模型并归一化；印尼实际生产回合7才开始，因此正式6产量固定0，机器投资仅计本期财务影响。泰国新增机器本期生效。不计第7回合收益，不自行增加终局残值。[本次条件实现]('+link+')。', 1)
        path.write_text(text, encoding='utf-8')
        documents[rel] = dict(before_sha256=before, backup_sha256=sha(backup), after_sha256=sha(path))
        assert before == sha(backup)
    save(out/'document_changes.json', documents)
    local_links = []
    for path in [out/'report.md', out/'input_review.md', ROOT/'code/model_v2/t6v1_README.md']:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' not in target and not target.startswith('#'):
                assert (path.parent/target.split('#')[0]).exists(), target
                local_links.append(target)
    save(out/'link_checks.json', dict(status='PASS', checked=len(local_links)))
    for rel in ['code/model_v2/t6v1.py', 'work/build_t6v1.py']:
        shutil.copy2(ROOT/rel, out/Path(rel).name)
    with (out/'work_log.md').open('a', encoding='utf-8') as stream:
        stream.write('\n\n'+datetime.now(TZ).isoformat()+' 完成：四步离线实施、两候选、56字段、机制检查及来源哈希复核通过。保留原模型和既有未提交修改。未访问平台，投标/分包和细分投入未识别，不宣称全参数最优。\n')
    save(out/'manifest.json', dict(version='t6v1', completed_at=datetime.now(TZ).isoformat(), base_version='t6v0',
        output_hashes={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()},
        source_hashes=app.read(out/'source_hashes.json'), documents=documents))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=300)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    assert (out/'work_log.md').exists() and not (out/'manifest.json').exists()
    if args.resume:
        reg = app.read(out/'models_full.json'); fields = app.read(out/'current_fields.json')
    else:
        reg, fields = build(out)
    m = app.ApplicationModel(out)
    checks = self_check(m)
    save(out/'initial_checks.json', checks)
    print('INPUT_AND_MECHANISM_CHECKS_PASS', len(fields), flush=True)
    if args.resume and (out/'candidates_partial.json').exists():
        candidates = app.read(out/'candidates_partial.json')
        assert len(candidates) == 2
    else:
        candidates = solve(m, out, args.iterations)
    finish(m, out, fields, candidates, checks)
    print('COMPLETE', out, flush=True)


if __name__ == '__main__':
    main()
