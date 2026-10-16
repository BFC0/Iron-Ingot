"""Repair t6v1n1 proxy semantics, then reuse its five-plan terminal optimizer."""
import argparse
import itertools
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import optimize_t6v1n1 as old
import t6v1n2 as app
import core
import numpy as np

ROOT, save, sha = old.ROOT, old.save, old.sha
SOURCE = ROOT/'output/t6v1n1/20261016T174823123'


def checks(m):
    x = m.baseline.copy()
    _, replay = m.demand(x, dict(replay_training=True))
    for j, p in enumerate(app.PRODUCTS):
        for k, country in enumerate(app.COUNTRIES[:2]):
            rows = [dict(q, market_id=5, phase='formal', round=5, country=country, initial_price=1.)
                    for q in m.r['competition'][p][country]]
            features = core.features(rows, m.r['training_curves']['rd/'+p]['parameters'], .5, False)
            expected = core.predict(rows, features, m.r['demand'][p]['COUNTRY/'+country]['beta'])
            assert np.allclose(replay[j,k,:,0], expected, atol=1e-12)
        for k in range(3):
            country = app.COUNTRIES[k if k < 2 else 0]
            own = m.r['own_indices'][p][country]
            rows = [dict(q, market_id=5, phase='formal', round=6, country=country, initial_price=1.)
                    for q in m.r['competition'][p][country]]
            if k == 2:
                for row in rows: row['price'] = m.r['guide_prices'][j]
            rows[own].update(price=x[3*j+k],general=x[6:12].sum(),designer=x[12:18].sum(),
                             rd=x[18:20].sum(),previous_rd=rows[own]['rd'])
            f = core.features(rows,m.r['training_curves']['rd/'+p]['parameters'],.5,False)
            expected = core.predict(rows,f,m.r['demand'][p]['COUNTRY/'+country]['beta'])
            assert np.allclose(m.demand(x,{})[1][j,k,:,0],expected,atol=1e-12)
    a = m.evaluate(x, details=True)
    changed = x.copy(); changed[19] += 100
    assert m.evaluate(changed, details=True)['demand'][0][1] > a['demand'][0][1]
    changed = x.copy(); changed[18] -= 100; changed[19] += 100
    assert np.allclose(m.demand(changed, {})[0], m.demand(x, {})[0])
    changed = x.copy(); changed[12] += changed[13]; changed[13] = 0
    assert np.allclose(m.demand(changed, {})[0], m.demand(x, {})[0])
    for j in range(2):
        for k in range(3):
            xx = x.copy(); xx[3*j+k] *= 1.1
            assert m.demand(xx, {})[0][j,k,0] < m.demand(x, {})[0][j,k,0]
    for cfg in [dict(old_price=0), dict(old_rival_price=True), dict(rd_gain=1.1),
                dict(marketing_gain=-1), dict(ph_price=float('nan')), dict(rival_scale=0)]:
        try:
            m.demand(x, cfg)
        except ValueError:
            pass
        else:
            raise AssertionError(cfg)
    for bad in [x[:-1], [True]+x[1:].tolist(), np.full(28, np.nan)]:
        try:
            m.validate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid decision')
    for cfg in m.r['scenarios']:
        ev = m.evaluate(x, cfg, True)
        assert np.allclose(np.sum(ev['shares'], axis=2), 1)
        assert np.allclose(np.array(ev['market_totals'])*ev['own_shares'], ev['demand'])
        assert abs(ev['balance_error']) < 1e-7 and ev['quantity_error'] < 1e-8
        assert ev['production_indonesia'] == [0., 0.]
        assert np.allclose(m.evaluate(np.column_stack([x,x]), cfg)[0], ev['profit'])
    xx = x.copy(); xx[6:18] += 100; xx[18:20] += 100
    assert np.all(m.demand(xx, dict(marketing_gain=0, rd_gain=0))[0] <= m.demand(xx, {})[0]+1e-12)
    xx = x.copy(); xx[6:20] = 0
    assert np.allclose(m.demand(xx,dict(marketing_gain=0,rd_gain=0))[0],m.demand(xx,{})[0])
    assert np.all(m.demand(x, dict(disable_ph=True))[0][:,2] == 0)
    return dict(training_feature_replay=True, independent_six_market_forward_features=True,
                consistent_company_rd=True, rd_product_split_unidentified=True,
                marketing_split_unidentified=True, six_price_directions=True, invalid_input_rejected=True,
                response_failure_direction=True, share_and_quantity_and_balance_conservation=True,
                vectorized_replay=True, scenarios=len(m.r['scenarios']))


