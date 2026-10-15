"""Formal4 research training; only captured final-group decisions are decision inputs."""
import argparse
import copy
import importlib.util
import json
import math
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code'), str(Path(__file__).parent)]
sys.dont_write_bytecode = True
import numpy as np
import t4v1 as prior
from connector_free_production import self_check as connector_check
from joint_allocation import self_check as joint_check

nd = prior.nd
CLOSE = ROOT/'output/round_close/20261014_formal4_close'
FINAL = CLOSE/'final_validation'
DEC = CLOSE/'decision_history/20261014T233043761904+0800'
CURVES = ROOT/'output/round_close/20261013_formal3_close/formal4_initial/curves/20261014T004027'
OLD = ROOT/'output/t4v1_deduplicated/20261014T162452595723+0800'


def final_field(fields, section, product, label):
    matches = [r for r in fields if (r['section'], r['product_or_location'], r['label']) == (section, product, label)]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous captured final decision')
    r = matches[0]
    if (r['phase'], r['round'], r['market_id'], r['column'], r['column_identity'], r['category']) != (
            'formal', 4, 5, 1, '营销团队', 'ROUND_4_GROUP_FINAL_DECISION'):
        raise ValueError('Only captured formal4 final-group decision columns are accepted')
    value, half = nd.numeric(r['display'])
    if value is None or value != r['value']:
        raise ValueError('Invalid captured decision value')
    return dict(value=value, half=half, source=r['source_path'], sha256=r['sha256'],
                table=r['table'], row=r['row'], column=1, round=4, category=r['category'])


