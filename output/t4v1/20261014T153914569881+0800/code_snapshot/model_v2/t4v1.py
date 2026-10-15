"""Formal3 research update, with final-group decisions as the only decision source."""
import argparse
import copy
import json
import math
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code'), str(Path(__file__).parent)]
sys.dont_write_bytecode = True
import numpy as np
import t3v0 as base
import interest_rate_model as interest
import material_unit_cost_model as material
from scipy.optimize import lsq_linear
from fit_chart_json import fit_points
from stepwise_model import curve_value
from explore_six_models import shift_basis

nd = base.nd
CLOSE = ROOT/'output/round_close/20261013_formal3_close'
AUDIT = CLOSE/'archive_audit/validation/20261014T142929.104834+0800'
PRIOR = base.AUDIT
HISTORY = CLOSE/'historical_supplement/raw'
DECISIONS = CLOSE/'decision_history/final_decisions_labeled/all_fields.json'
CURVE_AUDIT = CLOSE/'historical_supplement/audit/20261014T003016.068712+0800/chart_ranges_and_svg.json'
REPAIRS = ROOT/'output/round_close/20261014_resume_verified/acceptance/20261014T152737.694032+0800'
PRODUCTS = ('复合梁', '连接件')


def product_context(row):
    if '_product' in row:
        return row['_product']
    return next((s for s in reversed(row.get('section_path', [])) if s in PRODUCTS), None)


class Actuals:
    def __init__(self, rows):
        products = {}
        self.rows = []
        for raw in rows:
            r = dict(raw); cells = r.get('cells', [])
            key = (r['source'], r.get('table_index'))
            if cells and cells[0] in PRODUCTS and len(cells) <= 2:
                products[key] = cells[0]
            r['_product'] = products.get(key, product_context(raw))
            if len(cells) == 11 and len(r.get('team_order', [])) == 10:
                self.rows.append(r)

    def teams(self, market):
        rows = [r for r in self.rows if r['market'] == market and r['panel'] == 'marketdetails']
        return [nd.team_id(market, name) for name in rows[0]['team_order']] if rows else []

    def get(self, market, round_, team, panel, label, product=None, section=None):
        matches = [r for r in self.rows if r.get('phase') == 'formal' and (r['market'], r['round'], r['panel'], r['cells'][0].strip().rstrip(' ?'))
                   == (market, round_, panel, label) and (product is None or product_context(r) == product)
                   and (section is None or r['semantic_section'] == section)]
        if len(matches) != 1:
            raise ValueError(f'Missing/ambiguous numeric field {market}/{round_}/{panel}/{label}/{product}: {len(matches)}')
        r = matches[0]
        columns = [i for i, name in enumerate(r['team_order'], 1) if nd.team_id(market, name) == team]
        if len(columns) != 1:
            raise ValueError('Missing/ambiguous team identity')
        col = columns[0]
        value, half = nd.numeric(r['cells'][col])
        if value is None:
            raise ValueError('Missing numeric actual, not zero')
        return dict(value=value, half=half, source=r['source'], sha256=r['sha256'],
                    table=r.get('table_index'), row=r.get('row_index'), column=col,
                    phase='formal', round=round_, product=product, category='actual_result')


def final_field(fields, section, product, label):
    rows = [r for r in fields if (r['round_id'], r['section'], r['subsection'], r['label'])
            == ('formal3', section, product, label)]
    if len(rows) != 1 or rows[0]['category'] != 'HISTORICAL_GROUP_DECISION_INPUT':
        raise ValueError('A unique final group decision input is required; estimates/budget rejected')
    r = rows[0]
    if r['group_column_zero_based'] != 1 or r['group_data_label'] != '回合3小组最终决策':
        raise ValueError('Not the captured final group column')
    value, half = nd.numeric(r['group_value'])
    if value is None:
        raise ValueError('Non-numeric decision input')
    return dict(value=value, half=half, source=str((CLOSE/r['source']).relative_to(ROOT)),
                table=r['source_table_zero_based'], row=r['source_row_zero_based'], column=1,
                category='FORMAL3_GROUP_FINAL_DECISION', round=3)


def table_cells(doc):
    def walk(value):
        if isinstance(value, list):
            if value and all(isinstance(v, str) for v in value):
                yield value
            else:
                for v in value:
                    yield from walk(v)
    return list(walk(doc['tables']))


def published(doc):
    ledger = {}
    for i, cells in enumerate(table_cells(doc)):
        if len(cells) == 4:
            value, half = nd.numeric(cells[1])
            if value is not None:
                ledger.setdefault(cells[0], []).append(dict(value=value, half=half, row=i, column=1))
    return ledger


