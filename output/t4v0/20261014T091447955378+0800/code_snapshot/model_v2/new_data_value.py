"""Offline new-data audit, paired ablations and gated research refits.

python code/model_v2/new_data_value.py --stage audit --audit <fixed audit directory>
python code/model_v2/new_data_value.py --stage ablation --audit <fixed audit directory>
python code/model_v2/new_data_value.py --stage train --audit <directory> --evidence <ablation run>
"""
import argparse
import csv
import hashlib
import html
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import table_rows

TZ = timezone(timedelta(hours=8))
SEED = 20261013
PENALTIES = [1e-6, 1e-5, 1e-4, 3e-4, .001, .003, .01, .03, .1, .3, 1]
OLD_DATA = ROOT / 'output/formal_update/20261011T225637591747+0800_training/dataset.json'
FROZEN = ROOT / '分步模型拟合与验证.json'
HISTORICAL_DIFF = ROOT / 'output/new_data_models/20261013T121104/对比核验.json'
OLD_STRUCTURED = ROOT / '结构化模型输入.json'
FIELDS = {
    '生产规模, 千单位': ('q', '千单位'), '生产能力, 千单位': ('capacity', '千单位'),
    '生产效率, 千单位/人': ('eta', '千单位/人'), '生产线人工数量': ('workers', '人'),
    '换班班数': ('shifts', '班'), '工资分摊, 千 美元': ('wage', '千美元'),
    '每人平均工资, 千 美元': ('average_wage', '千美元/人'),
    '生产人员数量, 上回合': ('previous_workers', '人'), '生产人员数量, 本回合': ('current_workers', '人'),
    '辞职': ('quits', '人'), '招聘 + / 裁员 -': ('hires_fires', '人'), '裁员, %': ('layoff_percent', '%'),
    '运营改进': ('operations', '千美元'), '运营改进, 千 美元': ('operations', '千美元'),
    '生产工资合计, 千 美元': ('hr_wage', '千美元'), '解雇成本': ('severance', '千美元'),
    '本回合利润': ('profit', '千美元'), '期末库存, 千单位': ('inventory', '千单位'),
    '短期贷款': ('short_debt', '千美元'), '大客户订单, 千单位': ('bulk_orders', '千单位'),
}
RESOURCE_HEADINGS = {
    '二氧化碳排放, 公吨': ('co2', '公吨'), '能源消耗, MWh': ('energy', 'MWh'),
    '用水量, m3': ('water', 'm³'), '二氧化碳排放, kg': ('co2_intensity', 'kg/单位'),
    '能源消耗, kWh': ('energy_intensity', 'kWh/单位'), '用水量, l': ('water_intensity', '升/单位'),
}
NEW_LABELS = {'previous_workers', 'quits', 'hires_fires', 'layoff_percent', 'average_wage'}
OLD_FIELDS = {'q','capacity','eta','workers','shifts','wage','operations','severance','profit','inventory','short_debt','bulk_orders'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def norm(text):
    return re.sub(r'[\s?，,]', '', text)


def team_id(market, name):
    return f'M{market:02d}-' + hashlib.sha256(norm(name).encode()).hexdigest()[:16]


def numeric(value):
    text = re.sub(r'\s', '', str(value)).replace(',', '').replace('%', '')
    try:
        val = float(text)
    except (ValueError, TypeError):
        return None, None
    if not math.isfinite(val):
        return None, None
    decimals = len(text.split('.')[1]) if '.' in text else 0
    return val, .5 * 10 ** -decimals


def interval(value, half):
    return [value-half, value+half]


def compatible(a, ah, b, bh):
    return abs(a-b) <= ah+bh+1e-10


def previous_key(key):
    m, phase, round_, team, country, product = key
    if round_ == 1:
        return m, 'initial', 0, team, country, product
    return m, phase, round_-1, team, country, product


def intersect(bounds):
    if not bounds:
        return None
    low, high = max(b[0] for b in bounds), min(b[1] for b in bounds)
    return [low, high] if low <= high else None


def key_string(key):
    return '|'.join(map(str, key))


def csv_write(path, rows):
    if not rows:
        rows = [{'status': 'NO_ELIGIBLE_ROWS'}]
    keys = sorted({k for row in rows for k in row})
    with Path(path).open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list)) else v
                         for k,v in row.items()} for row in rows)


def input_bundle(audit):
    audit = Path(audit).resolve()
    required = ['validation.json','rows.json','charts.json','sources.json','printable_references.json']
    if not all((audit/name).is_file() for name in required):
        raise ValueError('归档核验目录未完整生成')
    files = {str(audit/name): sha(audit/name) for name in required}
    refs = read(audit/'printable_references.json')
    files.update({str(ROOT/ref['source']): sha(ROOT/ref['source']) for ref in refs})
    for path in [OLD_DATA, OLD_STRUCTURED, FROZEN, HISTORICAL_DIFF, Path(__file__), ROOT/'code/archive_and_report.py']:
        files[str(path.resolve())] = sha(path)
    base = audit.parent.parent
    sources = read(audit/'sources.json')
    bad_sources = []
    for source in sources:
        path = (base/source['source']).resolve()
        if not path.is_relative_to(base.resolve()):
            raise ValueError('来源路径越界')
        if not path.is_file() or sha(path) != source['sha256']:
            bad_sources.append(source['source'])
        else:
            files[str(path)] = source['sha256']
    if bad_sources:
        raise ValueError('来源哈希不一致：' + ', '.join(bad_sources[:5]))
    return dict(audit=str(audit), files=files, validation=read(audit/'validation.json'), refs=refs,
                sources=sources, frozen_at=datetime.now(TZ).isoformat())


def assert_unchanged(bundle):
    changed = [str(Path(p).name) for p,h in bundle['files'].items() if not Path(p).is_file() or sha(p)!=h]
    if changed:
        raise ValueError('冻结来源运行中变化：'+', '.join(changed[:5]))


def parameter_ledger(bundle):
    paths = {('practice',1): 'raw/20261011_practice1_outlook.json',
             ('practice',2): 'raw/20261011_practice2_outlook.json',
             ('formal',1): 'raw/20261011_model_v2_round1_outlook.json',
             ('formal',2): 'output/formal_update/20261011T223000+0800_sources/formal2_outlook.json'}
    labels = {'泰国':'base_wage','两班倒':'second_shift','三班倒':'third_shift',
              '年人员离职率（without costs），%':'attrition','裁员成本，占薪资%':'severance_ratio'}
    ledger = {}
    for scope, relative in paths.items():
        path = ROOT/relative
        if not path.is_file():
            continue
        data = {}
        for row in table_rows(read(path).get('snapshot','')):
            if len(row['cells'])>=2 and row['cells'][0] in labels:
                val,_ = numeric(row['cells'][1])
                if val is not None:
                    name = labels[row['cells'][0]]
                    if name not in data:
                        data[name] = val/100 if name in ('attrition','severance_ratio') else val
        if len(data)==len(labels):
            ledger[scope] = dict(values=data, source=relative, source_market=5,
                                 sharing='用户同期共享假设；非已证平台跨市场规则')
            bundle['files'][str(path)] = sha(path)
    return ledger


