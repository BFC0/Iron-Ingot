"""Fill only missing, explicitly defined formal4 print metrics."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'output/round_close/20261014_formal4_close'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(text):
    cleaned = re.sub(r'\s+', '', text).replace(',', '')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', cleaned):
        raise ValueError('Missing or nonnumeric input')
    digits = len(cleaned.split('.')[1]) if '.' in cleaned else 0
    return float(cleaned), .5 * 10 ** -digits


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    out = BASE / 'calculated' / now.strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'work_log.md').write_text('# 打印缺项计算\n\n不要输出真名，姓名统一用首字母替代。\n\n开始：' + now.isoformat() + '\n授权：正式4结算只读采集流程；只计算缺项，不覆盖直接值，不重训。\n', encoding='utf-8')
    results, gaps, checks, sources = [], [], [], []
    for path in sorted((BASE / 'raw').glob('market*_formal4_print.json')):
        market = int(re.search(r'market(\d+)', path.name)[1])
        data = read(path)
        summary_path = BASE / 'raw' / f'market{market}_formal4_summary_complete.json'
        if not summary_path.exists():
            summary_path = BASE / 'raw' / f'market{market}_formal4_summary.json'
        summary = read(summary_path)
        selections = {s.get('selected') for s in summary.get('selects', [])}
        assert f'市场 {market}' in selections and '回合4' in selections
        table = data['tables'][0]
        rows = [(i, r) for i, r in enumerate(table) if r]
        def position(label, start=0):
            return next(i for i, r in rows if i >= start and r[0] == label)
        def ref(index, col):
            value, half = number(table[index][col])
            return dict(value=value, display=table[index][col], half_step=half,
                        source_path=path.relative_to(ROOT).as_posix(), sha256=sha(path),
                        table=0, row=index, column=col, source_label=table[index][0],
                        indexing='zero_based',market_id=market,phase='formal',round=4,
                        team_id=f'M{market}_C{col}')
        def emit(col, metric, product, country, unit, formula, inputs, numerator_count=0):
            if numerator_count:
                numerator, denominator = inputs[:numerator_count], inputs[numerator_count:]
                n, nh = sum(x['value'] for x in numerator), sum(x['half_step'] for x in numerator)
                d, dh = sum(x['value'] for x in denominator), sum(x['half_step'] for x in denominator)
                if d - dh <= 0:
                    gaps.append(dict(market_id=market, team_column=col, metric=metric, reason='分母区间含零'))
                    return
                scale = 100 if unit == '%' else 1
                value, interval = scale*n/d, [scale*max(n-nh, 0)/(d+dh), scale*(n+nh)/(d-dh)]
            else:
                value = sum(x.get('sign', 1)*x['value'] for x in inputs)
                half = sum(x['half_step'] for x in inputs)
                interval = [value-half, value+half]
            results.append(dict(market_id=market, phase='formal', round=4, team_id=f'M{market}_C{col}',
                team_column=col, product=product, country=country, metric=metric, value=value,
                value_type='calculated', category='ACTUAL_RESULT_DERIVED_FROM_PRINT', formula=formula,
                unit=unit, inputs=inputs, approximate_display_interval=interval,
                precision_note='输入按原显示位数近似最近舍入半步区间；实际舍入规则未核实，输出小数位不表示内部精度。',
                code_path=Path(__file__).relative_to(ROOT).as_posix()))
        header = table[position('概要')+1]
        assert len(header) == 11
        summary_headers = [r for t in summary.get('tables', []) for r in t if len(r) == 11 and r[1:] == header[1:]]
        assert summary_headers, 'Print/summary team order mismatch'
        source_record = dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path),
            summary_path=summary_path.relative_to(ROOT).as_posix(), summary_sha256=sha(summary_path),
            market_id=market, phase='formal', round=4, team_columns=10,
            selected_market_verified=True, selected_round_verified=True, team_order_verified=True)
        sources.append(source_record)
        market_start = position('市场报告')
        sale_start, demand_start = position('销售, 千单位', market_start), position('需求, 千单位', market_start)
        for product in ('复合梁', '连接件'):
            dp, sp = position(product, demand_start), position(product, sale_start)
            demand_rows = [position(c, dp) for c in ('泰国', '印尼')]
            sale_rows = [position(c, sp) for c in ('泰国', '印尼')]
            sales_total = position(f'销售额总计, 千单位 - {product}', sale_start)
            all_sales = [ref(i, c) for c in range(1, 11) for i in sale_rows]
            for col in range(1, 11):
                demand_inputs, sale_inputs = [ref(i,col) for i in demand_rows], [ref(i,col) for i in sale_rows]
                emit(col,'产品跨国需求总计',product,'全部销售国家','千单位','泰国需求 + 印尼需求',demand_inputs)
                direct = ref(sales_total,col)
                delta = abs(direct['value'] - sum(x['value'] for x in sale_inputs))
                assert delta <= direct['half_step'] + sum(x['half_step'] for x in sale_inputs) + 1e-9
                checks.append(dict(market_id=market, team_column=col, product=product,
                    metric='产品跨国销量总计', status='DIRECT_VALUE_PRESERVED', direct_source=direct,
                    calculated_crosscheck_passed=True))
                emit(col,'产品整体销量市场份额',product,'全部销售国家','%',
                     '100 * 本队该产品泰国及印尼零售销量 / 全部团队该产品泰国及印尼零售销量',sale_inputs+all_sales, 2)
        balance_start = position('资产负债表, 千 美元')
        current_start, asset_end = position('流动资产', balance_start), position('资产总计',balance_start)
        current_rows = [i for i,r in rows if current_start < i < asset_end and len(r)==11 and any(re.search(r'\d', s) for s in r[1:])]
        assert [table[i][0] for i in current_rows] == ['成品库存','应收帐款','现金及现金等价物']
        production_start = position('生产报告')
        wage_row = position('生产工资合计, 千 美元',production_start)
        workforce_rows = [position('生产线人工数量',position(p,production_start)) for p in ('复合梁','连接件')]
        allocation_rows = [position('工资分摊, 千 美元',position(p,production_start)) for p in ('复合梁','连接件')]
        prior_path = ROOT / f'output/round_close/20261014_resume_verified/raw/market{market}_formal3_productionhr.json'
        prior = read(prior_path) if prior_path.exists() else None
        prior_table, prior_index = None, None
        if prior:
            selectors = prior.get('selects',[])
            assert any(str(s.get('value')) == str(market-1) and ('group' in s.get('id','') or s.get('selected')==f'市场 {market}') for s in selectors)
            assert any(str(s.get('value')) == '5' and ('round' in s.get('id','') or s.get('selected')=='回合3') for s in selectors)
            prior_table = prior['tables'][0]
            assert prior_table[0] == ['泰国'] and prior_table[1][1:] == header[1:]
            prior_index = next(i for i,r in enumerate(prior_table) if r and r[0]=='生产人员数量, 本回合')
            source_record['prior_personnel_source'] = prior_path.relative_to(ROOT).as_posix()
            source_record['prior_personnel_sha256'] = sha(prior_path)
        for col in range(1,11):
            emit(col,'总流动资产','公司','全部','千美元','成品库存账面价值 + 应收帐款 + 现金及现金等价物',[ref(i,col) for i in current_rows])
            wage, workforce = ref(wage_row,col), [ref(i,col) for i in workforce_rows]
            allocations = [ref(i,col) for i in allocation_rows]
            assert abs(wage['value']-sum(x['value'] for x in allocations)) <= wage['half_step']+sum(x['half_step'] for x in allocations)+1e-9
            emit(col,'每人平均生产工资','全部生产产品','泰国','千美元/人',
                 '泰国生产工资合计 / (复合梁生产线人工数量 + 连接件生产线人工数量)',
                 [wage]+workforce,1)
            checks.append(dict(market_id=market,team_column=col,metric='净现金',status='DIRECT_VALUE_PRESERVED',direct_source=ref(position('净现金'),col)))
            if prior_table:
                previous, half = number(prior_table[prior_index][col])
                prior_input = dict(value=previous, half_step=half, display=prior_table[prior_index][col],
                    source_path=prior_path.relative_to(ROOT).as_posix(),sha256=sha(prior_path),
                    table=0,row=prior_index,column=col,source_label='生产人员数量, 本回合',
                    indexing='zero_based',phase='formal',round=3,market_id=market,
                    team_id=f'M{market}_C{col}',sign=-1)
                emit(col,'人员净变化','全部生产产品','泰国','人',
                     '正式4复合梁及连接件生产线人工数量之和 - 已核正式3生产HR本回合人员数量',
                     workforce+[prior_input])
            else:
                gaps.append(dict(market_id=market,phase='formal',round=4,team_column=col,metric='人员净变化',
                             reason='缺已核正式3人员原件；不补零，不称招聘/裁员'))
    assert results and len({(r['market_id'],r['team_id'],r['metric'],r['product'],r['country']) for r in results})==len(results)
    assert number('1\u00a0234.50') == (1234.5,.005)
    for market in {r['market_id'] for r in results}:
        for product in ('复合梁','连接件'):
            shares=[r['value'] for r in results if r['market_id']==market and r['product']==product and r['metric']=='产品整体销量市场份额']
            assert len(shares)==10 and abs(sum(shares)-100)<1e-9
    for filename, value in [('calculated_values.json',results),('direct_preserved.json',checks),
                             ('gaps.json',gaps),('source_manifest.json',sources)]:
        with (out/filename).open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
    status=dict(status='CALCULATED_GAPS_RETAINED' if gaps else 'CALCULATED_AND_CHECKED',markets=[s['market_id'] for s in sources],
                calculated_count=len(results),direct_preserved=len(checks),remaining_gaps=len(gaps),
                no_cross_product_quantity_sum=True,no_direct_value_overwrites=True,no_training=True)
    with (out/'acceptance.json').open('x',encoding='utf-8') as stream:
        json.dump(status,stream,ensure_ascii=False,indent=2)
    with (out/'work_log.md').open('a',encoding='utf-8') as stream:
        stream.write('\n完成：'+json.dumps(status,ensure_ascii=False)+'\n')
    print(json.dumps(dict(output=out.relative_to(ROOT).as_posix(),**status),ensure_ascii=False))


if __name__=='__main__':
    main()