def fit_curves(doc, evidence):
    assert doc['market'] == 5 and doc['selected_period']['id'] == 'formal3'
    accepted = next(e for e in evidence if e['source'] == str((HISTORY/'market5_formal3_productionplanning.json').relative_to(ROOT)).replace('\\', '/'))
    paired = {p['series']: p for p in accepted['curve_y_pairings']}
    result = {}
    for c in accepted['charts']:
        if c['id'] not in ('quality.control.chart', 'cost.efficiency.chart'):
            continue
        data = c['data']; form = 'power' if c['id'] == 'quality.control.chart' else 'saturation'
        x = np.array([float(p['label']) for p in data['categories'][0]['category']])
        for s in data['dataset']:
            if not s['seriesname'].startswith('曲线,'):
                continue
            pair = paired[s['seriesname']]
            assert pair['status'] == 'pass_y_values' and pair['points'] == 200 and pair['max_y_difference'] < 1e-10
            y = np.array([float(p['value']) for p in s['data']])
            assert len(x) == len(y) == 200 and np.all(np.diff(x) > 0)
            key = ('rd/' if form == 'power' else 'operations/') + s['seriesname'].split(', ')[1]
            result[key] = dict(**fit_points(x, y, form), form=form, points=np.c_[x, y].tolist(),
                               x_range=[float(x[0]), float(x[-1])], source=accepted['source'],
                               source_sha256=accepted['sha256'], json_svg_pairing=pair,
                               input='本回合有效投入，千美元；不是当期决策支出', round=3)
    assert set(result) == {'rd/复合梁', 'rd/连接件', 'operations/泰国'}
    return result


def self_check():
    fields = [dict(round_id='formal3', section='研发, 千 美元', subsection='复合梁', label='复合梁',
                   category='HISTORICAL_GROUP_DECISION_INPUT', group_column_zero_based=1,
                   group_data_label='回合3小组最终决策', group_value='1000', source='selfcheck',
                   source_table_zero_based=0, source_row_zero_based=1)]
    assert final_field(fields, '研发, 千 美元', '复合梁', '复合梁')['value'] == 1000
    for change in [dict(category='HISTORICAL_PLAYER_ESTIMATE_NOT_MODEL_FORECAST'), dict(group_column_zero_based=5),
                   dict(group_data_label='个人草稿'), dict(group_value='NaN'), dict(round_id='formal4')]:
        try:
            final_field([dict(fields[0], **change)], '研发, 千 美元', '复合梁', '复合梁')
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid decision source accepted')
    assert product_context(dict(section_path=['复合梁', '连接件', '复合梁'])) == '复合梁'
    fake = [dict(market=5, phase='formal', round=3, panel='productiondetails', cells=['生产规模, 千单位']+['1']*10,
                 team_order=[f'T{i}' for i in range(10)], section_path=[p], semantic_section='', source='selfcheck') for p in PRODUCTS]
    for r in fake:
        r.update(sha256='', table_index=0, row_index=0)
    actual = Actuals(fake); team = nd.team_id(5, 'T0')
    assert actual.get(5, 3, team, 'productiondetails', '生产规模, 千单位', '连接件')['value'] == 1
    try:
        actual.get(5, 3, team, 'productiondetails', '生产规模, 千单位')
    except ValueError:
        pass
    else:
        raise AssertionError('Ambiguous multiproduct row accepted')
    interest.self_check(); material.self_check()
    return dict(decision_source_guards=True, product_ambiguity_rejected=True, financial_model_selfchecks=True)


class DemandFit(base.DemandFit):
    def select(self, ids, country_independent=False):
        markets=sorted({self.rows[i]['market_id'] for i in ids});path=[]
        price_modes=(False,True) if self.rows[0]['product']=='复合梁' else (False,)
        def evaluate(config):
            scores=[]
            for held in markets:
                tr=[i for i in ids if self.rows[i]['market_id']!=held];te=[i for i in ids if self.rows[i]['market_id']==held]
                m=self.fit(tr,config);rr=[self.rows[i] for i in te]
                p=base.core.predict(rr,self.features(config['rho'],config['piecewise'])[te],m['beta'])
                scores.append(dict(market=held,mae_pp=100*base.core.score(rr,p),scale=m['scale']))
            path.append(dict(config=config,mae_pp=float(np.mean([s['mae_pp'] for s in scores])),folds=scores,
                             parameter_count=(4 if country_independent else 5)+int(config['piecewise'])*(1 if country_independent else 2)))
        for standardized in (False,True):
            for piecewise in price_modes:
                for rho in base.core.RHOS:
                    for penalty in base.core.PENALTIES:
                        evaluate(dict(standardized=standardized,piecewise=piecewise,rho=rho,penalty=penalty,loss='log'))
        rho=min(path,key=lambda p:p['mae_pp'])['config']['rho']
        for piecewise in price_modes:
            for penalty in base.core.PENALTIES:
                evaluate(dict(standardized=True,piecewise=piecewise,rho=rho,penalty=penalty,loss='share'))
        best=min(p['mae_pp'] for p in path)
        chosen=min([p for p in path if p['mae_pp']<=best*1.01],key=lambda p:(p['parameter_count'],p['mae_pp']))
        model=self.fit(ids,chosen['config']);rr=[self.rows[i] for i in ids]
        p=base.core.predict(rr,self.features(model['rho'],model['piecewise'])[ids],model['beta'])
        model.update(cv_path=path,internal_selection_mae_pp=chosen['mae_pp'],training_mae_pp=100*base.core.score(rr,p),
                     evaluation='训练内整市场选参；合计投入代理；条件回溯，不是事前预测')
        return model

    def nested(self, ids, country_independent):
        folds, predictions = [], []
        for held in sorted({self.rows[i]['market_id'] for i in ids}):
            tr=[i for i in ids if self.rows[i]['market_id']!=held]
            te=[i for i in ids if self.rows[i]['market_id']==held]
            m=self.select(tr,country_independent)
            rr=[self.rows[i] for i in te]
            p=base.core.predict(rr,self.features(m['rho'],m['piecewise'])[te],m['beta'])
            folds.append(dict(held_markets=[held],training_keys=m['training_keys'],test_keys=[base.core.key(r) for r in rr],
                selected={k:m[k] for k in ('rho','penalty','loss','standardized','piecewise')},mae_pp=100*base.core.score(rr,p)))
            y=base.core.actual_shares(rr)
            predictions.extend(dict(key=base.core.key(r),product=r['product'],actual_share=float(a),predicted_share=float(b)) for r,a,b in zip(rr,y,p))
        return dict(folds=folds,predictions=predictions,mae_pp=float(np.mean([f['mae_pp'] for f in folds])),
                    scope='嵌套整市场留出；已实现竞争输入与行业总量；不是事前预测')


