"""Read-only archive analysis. Browser collection is performed separately through cua.

Run with installed Python + NumPy/SciPy: python code/cross_market_validation.py
New files live in output/cross_market; existing model artifacts are never replaced.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear

from archive_and_report import number, table_rows, write_json
from stepwise_model import curve_value, shares

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'raw' / 'cross_market'
OUT = ROOT / 'output' / 'cross_market'
COUNTRIES = ['泰国', '印尼']
PENALTIES = [.01, .1, 1, 10]
NAMES = ['泰国价格弹性', '印尼价格弹性', '合计一般营销代理', '合计设计师营销代理', '研发曲线作用']


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def source_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(text):
    if text.strip() in ('', '-', '—', 'null', 'N/A'):
        return None
    result = number(text)
    if not np.isfinite(result):
        raise ValueError('Nonfinite source value')
    return result


def group_key(row):
    return row['market_id'], row['phase'], row['round'], row['country']


def groups(rows):
    result = defaultdict(list)
    for i, row in enumerate(rows):
        result[group_key(row)].append(i)
    return result


def parse_report(path, meta):
    doc = read(path)
    meta = dict(meta, captured_at=doc.get('captured_at'), source_url=doc.get('source_url'))
    rr = table_rows(doc['snapshot'])
    price_row = next(r for r in rr if r['cells'] and r['cells'][0] == '泰国, 美元')
    n = len(price_row['cells']) - 1
    assert n >= 2, path
    # Repeated headers identify report columns, including displayed duplicate/null names.
    candidates = [tuple(r['cells']) for r in rr if len(r['cells']) == n and
                  all(not s.replace(' ', '').replace('.', '').isdigit() for s in r['cells'])]
    assert candidates, ('Missing team headers', path)
    teams, count = Counter(candidates).most_common(1)[0]
    assert count >= 2, ('Ambiguous team headers', path)
    cells = []

    def field(label, col, occurrence=0):
        matches = [r for r in rr if len(r['cells']) == n+1 and r['cells'][0] == label]
        if len(matches) <= occurrence:
            return None, None
        row = matches[occurrence]
        value = numeric(row['cells'][col])
        ref = dict(file=path.relative_to(ROOT).as_posix(), line=row['line'], column=col,
                   label=label, occurrence=occurrence, text=row['cells'][col])
        cells.append(dict(**meta, team=teams[col-1], team_column=col, value=value, source=ref))
        return value, ref

    records = []
    for col, team in enumerate(teams, 1):
        common, refs = {}, {}
        for key, label, occurrence in [
            ('general', '一般营销', 0), ('designer', '设计师营销', 0), ('rd', '研发', 0),
            ('operations', '运营改进', 0), ('capacity', '生产能力, 千单位', 0),
            ('inventory', '复合梁', 0), ('cash', '现金及现金等价物', 0),
            ('short_debt', '短期贷款', 0), ('long_debt', '长期贷款', 0),
            ('bulk_orders', '大客户订单', 0), ('profit', '本回合利润, 千 美元', 0)]:
            common[key], refs[key] = field(label, col, occurrence)
        for country in COUNTRIES:
            row = dict(**meta, team=team, team_column=col,
                       team_id=f"{meta['market_id']}:{col}:{team}", country=country,
                       kind='actual_result', **common, sources=dict(refs))
            for key, label, occurrence in [('price', country+', 美元', 0),
                                            ('sales', country, 0), ('demand', country, 1),
                                            ('unmet', country, 2)]:
                row[key], row['sources'][key] = field(label, col, occurrence)
            assert row['price'] is None or row['price'] > 0
            assert all(row[k] is None or row[k] >= 0 for k in ['sales','demand','unmet','general','designer','rd'])
            if row['sales'] is not None and row['demand'] is not None:
                assert row['sales'] <= row['demand']+.015, row['sources']
            if all(row[k] is not None for k in ['sales','demand','unmet']):
                assert abs(row['demand']-row['sales']-row['unmet']) <= .015, row['sources']
            row['supply_limited'] = None if row['sales'] is None or row['demand'] is None else row['demand']-row['sales'] > .015
            row['units'] = dict(demand='千单位', sales='千单位', price='美元/单位', inputs='千美元')
            records.append(row)
    return records, cells, dict(**meta, file=path.relative_to(ROOT).as_posix(), sha256=source_hash(path),teams=list(teams))


def load_dataset():
    descriptors = [(ROOT/'raw'/f'{name}_printable.json', dict(market_id=5, phase=phase, round=rnd))
                   for name, phase, rnd in [('initial0','initial',0), ('practice1','practice',1), ('practice2','practice',2)]]
    for path in sorted(RAW.glob('market_*_*.json')):
        doc = read(path)
        if doc.get('kind') != 'actual_result':
            continue
        assert doc.get('selection_verified') is True, path
        meta = {k: doc[k] for k in ['market_id','phase','round']}
        assert doc['selected_market'] == f"市场 {meta['market_id']}"
        selection_path = ROOT / doc['selection_file']
        selection = read(selection_path)['snapshot']
        assert f'option "{doc["selected_market"]}" [selected]' in selection, selection_path
        assert f'option "{doc["selected_round"]}" [selected]' in selection, selection_path
        matching = [i for i, (_, old) in enumerate(descriptors) if old == meta]
        if matching:
            descriptors[matching[0]] = path, meta
        else:
            descriptors.append((path, meta))
    rows, source_cells, sources = [], [], []
    for path, meta in descriptors:
        r, c, s = parse_report(path, meta)
        if path.parent==RAW:
            selected=read(ROOT/read(path)['selection_file'])['snapshot']
            assert any(row['cells']==s['teams'] for row in table_rows(selected)), ('Selection/report teams differ',path)
        rows.extend(r); source_cells.extend(c); sources.append(s)
    keys = [(r['market_id'],r['phase'],r['round'],r['team_column'],r['country']) for r in rows]
    assert len(set(keys)) == len(keys)
    lookup = {k:r for k,r in zip(keys,rows)}
    for r in rows:
        initial = lookup.get((r['market_id'],'initial',0,r['team_column'],r['country']))
        prev_phase = 'initial' if r['round'] == 1 else r['phase']
        previous = lookup.get((r['market_id'],prev_phase,r['round']-1,r['team_column'],r['country']))
        r['initial_price'] = initial['price'] if initial else None
        r['previous_rd'] = previous['rd'] if previous else None
        r['previous_rd_source'] = previous['sources']['rd'] if previous else None
        r['team_history_verified'] = previous is not None and previous['team'] == r['team']
        r['usable_for_fit'] = r['phase'] in ('practice','formal') and r['team_history_verified'] and all(
            r[k] is not None for k in ['price','initial_price','demand','general','designer','rd','previous_rd'])
    return rows, source_cells, sources


def feature_matrix(rows, rd_params):
    x = np.zeros((len(rows),5))
    for i,r in enumerate(rows):
        assert r['price'] > 0 and r['initial_price'] > 0
        assert all(r[k] >= 0 for k in ['general','designer','rd','previous_rd'])
        x[i,COUNTRIES.index(r['country'])] = -np.log(r['price']/r['initial_price'])
        x[i,2:4] = np.log1p(np.array([r['general'],r['designer']])/1000)
        multiplier = curve_value(r['rd']+.5*r['previous_rd'],rd_params,'power')
        assert multiplier > 0
        x[i,4] = np.log(multiplier)
    assert np.all(np.isfinite(x))
    return x


def weights(rows):
    counts = Counter(r['market_id'] for r in rows)
    return np.array([1/(len(counts)*counts[r['market_id']]) for r in rows])


def fit(rows, x, penalty, mode='competitive'):
    ids = [i for i,r in enumerate(rows) if r['demand'] > 0]
    rr = [rows[i] for i in ids]; xx = x[ids]
    assert len(rr) > 5, 'Insufficient positive-demand training samples'
    y = np.log([r['demand'] for r in rr])
    if mode == 'competitive':
        usable = []
        for group in groups(rr).values():
            if len(group) < 2:
                continue
            xx[group] -= xx[group].mean(axis=0)
            y[group] -= y[group].mean()
            usable.extend(group)
        rr = [rr[i] for i in usable]; xx = xx[usable]; y = y[usable]
        assert len(rr) > 5
        lower = np.zeros(5)
        reg = np.eye(5)
    else:
        intercept = np.array([[float(r['country']==c) for c in COUNTRIES] for r in rr])
        xx = np.c_[intercept,xx]
        lower = np.r_[[-np.inf]*2,[0]*5]
        reg = np.diag([0,0,1,1,1,1,1])
    w = np.sqrt(weights(rr))
    result = lsq_linear(np.vstack([xx*w[:,None],np.sqrt(penalty)*reg]),
                       np.r_[y*w,np.zeros(len(lower))],bounds=(lower,np.full(len(lower),np.inf)),tol=1e-12)
    assert result.success
    return result.x


def predict_shares(rows, x, beta):
    out = np.zeros(len(rows))
    for ids in groups(rows).values():
        out[ids] = shares(x[ids],beta)
        assert abs(sum(out[ids])-1) < 1e-12
    return out


def choose_penalty(rows, x, mode):
    # Entire team histories are held out; validation labels never enter training centering.
    scores = {}
    for penalty in PENALTIES:
        market_errors = defaultdict(list)
        for team in sorted({r['team_id'] for r in rows}):
            train = [i for i,r in enumerate(rows) if r['team_id'] != team]
            assert all(rows[i]['team_id'] != team for i in train)
            beta = fit([rows[i] for i in train],x[train],penalty,mode)
            if mode == 'competitive':
                pred = predict_shares(rows,x,beta)
                totals = {k:sum(rows[i]['demand'] for i in ids) for k,ids in groups(rows).items()}
                for i,r in enumerate(rows):
                    total = totals[group_key(r)]
                    if r['team_id'] == team and total > 0:
                        market_errors[r['market_id']].append(abs(pred[i]-r['demand']/total))
            else:
                z = np.c_[np.array([[float(r['country']==c) for c in COUNTRIES] for r in rows]),x]
                pred = np.exp(z@beta)
                for i,r in enumerate(rows):
                    if r['team_id'] == team:
                        market_errors[r['market_id']].append(abs(pred[i]-r['demand']))
        scores[penalty] = float(np.mean([np.mean(v) for v in market_errors.values()]))
    assert all(np.isfinite(v) for v in scores.values())
    chosen = min(scores,key=scores.get)
    return chosen, scores


def metric(actual, predicted):
    a,p = np.asarray(actual),np.asarray(predicted)
    if len(a) == 0:
        return dict(n=0,MAE=None,WAPE=None,bias=None)
    assert np.all(np.isfinite(a)) and np.all(np.isfinite(p))
    return dict(n=len(a),MAE=float(np.mean(abs(a-p))),
                WAPE=float(sum(abs(a-p))/sum(a)) if sum(a)>0 else None,bias=float(np.mean(p-a)))


def evaluate(train, test, history, rd_params, name, excluded_market=None):
    assert not {(r['market_id'],r['phase'],r['round'],r['team_column'],r['country']) for r in train} & {
        (r['market_id'],r['phase'],r['round'],r['team_column'],r['country']) for r in test}
    if excluded_market is not None:
        assert all(r['market_id'] != excluded_market for r in train)
    xtr,xt = feature_matrix(train,rd_params),feature_matrix(test,rd_params)
    fitted = {}
    for mode in ['competitive','own_only']:
        penalty,scores = choose_penalty(train,xtr,mode)
        beta = fit(train,xtr,penalty,mode)
        fitted[mode] = dict(coefficients=beta.tolist(),penalty=penalty,inner_scores=scores)
    share = predict_shares(test,xt,np.array(fitted['competitive']['coefficients']))
    z = np.c_[np.array([[float(r['country']==c) for c in COUNTRIES] for r in test]),xt]
    own = np.exp(z@np.array(fitted['own_only']['coefficients']))
    hist_totals = {k:sum(history[i]['demand'] for i in ids) for k,ids in groups(history).items()
                   if all(history[i]['demand'] is not None for i in ids)}
    limits = {c:{key:(min(r[key] for r in train if r['country']==c),max(r[key] for r in train if r['country']==c))
                 for key in ['price','general','designer','rd']} for c in COUNTRIES}
    records = []
    for key,ids in groups(test).items():
        mid,phase,rnd,country = key
        previous = hist_totals.get((mid,'initial' if rnd==1 else phase,rnd-1,country))
        before = hist_totals.get((mid,'initial' if rnd==2 else phase,rnd-2,country))
        forecast_total = previous*previous/before if previous is not None and before and rnd>=2 else None
        total = sum(test[i]['demand'] for i in ids)
        for i in ids:
            r=test[i]
            records.append(dict(fold=name,market_id=mid,phase=phase,round=rnd,country=country,
                team=r['team'],team_id=r['team_id'],actual=r['demand'],sales=r['sales'],
                actual_share=r['demand']/total if total>0 else None,predicted_share=float(share[i]),
                competitive=float(share[i]*forecast_total) if forecast_total is not None else None,
                equal_share=forecast_total/len(ids) if forecast_total is not None else None,
                own_only=float(own[i]),oracle_total=float(share[i]*total),forecast_total=forecast_total,
                actual_total=total,supply_limited=r['supply_limited'],
                in_training_range=all(lo<=r[k]<=hi for k,(lo,hi) in limits[country].items()),
                source=r['sources']['demand']))
    return dict(name=name,excluded_market=excluded_market,train_markets=sorted({r['market_id'] for r in train}),
                train_rounds=sorted({(r['phase'],r['round']) for r in train}),train_n=len(train),
                models=fitted,records=records,information='已实现当期对手策略；事后条件回溯检验，非事前独立预测')


def summaries(records):
    partitions = {'all':records}
    for key in ['market_id','country','supply_limited','in_training_range']:
        for val in sorted({str(r[key]) for r in records}):
            partitions[f'{key}={val}'] = [r for r in records if str(r[key])==val]
    result = {}
    for label,rr in partitions.items():
        valid_share = [r for r in rr if r['actual_share'] is not None]
        result[label] = {model:metric([r['actual'] for r in rr if r[model] is not None],
                                    [r[model] for r in rr if r[model] is not None])
                         for model in ['competitive','equal_share','own_only','oracle_total']}
        result[label]['share_MAE_pp'] = float(np.mean([abs(r['actual_share']-r['predicted_share'])*100
                                                       for r in valid_share])) if valid_share else None
    market_summaries = [s for k,s in result.items() if k.startswith('market_id=')]
    result['market_equal_mean'] = {
        model: {key:float(np.mean([s[model][key] for s in market_summaries if s[model][key] is not None]))
                if any(s[model][key] is not None for s in market_summaries) else None
                for key in ['MAE','WAPE','bias']}
        for model in ['competitive','equal_share','own_only','oracle_total']}
    return result


def comparability(rows):
    result=[]
    for key,ids in groups(rows).items():
        mid,phase,rnd,country=key
        other=[rows[i] for i in ids]
        reference=[r for r in rows if group_key(r)==(5,phase,rnd,country)]
        if not reference:
            continue
        for field in ['price','demand','sales','general','designer','rd','operations','capacity',
                      'inventory','cash','long_debt','short_debt','bulk_orders','profit']:
            values=[r[field] for r in other]; base=[r[field] for r in reference]
            missing=any(v is None for v in values+base)
            equal=not missing and sorted(values)==sorted(base)
            classification='暂不可比较' if missing else '可直接比较' if equal or field not in ['demand','sales'] else '需明确转化'
            result.append(dict(market_id=mid,phase=phase,round=rnd,country=country,field=field,
                classification=classification,observed_distribution_equal=equal if not missing else None,
                values=values,market5_values=base,
                interpretation='缺失保留，不能补零' if missing else
                    '同口径观测分布一致；不推论隐藏机制相同' if equal else
                    '数量受规模及竞争影响；比较份额和增长' if field in ['demand','sales'] else
                    '同口径数值不同；区分决策、状态与机制参数',
                sources=[r['sources'][field] for r in other],market5_sources=[r['sources'][field] for r in reference]))
        result.append(dict(market_id=mid,phase=phase,round=rnd,country=country,field='team_count',
            classification='可直接比较',observed_distribution_equal=len(other)==len(reference),
            values=[len(other)],market5_values=[len(reference)],interpretation='每个市场使用自己的完整竞争集合',
            sources=[],market5_sources=[]))
    for mid in sorted({r['market_id'] for r in rows}):
        for field in ['同回合跨市场前景参数','跨市场可见研发运营曲线','跨编号市场耦合规则']:
            result.append(dict(market_id=mid,phase='shared',round=None,country='两国',field=field,
                classification='暂不可比较',observed_distribution_equal=None,values=[],market5_values=[],
                interpretation='结果筛选器不提供该证据；共用课程资料不能证明各市场隐藏配置相同',sources=[],market5_sources=[]))
    return result


def rule_evidence():
    result=[]
    patterns=[('同市场小组竞争','一个市场由相互竞争'),('仅小组决策计算实际结果','只根据团队决策计算'),
              ('市场增长受竞争行为影响','市场受到竞争者行为的影响'),('大客户订单分配','同等吸引力'),
              ('行业投入影响总规模','整个行业在市场营销和设计师推广')]
    for name in ['online_manual','20261011_case']:
        path=ROOT/'raw'/f'{name}.json'
        for line_no,line in enumerate(read(path)['snapshot'].splitlines(),1):
            for channel,pattern in patterns:
                if pattern in line:
                    result.append(dict(channel=channel,status='规则直接支持',file=path.relative_to(ROOT).as_posix(),
                        line=line_no,text=line.strip(),sha256=source_hash(path),causal_effect_estimated=False))
    result.append(dict(channel='跨编号市场需求耦合',status='未取得规则证据',file='',line=None,
                       text='课程排名不等于跨市场需求竞争',sha256='',causal_effect_estimated=False))
    return result


def prospective(rows,models,params,freeze_time):
    initial=[r for r in rows if r['phase']=='initial']
    practice1=[r for r in rows if r['phase']=='practice' and r['round']==1]
    initial_map={(r['market_id'],r['team_column'],r['country']):r for r in initial}
    initial_totals={k:sum(initial[i]['demand'] for i in ids) for k,ids in groups(initial).items()}
    prior_totals={k:sum(practice1[i]['demand'] for i in ids) for k,ids in groups(practice1).items()}
    checklist=RAW/'checklist_after.json'
    if not checklist.exists():
        checklist=RAW/'checklist_before.json'
    own={}
    if checklist.exists():
        rr=table_rows(read(checklist)['snapshot'])
        def val(label,occurrence=0):
            matches=[r for r in rr if len(r['cells'])==6 and r['cells'][0]==label]
            assert len(matches)>occurrence
            return numeric(matches[occurrence]['cells'][5])
        own=dict(prices=[val(c+', 美元') for c in COUNTRIES],general=val('泰国',0)+val('印尼',0),
                 designer=val('泰国',1)+val('印尼',1),rd=val('复合梁',1))
    forecasts=[]
    for strategy,base in [('initial0',initial),('practice1',practice1)]:
        scenario=[]
        for r in base:
            start=initial_map[(r['market_id'],r['team_column'],r['country'])]
            candidate=dict(r,phase='formal',round=1,previous_rd=start['rd'],initial_price=start['price'])
            if r['market_id']==5 and r['team']=='营销团队' and own:
                candidate.update(price=own['prices'][COUNTRIES.index(r['country'])],general=own['general'],
                                 designer=own['designer'],rd=own['rd'])
            scenario.append(candidate)
        x=feature_matrix(scenario,params)
        for model in ['A','B']:
            pp=predict_shares(scenario,x,np.array(models[model]['competitive']['coefficients']))
            for i,r in enumerate(scenario):
                key=(r['market_id'],'initial',0,r['country'])
                m0=initial_totals[key]
                m1=prior_totals.get((r['market_id'],'practice',1,r['country']))
                for scale,total in [('flat',m0),('practice1_growth',m1 if m1 is not None else None)]:
                    if total is None:
                        continue
                    forecasts.append(dict(frozen_at=freeze_time,model=model,market_id=r['market_id'],phase='formal',round=1,
                        country=r['country'],team=r['team'],team_id=r['team_id'],competitor_strategy=strategy,
                        scale_scenario=scale,total_assumption=total,predicted_share=float(pp[i]),
                        predicted_demand=float(total*pp[i]),actual=None,kind='model_scenario_prediction',
                        own_decision_source=checklist.relative_to(ROOT).as_posix() if own and r['market_id']==5 and r['team']=='营销团队' else '历史策略情景',
                        state_reset='正式1研发上期、初始价格、行业基数均来自初始0；未继承练习2财务状态'))
    return forecasts


def industry_diagnostics(rows):
    totals={}
    for key,ids in groups(rows).items():
        rr=[rows[i] for i in ids]
        if not all(r['demand'] is not None and r['general'] is not None and r['designer'] is not None for r in rr):
            continue
        totals[key]=dict(total_demand=sum(r['demand'] for r in rr),
            general_proxy=sum(r['general'] for r in rr),designer_proxy=sum(r['designer'] for r in rr),
            mean_price=float(np.mean([r['price'] for r in rr])))
    output=[]
    for key,current in totals.items():
        mid,phase,rnd,country=key
        previous=totals.get((mid,'initial' if rnd==1 else phase,rnd-1,country))
        if previous is None:
            continue
        output.append(dict(market_id=mid,phase=phase,round=rnd,country=country,**current,
            previous_total=previous['total_demand'],growth=current['total_demand']/previous['total_demand']-1
            if previous['total_demand']>0 else None,
            general_change=current['general_proxy']-previous['general_proxy'],
            designer_change=current['designer_proxy']-previous['designer_proxy'],
            limitation='营销合计为跨国代理，不是国别投入；增长同时受价格、历史及环境影响，不能解释为营销因果收益'))
    return output


def archive_index():
    entries=[]
    for path in sorted(RAW.glob('*.json')):
        doc=read(path)
        entries.append(dict(file=path.relative_to(ROOT).as_posix(),sha256=source_hash(path),bytes=path.stat().st_size,
            captured_at=doc.get('captured_at'),source_url=doc.get('source_url'),market_id=doc.get('market_id'),
            phase=doc.get('phase'),round=doc.get('round'),kind=doc.get('kind','context_or_selection'),
            usable_as_actual_demand=doc.get('kind')=='actual_result' and doc.get('selection_verified') is True))
    return entries


def register_archive():
    entries=archive_index()
    indexed={r['file'] for r in entries}
    path=ROOT/'数据分组索引.json'
    existing=read(path)
    merged=[]
    for r in entries:
        merged.append(dict(**r,market=r['market_id'],data_kind=r['kind'],
            usable_for_demand_fit=r['usable_as_actual_demand'] and r['phase']!='initial',
            usage='跨市场历史实际；初始0仅作状态' if r['usable_as_actual_demand'] else
                  '筛选/课程身份/决策混合页证据，不作为实际需求标签'))
    write_json(path,[r for r in existing if r['file'] not in indexed]+merged)
    grouped=[];plain=[]
    for entry in entries:
        doc=read(ROOT/entry['file'])
        if 'snapshot' not in doc:
            continue
        for row in table_rows(doc['snapshot']):
            raw=json.dumps(row['cells'],ensure_ascii=False)
            grouped.append([entry['file'],entry['phase'],entry['round'],entry['kind'],entry['captured_at'],row['line'],row['row_text'],raw])
            plain.append([entry['file'],row['line'],row['row_text'],raw])
    for name,new in [('分组表格行索引.csv',grouped),('全部表格行索引.csv',plain)]:
        with (ROOT/name).open(encoding='utf-8-sig',newline='') as stream:
            old=list(csv.reader(stream))
        with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as stream:
            csv.writer(stream).writerows([r for r in old if r[0] not in indexed]+new)
    coverage=read(ROOT/'归档覆盖与待办.json')
    coverage['files']=[r for r in coverage['files'] if r['file'] not in indexed]+merged
    coverage['cross_market_validation']=dict(updated_at=datetime.now(timezone.utc).isoformat(),
        market_ids=sorted({r['market_id'] for r in entries if r['usable_as_actual_demand']} | {5}),
        report='output/cross_market/report.md',result='output/cross_market/validation.json',
        decisions_modified=False,formal_actual_pending=True)
    write_json(ROOT/'归档覆盖与待办.json',coverage)
    manifest=[]
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and path.name!='SHA256_manifest.json' and '__pycache__' not in path.parts and '.git' not in path.parts:
            manifest.append(dict(file=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=source_hash(path)))
    write_json(ROOT/'SHA256_manifest.json',manifest)


def assess_transfer(folds):
    assessments=[]
    for fold in folds:
        if not fold['name'].startswith('A_'):
            continue
        for label,s in fold['summary'].items():
            if not label.startswith('market_id='):
                continue
            rr=[r for r in fold['records'] if str(r['market_id'])==label.split('=')[1] and r['actual_share'] is not None]
            counts=Counter((r['market_id'],r['phase'],r['round'],r['country']) for r in rr)
            equal_error=float(np.mean([abs(r['actual_share']-1/counts[(r['market_id'],r['phase'],r['round'],r['country'])])*100 for r in rr]))
            share_better=s['share_MAE_pp']<equal_error
            demand_better=s['competitive']['WAPE'] is not None and s['competitive']['WAPE']<s['equal_share']['WAPE']
            raw_better=s['own_only']['WAPE'] is not None and s['own_only']['WAPE']<s['equal_share']['WAPE']
            classification='原始规模预测与份额均优于等份额基线' if share_better and demand_better and raw_better else (
                '份额转化有用，绝对规模层仍需校准' if share_better else '转化后未优于份额基线，暂不支持迁移')
            assessments.append(dict(market_id=int(label.split('=')[1]),fold=fold['name'],classification=classification,
                demand_WAPE=s['competitive']['WAPE'],raw_own_only_WAPE=s['own_only']['WAPE'],
                baseline_WAPE=s['equal_share']['WAPE'],share_MAE_pp=s['share_MAE_pp'],equal_share_MAE_pp=equal_error,
                limitation='单个练习时间切分的经验判断；不证明隐藏机制相同，也不是置信区间'))
    return assessments


def score_frozen_forecasts(rows):
    actual={(r['market_id'],r['phase'],r['round'],r['team_column'],r['country']):r for r in rows if r['phase']=='formal'}
    output=[]
    for path in sorted(OUT.glob('future_predictions_*.json')):
        doc=read(path)
        if not doc['prospective']:
            continue
        by_scenario=defaultdict(list)
        for r in doc['records']:
            column=int(r['team_id'].split(':')[1])
            observed=actual.get((r['market_id'],r['phase'],r['round'],column,r['country']))
            if observed is None or observed['demand'] is None or observed['team']!=r['team']:
                continue
            key=(r['model'],r['competitor_strategy'],r['scale_scenario'],r['market_id'],r['country'])
            by_scenario[key].append((observed['demand'],r['predicted_demand']))
        for key,pairs in by_scenario.items():
            output.append(dict(file=path.name,frozen_at=doc['frozen_at'],model=key[0],competitor_strategy=key[1],
                scale_scenario=key[2],market_id=key[3],country=key[4],**metric(*zip(*pairs)),
                source='正式实际需求；只评分历史冻结档案，不重新拟合或按结果挑选情景'))
    return output


def csv_write(path, records):
    if not records:
        return
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]))
        writer.writeheader()
        for row in records:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        self_test(); print('cross-market self-tests passed'); return
    OUT.mkdir(parents=True,exist_ok=True)
    rows,cells,sources=load_dataset()
    rd_params=read(ROOT/'分步模型拟合与验证.json')['curves']['rd']['parameters']
    usable=[r for r in rows if r['usable_for_fit']]
    complete=[]
    for ids in groups(usable).values():
        group=[usable[i] for i in ids]
        original=[r for r in rows if group_key(r)==group_key(group[0])]
        if len(group)==len(original):
            complete.extend(group)
    market_ids=sorted({r['market_id'] for r in rows})
    folds=[]
    for phase in ['practice','formal']:
        available=sorted({r['round'] for r in complete if r['phase']==phase})
        for target in available[1:]:
            train=[r for r in complete if r['phase']==phase and r['round']<target]
            test=[r for r in complete if r['phase']==phase and r['round']==target]
            if not train or not test:
                continue
            a=[r for r in train if r['market_id']==5]
            folds.append(evaluate(a,test,rows,rd_params,f'A_{phase}_forward_{target}'))
            folds.append(evaluate(train,test,rows,rd_params,f'B_{phase}_forward_{target}'))
            for mid in market_ids:
                tr=[r for r in train if r['market_id']!=mid]
                te=[r for r in test if r['market_id']==mid]
                if tr and te:
                    folds.append(evaluate(tr,te,rows,rd_params,f'B_{phase}_leave_market_{mid}_round_{target}',mid))
    for fold in folds:
        fold['summary']=summaries(fold['records'])
    checks=[]
    for key,ids in groups(rows).items():
        rr=[rows[i] for i in ids]
        total=sum(r['demand'] for r in rr) if all(r['demand'] is not None for r in rr) else None
        checks.append(dict(market_id=key[0],phase=key[1],round=key[2],country=key[3],
                           team_count=len(rr),total_demand=total,
                           demand_sales_unmet_checked=all(r['unmet'] is not None for r in rr),
                           normalized_shares_sum=1 if total and total>0 else None,
                           limitation='份额由需求归一化得到，合计为1是恒等式，不是竞争机制的独立证据'))
    missing=[dict(market_id=mid,status='未采集',reason='登录会话中断或尚未读取') for mid in range(1,11) if mid not in market_ids]
    for mid in market_ids:
        for phase,rnd in [('initial',0),('practice',1),('practice',2)]:
            if not any(r['market_id']==mid and r['phase']==phase and r['round']==rnd for r in rows):
                missing.append(dict(market_id=mid,status='部分采集',reason=f'缺少{phase}回合{rnd}'))
    payload=dict(generated_at=datetime.now(timezone.utc).isoformat(),market_ids=market_ids,
                 rows=rows,source_cells=cells,sources=sources,coverage_gaps=missing,
                 folds=folds,quantity_checks=checks,comparability=comparability(rows),rule_evidence=rule_evidence(),
                 industry_diagnostics=industry_diagnostics(rows),transfer_assessments=assess_transfer(folds),
                 frozen_formal_scores=score_frozen_forecasts(rows),
                 exclusions=[r['sources']['demand'] for r in rows if r['phase']!='initial' and not r['usable_for_fit']],
                 limitations=['当期对手策略来自事后结果','零需求保留评价，但从对数训练中排除',
                              '只有两个练习回合，跨回合差异不能识别因果效应',
                              '曲线使用市场5可见曲线；其他市场隐藏机制未证实一致',
                              '累计营销存量未识别；研发延续0.5为假设'])
    csv_write(OUT/'source_cells.csv',cells)
    csv_write(OUT/'quantity_checks.csv',checks)
    roster={(r['market_id'],r['team_column']):dict(market_id=r['market_id'],team_column=r['team_column'],
        team_id=r['team_id'],team=r['team']) for r in rows}
    csv_write(OUT/'team_roster.csv',list(roster.values()))
    csv_write(OUT/'comparability.csv',payload['comparability'])
    csv_write(OUT/'competition_evidence.csv',payload['rule_evidence'])
    csv_write(OUT/'industry_diagnostics.csv',payload['industry_diagnostics'])
    csv_write(OUT/'transfer_assessments.csv',payload['transfer_assessments'])
    write_json(OUT/'frozen_formal_scores.json',payload['frozen_formal_scores'])
    write_json(OUT/'archive_index.json',archive_index())
    csv_write(OUT/'predictions.csv',[r for f in folds for r in f['records']])
    payload['frozen_artifacts']=freeze_models(complete,rows,rd_params,sources,market_ids)
    write_json(OUT/'validation.json',payload)
    report(payload)
    register_archive()
    print(json.dumps(dict(markets=market_ids,rows=len(rows),folds=len(folds),gaps=len(missing)),ensure_ascii=False))


def freeze_models(rows,history,params,sources,market_ids):
    models={}
    for label,train in [('A',[r for r in rows if r['market_id']==5 and r['phase']=='practice']),
                        ('B',[r for r in rows if r['phase']=='practice'])]:
        x=feature_matrix(train,params)
        models[label]={}
        for mode in ['competitive','own_only']:
            penalty,scores=choose_penalty(train,x,mode)
            models[label][mode]=dict(coefficients=fit(train,x,penalty,mode).tolist(),penalty=penalty,
                inner_scores=scores,train_markets=sorted({r['market_id'] for r in train}),train_n=len(train),
                zero_demand_excluded_from_log_fit=sum(r['demand']==0 for r in train),
                training_keys=[[r['market_id'],r['phase'],r['round'],r['team_column'],r['country']] for r in train])
    frozen_at=datetime.now(timezone.utc).isoformat()
    frozen=dict(frozen_at=datetime.now(timezone.utc).isoformat(),models=models,
                rd_curve_parameters=params,feature_names=NAMES,source_hashes=sources,
                curve_model_source='分步模型拟合与验证.json',curve_model_sha256=source_hash(ROOT/'分步模型拟合与验证.json'),
                implementation_sha256=source_hash(Path(__file__)),
                weighting='各编号市场总权重相同且全部权重和为1；每项权重=1/(市场数×该市场样本数)',
                status='独立A/B候选；B训练市场以training_keys为准' if len(market_ids)>1 else '仅市场5；B与A重合，尚非跨市场训练',
                future_prediction_status='正式1条件情景；未知竞争策略及规模，非保证区间',
                formula='u=-e*ln(P/P_initial)+bg*ln(1+Gtotal/1000)+bd*ln(1+Mtotal/1000)+br*ln(f_rd(R+0.5*Rprev)); D=M*softmax(u)')
    # Freeze versions are immutable; reruns produce a new version rather than overwrite evidence.
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    write_json(OUT/f'parameters_{stamp}.json',frozen)
    write_json(OUT/'parameters_latest.json',frozen)
    predictions=prospective(history,models,params,frozen_at)
    future=dict(frozen_at=frozen_at,parameter_file=f'parameters_{stamp}.json',
                prospective=datetime.fromisoformat(frozen_at)<datetime(2026,10,11,14,tzinfo=timezone.utc),
                target_deadline_beijing='2026-10-11 22:00',records=predictions,
                assumptions='对手取初始0/练习1策略；规模取初始0不变/练习1增长；本队取当前个人策略',
                limitation='不是小组最终提交策略；不使用正式结果或练习2财务状态')
    write_json(OUT/f'future_predictions_{stamp}.json',future)
    csv_write(OUT/'future_predictions_latest.csv',predictions)
    return dict(parameters=f'parameters_{stamp}.json',future_predictions=f'future_predictions_{stamp}.json')


def report(payload):
    local_time=datetime.fromisoformat(payload['generated_at']).astimezone(timezone(timedelta(hours=8)))
    lines=['# 跨市场与小组竞争验证','',f"更新（北京时间）：{local_time.strftime('%Y-%m-%d %H:%M:%S')}",'',
           f"已归档市场：{payload['market_ids']}；实际国别记录：{len(payload['rows'])}。",'',
           '同一编号市场的小组相互竞争有在线指南直接支持；跨编号市场是否存在其他耦合未取得规则证据。',
           '当前分析假设（2026-10-11，用户指定）：编号市场之间不存在直接作用，各市场独立确定竞争集合、行业规模和订单分配；同市场内的小组竞争保留。B共用系数是统计估计，不表示跨市场传导。共同环境可能造成相关性；本假设尚未被证明，取得相反证据时修订。',
           '案例同时说明行业营销与设计师推广可扩大行业规模；大客户按价格、质量与销售努力评标。',
           '规则来源：raw/online_manual.json；raw/20261011_case.json。','',
           '编号市场与团队对应见team_roster.csv；同名团队通过市场编号与报告列区分。','',
           '## 已观察的数据差异','',
           '| 阶段/回合 | 国家 | 各市场实际需求总量范围，千单位 |','| --- | --- | ---: |']
    for phase,rnd in [('initial',0),('practice',1),('practice',2)]:
        for country in COUNTRIES:
            values=[r['total_demand'] for r in payload['quantity_checks'] if r['phase']==phase and r['round']==rnd and r['country']==country and r['total_demand'] is not None]
            if values:
                lines.append(f'| {phase}/{rnd} | {country} | {min(values):.2f}–{max(values):.2f} |')
    comparable_initial=[r for r in payload['comparability'] if r['phase']=='initial' and r['field'] in
                        ['price','general','designer','rd','operations','capacity','cash','long_debt','short_debt','inventory']]
    same=all(r['observed_distribution_equal'] is True for r in comparable_initial)
    lines += ['', '已归档市场的上述初始决策与状态分布一致。' if same else '初始状态存在差异或缺口，详见逐字段表。',
              '初始一致但后续总量不同，需控制竞争策略及投入历史；仍不能归因于隐藏机制差异。','',
           '## 回溯结果','',
           '| 验证 | 需求WAPE | 等份额WAPE | 自身策略WAPE | 份额MAE，百分点 |',
           '| --- | ---: | ---: | ---: | ---: |']
    def fmt(x):
        return '未定义' if x is None else f'{x:.3f}'
    for f in payload['folds']:
        s=f['summary']['all']
        lines.append(f"| {f['name']} | {fmt(s['competitive']['WAPE'])} | {fmt(s['equal_share']['WAPE'])} | {fmt(s['own_only']['WAPE'])} | {fmt(s['share_MAE_pp'])} |")
    a=next((f for f in payload['folds'] if f['name']=='A_practice_forward_2'),None)
    b=next((f for f in payload['folds'] if f['name']=='B_practice_forward_2'),None)
    if a and b:
        lines += ['', '**市场5的同一验证回合：**','',
                  '| 模型 | 需求WAPE | 份额MAE，百分点 |','| --- | ---: | ---: |']
        for name,fold in [('A 市场5训练',a),('B 共同训练',b)]:
            s=fold['summary']['market_id=5']
            lines.append(f"| {name} | {s['competitive']['WAPE']:.2%} | {s['share_MAE_pp']:.3f} |")
        lines += ['', '此处B包含市场5较早回合，检验增加其他市场训练数据是否改善市场5未来回合预测。',
                  'B整市场留出市场5的结果另见上表，检验完全不使用市场5训练能否迁入。']
    lines += ['', 'WAPE以比例表示，0.10即10%。以上均给定已实现当期对手策略；真实总量仅用于oracle诊断。',
              '逐市场、国别、缺货和训练范围分层结果见validation.json；原始定位见source_cells.csv。','',
              '## 可比性与数据转化','',
              '逐字段差异及来源见comparability.csv；团队集合分别归一化，需求不直接乘跨市场固定比例。',
              '以实际需求归一化诊断份额；事前规模使用已知历史，实际验证期总量不进入事前预测。',
              '市场5冻结迁移的分市场判断见transfer_assessments.csv，判据为与同信息基线比较，非官方误差阈值。',
              '前景参数及跨市场曲线未独立取得，因此B是共同机制假设下的候选，不是已证明通用模型。','',
              '## 参数与未来验证','',
              'A仅市场5训练；B按市场等权共同训练。独立时间戳参数档案保留全部训练键和源哈希。',
              '回溯评分只用练习1拟合；以下正式1冻结候选用已结束练习1和2重训，两者参数不能混用。',
              f"最终参数：[冻结档案]({payload['frozen_artifacts']['parameters']})；正式1预测：[冻结情景]({payload['frozen_artifacts']['future_predictions']})。",
              '正式1条件情景见future_predictions_*.json；两个对手策略×两个规模假设分别保存。',
              '营销团队使用采集时个人策略，其他团队为历史策略情景；个人保存不等于小组最终提交。',
              '正式1从初始0开始。正式结果公布后须评价这份冻结档案，不能用重训结果替代其分数。','',
              '## 缺口与结论边界','']
    lines += [f"- 市场{g['market_id']}：{g['reason']}。" for g in payload['coverage_gaps']]
    lines += [f'- {s}。' for s in payload['limitations']]
    parameters=read(OUT/'parameters_latest.json')
    lines += ['', '## 冻结竞争参数','', '| 参数 | A | B |', '| --- | ---: | ---: |']
    for i,name in enumerate(NAMES):
        lines.append(f"| {name} | {parameters['models']['A']['competitive']['coefficients'][i]:.6f} | {parameters['models']['B']['competitive']['coefficients'][i]:.6f} |")
    checklist_before=RAW/'checklist_before.json';checklist_after=RAW/'checklist_after.json'
    if checklist_before.exists() and checklist_after.exists():
        before=[r['cells'] for r in table_rows(read(checklist_before)['snapshot'])]
        after=[r['cells'] for r in table_rows(read(checklist_after)['snapshot'])]
        tooltip=['进入决策区域制定决策或浏览。登录时，你自己的决策区域为默认区域。']
        matched=[r for r in before if r!=tooltip]==[r for r in after if r!=tooltip]
        write_json(OUT/'decision_state_check.json',dict(before=checklist_before.relative_to(ROOT).as_posix(),
            after=checklist_after.relative_to(ROOT).as_posix(),raw_table_cells_equal=before==after,
            decision_and_budget_cells_equal=matched,ignored_instruction_row=tooltip,
            decision_write_actions=0,interpretation='排除已知说明提示行后，采集前后全部决策及预算单元格一致' if matched else
            '期间状态有变化；本流程无写入动作，需排查用户或小组同期操作，不自动恢复'))
        lines += ['', '排除说明提示行显示差异后，采集前后全部决策及预算单元格一致。' if matched else '采集前后决策状态存在变化，详见decision_state_check.json；未自动恢复。']
    lines += ['', '尚不以误差阈值或不显著差异宣称隐藏机制一致；转化按目标规模及独立竞争集合进行。',
              '本脚本仅读取归档，不操作网页，不修改比赛决策。']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def self_test():
    assert metric([0,0],[0,1])['WAPE'] is None
    assert metric([2,4],[3,3])['MAE']==1
    assert numeric('1 234.50')==1234.5 and numeric('') is None
    rr=[dict(market_id=m,phase='practice',round=1,country='泰国') for m in [1,1,2,2,2]]
    xx=np.array([[0],[1],[9],[10],[11]],dtype=float)
    pp=predict_shares(rr,xx,np.array([1.]))
    assert np.isclose(sum(pp[:2]),1) and np.isclose(sum(pp[2:]),1)
    assert np.isclose(sum(weights(rr)[:2]),sum(weights(rr)[2:]))
    params=[.1,.2,.5,.2]
    train=[]
    rng=np.random.default_rng(7)
    for m in [1,2]:
        for c in COUNTRIES:
            for i in range(8):
                train.append(dict(market_id=m,phase='practice',round=1,country=c,
                    price=float(rng.uniform(1800,2600)),initial_price=1800 if c=='泰国' else 2000,
                    general=float(rng.uniform(100,900)),designer=float(rng.uniform(100,900)),
                    rd=float(rng.uniform(200,1000)),previous_rd=600,team_id=f'{m}:{i}'))
    x=feature_matrix(train,params); beta=np.array([2,1,.3,.2,.4])
    p=predict_shares(train,x,beta)
    for i,r in enumerate(train):
        r['demand']=p[i]*100
    recovered=fit(train,x,1e-9)
    assert np.allclose(beta,recovered,atol=1e-4), recovered
    shifted=[dict(r,market_id=r['market_id']+20) for r in train]
    assert np.allclose(p,predict_shares(shifted,x,beta))
    changed=x.copy(); changed[0,0]-=1
    assert predict_shares(train,changed,beta)[0]<p[0]
    assert np.allclose(predict_shares(train,changed,beta)[8:16],p[8:16])
    zero_train=[dict(r,demand=0 if i==0 else r['demand']) for i,r in enumerate(train)]
    assert np.all(np.isfinite(fit(zero_train,x,.01)))
    repeated=[dict(r,market_id=7,team_id='7:'+r['team_id'].split(':')[1]) for r in train if r['market_id']==1]
    repeated_x=x[:16]
    beta_single=fit(train[:16],x[:16],.01)
    beta_double=fit(train[:16]+repeated,np.r_[x[:16],repeated_x],.01)
    # Duplicating a market must not change the loss/regularizer ratio.
    assert np.allclose(beta_single,beta_double,atol=1e-8)
    bad=dict(train[0],price=0)
    try:
        feature_matrix([bad],params)
    except AssertionError:
        pass
    else:
        raise AssertionError('Invalid price accepted')


if __name__=='__main__':
    main()
