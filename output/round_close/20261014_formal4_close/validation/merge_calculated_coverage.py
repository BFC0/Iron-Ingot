"""Add traceable calculated alternatives without overwriting direct field evidence."""
import argparse
import importlib.util
import json
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path

BASE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('validation',BASE/'validate_market.py')
validation=importlib.util.module_from_spec(spec);spec.loader.exec_module(validation)
CALCULATED=BASE.parent/'calculated/20261014T223424833674+0800'


def target(record):
    metric=record['metric'];product=record['product']
    if metric=='产品跨国需求总计':return 'marketdetails:0:'+('22' if product=='复合梁' else '26')
    if metric=='产品整体销量市场份额':return 'marketdetails:0:'+('32' if product=='复合梁' else '36')
    if metric=='总流动资产':return 'balancesheet:0:18'
    if metric=='每人平均生产工资':return 'productionhr:0:2'
    return None


def main():
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S.%f+0800')
    out=BASE/'merged'/stamp;out.mkdir(parents=True,exist_ok=False)
    values=validation.read(CALCULATED/'calculated_values.json')
    index=validation.read(CALCULATED/'calculated_index.json')
    assert len(values)==len(index)==700
    source_cache={};input_checks=[]
    for i,record in enumerate(values):
        assert record['phase']=='formal' and record['round']==4 and record['value_type']=='calculated'
        assert index[i]['json_pointer']==f'/calculated_values.json/{i}'
        assert index[i]['metric']==record['metric'] and index[i]['market_id']==record['market_id']
        for inp in record['inputs']:
            path=validation.ROOT/inp['source_path']
            if path not in source_cache:
                source_cache[path]=validation.read(path)
            assert validation.rules.sha(path)==inp['sha256']
            doc=source_cache[path]
            assert validation.formal.full_html(doc['html'],doc.get('html_length'))
            shown=doc['tables'][inp['table']][inp['row']][inp['column']]
            assert validation.rules.num(shown)[0]==inp['value']
            input_checks.append(dict(record_index=i,source=inp['source_path'],sha256=inp['sha256'],status='pass'))
    coverage=[];comparisons=[];runs=[]
    for market in range(1,11):
        run=sorted((BASE/f'market{market}').glob('*/validation.json'))[-1].parent
        fields=validation.read(run/'field_gaps.json')
        assert len(fields)==200
        runs.append(dict(market=market,source=validation.reference(run/'validation.json')))
        for field in fields:
            alternatives=[(i,r) for i,r in enumerate(values) if r['market_id']==market and target(r)==field['requirement_id']]
            if alternatives:
                assert len(alternatives)==10 and {r['team_column'] for i,r in alternatives}==set(range(1,11))
                field['calculated_alternatives']=[dict(reference=validation.reference(CALCULATED/'calculated_values.json'),json_pointer=f'/{i}',**r) for i,r in alternatives]
                if field['formal4_status']=='calculate_or_targeted_web_supplement_required':
                    field['formal4_status']='calculated_verified'
                else:
                    for i,record in alternatives:
                        direct=next(x for x in field['formal4_values'] if x['column_index']==record['team_column'])
                        half=validation.rules.num(direct['display'])[1]
                        lower,upper=record['approximate_display_interval']
                        overlap=direct['value']+half>=lower and direct['value']-half<=upper
                        comparisons.append(dict(market=market,requirement_id=field['requirement_id'],team_column=record['team_column'],
                                                calculated_index=i,value=record['value'],direct_value=direct['value'],
                                                approximate_interval=[lower,upper],direct_half_step=half,
                                                status='pass' if overlap else 'fail'))
            coverage.append(field)
    assert target({'metric':'人员净变化','product':'全部生产产品'}) is None
    summary=dict(status='MERGED_COVERAGE_WITH_EXPLICIT_GAPS',calculated_count=len(values),
                 field_status_counts=dict(Counter(x['formal4_status'] for x in coverage)),
                 input_checks=dict(Counter(x['status'] for x in input_checks)),
                 direct_calculated_checks=dict(Counter(x['status'] for x in comparisons)),
                 calculated_index_source=validation.reference(CALCULATED/'calculated_index.json'),
                 calculated_value_source=validation.reference(CALCULATED/'calculated_values.json'),source_runs=runs,
                 net_personnel_change_is_not_hiring_or_layoff=True,complete_round_archive=False)
    for name,data in [('field_coverage',coverage),('direct_calculated_checks',comparisons),('input_checks',input_checks),('validation',summary)]:
        with (out/f'{name}.json').open('x',encoding='utf-8') as stream:json.dump(data,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(output=str(out),**{k:v for k,v in summary.items() if k!='source_runs'}),ensure_ascii=False))


if __name__=='__main__':main()