def absolute_fit(rows,params):
    x=base.core.features(rows,params)
    x=np.c_[[[int(r['country']==c) for c in base.core.COUNTRIES] for r in rows],x]
    ids=[i for i,r in enumerate(rows) if r['demand']>0]
    def fit(train,penalty):
        rr=[rows[i] for i in train];xx=x[train];y=np.log([r['demand'] for r in rr]);w=base.core.equal_weights(rr)
        scale=np.sqrt(np.sum(w[:,None]*xx[:,2:]**2,axis=0));scale[scale<1e-12]=1
        z=xx.copy();z[:,2:]/=scale
        result=lsq_linear(np.vstack([z*np.sqrt(w)[:,None],np.diag([0,0]+[np.sqrt(penalty)]*5)]),
                         np.r_[y*np.sqrt(w),np.zeros(7)],bounds=([-np.inf]*2+[0]*5,[np.inf]*7),tol=1e-12)
        assert result.success
        beta=result.x.copy();beta[2:]/=scale
        return beta
    scores=[]
    for penalty in base.core.PENALTIES:
        errors=[]
        for market in sorted({r['market_id'] for r in rows}):
            tr=[i for i in ids if rows[i]['market_id']!=market];te=[i for i in ids if rows[i]['market_id']==market]
            b=fit(tr,penalty);errors.append(float(np.mean(abs(np.exp(x[te]@b)-[rows[i]['demand'] for i in te]))))
        scores.append(dict(penalty=penalty,mae_kunits=float(np.mean(errors))))
    chosen=min(scores,key=lambda s:s['mae_kunits'])
    return dict(beta=fit(ids,chosen['penalty']).tolist(),penalty=chosen['penalty'],cv_path=scores,
                training_keys=[base.core.key(rows[i]) for i in ids],zero_demand_exclusions=len(rows)-len(ids),
                curve_round=3,rho=.5,status='TRAINING_INTERNAL_SELECTION_NOT_INDEPENDENT_VALIDATION')


