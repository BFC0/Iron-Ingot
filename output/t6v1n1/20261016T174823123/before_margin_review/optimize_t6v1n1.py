"""Build the Thailand-transfer model and solve profit versus Philippine share."""
import argparse
import copy
import itertools
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import build_t6v1 as w
import t6v1n1 as app
import t6v1n as prior
import numpy as np
from scipy.optimize import differential_evolution

ROOT, save, sha = w.ROOT, w.save, w.sha
SOURCE = ROOT/'output/t6v1n_optimization/20261016T173718998'


def mechanism_checks(m):
    old = prior.ApplicationModel(SOURCE)
    vectors = [m.baseline]+[np.array(c['x']) for c in app.read(SOURCE/'result.json')['candidates']]
    count = 0
    for x in vectors:
        for cfg in m.r['scenarios']:
            ev = m.evaluate(x, cfg, True)
            assert abs(ev['balance_error']) < 1e-7 and ev['quantity_error'] < 1e-8
            assert np.allclose(np.sum(ev['shares'], axis=2), 1.)
            assert np.allclose(np.array(ev['market_totals'])*ev['own_shares'], ev['demand'])
            assert ev['production_indonesia'] == [0., 0.]
            assert np.allclose(np.array(ev['demand'])[:, :2], np.array(old.evaluate(x, cfg, True)['demand'])[:, :2])
            count += 1
    x = m.baseline.copy()
    _, shares = m.demand(x, {})
    # Independent direct softmax from Thai features at the baseline normalization point.
    for j, p in enumerate(app.PRODUCTS):
        rows = m.r['competition'][p]['泰国']
        own = m.r['own_indices'][p]['泰国']
        b = np.array(m.r['demand'][p]['COUNTRY/泰国']['beta'])
        g = np.array([q['general'] for q in rows]); g[own] = x[6:12].sum()
        d = np.array([q['designer'] for q in rows]); d[own] = x[12:18].sum()
        rd = np.array([q['rd']+.5*q['previous_rd'] for q in rows])
        rdlog = np.log(prior.base.curve(rd, m.r['training_curves']['rd/'+p]))
        mapping = m.r['investment_mapping']; prev = m.r['previous_rd'][j]
        rdlog[own] += np.log(prior.base.curve(mapping['rd_current']*x[18+j]+mapping['rd_previous']*prev, m.r['curves']['rd/'+p])/prior.base.curve((mapping['rd_current']+mapping['rd_previous'])*prev, m.r['curves']['rd/'+p]))
        utility = b[2]*np.log1p(g/1000)+b[3]*np.log1p(d/1000)+b[4]*rdlog
        utility[own] -= b[0]*np.log(x[j*3+2]/m.r['guide_prices'][j])
        expected = np.exp(utility-utility.max()); expected /= expected.sum()
        assert np.allclose(expected, shares[j, 2, :, 0], atol=1e-12)
        trial = x.copy(); trial[j*3+2] *= 1.05
        assert m.demand(trial, {})[1][j, 2, own, 0] < shares[j, 2, own, 0]
    original = copy.deepcopy(m.r)
    for p in app.PRODUCTS:
        m.r['demand'][p]['COUNTRY/印尼']['beta'] = [v*2 for v in m.r['demand'][p]['COUNTRY/印尼']['beta']]
    assert np.array_equal(m.demand(x, {})[1][:, 2], shares[:, 2])
    m.r = copy.deepcopy(original)
    for p in app.PRODUCTS:
        own = m.r['own_indices'][p]['泰国']
        for row in m.r['competition'][p]['泰国']:
            row.update({k: m.r['competition'][p]['泰国'][own][k] for k in ['general', 'designer', 'rd', 'previous_rd']})
    assert np.allclose(m.demand(x, dict(replay_training=True))[1][:, 2], .1)
    m.r = original
    assert np.all(m.demand(x, dict(disable_ph=True))[0][:, 2] == 0)
    assert np.allclose(m.demand(x, dict(market_scale=.9))[0], m.demand(x, {})[0]*.9)
    assert np.allclose(m.evaluate(np.column_stack(vectors))[0], [m.evaluate(v)[0][0] for v in vectors])
    for cfg in [dict(ph_rival_price=0), dict(ph_rival_price=True), dict(new_market_totals=[-1, 105]), dict(rival_scale=0)]:
        try:
            m.demand(x, cfg)
        except ValueError:
            pass
        else:
            raise AssertionError(cfg)
    for bad in [x[:-1], np.full(28, np.nan), [True]+x[1:].tolist()]:
        try:
            m.validate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid decision accepted')
    return dict(replay_cases=count, old_market_demand_unchanged=True, independent_thai_softmax=True,
                indonesia_coefficients_do_not_drive_philippines=True, equal_inputs_equal_share=True,
                conservation=True, vectorized_replay=True, invalid_inputs_rejected=True)