def extract(bundle):
    audit = Path(bundle['audit'])
    rows = read(audit/'rows.json')
    training_fields={k for row in read(OLD_DATA)['rows'] for k in row}
    structured_fields={k for row in read(OLD_STRUCTURED)['history'] for k in row['fields']}
    old_names={'q':'production','eta':'efficiency','capacity':'capacity','workers':'workers','wage':'wage',
               'operations':'operations','profit':'profit','inventory':'inventory','short_debt':'short_debt'}
    old_labels = {}
    for ref in bundle['refs']:
        old_labels[tuple(ref['key'])] = {norm(r['cells'][0]) for r in
            table_rows(read(ROOT/ref['source']).get('snapshot','')) if r['cells']}
    samples, evidence, exclusions, conflicts = {}, [], [], []
    grouped = defaultdict(list)
    source_countries=defaultdict(set)
    for row in rows:
        grouped[(row['source'],row['table_index'])].append(row)
        if row['cells'] and len(row['cells'])<=2:
            label_=row['cells'][0]
            for country_ in ('泰国','印尼'):
                if label_==country_ or label_.startswith(country_+',') or ' - '+country_+',' in label_:
                    source_countries[row['source']].add(country_)
    for group in grouped.values():
        heading, product, country = '', None, None
        transport_basis=''
        table_products = {p for row_ in group for p in ('复合梁','连接件')
                          if row_['cells'] and p in row_['cells'][0]}
        if len(table_products)==1:
            product=next(iter(table_products))
        for row in sorted(group,key=lambda r:r['row_index']):
            cells = row['cells']
            if not cells:
                continue
            label = cells[0].strip()
            if len(cells)<=2:
                heading = label
                if 'kg CO2' in label or '平均每单位销售' in label:
                    transport_basis=label
                if label in ('泰国','印尼') or label.startswith(('泰国,','印尼,')):
                    country = label.split(',')[0]
                if '复合梁' in label:
                    product = '复合梁'
                elif '连接件' in label:
                    product = '连接件'
            panel = row['panel']
            field = FIELDS.get(label) if panel in ('productiondetails','productionhr','incomestatement','balancesheet','logisticsdetails') else None
            if panel=='productionenvironmental' and label in ('复合梁','连接件'):
                field = RESOURCE_HEADINGS.get(heading)
                product = label
            if panel in ('logisticsdetails','logisticsemissions') and label in ('运往 泰国','运往 印尼'):
                route = 'TH' if label.endswith('泰国') else 'ID'
                if panel=='logisticsdetails':
                    field = ('route_'+route, '千单位')
                elif '平均每单位' in transport_basis:
                    field = ('route_intensity_'+route, 'g/单位')
                elif 'kg CO2' in transport_basis:
                    field = ('route_co2_'+route, 'kg')
            if not field:
                continue
            name, unit = field
            if row['identity_status']!='verified' or row['phase'] not in ('initial','practice','formal'):
                exclusions.append(dict(source=row['source'],field=name,reason='身份或阶段未通过'))
                continue
            if row['kind'] in ('platform_budget','decision_input','player_forecast'):
                exclusions.append(dict(source=row['source'],field=name,reason='非实际数据类别'))
                continue
            if row['phase']=='formal' and row['round']>=3:
                exclusions.append(dict(source=row['source'],field=name,reason='当前决策或预算不能当实际标签'))
                continue
            headers = row['team_order']
            if len(cells)!=len(headers)+1 or len(headers)!=10 or len({team_id(row['market'],h) for h in headers})!=10:
                exclusions.append(dict(source=row['source'],field=name,reason='团队表头缺失或列宽不匹配'))
                continue
            if not product:
                products = set(x for x in row['product_context'] if x in ('复合梁','连接件'))
                product = next(iter(products)) if len(products)==1 else None
            # Company HR/expenses are not silently allocated to individual products.
            if panel in ('productionhr','incomestatement','balancesheet'):
                product = '公司'
            if panel in ('incomestatement','balancesheet'):
                country='公司'
            elif country is None:
                candidates=source_countries[row['source']]
                country=next(iter(candidates)) if len(candidates)==1 else None
            if country is None:
                exclusions.append(dict(source=row['source'],field=name,reason='国家/工厂上下文缺失或歧义'))
                continue
            if not product:
                exclusions.append(dict(source=row['source'],field=name,reason='产品上下文缺失'))
                continue
            for column, (header,text) in enumerate(zip(headers,cells[1:]),1):
                value, half = numeric(text)
                team = team_id(row['market'],header)
                key = row['market'],row['phase'],row['round'],team,country,product
                ref = dict(source=row['source'],sha256=row['sha256'],table=row['table_index'],row=row['row_index'],
                           column=column,unit=unit,display_half_unit=half,rounding='nearest-display interval assumption; mode unverified')
                relation = '真正新增' if name in NEW_LABELS or name.startswith(('co2','energy','water','route_co2','route_intensity')) else '旧有未入模或语义对应'
                if name in ('previous_workers','current_workers'):
                    relation = '新增直接历史字段；旧人数路径可派生' if name=='previous_workers' else '旧生产人数语义对应'
                if name=='average_wage':
                    relation = '新增直接监督；待检验工资/人数派生性'
                paired = old_labels.get((row['market'],row['phase'],row['round']))
                purpose = '新增真实监督标签' if name in NEW_LABELS else '历史精度校准或公式核验'
                evidence.append(dict(sample_id=key_string(key),market=row['market'],phase=row['phase'],round=row['round'],
                    team_id=team,country=country,product=product,technical_condition='UNKNOWN_VERSION',field=name,
                    label=label,section_heading=heading,unit=unit,value=value,display_half_unit=half,
                    source=row['source'],sha256=row['sha256'],table=row['table_index'],row=row['row_index'],column=column,
                    category='actual_result',relation=relation,old_paired_label=norm(label) in paired if paired is not None else None,
                    old_training_field=name in training_fields or old_names.get(name) in training_fields,
                    old_structured_field=old_names.get(name,name) in structured_fields,
                    available_after_round=row['round'],allowed_feature_round=row['round']+1,purpose=purpose,
                    status='missing' if value is None else 'observed'))
                if value is None:
                    continue
                sample = samples.setdefault(key,dict(key=list(key),market=key[0],phase=key[1],round=key[2],team_id=key[3],
                    country=country,product=product,values={},refs={},calibrated={},scope='historical conditional replay'))
                if name in sample['values']:
                    old = sample['values'][name]
                    if not compatible(old,sample['refs'][name]['display_half_unit'],value,half):
                        conflicts.append(dict(sample_id=key_string(key),field=name,reason='重复来源观测区间冲突'))
                        sample.setdefault('invalid_fields',[]).append(name)
                    continue
                sample['values'][name], sample['refs'][name] = value, ref
    # Bind company observations only if a single production product is actually observed.
    products = defaultdict(set)
    for key,s in samples.items():
        if 'q' in s['values']:
            products[key[:4]].add(key[5])
    for key,s in samples.items():
        if s['product']=='公司':
            continue
        if len(products[key[:4]])==1:
            for country_ in ('泰国','公司'):
                company = samples.get((*key[:4],country_,'公司'))
                if company:
                    for field,val in company['values'].items():
                        if field not in s['values']:
                            s['values'][field],s['refs'][field] = val,company['refs'][field]
                    s.setdefault('invalid_fields',[]).extend(company.get('invalid_fields',[]))
        else:
            s['company_binding_reason']='多产品/总量不可直接分摊'
    for key,s in samples.items():
        prev = samples.get(previous_key(key))
        s['previous_sample_id'] = key_string(previous_key(key)) if prev else None
        if prev and 'operations' in prev['values']:
            s['values']['previous_operations']=prev['values']['operations']
        if prev and 'workers' in prev['values']:
            s['values']['previous_workers_old']=prev['values']['workers']
            s['refs']['previous_workers_old']=prev['refs']['workers']
        if s['round']==1 and 'previous_operations' not in s['values'] and s['phase']=='formal':
            # Formal restart has no inherited practice operations.
            s['values']['previous_operations']=0.0
    for chart in read(audit/'charts.json'):
        if chart['identity_status']!='verified' or chart['panel']!='productionhr':
            continue
        data = chart['chart'].get('data',{})
        if not isinstance(data,dict):
            continue
        categories = data.get('categories',[{}])[0].get('category',[])
        for series in data.get('dataset',[]):
            team = team_id(chart['market'],series.get('seriesname',''))
            for cat,point in zip(categories,series.get('data',[])):
                round_,_ = numeric(cat.get('label'))
                value,_ = numeric(point.get('value'))
                if round_ is None or value is None or int(round_)!=chart['round']:
                    continue
                phase = chart['phase']
                for key,s in samples.items():
                    if key[:4]!=(chart['market'],phase,int(round_),team) or 'workers' not in s['values']:
                        continue
                    if compatible(value,0,s['values']['workers'],s['refs']['workers']['display_half_unit']):
                        s['exact_workers'] = value
                        s['exact_workers_source']=dict(source=chart['source'],sha256=chart['sha256'],chart_id=chart['chart']['id'])
                    else:
                        conflicts.append(dict(sample_id=key_string(key),field='workers',reason='JSON与表格人数冲突'))
                        s.setdefault('invalid_fields',[]).append('workers')
    physical = [s for s in samples.values() if s['product']!='公司']
    return physical,evidence,exclusions,conflicts