def report(m, out, fields, candidates):
    lines = ['# t6v1n2：基于t6v1n1的印尼梁定价链修复与优化', '',
        '2026-10-16，北京时间。正式6终局；部分优化，非全参数最优。保留原版及菲律宾迁移泰国假设，未填写平台。', '',
        '## 修复与使用边界', '',
        '- 研发需求特征统一为公司当期研发合计＋0.5×上期公司合计，使用冻结回合5训练曲线的代理尺度；删除单产品0.75/0.50曲线比值对公司合计训练特征的替换。正式6研发曲线原件仍保留，但不再把其单产品横轴直接套在公司合计系数上。这个修复统一口径，不证明公司费用具有因果作用或跨回合不变。',
        '- 原五类候选保留，均重新联合搜索。稳健求解覆盖旧市场价格敏感度+20%/+50%、营销新增收益失效、研发新增收益失效，以及联合不利叠加两种增益失效和价格敏感度+50%。保留原菲律宾及财务情景，共18种。',
        '- 新增收益失效只取消相对正式5公司代理特征的正增量，削减历史投入的负增量仍保留。它是保守压力定义，不是零投入也能保有旧需求的保证。50%压力是分析假设，不是置信区间。',
        '- 营销仍为公司费用研究代理。营销及研发细分不可识别：同合计重分配仍不改变需求，不把这一缺口宣称已修复。新菲律宾投入影响旧市场的可能偏差以营销增益失效情景覆盖，真实细分机制仍缺。',
        '- 价格系数不任意放大、不压售价上限，不新设印尼最低份额。当前缺乏真实标签来识别硬价格门槛；十队竞争价格仍沿用各自正式5价格。', '',
        '## 假设与期限', '',
        '所有候选均仅比较正式6新增税后利润；正式5期末状态为共同基准，15项期初状态仍缺独立核验。泰国/印尼总量沿用真实需求×1.04/1.05，菲律宾5/105千单位、指导价1600/23及运费170/2.2。费用、税率、班次、机器当期生效、印尼本期零产量与原版一致；融资时点、厂房支出800、税亏0和账期30天仍为情景，另列压力。没有第7回合或新增残值。', '',
        '中性优化中性利润；稳健优化保存的九种核心情景最低利润（见模型robust_scenario_names）；份额10%/20%/30%约束菲律宾两产品各自中性交付份额，非印尼份额目标，压力下不保证。现金检查期初投资后和期末两个时点。', '',
        '## 统一情景比较', '',
        '金额千美元，份额为实际可交付销量/总市场需求。旧候选也在本次新版18情景下回放；修复前后模型分数不能混作收益改善。', '',
        '| 来源/候选 | 印尼梁价 | 印尼梁需求，千单位 | 印尼梁份额 | 中性利润 | 18情景最低利润 | 中性期末现金 | 最低采样现金 | 最大短贷 | 菲律宾梁/件份额 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    previous = app.read(out/'prior_candidates_replay.json')
    for label, group in [('旧方案新模型回放', previous), ('新版', candidates)]:
        for c in group:
            es = c['evaluations']; e = es[0]
            lines.append(f"| {label}/{c['name']} | {c['x'][1]:.1f} | {e['demand'][0][1]:.4f} | {e['own_shares'][0][1]:.2%} | {e['profit']:.2f} | {min(v['profit'] for v in es):.2f} | {e['cash']:.2f} | {min(v['minimum_sampled_cash'] for v in es):.2f} | {max(v['short_debt'] for v in es):.2f} | {e['ph_sales_shares'][0]:.2%}/{e['ph_sales_shares'][1]:.2%} |")
    worst = min(v['profit'] for v in candidates[1]['evaluations'])
    lines += ['', f'风险优先时，新版稳健候选比追求中性利润更适合作为进一步审核基准；但其18情景最低利润为{worst:.2f}千美元，'+('仍亏损，不能称为安全盈利方案或直接执行建议。' if worst < 0 else '仅在所列有限情景中非负，不能保证真实盈利。')+'真实预测精度及全局最优仍未验证。份额候选用于比较抢占代价，不能以目标达标替代收益与风险验收。', '',
        '## 全部56项字段', '', '当前值来自归档小组草稿。公司合计费用纳入搜索，细分仅作旧版展示约定；研发合计决定需求，产品拆分仍会影响旧界面展示，不代表已识别单产品需求收益。投标、分包等明确未求解。']
    heads = ['需求','生产—投资','生产—计划','销售—泰国','销售—印尼','销售—菲律宾','销售—大客户订单','物流','财务']
    coverage = []; last = None
    for f in sorted(fields, key=old.w.field_page):
        page = old.w.field_page(f)[0]
        if page != last:
            lines += ['', '### '+heads[page], '', '| 参数 | 产品/国家 | 单位 | 当前值 | '+' | '.join(c['name'] for c in candidates)+' | 优化状态及依据 |',
                      '|---|---|---|---:|'+'---:|'*len(candidates)+'---|']
            last = page
        values = [old.w.field_value(f,c,m.r) for c in candidates]
        fmt = lambda v:f'{v:.4f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)
        status, reason = values[0][1:]
        if f['section']=='研发, 千 美元':
            status, reason = '合计求解；细分未识别', '需求使用公司研发合计代理，不解释为产品独立边际收益'
        lines.append('| '+' | '.join([f['section'],'/'.join(v for v in [f['product'],f['label']] if v),old.w.unit(f),fmt(f['value'])]+[fmt(v[0]) for v in values]+[status+'；'+reason])+' |')
        coverage.append(dict(key=f['key'],current=f['value'],unit=old.w.unit(f),status=status,reason=reason,
                             plans={c['name']:v[0] for c,v in zip(candidates,values)}))
    assert len(coverage)==len({f['key'] for f in fields})==56
    save(out/'field_coverage.json',coverage)
    lines += ['', '## 全部情景及约束', '', '| 候选 | 情景 | 利润 | 期末现金 | 最低采样现金 | 短贷 | 印尼梁需求 | 约束 |', '|---|---|---:|---:|---:|---:|---:|---|']
    for c in candidates:
        for e in c['evaluations']:
            lines.append(f"| {c['name']} | {e['scenario']} | {e['profit']:.2f} | {e['cash']:.2f} | {e['minimum_sampled_cash']:.2f} | {e['short_debt']:.2f} | {e['demand'][0][1]:.4f} | {'通过' if e['feasible'] else '未通过'} |")
    lines += ['', '## 搜索与未求解', '', '| 候选 | 种子 | 迭代 | 收敛 |', '|---|---:|---:|---|']
    lines += [f"| {q['plan']} | {q['seed']} | {q['iterations']} | {q['success']} |" for q in app.read(out/'search_trace.json')]
    lines += ['', '达到迭代上限仅为已找到候选；不是局部或全局最优证明。分析边界继承原包，非平台上限。']
    lines += ['- '+c['name']+'触界：'+('、'.join(c['boundary_variables']) or '无') for c in candidates]
    lines += ['- '+v for v in m.r['unresolved']]
    lines += ['', '没有重训价格参数或识别细分真实营销/研发机制，没有验证真实订单、期初状态和跨回合因果精度。低价不保证利润提升，高价也不因优化器推荐而得到验证。', '',
        '[模型及假设](models_full.json) · [完整结果](result.json) · [旧方案新版回放](prior_candidates_replay.json) · [检查](checks.json) · [搜索轨迹](search_trace.json) · [56项字段](field_coverage.json) · [运行说明](../../../code/model_v2/t6v1n2_README.md)']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def verify(out):
    m = app.ApplicationModel(out)
    record = checks(m)
    count = 0
    for c in app.read(out/'result.json')['candidates']:
        x = m.validate(c['x'])
        for cfg, saved in zip(m.r['scenarios'], c['evaluations']):
            ev = m.evaluate(x,cfg,True,priorities=c['fixed_priorities'])
            for k in ['profit','cash','revenue','short_debt','minimum_sampled_cash']:
                assert abs(ev[k]-saved[k])<1e-8,(c['name'],k)
            assert ev['feasible'] and abs(ev['balance_error'])<1e-7 and ev['quantity_error']<1e-8
            assert np.allclose(ev['demand'],saved['demand'])
            count += 1
        if c['target_share']:
            assert min(c['evaluations'][0]['ph_sales_shares'])>=c['target_share']-1e-10
        orders=list(itertools.product(range(6),repeat=2))
        if c['target_share']:
            orders=[o for o in orders if all(app.ORDERS[i][0]==2 for i in o)]
        assert abs(max(m.evaluate(x,details=True,priorities=o)['profit'] for o in orders)-c['evaluations'][0]['profit'])<1e-7
    assert len(app.read(out/'field_coverage.json'))==56
    for rel, expected in app.read(out/'source_hashes.json').items():
        assert sha(ROOT/rel)==expected,rel
    record.update(saved_replay_cases=count,fields=56,training_performed=False,platform_verified=False,
                  independent_forward_validation=False,full_global_optimum=False)
    save(out/'checks.json',record)
    print('PASS',record,flush=True)


def main(out, iterations):
    out.mkdir(parents=True,exist_ok=False)
    (out/'work_log.md').write_text('用户确认基于t6v1n1修复优化。新建t6v1n2，保留旧版，研发统一代理口径，增加旧市场价格及新增收益失效压力；复用五候选及完整字段。\n',encoding='utf-8')
    source_manifest=app.read(SOURCE/'manifest.json')
    for rel, expected in source_manifest['output_hashes'].items():
        assert sha(SOURCE/rel)==expected,rel
    sources={p.relative_to(ROOT).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    for path in [Path(__file__),ROOT/'code/model_v2/t6v1n2.py',ROOT/'code/model_v2/t6v1n2_README.md',
                 ROOT/'work/optimize_t6v1n1.py',ROOT/'code/model_v2/t6v1n1.py',ROOT/'code/model_v2/t6v1n.py',ROOT/'code/model_v2/t6v1.py']:
        sources[path.relative_to(ROOT).as_posix()]=sha(path)
    save(out/'source_hashes.json',sources)
    r=app.read(SOURCE/'models_full.json')
    r.update(version='t6v1n2',base_version='t6v1n1',rd_demand_mapping=dict(
        feature='company_total_rd_current + 0.5 * company_total_rd_previous',
        curve='frozen_round5_training_curve_proxy_scale',scope='口径一致性修复；关联代理，非因果或正式6验证'))
    r['investment_mapping']={'ops_previous':r['investment_mapping']['ops_previous'],
        'status':'仅运营效率沿用原映射；需求研发使用rd_demand_mapping'}
    scenarios=r['scenarios']
    r['scenarios']=[scenarios[0],dict(name='旧市场价格敏感度+20%',old_price=1.2),
        dict(name='旧市场价格敏感度+50%',old_price=1.5),dict(name='营销新增收益失效',marketing_gain=0.),
        dict(name='研发新增收益失效',rd_gain=0.),
        dict(name='联合不利加旧市场价格与投入失效',old_price=1.5,marketing_gain=0.,rd_gain=0.,
             market_scale=.9,rival_scale=1.2,efficiency_scale=.9,material_scale=1.05,ar_days=60.)]+scenarios[6:]+scenarios[1:6]
    r['robust_scenario_names']=[q['name'] for q in r['scenarios'][:6]]+[r['scenarios'][i]['name'] for i in [9,11,12]]
    r['market_forecast']['share_scope']='菲律宾迁移泰国；公司费用代理统一口径；旧市场价格和新增投入收益失效压力'
    save(out/'models_full.json',r)
    fields=app.read(SOURCE/'current_fields.json')
    save(out/'current_fields.json',fields)
    shutil.copy2(SOURCE/'published_parameters.json',out/'published_parameters.json')
    m=app.ApplicationModel(out)
    save(out/'initial_checks.json',checks(m))
    print('MECHANISM_PASS',len(r['scenarios']),flush=True)
    candidates=old.solve(m,out,iterations)
    previous=[]
    for c in app.read(SOURCE/'result.json')['candidates']:
        previous.append(dict(name=c['name'],x=c['x'],evaluations=[dict(scenario=cfg['name'],
            **m.evaluate(c['x'],cfg,True,priorities=c['fixed_priorities'])) for cfg in r['scenarios']]))
    save(out/'prior_candidates_replay.json',previous)
    save(out/'result.json',dict(version='t6v1n2',base_version='t6v1n1',start_round=6,end_round=6,
        status='PARTIAL_CONDITIONAL_OPTIMIZATION_WITH_UNSOLVED_MECHANISMS',candidates=candidates,
        baseline=m.evaluate(m.baseline,details=True)))
    save(out/'example_request.json',dict(version='t6v1n2',round=6,decision_vector=candidates[1]['x'],scenario='中性'))
    report(m,out,fields,candidates)
    verify(out)
    print('COMPLETE',out,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--iterations',type=int,default=600)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify: verify(args.out)
    else: main(args.out,args.iterations)