def share_floor(m, x):
    x = np.asarray(x); x = x[:, None] if x.ndim == 1 else x
    demand, _ = m.demand(x, {})
    capacity = np.array(m.r['capacity'])[:, None]+x[21:23]*np.array([1, 20])[:, None]
    available = capacity*x[25:27]/100+np.array(m.r['inventory'])[:, None]
    # PH is first for share-target plans, so this is its actual delivered quantity.
    return np.minimum(demand[:, 2], available)/m.market_forecast({})[:, 2, None]


def solve(m, out, iterations):
    candidates, trace = [], []
    ph_first = [app.ORDERS.index((2, 1, 0))]*2
    goals = [('中性', None), ('稳健', None), ('份额10%', .1), ('份额20%', .2), ('份额30%', .3)]
    for name, target in goals:
        configs = m.r['scenarios'][:6]+[m.r['scenarios'][9], m.r['scenarios'][11], m.r['scenarios'][12]] if name == '稳健' else m.r['scenarios'][:1]
        priorities = ph_first if target else None
        ph_orders = list(itertools.product([app.ORDERS.index((2, 0, 1)), app.ORDERS.index((2, 1, 0))], repeat=2))
        def score(x):
            ev = [m.evaluate(x, cfg, priorities=priorities) for cfg in configs]
            if target:
                alternatives = [m.evaluate(x, configs[0], priorities=o) for o in ph_orders]
                value = -np.max([v[0] for v in alternatives], axis=0)+np.max([v[2] for v in alternatives], axis=0)
            else:
                value = -np.min([v[0] for v in ev], axis=0)+np.max([v[2] for v in ev], axis=0)
            if target:
                value += 1e6*np.maximum(target-share_floor(m, x), 0).sum(axis=0)
            return value
        best = None
        for seed in [11, 29]:
            start = np.array(candidates[0]['x']) if candidates else m.baseline
            fit = differential_evolution(score, m.bounds, seed=seed, popsize=7, maxiter=iterations,
                tol=.0005, atol=.5, polish=False, vectorized=True, updating='deferred',
                integrality=[i in prior.base.INTEGER for i in range(28)], x0=start)
            trace.append(dict(plan=name, seed=seed, success=bool(fit.success), iterations=fit.nit, objective=float(fit.fun)))
            save(out/'search_trace.json', trace)
            print('SEARCH', name, seed, fit.nit, -fit.fun, flush=True)
            if best is None or fit.fun < best.fun:
                best = fit
        x = w.rounded(best.x)
        for _ in range(8):
            changed = False
            for i in range(28):
                step = .1 if i < 6 or i in [25, 26] else 1.
                options = [x[i], x[i]-step, x[i]+step]
                if 21 <= i < 25: options = list(range(21))
                if i == 27: options = list(range(int(m.bounds[i, 0]), int(m.bounds[i, 1])+1))
                if 6 <= i < 21: options += [0., x[i]*.9, x[i]*1.1]
                options = sorted({float(round(v, 1 if step == .1 else 0)) for v in options if m.bounds[i, 0] <= v <= m.bounds[i, 1]})
                trials = np.repeat(x[:, None], len(options), axis=1); trials[i] = options
                scores = score(trials); at = int(np.argmin(scores))
                if scores[at] < score(x)[0]-1e-7:
                    x[i] = options[at]; changed = True
            if not changed: break
        # shortcut: country/product marketing splits are unidentifiable; retain the previous display convention until causal data exist.
        before = score(x).copy()
        for start in [6, 12]:
            total = round(float(x[start:start+6].sum()))
            weights = m.baseline[start:start+6].reshape(2, 3).copy()
            weights[:, 2] = weights[:, :2].mean(axis=1)
            weights = weights.ravel()/weights.sum()
            split = np.floor(total*weights)
            split[np.argsort(total*weights-split)[::-1][:int(total-split.sum())]] += 1
            x[start:start+6] = split
        assert np.allclose(score(x), before)
        m.validate(x)
        if target:
            priorities = max(ph_orders, key=lambda o:m.evaluate(x, priorities=o)[0][0])
        ev = m.evaluate(x, details=True, priorities=priorities)
        fixed = priorities if priorities is not None else [app.ORDERS.index(tuple(o)) for o in ev['priorities']]
        evaluations = [dict(scenario=c['name'], **m.evaluate(x, c, True, priorities=fixed)) for c in m.r['scenarios']]
        assert all(e['feasible'] for e in evaluations)
        if target:
            assert min(ev['ph_sales_shares']) >= target-1e-10, (name, ev['ph_sales_shares'])
            assert np.allclose(ev['ph_sales_shares'], share_floor(m, x)[:, 0])
        candidates.append(dict(name=name, target_share=target, target_scope='中性情景两产品分别的实际交付份额；压力下不保证',
            x=x.tolist(), evaluations=evaluations, fixed_priorities=fixed,
            objective=float(score(x)[0]), boundary_variables=[prior.base.NAMES[i] for i, v in enumerate(x) if v in m.bounds[i]]))
        save(out/'candidates_partial.json', candidates)
    return candidates