def audit_stats(samples):
    fields = defaultdict(list)
    for s in samples:
        for name,value in s['values'].items():
            if name!='previous_operations':
                fields[name].append((s,value))
    result = {}
    for name,items in sorted(fields.items()):
        groups = defaultdict(list)
        for s,v in items:
            groups[(s['market'],s['phase'],s['round'],s['country'],s['product'])].append((v,s['refs'][name]['display_half_unit']))
        varying = sum(max(v-h for v,h in values)>min(v+h for v,h in values) for values in groups.values())
        result[name]=dict(cells=len(items),nonzero=sum(v!=0 for _,v in items),markets=len({s['market'] for s,_ in items}),
            min=min(v for _,v in items),max=max(v for _,v in items),groups=len(groups),varying_groups=varying,
            interpretation='同表/派生指标非独立样本；精度区间依赖未核实显示舍入')
    checks=[]
    for s in samples:
        v,r=s['values'],s['refs']
        k=key_string(s['key'])
        if all(f in v for f in ('previous_workers','quits','hires_fires','current_workers')):
            fields_=('previous_workers','quits','hires_fires','current_workers')
            residual=v[fields_[0]]+v[fields_[1]]+v[fields_[2]]-v[fields_[3]]
            tolerance=sum(r[f]['display_half_unit'] for f in fields_)
            checks.append(dict(sample_id=k,check='人员流动恒等式',residual=residual,tolerance=tolerance,pass_=abs(residual)<=tolerance+1e-10))
            residual=.1*v['previous_workers']+v['quits']
            tolerance=.1*r['previous_workers']['display_half_unit']+r['quits']['display_half_unit']
            checks.append(dict(sample_id=k,check='10%离职规则',residual=residual,tolerance=tolerance,pass_=abs(residual)<=tolerance+1e-10))
        if all(f in v for f in ('average_wage','hr_wage','current_workers')):
            n,nh=v['current_workers'],r['current_workers']['display_half_unit']
            w,wh=v['average_wage'],r['average_wage']['display_half_unit']
            low,high=(n-nh)*(w-wh),(n+nh)*(w+wh)
            actual,half=v['hr_wage'],r['hr_wage']['display_half_unit']
            checks.append(dict(sample_id=k,check='人均工资派生性',residual=n*w-actual,
                tolerance=max(n*w-low,high-n*w)+half,pass_=low<=actual+half and high>=actual-half))
    return result,checks


def information_verdicts(stats,checks):
    average=[c for c in checks if c['check']=='人均工资派生性']
    result=[]
    for name,s in stats.items():
        if name=='average_wage' and average and all(c['pass_'] for c in average):
            purpose='只能进行恒等式、合计或来源核验'; decision='派生值，未解锁独立预测变量'
        elif name in ('quits','hires_fires','layoff_percent','previous_workers'):
            purpose='新增真实监督标签；上期值可作为下一期候选特征'; decision='人员事件提供监督，跨期预测增量待留出实验'
        elif name.startswith(('co2','energy','water')):
            purpose='可校准历史观测精度' if s['varying_groups']==0 or name in ('co2','energy','water') else '数据不足，暂不能判断'
            decision='环境通道可能相关，不作为独立需求驱动'
        elif name.startswith(('route_co2','route_intensity')):
            purpose='只能进行恒等式、合计或来源核验'; decision='路线数量与单位系数的变换，不重复入模'
        elif name in OLD_FIELDS or name in ('current_workers','hr_wage','previous_workers_old'):
            purpose='旧有输入或监督标签'; decision='非真正新增；用于同集合基线'
        else:
            purpose='数据不足，暂不能判断'; decision='保留来源与缺口'
        result.append(dict(field=name,purpose=purpose,decision=decision,**s))
    return result