def load_previous():
    previous = nd.read(PRIOR/'rows.json')
    for row in previous:
        row['source'] = str((PRIOR.parent.parent/row['source']).relative_to(ROOT))
    repaired = nd.read(REPAIRS/'historical_rows.json')
    key = lambda r: (r['market'], r['phase'], r['round'], r['panel'])
    replaced = {key(r) for r in repaired}
    return [r for r in previous if key(r) not in replaced] + repaired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); checks = self_check()
    if args.self_check:
        print(json.dumps(checks)); return
    out = args.output or ROOT/'output/t4v1'/datetime.now(nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
    if args.output:
        assert (out/'work_log.md').is_file() and not (out/'models.json').exists()
    else:
        out.mkdir(parents=True, exist_ok=False)
        (out/'work_log.md').write_text('# t4v1 工作日志\n正式3全模型核验与可估计模型训练。不要输出真名，姓名统一用首字母替代。\n', encoding='utf-8')
    print('OUTPUT', out, flush=True)
    inputs = [AUDIT/'rows.json', AUDIT/'sources.json', AUDIT/'validation.json', AUDIT/'financial_checks.json',
              PRIOR/'rows.json', REPAIRS/'historical_rows.json', REPAIRS/'acceptance.json', REPAIRS/'sources.json', DECISIONS, CURVE_AUDIT, HISTORY/'market5_formal3_outlook.json',
              HISTORY/'market5_formal3_productionplanning.json', CLOSE/'score_preparation/acceptance.md',
              ROOT/'output/t3v0/20261013T182432038858+0800/models.json',
              ROOT/'output/t3v0/20261013T182432038858+0800/model_inventory.json',
              ROOT/'output/t3v0/20261013T182432038858+0800/manifest.json']
    hashes = {str(p.relative_to(ROOT)): nd.sha(p) for p in inputs}
    validation = nd.read(AUDIT/'validation.json')
    assert validation['valid_complete_pages'] == 150 and validation['structure_reviews'] == 0
    assert validation['financial_counts'] == {'pass': 500} and not validation['raw_hash_changes']
    sources = nd.read(AUDIT/'sources.json') + nd.read(REPAIRS/'sources.json')
    for s in sources:
        path = ROOT/s['source']; assert nd.sha(path) == s['sha256']
        hashes[s['source']] = s['sha256']
    labeled = nd.read(DECISIONS); fields = [f for f in labeled['fields'] if f['round_id'] == 'formal3']
    source = CLOSE/'raw/market5_formal3_decisionchecklist_verified.json'
    coverage = next(c for c in labeled['coverage'] if c['round_id'] == 'formal3')
    assert nd.sha(source) == coverage['sha256'] and coverage['selected'] == '回合3' and coverage['group_column'] == 1
    hashes[str(source.relative_to(ROOT))] = nd.sha(source)
    outdoc = nd.read(HISTORY/'market5_formal3_outlook.json')
    assert outdoc['selected_period']['id'] == 'formal3'
    ledger = published(outdoc)
    curves = fit_curves(nd.read(HISTORY/'market5_formal3_productionplanning.json'), nd.read(CURVE_AUDIT))
    for c in curves.values():
        assert nd.sha(ROOT/c['source']) == c['source_sha256']; hashes[c['source']] = c['source_sha256']
    prior_rows = load_previous()
    for r in prior_rows:
        path=ROOT/r['source']
        assert nd.sha(path)==r['sha256']
        hashes[str(path.relative_to(ROOT))]=r['sha256']
    all_rows = prior_rows + nd.read(AUDIT/'rows.json')
    actual = Actuals(all_rows)
    assert sorted({r['market'] for r in nd.read(AUDIT/'rows.json')}) == list(range(1, 11))
    own_team = nd.team_id(5, '营销团队')
    pairs, risk, mats, exclusions = [], [], {p: [] for p in PRODUCTS}, []
    for market in sorted({r['market'] for r in nd.read(AUDIT/'rows.json')}):
        for team in actual.teams(market):
            states = {}
            for round_ in (2, 3):
                refs = {}
                for key, panel, label in [('cash','balancesheet','现金及现金等价物'), ('ar','balancesheet','应收帐款'),
                    ('ap','balancesheet','应付账款'), ('machine_book','balancesheet','机器'), ('building_book','balancesheet','厂房'),
                    ('long_debt','balancesheet','长期贷款'), ('short_debt','balancesheet','短期贷款'),
                    ('assets','balancesheet','资产 总计'), ('equity','balancesheet','股东权益合计'),
                    ('advance_receipts','balancesheet','已收预付款'), ('operations','incomestatement','运营改进')]:
                    try:
                        refs[key] = actual.get(market, round_, team, panel, label)
                    except ValueError:
                        refs[key] = dict(value=None, status='MISSING_OR_AMBIGUOUS', round=round_)
                states[round_] = dict(values={k: r['value'] for k, r in refs.items()}, refs=refs)
            pairs.append(dict(market_id=market, team_id=team, initial=states[2], closing=states[3],
                              initial_basis='formal2_actual_closing', closing_basis='formal3_actual_closing',
                              unknown=['tax_loss','complete_rd_stock','complete_operations_stock']))
            try:
                rate = actual.get(market, 3, team, 'ratios', '长期贷款利率，%')
                risk.append(dict(market_id=market, team_id=team, **interest.ratios(states[3]['values']),
                                 premium=rate['value']/100-ledger['基准利率'][0]['value']/100, rate=rate))
            except ValueError as e:
                exclusions.append(dict(model='RISK', market=market, team_id=team, reason=str(e)))
            for product in PRODUCTS:
                try:
                    q = actual.get(market, 3, team, 'productiondetails', '生产规模, 千单位', product)
                    cost = actual.get(market, 3, team, 'incomestatement', '原材料购买', product)
                    if q['value'] <= q['half']:
                        raise ValueError('Zero/tiny production: unit material cost unidentifiable')
                    price = ledger[product][0]['value']
                    mats[product].append(dict(market=market, phase='formal', round=3, team=team, product=product,
                        production=q['value'], published_material=price, material_cost=cost['value'],
                        implied_low=(cost['value']-cost['half'])/(q['value']+q['half']),
                        implied_high=(cost['value']+cost['half'])/(q['value']-q['half']), sources=dict(production=q,cost=cost)))
                except ValueError as e:
                    exclusions.append(dict(model='MATERIAL', market=market, team_id=team, product=product, reason=str(e)))
    assert len(pairs) == 100 and len({(p['market_id'], p['team_id']) for p in pairs}) == 100
    # Combined expenses remain company-level proxies, never invented product allocations.
    own = []; crosschecks = []
    for product in PRODUCTS:
        for country in base.core.COUNTRIES:
            refs = {key: final_field(fields, section, sub, label) for key, section, sub, label in [
                ('price','每单位价格',product,country+', 美元'), ('general','一般营销, 千 美元',product,country),
                ('designer','设计师营销, 千 美元',product,country), ('rd','研发, 千 美元','',product),
                ('operations','运营改进, 千 美元','', '泰国')]}
            for r in refs.values():
                r['sha256'] = nd.sha(ROOT/r['source'])
            demand = actual.get(5,3,own_team,'marketdetails',country,product,'需求, 千单位')
            sales = actual.get(5,3,own_team,'marketdetails',country,product,'销售, 千单位')
            price = actual.get(5,3,own_team,'marketdetails',country+', 美元',product,'价格')
            passed = nd.compatible(refs['price']['value'],refs['price']['half'],price['value'],price['half'])
            assert passed
            crosschecks.append(dict(product=product,country=country,field='price',passed=passed,decision=refs['price'],actual=price))
            own.append(dict(market_id=5,team_id=own_team,phase='formal',round=3,product=product,country=country,
                            **{k:r['value'] for k,r in refs.items()},demand=demand['value'],sales=sales['value'],
                            sources=dict(**refs,demand=demand,sales=sales),eligible_for_competitive_fit=False))
    for key,label in [('general','一般营销'),('designer','设计师营销'),('rd','研发')]:
        submitted = sum(r[key] for r in own)/(2 if key=='rd' else 1)
        observed = actual.get(5,3,own_team,'incomestatement',label)
        assert abs(submitted-observed['value']) <= observed['half']+1e-9
        crosschecks.append(dict(field=key,submitted=submitted,observed=observed,passed=True))
    assert own[0]['operations'] == actual.get(5,3,own_team,'incomestatement','运营改进')['value']
    nd.save(out/'frozen_evaluation_before_refit.json',dict(status='NO_MATCHING_PROSPECTIVE_FORECAST',
        source=str((CLOSE/'score_preparation/acceptance.md').relative_to(ROOT)),scored_n=0,
        reason='实际小组方案四项零售售价与冻结候选不同；不将条件重算冒充事前成绩'))
    training={p:[] for p in PRODUCTS}; previous_actual=base.Actuals(prior_rows)
    for pair in pairs:
        market,team=pair['market_id'],pair['team_id']
        common={k:actual.get(market,3,team,'incomestatement',label) for k,label in
                [('general','一般营销'),('designer','设计师营销'),('rd','研发'),('operations','运营改进')]}
        previous_rd=actual.get(market,2,team,'incomestatement','研发')
        for product in PRODUCTS:
            for country in base.core.COUNTRIES:
                price=actual.get(market,3,team,'marketdetails',country+', 美元',product,'价格')
                demand=actual.get(market,3,team,'marketdetails',country,product,'需求, 千单位')
                sales=actual.get(market,3,team,'marketdetails',country,product,'销售, 千单位')
                initial=previous_actual.get(market,'initial',0,team,'marketdetails',country+', 美元','价格') if product=='复合梁' else None
                row=dict(market_id=market,team_id=team,phase='formal',round=3,product=product,country=country,
                    context_id='T4V0_FORMAL3_ACTUAL_COMPANY_TOTAL_PROXY',price=price['value'],demand=demand['value'],sales=sales['value'],
                    **{k:v['value'] for k,v in common.items()},previous_rd=previous_rd['value'],
                    previous_operations=pair['initial']['values']['operations'],initial_price=initial['value'] if initial else 1.,
                    sources=dict(**common,price=price,demand=demand,sales=sales,previous_rd=previous_rd,initial_price=initial),
                    input_scope='公司合计营销/研发代理；不等于本产品投入；用户授权先全部以实际值训练',
                    initial_price_scope='initial0_actual' if initial else 'unit_reference_only_linear_price; no_initial_connector_price; no_piecewise')
                assert row['sales']<=row['demand']+.015
                if row['price']==0:
                    assert row['demand']==0 and row['sales']==0
                    exclusions.append(dict(model='DEMAND',market=market,team_id=team,product=product,country=country,
                        price=0,demand=0,sales=0,reason='零售价且实际需求/销量为零；对数模型范围外，原记录保留，不伪造正数'))
                    continue
                training[product].append(row)
    demand_models={}; demand_predictions=[]
    for product,rows in training.items():
        engine=DemandFit(rows,curves['rd/'+product]['parameters']); fitted={}
        for name,ids in [('SHARE',list(range(len(rows)))),*[(f'COUNTRY/{c}',[i for i,r in enumerate(rows) if r['country']==c]) for c in base.core.COUNTRIES]]:
            print('TRAIN',product,name,flush=True)
            fitted[name]=engine.select(ids,name.startswith('COUNTRY'))
            fitted[name]['nested_validation']=engine.nested(ids,name.startswith('COUNTRY'))
            fitted[name]['competition_group_counts']=[dict(market=key[0],country=key[-1],active_rows=len(group))
                for key,group in base.core.old.groups([rows[i] for i in ids]).items()]
            demand_predictions.extend(dict(model=name,**p) for p in fitted[name]['nested_validation']['predictions'])
            nd.save(out/(product+'_'+name.replace('/','_')+'.json'),fitted[name])
        fitted['ABS']=absolute_fit(rows,curves['rd/'+product]['parameters'])
        demand_models[product]=fitted
    nd.save(out/'demand_validation.json',demand_predictions)
    print('TRAIN formal3 curves, risk/interest and separate product materials',flush=True)
    risk_models = {}
    if len({r['market_id'] for r in risk}) >= 3:
        for form in interest.FORMS:
            folds = []
            for market in sorted({r['market_id'] for r in risk}):
                tr=[r for r in risk if r['market_id']!=market];te=[r for r in risk if r['market_id']==market]
                p=interest.fit(form,tr)
                folds.append(dict(market=market,parameters=p,mae_bp=float(np.mean(abs(interest.premium(form,p,te)-[r['premium'] for r in te])))*10000))
            risk_models[form]=dict(parameters=interest.fit(form,risk),market_holdouts=folds,
                mae_bp=float(np.mean([f['mae_bp'] for f in folds])),training_n=len(risk),
                limitation='给定实际期末资产负债的条件验证；前景叙述5%与表中4%冲突，按公布参数表4%拟合，不宣称已解决冲突')
    material_models = {}
    for product,rows in mats.items():
        if len({r['market'] for r in rows}) >= 3:
            fits={form:dict(**material.fit(rows,form),evaluation=material.evaluate(material.fit(rows,form),rows)) for form in material.FORMS}
            selected,scores=material.select(rows)
            material_models[product]=dict(models=fits,selected=selected,holdout_scores=scores,training_n=len(rows),
                scope='只拟合对应产品原材料购买；不把库存结转费用或总成本当材料费')
    efficiency = {}; efficiency_rows={p:[] for p in PRODUCTS}
    wage_checks = []
    for product in PRODUCTS:
        q=actual.get(5,3,own_team,'productiondetails','生产规模, 千单位',product)
        n=actual.get(5,3,own_team,'productiondetails','生产线人工数量',product)
        if min(q['value'],n['value'])>0:
            params=curves['operations/泰国']['parameters']; current=own[0]['operations']
            previous=next(p for p in pairs if p['market_id']==5 and p['team_id']==own_team)['initial']['values']['operations']
            scenarios=[]
            for rho in base.core.RHOS:
                factor=float(curve_value(current+rho*previous,params,'saturation'))
                scenarios.append(dict(rho=rho,theta=q['value']/n['value']/factor))
            efficiency[product]=dict(status='SINGLE_COMPANY_CALIBRATION_RHO_UNIDENTIFIABLE',scenarios=scenarios,
                production=q,workers=n,current_operations=current,previous_operations=previous,training_n=1,
                limitation='每个rho都可由单个theta精确拟合；不选最优rho、不作留出或部署')
        capacity=actual.get(5,3,own_team,'productiondetails',f'机器产能, {product}, 千单位')
        wage=actual.get(5,3,own_team,'productiondetails','工资分摊, 千 美元',product)
        multipliers=[ledger['两班倒'][0]['value']-1,ledger['三班倒'][0]['value']-1]
        predicted=n['value']*ledger['泰国'][0]['value']*(1+shift_basis(q['value'],capacity['value'])@multipliers)
        wage_checks.append(dict(product=product,actual=wage,predicted=float(predicted),
            residual_kusd=float(predicted-wage['value']),status='CONDITIONAL_DIAGNOSTIC',capacity=capacity,
            limitation='显示产量/人数舍入且班次分界规则待补证，不使用统一宽容差宣称通过'))
    for pair in pairs:
        market,team=pair['market_id'],pair['team_id']
        for product in PRODUCTS:
            try:
                q=actual.get(market,3,team,'productiondetails','生产规模, 千单位',product)
                n=actual.get(market,3,team,'productiondetails','生产线人工数量',product)
                if min(q['value'],n['value'])<=0:
                    continue
                efficiency_rows[product].append(dict(market_id=market,team_id=team,
                    operations=pair['closing']['values']['operations'],previous_operations=pair['initial']['values']['operations'],
                    effective_observed=q['value']/n['value'],source=dict(production=q,workers=n)))
            except ValueError as e:
                exclusions.append(dict(model='EFF',product=product,market=market,team_id=team,reason=str(e)))
    for product,rows in efficiency_rows.items():
        if len({r['market_id'] for r in rows})>=3:
            params=curves['operations/泰国']['parameters'];folds=[]
            for market in sorted({r['market_id'] for r in rows}):
                tr=[r for r in rows if r['market_id']!=market];te=[r for r in rows if r['market_id']==market]
                fitted=base.ops.select(tr,params)
                folds.append(dict(market=market,fit=fitted,metrics=base.ops.metrics(te,base.ops.predict(te,params,fitted))))
            efficiency[product]=dict(status='RETRAINED_SEPARATE_PRODUCT_BASE_WITH_MARKET_HOLDOUTS',
                chosen=base.ops.select(rows,params),holdouts=folds,rows=rows,curve_round=3,
                rounding_profile=base.ops.rounding_profile(rows,params),
                limitation='运营上期投入代理不是完整累计存量；留出只验证同回合关联')
    finance=nd.read(AUDIT/'financial_checks.json')
    nd.save(out/'dataset.json',dict(own_final_decision_rows=own,state_pairs=pairs,risk=risk,materials=mats,
        decision_crosschecks=crosschecks,exclusions=exclusions,competitive_rows_by_product=training,
        accepted_competitive_training_rows=sum(len(r) for r in training.values()),
        authorization='用户追加：先全部以实际值训练',
        competitor_gap='其他队分产品/国家营销和研发仍缺；训练保留公司合计代理，不拆分'))
    nd.save(out/'formal3_curves.json',dict(version='t4v1',round=3,curves=curves))
    nd.save(out/'published_formal3.json',dict(round=3,ledger=ledger,base_rate_conflict=[4,5]))
    nd.save(out/'labor_and_accounts.json',dict(wage_diagnostics=wage_checks,financial_checks=finance,complete_forecast=False))
    registry=dict(version='t4v1',training_phase='formal',training_round=3,decision_source='ACTUALS_AUTHORIZED_WITH_OWN_FINAL_GROUP_CHECKS',
        demand=demand_models,curves=curves,risk=risk_models,materials=material_models,efficiency=efficiency,
        interest=dict(base_rate=.04,short_spread=.03,selected=min(risk_models,key=lambda k:risk_models[k]['mae_bp']) if risk_models else None,
                      parameters=risk_models,scope='条件关联模型；基准利率叙述冲突保留'),deployment_enabled=False)
    nd.save(out/'models.json',registry)
    inventory=copy.deepcopy(nd.read(ROOT/'output/t3v0/20261013T182432038858+0800/model_inventory.json')['models'])
    for name in inventory:
        inventory[name]=dict(status='BLOCKED_MISSING_FINAL_COMPETITOR_OR_HISTORY_INPUTS',artifact='dataset.json',
                             reason='正式3完整小组最终决策仅市场5营销团队；不从双产品合计费用猜测产品输入')
    for name in ('RD','OPS'):
        inventory[name]=dict(status='RETRAINED_CURVE_200_POINTS_PER_SERIES',artifact='formal3_curves.json')
    for name in ('RISK_POWER','RISK_EXP','INTEREST'):
        inventory[name]=dict(status='RETRAINED_CONDITIONAL_WITH_RATE_SOURCE_CONFLICT',artifact='models.json',n=len(risk))
    for name in ('MATERIAL','MATERIAL_PROP'):
        inventory[name]=dict(status='RETRAINED_SEPARATE_PRODUCTS',artifact='models.json',counts={p:len(r) for p,r in mats.items()})
    for name in ('ABS','SHARE','COUNTRY'):
        inventory[name]=dict(status='RETRAINED_SEPARATE_PRODUCTS_COMPANY_TOTAL_PROXIES',artifact='models.json',
                             counts={p:len(r) for p,r in training.items()})
    inventory['EFF']=dict(status='RETRAINED_SEPARATE_PRODUCT_MARKET_HOLDOUTS',artifact='models.json',
                          counts={p:len(r) for p,r in efficiency_rows.items()})
    for name in ('CAPACITY','LABOR','OPERATING','FINANCE'):
        inventory[name]=dict(status='RULE_DIAGNOSTICS_WITH_EXPLICIT_GAPS',artifact='labor_and_accounts.json')
    for name in ('TOTAL','BASELINE','GROWTH'):
        inventory[name]=dict(status='ACTUAL_TOTAL_DIAGNOSTICS_NOT_PREDICTIVE_TRAINING',artifact='industry.json')
    inventory['METRICS']=dict(status='SOURCE_AND_SELF_CHECKS_PASS',artifact='checks.json')
    inventory['HORIZON']=dict(status='BLOCKED_INCOMPLETE_ROUNDS_4_TO_6_STATE_CHAIN',artifact='models.json')
    for name in ('CONNECTOR','CONNECTOR_V2','JOINT_ALLOCATION'):
        inventory[name]=dict(status='EXISTING_RULE_SELF_CHECK_NOT_FORMAL3_SUPERVISED_TRAINING',artifact='connector_checks.json',
                             reason='保留旧实现；决策/订单跨期训练证据不足，未部署')
    nd.save(out/'model_inventory.json',dict(version='t4v1',models=inventory,count=len(inventory),deployment=False))
    industry=[]
    for market in sorted({p['market_id'] for p in pairs}):
        for product in PRODUCTS:
            for country in base.core.COUNTRIES:
                refs=[actual.get(market,3,t,'marketdetails',country,product,'需求, 千单位') for t in actual.teams(market)]
                industry.append(dict(market=market,product=product,country=country,round=3,
                                     actual_total_kunits=sum(r['value'] for r in refs),equal_share_kunits=sum(r['value'] for r in refs)/10,
                                     forecast=False))
    nd.save(out/'industry.json',industry)
    nd.csv_write(out/'decision_actual_pairs.csv',own)
    nd.csv_write(out/'competitive_actual_inputs.csv',[r for rows in training.values() for r in rows])
    nd.csv_write(out/'demand_validation.csv',demand_predictions)
    nd.csv_write(out/'model_inventory.csv',[dict(model=k,**v) for k,v in inventory.items()])
    nd.csv_write(out/'industry.csv',industry)
    nd.csv_write(out/'financial_checks.csv',finance)
    point_rows=[dict(curve=k,round=3,x=x,y=y,predicted=float(curve_value(x,c['parameters'],c['form'])))
                for k,c in curves.items() for x,y in c['points']]
    nd.csv_write(out/'curve_points.csv',point_rows)
    checks.update(state_pairs=len(pairs),own_final_rows=len(own),curve_points=len(point_rows),
        final_decision_prices_match=True,budget_used_as_actual=False,formal4_used_in_training=False,
        financial_counts=dict(Counter(r['status'] for r in finance)),competitive_training_rows=sum(len(r) for r in training.values()),
        company_total_proxies_disclosed=True)
    nd.save(out/'checks.json',checks)
    nd.save(out/'input_manifest.json',dict(version='t4v1',input_hashes=hashes,training_cutoff='formal3_actual',units=base.core.UNITS))
    lines=['# t4v1 正式3训练与核验报告','',f'北京时间运行：{out.name}。研究版本，未部署。',
        f'已核验{len({p["market_id"] for p in pairs})}市场、{len(pairs)}队初终值；本组4条产品/国家输入严格来自正式3小组最终决策。',
        '正式3双产品数据分开处理；正式4曲线不进入训练。42项决策列表输入中玩家预估和预算不作为实际标签。',
        '用户追加授权“先全部以实际值训练”：需求按两个产品分别训练；营销/研发采用公司合计代理，不伪造分产品投入。',
        '三条当期曲线各200点拟合与交错留点验证；风险/利率两函数、分产品效率和材料费用分别重训。',
        '需求选参采用嵌套整市场留出；复合梁分段点使用初始0实际价×1.5，连接件缺初始价，仅训练线性价格。',
        '冻结候选与实际决策不匹配，可直接评分0项；不生成虚假的事前预测误差。',
        '', '| 模型 | 状态 |','|---|---|']
    lines += [f"| {k} | {v['status']} |" for k,v in inventory.items()]
    lines += ['', '## 当前全部问题与不足','',
        '需求ABS/SHARE/COUNTRY已经以实际公司合计代理训练；附加A–F历史或环境校准证据另核。',
        '正式3实际结果完整核验覆盖150/150页，10市场100队全部纳入。',
        '前景中央银行叙述5%与参数表4%冲突，风险拟合使用参数表4%，仍须补证。',
        '显示产量/人数的工资回放只作条件诊断；机器投资当期生效与旧模型假设冲突未在本任务伪装解决。',
        '', '## 因缺乏数据而无法验证的问题','',
        '其他队分产品/国家最终营销和研发；连接件完整订单、预收和跨期状态；税亏与完整投入存量；正式4–6未来条件。',
        '曲线图形误差不是经营验证。风险及材料为同期实际状态条件验证，不证明跨回合参数稳定。',
        '未填写决策、未提交平台、未优化或部署模型；旧参数及冻结结果保留。',
        '', '## 曲线留点误差','', '| 曲线 | MAE | 最大误差 |','|---|---:|---:|']
    lines += [f"| {k} | {c['held_mae']:.9g} | {c['held_max_error']:.9g} |" for k,c in curves.items()]
    for p,m in material_models.items():
        lines += ['',f"材料 {p}：{m['training_n']}样本，选型{m['selected']}，留出误差{m['holdout_scores'][m['selected']]['mae_kusd']:.6g}千美元。"]
    for form,m in risk_models.items():
        lines += ['',f"风险 {form}：{m['training_n']}样本，整市场留出MAE {m['mae_bp']:.6g}基点。"]
    for product,models in demand_models.items():
        for name,m in models.items():
            if name!='ABS':
                lines += ['',f"需求 {product}/{name}：嵌套整市场留出MAE {m['nested_validation']['mae_pp']:.6g}个百分点；同回合条件验证。"]
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for path,digest in hashes.items():
        assert nd.sha(ROOT/path)==digest, path
    snapshot=out/'code_snapshot'
    for p in (ROOT/'code').rglob('*.py'):
        dest=snapshot/p.relative_to(ROOT/'code');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    with (out/'work_log.md').open('a',encoding='utf-8') as f:
        f.write('\n完成10市场100队双产品需求、曲线、风险/利率、效率、材料重训；跨期与因果投入限制保留。来源哈希前后不变。\n')
    nd.save(out/'manifest.json',dict(version='t4v1',status='PARTIAL_TRAINING_WITH_EXPLICIT_DATA_GAPS',
        input_hashes=hashes,protected_inputs_unchanged=True,training_round=3,
        output_hashes={p.relative_to(out).as_posix():nd.sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE_WITH_GAPS',out,flush=True)


if __name__ == '__main__':
    main()