def report(m, out, fields, candidates, checks):
    heads = ['需求', '生产—投资', '生产—计划', '销售—泰国', '销售—印尼', '销售—菲律宾', '销售—大客户订单', '物流', '财务']
    lines = ['# t6v1n1 菲律宾迁移泰国模型及份额优化', '',
        '状态：部分优化候选，非全参数最优。用户指定泰国相似性假设；未用菲律宾真实标签重训，未操作平台。期限为正式6当期；不计第7回合和终局残值。', '',
        '## 全部56项字段', '', '当前值来自正式6归档小组草稿，非实时输入。营销分配仅展示约定，合计参与求解，细分效果未识别。']
    coverage = []; previous = None
    for f in sorted(fields, key=w.field_page):
        page = w.field_page(f)[0]
        if previous != page:
            lines += ['', '### '+heads[page], '', '| 参数 | 产品/国家 | 单位 | 当前值 | '+' | '.join(c['name'] for c in candidates)+' | 优化状态及依据 |',
                      '|---|---|---|---:|'+'---:|'*len(candidates)+'---|']
            previous = page
        values = [w.field_value(f, c, m.r) for c in candidates]
        fmt = lambda v: f'{v:.4f}'.rstrip('0').rstrip('.') if isinstance(v, (int, float)) else str(v)
        cells = [fmt(v[0])+('（调整）' if v[0] != f['value'] else '（不变）') for v in values]
        lines.append('| '+' | '.join([f['section'], '/'.join(v for v in [f['product'], f['label']] if v), w.unit(f), fmt(f['value'])]+cells+[values[0][1]+'；'+values[0][2]])+' |')
        coverage.append(dict(key=f['key'], current=f['value'], unit=w.unit(f), status=values[0][1], reason=values[0][2],
                             plans={c['name']:v[0] for c,v in zip(candidates, values)}))
    save(out/'field_coverage.json', coverage)
    assert len(coverage) == len({f['key'] for f in fields}) == 56
    baseline = m.evaluate(m.baseline, details=True)
    lines += ['', '## 同期限、同基准比较', '',
        '金额千美元；条件税后利润。参考基准用指导价替换菲律宾原零售价，其余为归档值，不等于原草稿预算。营销费为全公司合计，不能全部归因菲律宾。份额＝菲律宾实际销量÷当地总市场需求。', '',
        '| 候选 | 梁/连接件交付份额 | 中性利润 | 相对参考增量 | 全列情景最低利润 | 中性现金 | 全列最低采样现金 | 最大短贷 | 库存梁/件（千单位） |',
        '|---|---|---:|---:|---:|---:|---:|---:|---|']
    for c in [dict(name='参考基准', evaluations=[baseline])]+candidates:
        es = c['evaluations']; e = es[0]
        lines.append(f"| {c['name']} | {e['ph_sales_shares'][0]:.2%}/{e['ph_sales_shares'][1]:.2%} | {e['profit']:.2f} | {e['profit']-baseline['profit']:.2f} | {min(v['profit'] for v in es):.2f} | {e['cash']:.2f} | {min(v['minimum_sampled_cash'] for v in es):.2f} | {max(v['short_debt'] for v in es):.2f} | {e['closing_inventory'][0]:.4f}/{e['closing_inventory'][1]:.4f} |")
    lines += ['', '参考基准仅上表中性值，不作为跨情景风险比较。全部候选采用相同13种情景；最低现金只核投资后与期末两个时点。', '',
        '## 抢占的代价与推荐', '',
        '中性最大化本期利润；稳健最大化九种核心情景的最低利润；份额候选最大化中性利润并约束两产品各自交付份额≥10%/20%/30%。后三者菲律宾优先供货，其他市场按净售价排序。所有方案物流顺序在压力测试中固定。份额约束不保证压力下达标。', '',
        '| 候选 | 相对中性利润损失 | 菲律宾梁价/连接件价（美元） | 公司营销总额 | 对手降价20%后梁/件交付份额 | 对手降价20%后公司利润 |', '|---|---:|---|---:|---|---:|']
    for c in candidates:
        e = c['evaluations'][0]; stressed = c['evaluations'][9]; x = c['x']
        lines.append(f"| {c['name']} | {candidates[0]['evaluations'][0]['profit']-e['profit']:.2f} | {x[2]:.1f}/{x[5]:.1f} | {sum(x[6:18]):.0f} | {stressed['ph_sales_shares'][0]:.2%}/{stressed['ph_sales_shares'][1]:.2%} | {stressed['profit']:.2f} |")
    eligible = [c for c in candidates[2:] if c['evaluations'][0]['profit'] >= 0]
    attack = max(eligible, key=lambda c:c['target_share']) if eligible else None
    lines += ['', '利润与风险优先时推荐稳健候选；若明确优先抢占市场，'+('可考虑'+attack['name']+'候选，作为已比较且中性公司利润非负的最高目标；这不证明菲律宾单独盈利，也不保证真实份额。' if attack else '当前已搜索份额目标均未满足中性公司利润非负，不推荐直接采用。'), '',
        '## 参数与假设', '',
        '- 菲律宾使用t6v0的COUNTRY/泰国完整beta：价格取beta[0]，一般/设计师营销取beta[2:4]，研发取beta[4]；对手非价格代理沿用泰国正式5行并按team_id对齐。新市场各队不继承旧份额，基准售价统一指导价1600/23，本公司价格随候选变化。',
        '- 菲律宾总量5/105千单位保持前景；泰国/印尼真实总量×1.04/1.05；运费保持菲律宾170/2.2美元/单位，不迁移泰国本地运费。总量外生，不人为因降价扩大市场。',
        '- 公司合计营销代理保留；营销重分配不改变预测。展示按旧草稿比例，菲律宾权重取同产品两旧市场平均；不据此声称菲律宾投放收益或细分最优。',
        '- 研发本期0.75、上期0.50，运营上期0.35；上期研发2600/231、运营754；本期曲线归一化。历史存量及因果机制未识别。',
        '- 泰国机器立即生效；印尼正式6产量0；本期投资仍支出并比较折旧情景。不加未来收益和残值。材料、工资、班次、税率和成本继续沿用归档，见注册表。',
        '- 建造支出800、厂房折旧7%、应收应付30天、平均计息、税亏0均为继承条件假设；另测税亏919、建造支出0、回款60天。现金最低2000，自动短贷是情景机制，未核完整支付时序。',
        '- 分析边界：梁价500—4000，件价10—50；一般营销合计≤3000、设计师≤4000；研发各≤2600、运营≤1200；两地产能机器梁0—20、连接件0—400；贷款−7600至10000，均非平台已核上限。', '',
        '## 全情景结果', '', '| 候选 | 情景 | 利润 | 现金 | 最低采样现金 | 短贷 | 梁/件交付份额 | 约束 |', '|---|---|---:|---:|---:|---:|---|---|']
    for c in candidates:
        for e in c['evaluations']:
            lines.append(f"| {c['name']} | {e['scenario']} | {e['profit']:.2f} | {e['cash']:.2f} | {e['minimum_sampled_cash']:.2f} | {e['short_debt']:.2f} | {e['ph_sales_shares'][0]:.2%}/{e['ph_sales_shares'][1]:.2%} | {'通过' if e['feasible'] else '未通过'} |")
    lines += ['', '## 未求解及搜索边界', '']+['- '+q for q in m.r['unresolved']]
    lines += ['', '5项投标/分包维持归档占位，未求解；营销12项仅合计可识别。字段列全不等于全参数已求解。对手降价20%、新市场总量−30%等是分析压力假设，非置信区间。', '',
        '| 候选 | 种子 | 轮数 | 求解器收敛 |', '|---|---:|---:|---|']
    lines += [f"| {q['plan']} | {q['seed']} | {q['iterations']} | {q['success']} |" for q in app.read(out/'search_trace.json')]
    lines += ['', '达到轮数上限者仅称已找到候选；收敛也不证明全局最优。物流对中性/稳健枚举36对，对份额候选在菲律宾优先的4对中按利润选择。', '']
    lines += ['- '+c['name']+'触及边界：'+('、'.join(c['boundary_variables']) or '无') for c in candidates]
    lines += ['', '## 验证与复现', '',
        '[模型](models_full.json) · [结果](result.json) · [检查](checks.json) · [56字段](field_coverage.json) · [搜索](search_trace.json) · [价格扫描](price_scan.json) · [旧候选新模型回放](prior_candidates_replay.json) · [来源哈希](source_hashes.json) · [运行说明](../../../code/model_v2/t6v1n1_README.md)', '',
        '独立泰国softmax、旧市场需求不变、对称输入份额、守恒、批量、非法输入及保存回放核验；并未验证菲律宾独立预测精度。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def verify(out):
    manifest = app.read(out/'manifest.json')
    for rel, expected in manifest['source_hashes'].items():
        assert sha(ROOT/rel) == expected, rel
    for rel, expected in manifest['output_hashes'].items():
        assert sha(out/rel) == expected, rel
    for rel, record in manifest['documents'].items():
        assert sha(ROOT/rel) == record['after_sha256']
        assert sha(out/'documents_before'/rel) == record['before_sha256'] == record['backup_sha256']
    m = app.ApplicationModel(out)
    mechanism_checks(m)
    results = app.read(out/'result.json')
    cases = 0
    for c in results['candidates']:
        x = m.validate(c['x'])
        for cfg, saved in zip(m.r['scenarios'], c['evaluations']):
            actual = m.evaluate(x, cfg, True, priorities=c['fixed_priorities'])
            for key in ['profit', 'cash', 'short_debt', 'rate', 'revenue', 'minimum_sampled_cash']:
                assert abs(actual[key]-saved[key]) < 1e-8, (c['name'], key)
            assert actual['feasible'] and abs(actual['balance_error']) < 1e-7 and actual['quantity_error'] < 1e-8
            assert np.allclose(actual['ph_sales_shares'], saved['ph_sales_shares'])
            cases += 1
        if c['target_share']:
            assert min(c['evaluations'][0]['ph_sales_shares']) >= c['target_share']-1e-10
        orders = list(itertools.product(range(6), repeat=2))
        if c['target_share']:
            orders = [o for o in orders if all(app.ORDERS[k][0] == 2 for k in o)]
        best = max(m.evaluate(x, details=True, priorities=o)['profit'] for o in orders)
        assert abs(best-c['evaluations'][0]['profit']) < 1e-7
    assert len(app.read(out/'field_coverage.json')) == 56
    request = app.read(out/'example_request.json')
    assert request['version'] == 't6v1n1'
    assert np.isclose(m.evaluate(request['decision_vector'], details=True)['profit'], results['candidates'][1]['evaluations'][0]['profit'])
    print('PASS_SAVED_REPLAY', cases, flush=True)


def main(out, iterations):
    out = out.resolve()
    assert (out/'work_log.md').exists() and not (out/'models_full.json').exists()
    old_manifest = app.read(SOURCE/'manifest.json')
    sources = dict(old_manifest['source_hashes'])
    for rel, expected in sources.items():
        assert sha(ROOT/rel) == expected, rel
    for path in list(SOURCE.rglob('*'))+[Path(__file__), ROOT/'code/model_v2/t6v1n1.py', ROOT/'code/model_v2/t6v1n1_README.md']:
        if path.is_file(): sources[path.relative_to(ROOT).as_posix()] = sha(path)
    r = app.read(SOURCE/'models_full.json')
    r.update(version='t6v1n1', base_version='t6v1n', philippines_transfer=dict(country='泰国',
        scope='用户指定国别迁移假设，完整泰国beta及对手非价格代理；指导价归一化；保留菲律宾总量与运费',
        training_performed=False, independent_validation=False))
    r['market_forecast']['share_scope'] = '菲律宾迁移泰国，旧国不变；公司营销合计代理，细分未识别'
    r['scenarios'] += [dict(name='菲律宾对手降价20%', ph_rival_price=.8),
        dict(name='菲律宾对手涨价20%', ph_rival_price=1.2),
        dict(name='菲律宾总量减少30%', new_market_totals=[3.5, 73.5]),
        dict(name='联合不利加菲律宾降价缩量', market_scale=.9, rival_scale=1.2, efficiency_scale=.9,
             material_scale=1.05, ar_days=60., ph_rival_price=.8, new_market_totals=[3.5, 73.5])]
    save(out/'models_full.json', r)
    fields = app.read(SOURCE/'current_fields.json')
    save(out/'current_fields.json', fields)
    shutil.copy2(SOURCE/'published_parameters.json', out/'published_parameters.json')
    m = app.ApplicationModel(out)
    checks = mechanism_checks(m)
    save(out/'initial_checks.json', checks)
    print('MECHANISM_PASS', checks, flush=True)
    candidates = solve(m, out, iterations)
    save(out/'result.json', dict(version='t6v1n1', base_version='t6v1n', start_round=6, end_round=6,
        status='PARTIAL_CONDITIONAL_OPTIMIZATION_WITH_UNSOLVED_MECHANISMS',
        baseline=m.evaluate(m.baseline, details=True), candidates=candidates))
    save(out/'example_request.json', dict(version='t6v1n1', round=6, decision_vector=candidates[1]['x'], scenario='中性'))
    previous = []
    for c in app.read(SOURCE/'result.json')['candidates']:
        fixed = [app.ORDERS.index(tuple(o)) for o in c['evaluations'][0]['priorities']]
        previous.append(dict(name=c['name'], old_model_profit=c['evaluations'][0]['profit'],
            new_model_evaluation=m.evaluate(c['x'], details=True, priorities=fixed)))
    save(out/'prior_candidates_replay.json', previous)
    scan = []
    for c in candidates[:2]:
        for j, guide in enumerate(r['guide_prices']):
            for factor in [.7, .85, 1., 1.15, 1.3]:
                x = np.array(c['x']); x[j*3+2] = guide*factor
                ev = m.evaluate(x, details=True, priorities=c['fixed_priorities'])
                scan.append(dict(plan=c['name'], product=app.PRODUCTS[j], price=float(x[j*3+2]),
                    profit=ev['profit'], ph_sales_shares=ev['ph_sales_shares'], cash=ev['cash'], feasible=ev['feasible'],
                    scope='单因素诊断，其余变量固定；非独立优化方案'))
    save(out/'price_scan.json', scan)
    save(out/'checks.json', dict(status='PASS_CONDITIONAL_IMPLEMENTATION', mechanisms=checks,
        fields=56, candidates=5, candidate_scenarios=65, training_performed=False,
        independent_forward_validation=False, full_global_optimum=False, platform_verified=False))
    report(m, out, fields, candidates, checks)
    documents = {}
    link = out.relative_to(ROOT).as_posix()+'/report.md'
    for rel in ['README.md', 'code/model_v2/README.md', 'Cesim_任务要求与当前情况说明.md']:
        path = ROOT/rel; backup = out/'documents_before'/rel
        backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, backup)
        before = path.read_text(encoding='utf-8-sig')
        if rel == 'README.md':
            anchor = '| 自上而下需求应用 |'
            new = before.replace(anchor, '| 菲律宾泰国迁移及份额优化 | **t6v1n1**：[56字段及五候选]('+link+')、[运行说明](code/model_v2/t6v1n1_README.md) | 菲律宾改迁移泰国，保留前景总量/指导价/菲律宾运费；中性、稳健及10%/20%/30%交付份额，13情景；部分优化、未重训、未写平台。 |\n'+anchor, 1)
        elif rel.startswith('code/'):
            anchor = '- [t6v1n自上而下需求]'
            new = before.replace(anchor, '- [t6v1n1菲律宾泰国迁移](t6v1n1_README.md)：[56项及五候选](../../'+link+')，份额与利润比较；未重训、未写平台，细分机制缺口保留。\n\n'+anchor, 1)
        else:
            new = re.sub(r'^正式6终局口径（2026-10-16用户确认）.*$', lambda _: '正式6终局口径（2026-10-16用户确认）：最新t6v1n1按用户要求将菲律宾迁移来源改为t6v0泰国国别模型，并按菲律宾指导价归一化；泰国相似性属假设，旧t6v1/t6v1n迁移印尼的历史结果保留。菲律宾前景总量和运费不变。印尼正式6产量固定0，机器投资仅计本期财务影响；泰国机器当期生效。不计第7回合收益或新增终局残值。[最新实现与份额优化]('+link+')。', before, count=1, flags=re.M)
        assert new != before and 't6v1n1' not in before
        path.write_text(new, encoding='utf-8')
        documents[rel] = dict(before_sha256=sha(backup), backup_sha256=sha(backup), after_sha256=sha(path))
    save(out/'source_hashes.json', sources)
    save(out/'document_changes.json', documents)
    gaps = []
    for path in [out/'report.md', ROOT/'code/model_v2/t6v1n1_README.md']+[ROOT/p for p in documents]:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8-sig')):
            if '://' in target or target.startswith('#'): continue
            if not (path.parent/target.strip('<>').split('#')[0]).exists():
                rel = path.relative_to(ROOT).as_posix()
                assert rel in documents and ']('+target+')' in (out/'documents_before'/rel).read_text(encoding='utf-8-sig'), (str(path), target)
                gaps.append(dict(document=rel, preexisting_missing=target))
    save(out/'link_checks.json', dict(new_links_valid=True, preexisting_gaps=gaps))
    for path in [Path(__file__)]+[ROOT/'code/model_v2'/f for f in ['t6v1.py', 't6v1n.py', 't6v1n1.py']]:
        shutil.copy2(path, out/path.name)
    for rel, expected in sources.items(): assert sha(ROOT/rel) == expected, rel
    with (out/'work_log.md').open('a', encoding='utf-8') as f:
        f.write('\n\n状态：已完成。北京时间：'+w.datetime.now(w.TZ).isoformat()+'。泰国迁移、五候选及65情景保存；56字段覆盖；守恒/对称/批量/旧国不变等检查通过。来源哈希、说明备份和新链接已核。旧文件保留。未重训或操作平台；菲律宾独立精度及投标/分包/营销细分未解决。\n')
    save(out/'manifest.json', dict(version='t6v1n1', completed_at=w.datetime.now(w.TZ).isoformat(),
        source_hashes=sources, documents=documents,
        output_hashes={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    verify(out)
    print('COMPLETE', out, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--iterations', type=int, default=1200)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify: verify(args.out)
    else: main(args.out, args.iterations)