def calibration(s, coefficients=None, channels=('co2','energy')):
    v,r=s['values'],s['refs']
    if not all(f in v for f in ('q','workers')) or v['workers']<=0:
        return dict(status='MISSING_POSITIVE_OUTPUT_OR_WORKERS')
    bounds=[interval(v['q'],r['q']['display_half_unit'])]
    used=[]
    for name in channels:
        intensity=name+'_intensity'
        if name not in v or intensity not in v:
            continue
        k=(coefficients or {}).get(name)
        if k is None:
            continue
        half=r[intensity]['display_half_unit']
        if k<=half:
            continue
        totalhalf=r[name]['display_half_unit']
        bounds.append([(v[name]-totalhalf)/(k+half),(v[name]+totalhalf)/(k-half)])
        used.append(name)
    qbound=intersect(bounds)
    n=s.get('exact_workers',v['workers'])
    nh=0 if 'exact_workers' in s else r['workers']['display_half_unit']
    if qbound is None or n<=nh:
        return dict(status='CONFLICTING_OBSERVATIONS',channels=used)
    ebound=[qbound[0]/(n+nh),qbound[1]/(n-nh)]
    if 'eta' in v and intersect([ebound,interval(v['eta'],r['eta']['display_half_unit'])]) is None:
        return dict(status='CONFLICTING_EFFICIENCY_LABEL',channels=used)
    return dict(status='CALIBRATION_ONLY',q_interval=qbound,eta_interval=ebound,q=sum(qbound)/2,
                workers=n,eta=sum(ebound)/2,channels=used,
                exact_workers='exact_workers' in s,
                precision_improved=qbound[1]-qbound[0]<2*r['q']['display_half_unit']-1e-12 or nh==0,
                scope='事后历史观测；相关环境通道不算独立置信证据')


def resource_coefficients(train):
    result={}
    for name in ('co2','energy','water'):
        values=[s['values'][name+'_intensity'] for s in train if name+'_intensity' in s['values']]
        if values:
            result[name]=float(np.median(values))
    return result


def curve(s, frozen):
    a,b,c=frozen['curves']['operations']['parameters']
    v=s['values']
    x=v['operations']+.5*v['previous_operations']
    return a+b*x/(c+x)


def fit_scale(train, frozen, calibrated=False):
    x=np.array([curve(s,frozen) for s in train])
    y=np.array([s['calibrated']['eta'] if calibrated else s['values']['q']/s['values']['workers'] for s in train])
    # Equal market weighting, irrespective of how many teams were captured.
    count=Counter(s['market'] for s in train)
    weights=np.array([1/count[s['market']] for s in train])
    return float(np.sum(weights*x*y)/np.sum(weights*x*x))


def market_scores(rows, name):
    groups=defaultdict(list)
    for r in rows:
        groups[r['market']].append(abs(r[name]-r['actual']))
    return {m:float(np.mean(v)) for m,v in groups.items()}


def paired_summary(rows, baseline='B1', candidate='B2'):
    if not rows:
        return dict(status='NOT_RUN',reason='无同集合折外预测',allowed_refit=False)
    base,cand=market_scores(rows,baseline),market_scores(rows,candidate)
    markets=sorted(base)
    b,c=float(np.mean(list(base.values()))),float(np.mean(list(cand.values())))
    improvement=(b-c)/b if b>1e-15 else None
    deltas=np.array([base[m]-cand[m] for m in markets])
    rng=np.random.default_rng(SEED)
    boot=np.mean(rng.choice(deltas,(1000,len(markets)),replace=True),axis=1)
    bounds=np.quantile(boot,[.025,.975]).tolist()
    fraction=float(np.mean(deltas>0))
    point_pass=len(markets)>=5 and improvement is not None and improvement>.01 and fraction>=2/3
    return dict(status='PREDICTIVE_INCREMENT' if point_pass and bounds[0]>0 else 'RESEARCH_INCONCLUSIVE',
        market_count=len(markets),cells=len(rows),baseline_mae=b,candidate_mae=c,relative_improvement=improvement,
        improved_market_fraction=fraction,delta_interval_95=bounds,bootstrap_samples=1000,seed=SEED,
        allowed_refit=bool(point_pass and bounds[0]>0),allow_deployment=False,
        deployment_reason='缺独立后续正式回合验证；仅历史条件回放',
        per_market=[dict(market=m,baseline_mae=base[m],candidate_mae=cand[m],delta=base[m]-cand[m]) for m in markets])


def select_ridge(train_x, train_y, markets):
    x,y=np.asarray(train_x,float),np.asarray(train_y,float)
    m=np.asarray(markets)
    def solve(ids,penalty):
        mean=x[ids].mean(axis=0); scale=x[ids].std(axis=0); scale=np.where(scale<1e-12,1,scale)
        z=(x[ids]-mean)/scale
        matrix=np.column_stack([np.ones(len(z)),z])
        count=Counter(m[ids]); weights=np.sqrt([1/count[g] for g in m[ids]])
        lhs=matrix*weights[:,None]; rhs=y[ids]*weights
        reg=np.diag([0]+[math.sqrt(penalty)]*x.shape[1])
        beta=np.linalg.lstsq(np.vstack([lhs,reg]),np.r_[rhs,np.zeros(x.shape[1]+1)],rcond=None)[0]
        return dict(beta=beta.tolist(),mean=mean.tolist(),scale=scale.tolist(),penalty=penalty)
    def predict(fit, xx):
        xx=np.asarray(xx,float)
        return np.column_stack([np.ones(len(xx)),(xx-fit['mean'])/fit['scale']])@fit['beta']
    scores=[]
    for penalty in PENALTIES:
        errs=[]
        for held in sorted(set(markets)):
            ids=np.flatnonzero(m!=held); test=np.flatnonzero(m==held)
            fit=solve(ids,penalty)
            errs.append(float(np.mean(abs(predict(fit,x[test])-y[test]))))
        scores.append((float(np.mean(errs)),penalty))
    best=min(scores)[0]
    penalty=max(p for score,p in scores if score<=best*1.01+1e-15)
    return solve(np.arange(len(x)),penalty),predict