def self_check():
    row = dict(section='price', product_or_location='beam', label='TH', phase='formal', round=4,
        market_id=5, column=1, column_identity='营销团队', category='ROUND_4_GROUP_FINAL_DECISION',
        display='10', value=10, source_path='selfcheck', sha256='', table=1, row=7)
    assert final_field([row], 'price', 'beam', 'TH')['value'] == 10
    for change in [dict(round=3), dict(column=2), dict(category='ROUND_4_GROUP_FINAL_PLAYER_ESTIMATE'),
                   dict(column_identity='PYT'), dict(display='NaN'), dict(value=11)]:
        try:
            final_field([dict(row, **change)], 'price', 'beam', 'TH')
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid decision source accepted')
    prior.interest.self_check(); prior.material.self_check()
    return dict(final_decision_guards=True, financial_selfchecks=True,
                connector=connector_check(), joint_allocation=joint_check())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        print(json.dumps(self_check())); return
    stamp = datetime.now(nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
    out = ROOT/'output/t5v0'/stamp
    out.mkdir(parents=True, exist_ok=False)
    log = out/'work_log.md'
    log.write_text('# t5v0 工作日志\n\n'+stamp+' 开始：用户授权立即执行正式4全模型训练。状态：进行中。\n'
        '不要输出真名，姓名统一用大写首字母替代。决策只用实际采集的正式4小组最终列。\n'
        '全部29类逐项处理，资料不足明确暂停；不覆盖旧模型，不修改平台。\n', encoding='utf-8')
    print('OUTPUT', out, flush=True)
    (ROOT/'work/t5v0_active_run.txt').write_text(str(out), encoding='utf-8')
    hashes = {}
    def track(path, expected=None):
        digest = nd.sha(path)
        if expected is not None:
            assert digest == expected, path
        hashes[path.relative_to(ROOT).as_posix()] = digest
        return path
    def read(path):
        return nd.read(track(path))
    snapshot = out/'code_snapshot'
    for path in (ROOT/'code').rglob('*.py'):
        dest = snapshot/path.relative_to(ROOT/'code'); dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(track(path), dest)
    checks = self_check()
    acceptance = read(FINAL/'acceptance_index.json')
    assert acceptance['status'] == 'FORMAL4_ARCHIVE_ACCEPTED' and acceptance['accepted_current_pages'] == 140
    assert len(acceptance['markets']) == 10
    for ref in acceptance['sources'] + acceptance['artifacts']:
        track(ROOT/ref['source'], ref['sha256'])
    spec = importlib.util.spec_from_file_location('formal4_row_rules',
        track(ROOT/'output/round_close/20261013_formal3_close/archive_audit/verify_formal3_close.py'))
    rules = importlib.util.module_from_spec(spec); spec.loader.exec_module(rules)
    rows = []
    for ref in acceptance['sources']:
        match = re.fullmatch(r'market(\d+)_formal4_([a-z]+)(?:_complete)?\.json', Path(ref['source']).name)
        if not match or match[2] == 'print':
            continue
        records, reviews, _ = rules.rows_for(read(ROOT/ref['source']), dict(ref, market=int(match[1]), panel=match[2]))
        for r in records:
            r['round'] = 4
        rows.extend(records)
    # Ratios/logistics details only appear in the accepted print: reuse their verified field mapping.
    for field in read(FINAL/'field_coverage.json'):
        if field['panel'] not in ('ratios', 'logisticsdetails'):
            continue
        ref = field['formal4_print_sources'][0]; doc = read(ROOT/ref['source'])
        table = doc['tables'][ref['table_index']]
        header = next(r[1:] for r in table if len(r) == 11 and not r[0].strip())
        cells = table[ref['row_index']]
        assert len(cells) == 11 and len(header) == 10
        rows.append(dict(source=ref['source'], sha256=ref['sha256'], market=field['market'], phase='formal',
            round=4, panel=field['panel'], table_index=ref['table_index'], row_index=ref['row_index'],
            cells=cells, team_order=header, section_path=field['section_path'], semantic_section=field['section_path'][-1]))
    previous = prior.load_previous() + read(prior.AUDIT/'rows.json')
    for r in previous:
        track(ROOT/r['source'], r['sha256'])
    actual = prior.Actuals(previous + rows)
    fields = read(DEC/'group_final_42.json')
    assert len(fields) == 42 and len({r['key'] for r in fields}) == 42
    raw = read(track(ROOT/fields[0]['source_path'], fields[0]['sha256']))
    assert raw['tables'][1][0][1] == '营销团队' and '回合4' in rules.selected(raw)
    for r in fields:
        track(ROOT/r['source_path'], r['sha256'])
        assert (r['round'], r['column']) == (4, 1)
        assert raw['tables'][r['table']][r['row']][r['column']] == r['display']
    nd.save(out/'captured_final_group_fields.json', fields)
    frozen = read(DEC/'frozen_score_verdict.json')
    nd.save(out/'frozen_evaluation_before_refit.json', frozen)
    outlook_path = ROOT/'output/round_close/20261013_formal3_close/formal4_initial/raw/market5_formal4_outlook.json'
    outlook = read(outlook_path)
    assert outlook['selected_period']['id'] == 'formal4'
    ledger = prior.published(outlook)
    nd.save(out/'published_formal4.json', dict(round=4, ledger=ledger))
    curve_map = {'rd_beam':'rd/复合梁', 'rd_connector':'rd/连接件', 'operations_thailand':'operations/泰国'}
    curves = {}; points = []
    for item in read(CURVES/'curve_index.json'):
        doc = read(CURVES/item['file']); source = track(ROOT/doc['source'], doc['source_sha256'])
        assert doc['valid_period'] == 'formal4' and doc['market'] == 5 and item['max_svg_y_delta'] < 1e-10
        x = np.array(doc['x_labels'], float); y = np.array(doc['original_y_values'], float)
        assert len(x) == len(y) == 200 and np.all(np.diff(x)>0) and np.isfinite(y).all()
        form = 'saturation' if item['chart_id'] == 'cost.efficiency.chart' else 'power'
        key = curve_map[Path(item['file']).stem]
        curves[key] = dict(**prior.fit_points(x,y,form), form=form, points=np.c_[x,y].tolist(),
            round=4, source=source.relative_to(ROOT).as_posix(), source_sha256=nd.sha(source),
            upstream_condition=doc['upstream_condition'], x_range=[float(x[0]),float(x[-1])],
            json_svg_max_y_delta=item['max_svg_y_delta'], input='本回合有效投入千美元，非当期支出')
        points.extend(dict(curve=key, round=4, x=float(a), y=float(b),
            predicted=float(prior.curve_value(a,curves[key]['parameters'],form))) for a,b in zip(x,y))
    nd.save(out/'formal4_curves.json', dict(version='t5v0', round=4, curves=curves))
    nd.csv_write(out/'curve_points.csv', points)
    pairs = []; own = []; exclusions = []; risks = []; materials = {p:[] for p in prior.PRODUCTS}
    wages = {p:[] for p in prior.PRODUCTS}; physics = []; severance = []; industry = []
    team = nd.team_id(5, '营销团队')
    state_fields = [('cash','现金及现金等价物'),('ar','应收帐款'),('ap','应付账款'),('machine_book','机器'),
        ('building_book','厂房'),('long_debt','长期贷款'),('short_debt','短期贷款'),('assets','资产 总计'),
        ('equity','股东权益合计'),('advance_receipts','已收预付款')]
    for m in range(1,11):
        assert len(actual.teams(m)) == 10
        for tid in actual.teams(m):
            states = {}
            for round_ in (3,4):
                refs = {k:actual.get(m,round_,tid,'balancesheet',label) for k,label in state_fields}
                states[round_] = dict(values={k:r['value'] for k,r in refs.items()}, refs=refs)
            pairs.append(dict(market_id=m,team_id=tid,initial=states[3],closing=states[4],
                initial_basis='formal3_actual_closing_state_carryover_not_all_opening_cash',
                unknown=['tax_loss','full_rd_stock','full_operations_stock','unobserved_opening_cash_timing']))
            try:
                rate = actual.get(m,4,tid,'ratios','长期贷款利率，%')
                risks.append(dict(market_id=m,team_id=tid,**prior.interest.ratios(states[4]['values']),
                    premium=rate['value']/100-ledger['基准利率'][0]['value']/100, rate=rate))
            except ValueError as e:
                exclusions.append(dict(model='RISK',market=m,team_id=tid,reason=str(e)))
            event = actual.get(m,4,tid,'productionhr','招聘 + / 裁员 -')
            cost = actual.get(m,4,tid,'incomestatement','解雇成本')
            factor = ledger['泰国'][0]['value']*ledger['裁员成本，占薪资%'][0]['value']/100
            prediction = max(-event['value'],0)*factor
            tol = cost['half']+event['half']*factor
            severance.append(dict(market=m,team_id=tid,actual=cost,prediction=prediction,tolerance=tol,
                passed=abs(prediction-cost['value'])<=tol+1e-9))
            for product in prior.PRODUCTS:
                q = actual.get(m,4,tid,'productiondetails','生产规模, 千单位',product)
                n = actual.get(m,4,tid,'productiondetails','生产线人工数量',product)
                c = actual.get(m,4,tid,'productiondetails',f'机器产能, {product}, 千单位')
                wage = actual.get(m,4,tid,'productiondetails','工资分摊, 千 美元',product)
                cost = actual.get(m,4,tid,'incomestatement','原材料购买',product)
                if q['value'] > q['half']:
                    price = ledger[product][0]['value']
                    materials[product].append(dict(market=m,phase='formal',round=4,team=tid,production=q['value'],
                        published_material=price,material_cost=cost['value'],
                        implied_low=(cost['value']-cost['half'])/(q['value']+q['half']),
                        implied_high=(cost['value']+cost['half'])/(q['value']-q['half']),sources=dict(q=q,cost=cost)))
                else:
                    exclusions.append(dict(model='MATERIAL',market=m,team_id=tid,product=product,reason='zero/tiny production'))
                if min(q['value'],n['value'],c['value']) > 0 and q['value']<=c['value']:
                    scale = n['value']*ledger['泰国'][0]['value']
                    wages[product].append(dict(market=m,team_id=tid,x=prior.shift_basis(q['value'],c['value']).tolist(),
                        y=wage['value']/scale-1,scale=scale,actual=wage['value'],sources=dict(q=q,n=n,c=c,wage=wage)))
                for name,total_label,intensity_label in [('co2','二氧化碳排放, 公吨','二氧化碳排放, kg'),
                    ('energy','能源消耗, MWh','能源消耗, kWh'),('water','用水量, m3','用水量, l')]:
                    def env(label):
                        found = [r for r in actual.rows if r['market']==m and r['round']==4 and r['panel']=='productionenvironmental'
                            and r['cells'][0]==product and r['section_path'][-1]==label]
                        assert len(found)==1
                        r=found[0]; col=next(i for i,v in enumerate(r['team_order'],1) if nd.team_id(m,v)==tid)
                        return nd.numeric(r['cells'][col])
                    total,th = env(total_label); intensity,ih = env(intensity_label)
                    pred=q['value']*intensity; tol=th+q['half']*abs(intensity)+ih*abs(q['value'])+q['half']*ih
                    physics.append(dict(model='E',market=m,team_id=tid,product=product,channel=name,actual=total,
                        predicted=pred,tolerance=tol,passed=abs(total-pred)<=tol+1e-8))
    for product in prior.PRODUCTS:
        for country in prior.base.core.COUNTRIES:
            refs = {k:final_field(fields,s,sub,label) for k,s,sub,label in [
                ('price','每单位价格',product,country+', 美元'),('general','一般营销, 千 美元',product,country),
                ('designer','设计师营销, 千 美元',product,country),('rd','研发, 千 美元','',product),
                ('operations','运营改进, 千 美元','','泰国')]}
            demand=actual.get(5,4,team,'marketdetails',country,product,'需求, 千单位')
            sales=actual.get(5,4,team,'marketdetails',country,product,'销售, 千单位')
            price=actual.get(5,4,team,'marketdetails',country+', 美元',product,'价格')
            assert nd.compatible(refs['price']['value'],refs['price']['half'],price['value'],price['half'])
            own.append(dict(market_id=5,team_id=team,round=4,product=product,country=country,
                **{k:r['value'] for k,r in refs.items()},demand=demand['value'],sales=sales['value'],sources=dict(**refs,demand=demand,sales=sales)))
    print('TRAIN curves/risk/materials/wages; decision-dependent competitive fits blocked',flush=True)
    risk_models={}; material_models={}; labor={}; comparison=[]
    old=read(OLD/'models_full.json')
    for form in prior.interest.FORMS:
        folds=[]
        for m in sorted({r['market_id'] for r in risks}):
            tr=[r for r in risks if r['market_id']!=m]; te=[r for r in risks if r['market_id']==m]
            params=prior.interest.fit(form,tr)
            folds.append(dict(held_market=m,parameters=params,mae_bp=float(np.mean(abs(prior.interest.premium(form,params,te)-[r['premium'] for r in te])))*10000))
        risk_models[form]=dict(parameters=prior.interest.fit(form,risks),training_n=len(risks),market_holdouts=folds,
            mae_bp=float(np.mean([f['mae_bp'] for f in folds])),deployment=False,
            scope='期末实际状态条件关联，非决策输入或事前利率预测')
        baseline=prior.interest.premium(form,old['risk'][form]['parameters'],risks)
        comparison.append(dict(model='risk/'+form,metric='mae_bp',old_frozen_on_formal4=float(np.mean(abs(baseline-[r['premium'] for r in risks])))*10000,
            new_market_holdout=risk_models[form]['mae_bp'],scope='旧时间外条件回放与新同期留出，不是相同验证设计'))
    for product, samples in materials.items():
        selected,scores=prior.material.select(samples)
        fits={form:dict(**prior.material.fit(samples,form),evaluation=prior.material.evaluate(prior.material.fit(samples,form),samples)) for form in prior.material.FORMS}
        material_models[product]=dict(models=fits,selected=selected,holdout_scores=scores,training_n=len(samples))
        old_model=old['materials'][product]['models'][old['materials'][product]['selected']]
        comparison.append(dict(model='materials/'+product,metric='mae_kusd',old_frozen_on_formal4=prior.material.evaluate(old_model,samples)['mae_kusd'],
            new_market_holdout=scores[selected]['mae_kusd'],scope='条件回放与选型留出，不是事前经营精度'))
        samples=wages[product]; x=np.array([r['x'] for r in samples]); rank=int(np.linalg.matrix_rank(x));folds=[]
        if rank==2:
            beta=prior.base.origin_fit(x,[r['y'] for r in samples],[r['market'] for r in samples])
            for m in sorted({r['market'] for r in samples}):
                tr=[r for r in samples if r['market']!=m]; te=[r for r in samples if r['market']==m]
                xx=np.array([r['x'] for r in tr])
                if np.linalg.matrix_rank(xx)<2:
                    folds.append(dict(held_market=m,status='UNIDENTIFIABLE'));continue
                b=prior.base.origin_fit(xx,[r['y'] for r in tr],[r['market'] for r in tr])
                folds.append(dict(held_market=m,parameters=(1+b).tolist(),mae_kusd=float(np.mean([abs(r['scale']*(1+np.array(r['x'])@b)-r['actual']) for r in te]))))
            labor[product]=dict(status='RETRAINED_CONDITIONAL',parameters=(1+beta).tolist(),rank=rank,n=len(samples),holdouts=folds)
        else:
            labor[product]=dict(status='UNIDENTIFIABLE',rank=rank,n=len(samples))
    inventory=read(OLD/'model_inventory_final.json')['models']
    inventory={name:dict(status='BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY',artifact='data_gaps.json') for name in inventory}
    def status(names, state, artifact):
        for name in names:
            inventory[name]=dict(status=state,artifact=artifact)
    status(('RD','OPS'),'RETRAINED_FORMAL4_CURVES','formal4_curves.json')
    status(('RISK_POWER','RISK_EXP','INTEREST'),'RETRAINED_CONDITIONAL_ACTUAL_STATE','models_full.json')
    status(('MATERIAL','MATERIAL_PROP'),'RETRAINED_SEPARATE_PRODUCTS','models_full.json')
    status(('C','LABOR'),'CONDITIONAL_WAGE_FIT_IDENTIFIABILITY_RECORDED','models_full.json')
    status(('B',),'PUBLISHED_RULE_CHECKED_WITH_DISPLAY_INTERVALS','severance_checks.csv')
    status(('E',),'ACTUAL_INTENSITY_FORMULA_CHECKED','physics_checks.csv')
    status(('FINANCE',),'1900_SOURCE_EQUATIONS_ACCEPTED_NO_COMPLETE_FORWARD_FORECAST','archive_acceptance.json')
    status(('CONNECTOR','CONNECTOR_V2','JOINT_ALLOCATION'),'RULE_SELF_CHECK_ONLY_NO_ACTUAL_LIFECYCLE_TRAINING','checks.json')
    status(('METRICS',),'SOURCE_HASH_AND_DECISION_GUARDS_CHECKED','checks.json')
    for m in range(1,11):
        for product in prior.PRODUCTS:
            for country in prior.base.core.COUNTRIES:
                totals={r:sum(actual.get(m,r,tid,'marketdetails',country,product,'需求, 千单位')['value'] for tid in actual.teams(m)) for r in (3,4)}
                industry.append(dict(market=m,product=product,country=country,round=4,total=totals[4],previous_total=totals[3],
                    realized_growth=totals[4]/totals[3]-1 if totals[3]>0 else None,equal_share=totals[4]/10,forecast=False))
    status(('TOTAL','BASELINE','GROWTH'),'ACTUAL_TOTALS_AND_GROWTH_DIAGNOSTICS_NOT_SUPERVISED_FIT','industry.json')
    gaps=dict(missing_competitor_final_decisions=99,own_final_group_decisions=29,own_player_estimates_excluded=13,
        demand_training='PAUSED: four own product/country observations cannot identify competitive coefficients',
        expense_proxies_used_as_decision_inputs=False,other=['完整研发运营存量及有效横轴映射','确认订单/交付/预收余款','期初税亏','正式5/6完整未来状态'],
        requires='补采核验其他99队正式4逐产品逐国最终小组决策，或用户明确允许另建实际费用代理研究版本')
    registry=dict(version='t5v0',training_phase='formal',training_round=4,decision_source='CAPTURED_FORMAL4_GROUP_FINAL_ONLY',
        curves=curves,risk=risk_models,materials=material_models,labor=labor,demand={},efficiency={},
        interest=dict(base_rate=ledger['基准利率'][0]['value']/100,short_spread=ledger['高于基准的短期利率溢价'][0]['value']/100,
            parameters_source='risk',selected=min(risk_models,key=lambda k:risk_models[k]['mae_bp'])),
        model_inventory=inventory,deployment_enabled=False,status='PARTIAL_TRAINING_WITH_EXPLICIT_DATA_GAPS')
    dataset=dict(own_final_decision_rows=own,state_pairs=pairs,risk=risks,materials=materials,wages=wages,exclusions=exclusions)
    for name,obj in [('dataset.json',dataset),('models_full.json',registry),('model_inventory_final.json',dict(version='t5v0',models=inventory,count=len(inventory))),
        ('data_gaps.json',gaps),('archive_acceptance.json',acceptance),('industry.json',industry),('old_new_comparison.json',comparison)]:
        nd.save(out/name,obj)
    for name,records in [('decision_actual_pairs.csv',own),('model_inventory_final.csv',[dict(model=k,**v) for k,v in inventory.items()]),
        ('industry.csv',industry),('old_new_comparison.csv',comparison),('physics_checks.csv',physics),('severance_checks.csv',severance)]:
        nd.csv_write(out/name,records)
    checks.update(version='t5v0',training_round=4,state_pairs=len(pairs),curve_points=len(points),
        captured_group_fields=42,actual_decision_fields=29,player_estimates_excluded=13,own_decision_pairs=len(own),
        decision_expense_proxies_used=False,budget_used_as_actual=False,
        severance_failures=sum(not r['passed'] for r in severance),physics_failures=sum(not r['passed'] for r in physics),
        financial_source_checks=acceptance['checks'],model_count=len(inventory))
    assert len(pairs)==100 and len(own)==4 and len(points)==600 and len(inventory)==29
    nd.save(out/'checks.json',checks)
    lines=['# t5v0 正式4全模型处理报告','',f'北京时间运行：{stamp}。状态：部分训练完成，明确保留资料缺口。',
        '全部29类逐项处理；不宣称29个独立模型全部训练通过。权威注册表：[models_full.json](models_full.json)。',
        '决策只使用已采集正式4小组最终列：29项决策，13项玩家预估排除。4条本组产品/国家输入与真实需求配对。',
        '其他99队逐产品/国别小组最终决策缺失，需求ABS/SHARE/COUNTRY暂停；不把结果费用或个人草稿当小组决策。',
        '正式3期末状态配正式4终值100队；前者是结转基准，未披露的期初现金时点、税亏及投入存量保持未知。',
        '原冻结候选未被采用，直接事前评分0项。风险/材料/工资为给定实际期末状态或产量的条件回溯，不是完整经营预测。',
        '', '| 模型 | 状态 |','|---|---|']
    lines += [f"| {k} | {v['status']} |" for k,v in inventory.items()]
    lines += ['', '## 曲线与条件验证','', '| 曲线 | 交错留点MAE | 最大误差 |','|---|---:|---:|']
    lines += [f"| {k} | {c['held_mae']:.9g} | {c['held_max_error']:.9g} |" for k,c in curves.items()]
    lines += ['', '三条曲线各200点，正式4市场5上期研发1000/400、运营600千美元；其他市场曲线共享未独立证实。横轴为取整有效投入，图形误差不是经营精度。',
        '', '| 风险形式 | 有效样本 | 整市场留出MAE，基点 |','|---|---:|---:|']
    lines += [f"| {k} | {v['training_n']} | {v['mae_bp']:.6g} |" for k,v in risk_models.items()]
    for product,m in material_models.items():
        lines += ['', f"材料{product}：{m['training_n']}条，选型{m['selected']}，选型留出MAE {m['holdout_scores'][m['selected']]['mae_kusd']:.6g}千美元；选型误差不是嵌套独立检验。"]
    lines += ['',f"解雇规则{len(severance)}项、环境恒等式{len(physics)}项：失败{checks['severance_failures']}/{checks['physics_failures']}；容差传播原显示精度。", 
        '', '## 当前全部问题与不足','',
        '- 决策依赖模型缺竞争队最终输入；EFF/A/D完整运营机制及历史投入仍不可识别。',
        '- 工资回溯使用实际产量/人数/产能，不解决生产预测、投资生效及跨期效应。',
        '- 风险、材料同期模型及曲线跨市场共享缺独立前向验证；新旧比较仅条件误差，不表明事前收益改善。',
        '', '## 因缺乏数据而无法验证的问题','',
        '- 99队正式4产品/国别最终决策；完整运营/研发存量、自动有效投入横轴。',
        '- 真实确认订单、交付、预收与余款、税亏及正式5–6经营状态链。',
        '- 本版本不部署、不输出完整利润排名；旧模型及原始证据保留。',
        '', '[数据缺口](data_gaps.json)；[新旧比较](old_new_comparison.json)；[逐项验收](checks.json)。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with log.open('a',encoding='utf-8') as f:
        f.write('\n'+datetime.now(nd.TZ).isoformat()+' 完成：曲线/风险/材料/工资可估计项已执行，29类完整状态保存；需求等缺最终决策项暂停。原件哈希复核通过。\n')
    for p,h in hashes.items():
        assert nd.sha(ROOT/p)==h,p
    nd.save(out/'input_manifest.json',dict(version='t5v0',input_hashes=hashes,training_cutoff='formal4_actual'))
    nd.save(out/'manifest.json',dict(version='t5v0',status=registry['status'],training_round=4,input_hashes=hashes,
        output_hashes={p.relative_to(out).as_posix():nd.sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE_WITH_GAPS',out,flush=True)


if __name__ == '__main__':
    main()