def run_experiments(samples, ledger, frozen, refit=False):
    experiments, predictions, splits, fits, calibration_rows = {},[],[],{},[]
    by_scope=defaultdict(list)
    for s in samples:
        if s.get('invalid_fields'):
            continue
        by_scope[(s['phase'],s['round'],s['country'],s['product'])].append(s)
    for scope,group in sorted(by_scope.items()):
        if scope[0]=='initial':
            continue
        tag='|'.join(map(str,scope))
        qualified=[s for s in group if all(f in s['values'] for f in ('q','workers','operations','previous_operations','co2','co2_intensity','energy','energy_intensity','water','water_intensity')) and s['values']['q']>0 and s['values']['workers']>0]
        if len({s['market'] for s in qualified})<5:
            experiments['A/B2|'+tag]=dict(status='NOT_RUN',reason='少于5个同条件合格市场或缺历史/观测配对',allowed_refit=False)
        else:
            rows=[]; failed_calibration_folds=[]
            for held in sorted({s['market'] for s in qualified}):
                train=[s for s in qualified if s['market']!=held]
                test=[s for s in qualified if s['market']==held]
                coeff=resource_coefficients(train)
                calibrated_train=[dict(s,calibrated=calibration(s,coeff)) for s in train]
                calibrated_test=[dict(s,calibrated=calibration(s,coeff)) for s in test]
                if any(s['calibrated']['status']!='CALIBRATION_ONLY' for s in calibrated_train+calibrated_test):
                    failed_calibration_folds.append(held)
                    continue
                theta1=fit_scale(train,frozen); theta2=fit_scale(calibrated_train,frozen,True)
                splits.append(dict(experiment='A/B2|'+tag,held_market=held,train_ids=[key_string(s['key']) for s in train],test_ids=[key_string(s['key']) for s in test],coefficients=coeff,
                                   B1_scale=theta1,B2_scale=theta2))
                for s in calibrated_test:
                    v=s['values']; cal=s['calibrated']; f=curve(s,frozen)
                    eta_actual=v['q']/v['workers']
                    # Test labels stay unchanged; calibrated inputs cannot redefine the score.
                    rows.append(dict(sample_id=key_string(s['key']),market=held,actual=eta_actual,B1=theta1*f,B2=theta2*f,metric='效率千单位/人',scope=tag))
                    calibration_rows.append(dict(sample_id=key_string(s['key']),fold=held,**cal,
                        independent_water_actual=v['water'],independent_water_prediction=coeff['water']*cal['q'],
                        water_not_used_for_state_calibration=True))
            summary=paired_summary(rows)
            if failed_calibration_folds:
                summary['failed_calibration_folds']=failed_calibration_folds
                summary['allowed_refit']=False
                summary['calibration_gate']='存在冲突折，不允许筛掉不利观测后重拟合'
            wage_rows=[]
            params=ledger.get(scope[:2])
            if params:
                p=params['values']
                for row in rows:
                    s=next(s for s in qualified if key_string(s['key'])==row['sample_id']); v=s['values']
                    if 'wage' not in v or 'capacity' not in v: continue
                    q,C=v['q'],v['capacity']; q1=min(q,C/3); q2=min(max(q-C/3,0),C/3); q3=max(q-2*C/3,0)
                    quantity=(q1+p['second_shift']*q2+p['third_shift']*q3)*p['base_wage']
                    wage_rows.append(dict(sample_id=row['sample_id'],market=s['market'],actual=v['wage'],B1=quantity/row['B1'],B2=quantity/row['B2'],metric='工资千美元',scope=tag))
                downstream=paired_summary(wage_rows)
                summary['downstream_wage']=downstream
                if downstream.get('relative_improvement') is None or downstream['relative_improvement']<-.01:
                    summary['allowed_refit']=False
                    summary['downstream_gate']='工资缺完整配对或恶化超过1%'
                predictions.extend(dict(r,experiment='A_wage|'+tag) for r in wage_rows)
            else:
                summary['allowed_refit']=False
                summary['downstream_gate']='缺对应当期基础工资参数，不能检验下游无恶化'
            experiments['A/B2|'+tag]=summary
            predictions.extend(dict(r,experiment='A/B2|'+tag) for r in rows)
            if refit and summary.get('allowed_refit'):
                allcal=[dict(s,calibrated=calibration(s,resource_coefficients(qualified))) for s in qualified]
                fits['A/B2|'+tag]=dict(technology_scale=fit_scale(allcal,frozen,True),rho=.5,
                    curve_parameters=frozen['curves']['operations']['parameters'],calibration_coefficients=resource_coefficients(qualified),
                    interpretation='旧效率代理的校准训练候选；历史条件曲线与累计机制未修复')
        # Human events provide direct supervision; compare with the same old-input samples.
        params=ledger.get(scope[:2])
        cost=[s for s in group if all(f in s['values'] for f in ('q','workers','previous_workers_old','hires_fires','severance'))]
        if not params or len({s['market'] for s in cost})<5:
            experiments['B3|'+tag]=dict(status='NOT_RUN',reason='缺对应工资/补偿规则或少于5个配对市场',allowed_refit=False)
        else:
            p=params['values']; rows=[]
            for held in sorted({s['market'] for s in cost}):
                train=[s for s in cost if s['market']!=held]; test=[s for s in cost if s['market']==held]
                old_x=np.array([max((1-p['attrition'])*s['values']['previous_workers_old']-s['values']['workers'],0)*p['base_wage'] for s in train])
                new_x=np.array([max(-s['values']['hires_fires'],0)*p['base_wage'] for s in train])
                y=np.array([s['values']['severance'] for s in train]); w=np.array([1/Counter(s['market'] for s in train)[s['market']] for s in train])
                b1=float(np.sum(w*old_x*y)/np.sum(w*old_x*old_x)) if np.sum(w*old_x*old_x)>0 else p['severance_ratio']
                # Published compensation rule is fixed, not freely re-estimated.
                b3=p['severance_ratio']
                splits.append(dict(experiment='B3|'+tag,held_market=held,train_ids=[key_string(s['key']) for s in train],test_ids=[key_string(s['key']) for s in test],old_coefficient=b1,published_coefficient=b3))
                for s in test:
                    v=s['values']; old=max((1-p['attrition'])*v['previous_workers_old']-v['workers'],0)*p['base_wage']
                    new=max(-v['hires_fires'],0)*p['base_wage']
                    rows.append(dict(sample_id=key_string(s['key']),market=held,actual=v['severance'],B1=b1*old,B3=b3*new,
                        published_old=p['severance_ratio']*old,metric='解聘费千美元',scope=tag,
                        evaluation='条件回算：给定实际人数/人员事件，非上游人数预测成绩'))
            summary=paired_summary(rows,'B1','B3')
            summary['upstream_prediction']='NOT_VERIFIED；事件为同期期末标签，未接入事前特征'
            summary['allowed_refit']=False
            summary['refit_reason']='补偿系数已公布；本项保留规则核验，不新增自由参数'
            experiments['B3|'+tag]=summary
            predictions.extend(dict(r,experiment='B3|'+tag) for r in rows)
        # Average wage is tested for derivation before allowing an extra model.
        wage=[s for s in group if all(f in s['values'] for f in ('average_wage','hr_wage','current_workers'))]
        compatible_count=0
        for s in wage:
            v,r=s['values'],s['refs']; n,nh=v['current_workers'],r['current_workers']['display_half_unit']; ww,wh=v['average_wage'],r['average_wage']['display_half_unit']
            compatible_count+=(n-nh)*(ww-wh)<=v['hr_wage']+r['hr_wage']['display_half_unit'] and (n+nh)*(ww+wh)>=v['hr_wage']-r['hr_wage']['display_half_unit']
        experiments['C|'+tag]=dict(status='DERIVED_NO_NEW_MODEL' if wage and compatible_count==len(wage) else 'INSUFFICIENT_OR_CONFLICTING_DERIVATION',
            cells=len(wage),compatible_cells=compatible_count,allowed_refit=False,
            reason='人均工资与工资/人数的显示区间相容则不新增自由参数；否则先解决观测冲突')
        for prefix,names in [('E',['co2','energy','water']),('F',['route_co2_TH','route_co2_ID'])]:
            errors=[]; identities=[]
            for s in group:
                v,r=s['values'],s['refs']
                for name in names:
                    if prefix=='E':
                        intensity=name+'_intensity'; quantity='q'; factor=1
                    else:
                        route=name.rsplit('_',1)[1]; intensity='route_intensity_'+route; quantity='route_'+route; factor=1
                        # 千单位 × g/单位 = kg; no additional 1000 factor.
                    if not all(f in v for f in (name,intensity,quantity)):continue
                    pred=v[intensity]*v[quantity]*factor
                    tolerance=(abs(v[intensity])*r[quantity]['display_half_unit']+abs(v[quantity])*r[intensity]['display_half_unit']+
                        r[intensity]['display_half_unit']*r[quantity]['display_half_unit'])*factor+r[name]['display_half_unit']
                    identities.append(abs(pred-v[name])<=tolerance+1e-8)
                    errors.append(dict(sample_id=key_string(s['key']),metric=name,actual=v[name],prediction=pred,tolerance=tolerance))
            experiments[prefix+'|'+tag]=dict(status='KNOWN_COEFFICIENT_FORMULA' if identities and all(identities) else 'NOT_RUN_OR_PHYSICAL_CONFLICT',
                checks=len(identities),compatible=sum(identities),allowed_refit=False,
                reason='结果页单位系数解释总量，仅作条件恒等式核验；同期期末强度不是事前已知参数，不把新指标误差当利润改善')
            predictions.extend(dict(r,experiment=prefix+'|'+tag,market=int(r['sample_id'].split('|')[0])) for r in errors)
    return experiments,predictions,splits,fits,calibration_rows


def temporal_experiment(samples, frozen):
    # Only formal1 -> formal2 is used here; practice never supplies formal predecessors.
    index={tuple(s['key']):s for s in samples}
    pairs=[]
    for s in samples:
        if s['phase']!='formal' or s['round']!=2 or s.get('invalid_fields'):continue
        prev=index.get(previous_key(tuple(s['key'])))
        if not prev or prev.get('invalid_fields'):continue
        needed=('q','workers','operations','previous_operations','co2','co2_intensity','energy','energy_intensity')
        events=('hires_fires','previous_workers')
        if not all(f in s['values'] for f in needed) or not all(f in prev['values'] for f in needed+events):continue
        if min(s['values']['workers'],prev['values']['workers'],prev['values']['previous_workers'],s['values']['q'],prev['values']['q'])<=0:continue
        pairs.append((prev,s))
    markets=sorted({s['market'] for _,s in pairs})
    if len(markets)<5:
        return dict(status='NOT_RUN',reason='少于5个完整正式1→正式2市场路径',allowed_refit=False),[],[]
    predictions,splits=[],[]
    for held in markets:
        train=[p for p in pairs if p[1]['market']!=held]; test=[p for p in pairs if p[1]['market']==held]
        # Fold-local residual construction, including the previous-period residual feature.
        def feature_data(subpairs, theta_prev, theta_next, coeff_prev, coeff_next):
            xx=[]; yy=[]
            for prev,s in subpairs:
                vp=prev['values']; vs=s['values']
                cp=calibration(prev,coeff_prev); cn=calibration(s,coeff_next)
                if cp['status']!='CALIBRATION_ONLY' or cn['status']!='CALIBRATION_ONLY':
                    raise ValueError('正式残差路径包含冲突观测，停止该实验')
                prev_err=math.log(cp['eta'])-math.log(theta_prev*curve(prev,frozen))
                hire=max(vp['hires_fires'],0)/vp['previous_workers']; fire=max(-vp['hires_fires'],0)/vp['previous_workers']
                xx.append([prev_err,hire,fire]); yy.append(math.log(cn['eta'])-math.log(theta_next*curve(s,frozen)))
            return xx,yy
        # Inner folds rebuild base scales and residuals; no all-data residual targets.
        oof=[]
        for innerheld in sorted({s['market'] for _,s in train}):
            innertrain=[p for p in train if p[1]['market']!=innerheld]; inner_test=[p for p in train if p[1]['market']==innerheld]
            cp=resource_coefficients([p for p,_ in innertrain]); cn=resource_coefficients([s for _,s in innertrain])
            pp=[dict(p,calibrated=calibration(p,cp)) for p,_ in innertrain]
            nn=[dict(s,calibrated=calibration(s,cn)) for _,s in innertrain]
            tp=fit_scale(pp,frozen,True); tn=fit_scale(nn,frozen,True)
            xx,yy=feature_data(inner_test,tp,tn,cp,cn)
            oof.extend((x,y,s['market']) for x,y,(_,s) in zip(xx,yy,inner_test))
        x=[x for x,_,_ in oof]; y=[y for _,y,_ in oof]; ms=[m for _,_,m in oof]
        cp=resource_coefficients([p for p,_ in train]); cn=resource_coefficients([s for _,s in train])
        pp=[dict(p,calibrated=calibration(p,cp)) for p,_ in train]
        nn=[dict(s,calibrated=calibration(s,cn)) for _,s in train]
        tp=fit_scale(pp,frozen,True); tn=fit_scale(nn,frozen,True)
        xt,yt=feature_data(test,tp,tn,cp,cn)
        # Candidate order fixes complexity; choose only on inner market validation.
        candidates=[]
        for cols in [[],[0],[0,1],[0,2],[0,1,2]]:
            design=np.asarray(x)[:,cols]
            if cols and np.linalg.matrix_rank(design-design.mean(axis=0))<len(cols):continue
            fit,predict=select_ridge(design,y,ms)
            errors=[]
            for innerm in sorted(set(ms)):
                tr=[i for i,m in enumerate(ms) if m!=innerm]; tt=[i for i,m in enumerate(ms) if m==innerm]
                nested,pr=select_ridge(design[tr],np.asarray(y)[tr],[ms[i] for i in tr])
                errors.append(float(np.mean(abs(pr(nested,design[tt])-np.asarray(y)[tt]))))
            candidates.append((float(np.mean(errors)),cols,fit))
        best=min(c[0] for c in candidates)
        _,cols,fit=min((c for c in candidates if c[0]<=best*1.01+1e-15),key=lambda c:len(c[1]))
        corrected=predict(fit,np.asarray(xt)[:,cols])
        splits.append(dict(experiment='B4|formal1->2',held_market=held,train_ids=[key_string(s['key']) for _,s in train],
            test_ids=[key_string(s['key']) for _,s in test],residuals='inner market out-of-fold',columns=cols,fit=fit))
        for correction,(_,s) in zip(corrected,test):
            base=tn*curve(s,frozen); actual=s['values']['q']/s['values']['workers']
            predictions.append(dict(sample_id=key_string(s['key']),market=held,actual=actual,B2=base,B4=base*math.exp(float(correction)),metric='下一期效率千单位/人'))
    result=paired_summary(predictions,'B2','B4')
    result['allowed_refit']=False
    result['scope']='正式1→2单一转移的条件回溯；基准next scale使用训练市场正式2结果，不是事前时间外预测'
    result['reason']='仅一个正式转移，后续时间外验证和曲线历史绑定缺失；不重拟合部署模型'
    return result,predictions,splits


def frozen_replay(frozen):
    a,b,c=frozen['curves']['operations']['parameters']
    fit=frozen['efficiency']['selected']
    residuals=[]
    for record in fit.get('records',[]):
        if 'predicted' not in record:continue
        x=record['operations']+fit['rho']*record['previous_operations']
        predicted=fit['technology_scale']*(a+b*x/(c+x))
        residuals.append(abs(predicted-record['predicted']))
    return dict(status='PASS' if residuals and max(residuals)<=1e-12 else 'NO_MATCH',
        records=len(residuals),max_abs_difference=max(residuals) if residuals else None,
        interpretation='复现原冻结效率数值；不是新实际预测成绩')


def render(out, result, stats, experiments):
    lines=['# 新增数据的信息价值审计与实验报告','',f"阶段：{result['stage']}；固定核验覆盖：{result['coverage']}。",
        '本报告只读本地，未操作平台、未替换冻结模型；所有成绩为历史研究。','',
        '## 字段与独立信息','', '| 字段 | 数值单元格 | 市场数 | 有效变化组 |','|---|---:|---:|---:|']
    for name,s in stats.items():
        lines.append(f"| {name} | {s['cells']} | {s['markets']} | {s['varying_groups']} |")
    lines+=['','## 实验与门槛','', '| 实验 | 状态 | 基线MAE | 候选MAE | 相对改善 | 重拟合 |','|---|---|---:|---:|---:|---|']
    for name,e in experiments.items():
        fmt=lambda x: f'{x:.6g}' if isinstance(x,(float,int)) else '—'
        lines.append(f"| {name} | {e['status']} | {fmt(e.get('baseline_mae'))} | {fmt(e.get('candidate_mae'))} | {fmt(e.get('relative_improvement'))} | {e.get('allowed_refit',False)} |")
    lines+=['','## 当前全部问题与不足','',
        '- 旧效率特征仍是一阶投入代理；本实验不修复累计运营与历史条件曲线结构。',
        '- 环境观测相关；精度区间依赖尚未核实的显示舍入，不是统计置信区间。',
        '- 人员事件可验证费用关系，但同期期末事件不能用于事前输入。',
        '- 缺基础参数的回合不计算工资；缺完整财务链不计算完整利润。',
        '- 来源列/身份/产品冲突按字段排除，不将补采页数作为训练样本数。','',
        '## 因缺乏数据而无法验证的问题','',
        '- 正式1→2之外的独立正式转移和事前冻结预测。',
        '- 新产品、未知技术版本和多产品工资分摊。',
        '- 自动短贷、非零库存与订单影响下的完整利润；本阶段范围外。',
        '- 排放影响需求、环境收费和随机离职机制未有有效证据。','',
        '详见字段证据.csv、样本资格.json、划分.json、实验.json、预测.json及manifest.json。']
    text='\n'.join(lines)+'\n'
    (out/'report.md').write_text(text,encoding='utf-8')
    start=lines.index('## 当前全部问题与不足')
    missing=lines.index('## 因缺乏数据而无法验证的问题')
    (out/'当前问题与不足.md').write_text('\n'.join(lines[start:missing])+'\n',encoding='utf-8')
    (out/'因缺数据无法验证.md').write_text('\n'.join(lines[missing:-1])+'\n',encoding='utf-8')
    status_names={'PASS':'通过','PREDICTIVE_INCREMENT':'有历史预测增量','RESEARCH_INCONCLUSIVE':'增量证据不足',
                  'DERIVED_NO_NEW_MODEL':'派生值，保留原公式','KNOWN_COEFFICIENT_FORMULA':'已知系数公式',
                  'NOT_RUN':'未运行','NOT_RUN_OR_PHYSICAL_CONFLICT':'缺配对或物理冲突','AUDIT_ONLY':'只完成审计',
                  'RESEARCH_REFIT_SAVED':'研究参数已保存','NO_MODEL_PASSED':'没有模型通过重拟合门槛'}
    overview='<h2>增量比较</h2><p>同集合、整市场留出；所有误差为条件回溯，非事前成绩。蓝色是基线，绿色是候选；各图独立缩放。</p>'
    for name,e in experiments.items():
        if e.get('baseline_mae') is None:continue
        b,c=e['baseline_mae'],e['candidate_mae']; maxv=max(b,c,1e-15)
        improvement=e.get('relative_improvement'); delta=f'{improvement:.2%}' if improvement is not None else '不可算'
        overview+=f'<div class="compare"><strong>{html.escape(name)}</strong><span>　相对改善 {delta}；{status_names.get(e["status"],e["status"])}</span><svg role="img" aria-label="基线与候选MAE比较" viewBox="0 0 680 70"><text x="0" y="20">基线</text><rect x="70" y="5" height="20" width="{480*b/maxv:.3f}" fill="#386b93"/><text x="565" y="20">{b:.6g}</text><text x="0" y="55">候选</text><rect x="70" y="40" height="20" width="{480*c/maxv:.3f}" fill="#207c65"/><text x="565" y="55">{c:.6g}</text></svg></div>'
    tables=overview
    for heading,items in [('字段统计',stats),('实验',experiments)]:
        tables+=f'<h2>{heading}</h2><table><tr><th>对象</th><th>详情</th></tr>'
        for name,e in items.items():
            tables+=f'<tr><td>{html.escape(name)}</td><td><pre>{html.escape(json.dumps(e,ensure_ascii=False,indent=2))}</pre></td></tr>'
        tables+='</table>'
    doc='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>新增数据价值实验</title><style>body{font:16px/1.6 system-ui;margin:32px;max-width:1400px;color:#182c32}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:10px;text-align:left}pre{white-space:pre-wrap;word-break:break-word}input{padding:8px;width:360px}svg{display:block;width:680px;max-width:100%;height:auto}.compare{padding:14px;border:1px solid #ccd;margin:12px 0;border-radius:6px}@media print{input{display:none}.compare{break-inside:avoid}}</style><h1>新增数据的信息价值验证</h1><p>历史条件回放；未接入决策。数字与JSON同源。输入关键词筛选：</p><input aria-label="筛选字段或实验" oninput="document.querySelectorAll(\'tr,.compare\').forEach(r=>r.hidden=(r.matches(\'.compare\')||r.querySelector(\'td\'))&&!r.textContent.toLowerCase().includes(this.value.toLowerCase()))">'+tables+'<h2>问题与限制</h2><pre>'+html.escape('\n'.join(lines[lines.index('## 当前全部问题与不足'):]))+'</pre></html>'
    (out/'report.html').write_text(doc,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['audit','ablation','train'],required=True)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--evidence',type=Path)
    args=parser.parse_args()
    if args.stage=='train' and not args.evidence:
        parser.error('train需要--evidence指向已完成ablation目录')
    out=ROOT/'output/new_data_models'/datetime.now(TZ).strftime('%Y%m%dT%H%M%S%f%z')
    out.mkdir(parents=True,exist_ok=False)
    log=out/'work_log.md'
    log.write_text(f'# 新增数据价值实验日志\n北京时间：{datetime.now(TZ).isoformat()}\n阶段：{args.stage}；只读本地原件；姓名用首字母/稳定哈希团队编号；进行中。\n',encoding='utf-8')
    try:
        bundle=input_bundle(args.audit); ledger=parameter_ledger(bundle)
        save(out/'manifest.json',dict(stage=args.stage,audit=bundle['audit'],frozen_at=bundle['frozen_at'],
            input_hashes=bundle['files'],coverage=bundle['validation']['coverage_counts'],historical_diff_baseline=str(HISTORICAL_DIFF.relative_to(ROOT)),seed=SEED))
        samples,evidence,exclusions,conflicts=extract(bundle)
        stats,checks=audit_stats(samples)
        csv_write(out/'字段证据.csv',evidence)
        save(out/'样本资格.json',dict(samples=samples,exclusions=exclusions,conflicts=conflicts,technical_versions='未核实；条件研究不宣称跨技术部署'))
        save(out/'字段统计.json',stats); save(out/'派生性检查.json',checks)
        csv_write(out/'字段结论.csv',information_verdicts(stats,checks))
        save(out/'参数依据.json',[dict(phase=k[0],round=k[1],**v) for k,v in ledger.items()])
        experiments={}; predictions=[]; splits=[]; fits={}; calibration_rows=[]
        frozen=read(FROZEN)
        experiments['B0']=frozen_replay(frozen)
        if experiments['B0']['status']!='PASS':
            raise ValueError('冻结效率基线无法复现')
        if args.stage=='ablation':
            experiments_,predictions,splits,fits,calibration_rows=run_experiments(samples,ledger,frozen)
            experiments.update(experiments_)
            temporal,tp,ts=temporal_experiment(samples,frozen)
            experiments['B4|formal1->2']=temporal; predictions+=tp; splits+=ts
        elif args.stage=='train':
            evidence_path=args.evidence.resolve()
            original=read(evidence_path/'manifest.json')
            if original['stage']!='ablation' or original['input_hashes']!=bundle['files']:
                raise ValueError('训练证据不是同一冻结输入的ablation')
            evidence_check=read(evidence_path/'verification.json')
            for name in ('manifest.json','实验.json'):
                if sha(evidence_path/name)!=evidence_check['artifacts'][name]:
                    raise ValueError('增量实验证据哈希变化，拒绝训练')
            previous=read(evidence_path/'实验.json')
            eligible={k:e for k,e in previous.items() if e.get('allowed_refit')}
            if eligible:
                result_,predictions,splits,fits,calibration_rows=run_experiments(samples,ledger,frozen,refit=True)
                fits={k:v for k,v in fits.items() if k in eligible and result_[k].get('allowed_refit')}
                experiments.update({k:result_[k] for k in eligible})
            experiments['train_gate']=dict(status='RESEARCH_REFIT_SAVED' if fits else 'NO_MODEL_PASSED',
                reason='只重拟合通过同样本留出/下游/区间门槛的候选；不自动接入',allowed_refit=False)
        else:
            for name in ('A','B','C','D','E','F'):
                experiments[name]=dict(status='AUDIT_ONLY',reason='先做信息审计；增量结论需ablation',allowed_refit=False)
        save(out/'实验.json',experiments); save(out/'预测.json',predictions); save(out/'划分.json',splits)
        save(out/'校准观测.json',calibration_rows)
        save(out/'模型参数.json',dict(models=fits,enabled=False,scope='research_only',coefficient_definitions={
            'technology_scale':'乘数到生产效率的技术尺度','rho':'旧单期历史投入代理，不是累计机制',
            'k_C/k_E/k_W':'单位生产资源强度','delta_N':'已公布自然离职率','kappa_F':'已公布补偿比例',
            'b1/b2':'有效工资班次斜率，仅非派生且有效增量时训练','beta_H/beta_F':'上期人员事件对下期效率残差的关联'}))
        save(out/'研究公式.json',dict(A='资源总量=单位强度×产量；产量=人数×效率；使用精度区间联合约束',
            B='N_available=N_previous*(1-delta_N); H=N_required-N_available; F=base_wage*kappa_F*max(-H,0)',
            C='w_eff/w_base=1+b1*max(s-1,0)+b2*max(s-2,0); 派生性通过则不训练',
            D='log_efficiency_residual_next=alpha+phi*residual_previous+beta_H*hire_rate+beta_F*fire_rate',
            E='production_resources=k_C/k_E/k_W * production_kunits',
            F='transport_kg=route_TH_kunits*e_TH_g_per_unit+route_ID_kunits*e_ID_g_per_unit',
            parameter_units=dict(k_C='kg/单位',k_E='kWh/单位',k_W='升/单位',e_TH='g/单位',e_ID='g/单位',
                delta_N='小数',kappa_F='基础工资比例',alpha='对数效率残差',phi='无量纲',beta_H='每单位招聘率的对数效率关联',beta_F='每单位裁员率的对数效率关联'),
            implementation='只保存通过门槛的研究参数，未训练参数不补值'))
        assert_unchanged(bundle)
        result=dict(stage=args.stage,status='COMPLETE',coverage=bundle['validation']['coverage_counts'],
            sample_count=len(samples),field_evidence_cells=len(evidence),conflicts=len(conflicts),exclusions=len(exclusions),
            refit_models=list(fits),platform_modified=False,old_models_replaced=False)
        render(out,result,stats,experiments)
        with log.open('a',encoding='utf-8') as stream:
            stream.write(f'\n完成：{json.dumps(result,ensure_ascii=False)}\n未验证：时间外正式预测、完整利润链、真实舍入模式；未部署。\n')
        save(out/'verification.json',dict(**result,source_hashes_unchanged=True,
            linked_source_fields=True,bootstrap_seed=SEED,artifacts={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
        print(json.dumps(dict(output=str(out),**result),ensure_ascii=False))
    except Exception as exc:
        # Failure retains partial artifacts and never modifies source files.
        with log.open('a',encoding='utf-8') as stream:
            stream.write(f'\nFAILED：{type(exc).__name__}；详见终端诊断。\n')
        raise


if __name__=='__main__':
    main()
