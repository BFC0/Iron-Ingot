"""Offline formal-6 archive checks. Raw captures are never changed."""
import importlib.util
import json
import re
import sys
from functools import lru_cache
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
spec = importlib.util.spec_from_file_location('prior_audit', ROOT / 'output/round_close/20261015_formal5_close/validation/validate_market.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
rules = prior.rules
PANELS = 'summary productionenvironmental productionhr logisticsemissions marketdetails productiondetails incomestatement balancesheet cashflow market production logistics societalimpact'.split()
pair_spec = importlib.util.spec_from_file_location('prior_pair', ROOT / 'output/round_close/20261015_formal5_close/validation/pair_results_svg.py')
pair = importlib.util.module_from_spec(pair_spec)
pair_spec.loader.exec_module(pair)
sha = lru_cache(maxsize=None)(rules.sha)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=rules.unique_object)


def selected(doc):
    return [s.get('selected', s.get('text')) for s in doc.get('selects', [])]


def html(doc):
    return ''.join(doc['html_parts']) if doc.get('html_parts') else doc.get('html', '')


def source(market, panel):
    paths = [BASE / f'm{market:02d}_{panel}{suffix}.json' for suffix in ['_complete', '']]
    return next((p for p in paths if p.exists()), None)


def reference(path, table=None, row=None, column=None):
    return dict(source=path.relative_to(ROOT).as_posix(), sha256=sha(path),
                table=table, row=row, column=column, indexing='zero_based')


def number(text):
    value = rules.num(text)
    assert value is not None, text
    return value


def main():
    out = BASE / 'validation' / datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True, exist_ok=False)

    def save(name, obj):
        text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)
        with (out / name).open('x', encoding='utf-8') as stream:
            stream.write(rules.redact_names(text))

    coverage, fields, finance, cumulative, rankings, chart_checks, issues = [], [], [], [], [], [], []
    rendering = []
    # Formal-6 adds three-country rows before the financial sections: verify every label before using offsets.
    expected = {194:'资产总计', 212:'负债与所有者权益总计', 189:'固定资产总和',
                187:'厂房', 188:'机器', 191:'成品库存', 192:'应收帐款', 193:'现金及现金等价物',
                211:'负债合计', 206:'长期贷款', 208:'短期贷款', 209:'已收预付款', 210:'应付账款',
                202:'股东权益合计', 198:'股本', 199:'额外实收资本', 200:'留存收益', 201:'本回合利润',
                153:'毛利', 140:'净销售额', 152:'可变成本总和', 168:'税息折旧及摊销前利润（EBITDA）',
                159:'营销和销售成本总和', 167:'杂费成本总和', 173:'息税前利润（EBIT）',
                171:'厂房', 172:'机器', 179:'税前利润', 176:'利息收入', 177:'长期贷款利息',
                178:'短期贷款利息', 181:'本回合利润', 180:'直接税', 227:'净营运资本总额变化（增加-/减少+）',
                223:'库存变化(增 - / 减 +)', 224:'应收帐变化(增 - / 减 +)', 225:'应付账变化(增 + / 减 -)',
                228:'经营活动现金流', 221:'营运资金总计', 233:'资本支出总计', 231:'厂房', 232:'机器',
                234:'融资前现金流', 238:'融资总计', 236:'长期贷款变化(增加 + / 减少 -)',
                237:'短期贷款变化(增加 + / 减少 -)', 239:'流动资产变化', 240:'1月1日的流动资产', 241:'12月31日的流动资产'}
    equations = {
        'assets_equal_liabilities_equity': [(194,1),(212,-1)],
        'assets_components': [(194,1),(189,-1),(191,-1),(192,-1),(193,-1)],
        'fixed_assets_components': [(189,1),(187,-1),(188,-1)],
        'liabilities_components': [(211,1),(206,-1),(208,-1),(209,-1),(210,-1)],
        'equity_components': [(202,1),(198,-1),(199,-1),(200,-1),(201,-1)],
        'gross_profit': [(153,1),(140,-1),(152,1)],
        'ebitda': [(168,1),(153,-1),(159,1),(167,1)],
        'ebit': [(173,1),(168,-1),(171,1),(172,1)],
        'pretax_profit': [(179,1),(173,-1),(176,-1),(177,1),(178,1)],
        'aftertax_profit': [(181,1),(179,-1),(180,1)],
        'working_capital': [(227,1),(223,-1),(224,-1),(225,-1),(226,-1)],
        'operating_cashflow': [(228,1),(221,-1),(227,-1)],
        'capex_components': [(233,1),(231,-1),(232,-1)],
        'prefinancing_cashflow': [(234,1),(228,-1),(233,1)],
        'financing_total': [(238,1),(236,-1),(237,-1)],
        'cash_change': [(239,1),(234,-1),(238,-1)],
        'cash_bridge': [(241,1),(240,-1),(239,-1)],
        'cash_balancesheet': [(241,1),(193,-1)],
        'profit_summary': [(181,1),(5,-1)],
    }
    for m in range(1, 11):
        pp, sp = source(m, 'print'), source(m, 'summary')
        assert pp and sp, (m, 'print_or_selection_missing')
        p, s = read(pp), read(sp)
        assert prior.formal.full_html(html(p), p.get('html_length')), pp
        assert prior.formal.full_html(html(s), s.get('html_length')), sp
        assert selected(s) == [f'市场 {m}', '回合6'], (m, selected(s))
        assert p['title'] == f'Results for 市场 {m}, 回合6', p['title']
        t = p['tables'][0]
        header = t[1][1:]
        assert len(header) == len(set(header)) == 10
        for row, label in expected.items():
            assert rules.label_key(t[row][0]) == rules.label_key(label), (m, row, t[row][0], label)
        assert '已收预付款变化' in t[226][0]
        assert s['tables'][0][3][1:] == header
        for pr, sr in [(2,4),(3,9),(4,13),(5,17),(6,21)]:
            assert all(prior.compare(a,b) for a,b in zip(t[pr][1:],s['tables'][0][sr][1:])), (m, pr, sr)
        for name, terms in equations.items():
            for col in range(1,11):
                nums = [number(t[row][col]) for row, sign in terms]
                residual = sum(n[0]*sign for n, (_,sign) in zip(nums,terms))
                tolerance = sum(n[1]*abs(sign) for n,(_,sign) in zip(nums,terms))+1e-9
                finance.append(dict(market=m,team_column=col,check=name,residual=residual,tolerance=tolerance,
                                    passed=abs(residual)<=tolerance,inputs=[dict(reference(pp,0,row,col),display=t[row][col],sign=sign) for row,sign in terms]))
        old = ROOT / f'output/round_close/20261015_formal5_close/raw/market{m}_formal5_summary.json'
        op = old.with_name(old.stem+'_complete.json')
        if op.exists(): old=op
        previous = read(old)['tables'][0]
        for col, team in enumerate(header,1):
            pc = previous[20][1:].index(team)+1
            vals = [number(t[6][col]),number(previous[21][pc]),number(t[5][col])]
            residual = vals[0][0]-vals[1][0]-vals[2][0]
            tolerance = sum(n[1] for n in vals)+1e-9
            cumulative.append(dict(market=m,team=team,column=col,passed=abs(residual)<=tolerance,
                                   residual=residual,tolerance=tolerance,previous=reference(old,0,21,pc),current=reference(pp,0,6,col)))
            rankings.append(dict(market=m,team=team,column=col,profit_kusd=number(t[5][col])[0],
                                 cumulative_kusd=number(t[6][col])[0],cash_kusd=number(t[193][col])[0],
                                 short_debt_kusd=number(t[208][col])[0],long_debt_kusd=number(t[206][col])[0],source=reference(pp)))
        for panel in ['print']+PANELS:
            path = source(m,panel)
            status = 'missing'
            if path:
                doc=read(path); h=html(doc)
                status='complete' if prior.formal.full_html(h,doc.get('html_length')) else 'incomplete_html'
                if panel!='print' and (f'市场 {m}' not in selected(doc) or '回合6' not in selected(doc)):status='selection_mismatch'
                if status=='complete':
                    parsed=rules.Tables();parsed.feed(h)
                    for ti,table in enumerate(doc['tables']):
                        context=[]
                        for ri,row in enumerate(table):
                            if len(row)!=11 or not any(rules.num(v) for v in row[1:]):
                                if row and row[0].strip():context.append(row[0].strip())
                                continue
                            assert ti<len(parsed.tables) and ri<len(parsed.tables[ti]), (path,ti,ri)
                            hr=parsed.tables[ti][ri]
                            assert len(hr)==11 and rules.label_key(hr[0])==rules.label_key(row[0]) and all(rules.num(a)==rules.num(b) for a,b in zip(row[1:],hr[1:])), (path,ti,ri)
                            for ci,v in enumerate(row[1:],1):
                                fields.append(dict(market=m,phase='formal',round=6,panel=panel,label=row[0],section_path=context[-8:],
                                                   team_column=ci,team=header[ci-1],value=rules.num(v)[0] if rules.num(v) else None,display=v,
                                                   value_type='direct_actual' if rules.num(v) else 'source_missing_not_zero',source=reference(path,ti,ri,ci)))
                    charts,errors=rules.charts(h)
                    assert not errors, (path,errors)
                    containers=pair.Containers();containers.feed(h)
                    svgs=re.findall(r'<svg\b[\s\S]*?</svg>',h,re.I)
                    assert len(svgs)==len(containers.ids)
                    for chart in charts:
                        chart_checks.append(dict(market=m,panel=panel,chart=chart,source=reference(path)))
                        container='cc-'+chart['id'].replace('.','-')
                        indices=[i for i,c in enumerate(containers.ids) if c==container]
                        rec=dict(market=m,panel=panel,chart_id=chart['id'],source=reference(path),container=container)
                        try:
                            assert len(indices)==1, ('svg_container_count',indices)
                            checks=pair.geometry(chart,svgs[indices[0]])
                            assert checks and all(c['status']=='pass' for c in checks), 'geometry_check_failed'
                            rec.update(status='pass',point_checks=checks)
                        except (AssertionError,ValueError,KeyError,pair.ET.ParseError) as error:
                            rec.update(status='pending',reason=str(error))
                        rendering.append(rec)
            coverage.append(dict(market=m,panel=panel,status=status,source=reference(path) if path else None))
    assert len(finance)==1900 and len(cumulative)==len(rankings)==100
    assert all(r['passed'] for r in finance+cumulative), [r for r in finance+cumulative if not r['passed']][:10]
    for r in rankings:
        peers=[x for x in rankings if x['market']==r['market']]
        r['rank_by_cumulative_in_market']=1+sum(x['cumulative_kusd']>r['cumulative_kusd'] for x in peers)
        r['rank_by_profit_in_market']=1+sum(x['profit_kusd']>r['profit_kusd'] for x in peers)
    assert number('1 234.50')[0]==1234.5 and number('-2')[0]==-2
    save('coverage.json',coverage);save('direct_fields.json',fields);save('finance_checks.json',finance)
    save('cumulative_checks.json',cumulative);save('rankings.json',rankings);save('charts.json',chart_checks)
    save('json_svg_pairing.json',rendering)
    summary=dict(markets=10,teams=100,finance_passed=len(finance),cumulative_passed=len(cumulative),
                 coverage=dict(Counter(x['status'] for x in coverage)),charts=len(chart_checks),numeric_cells=sum(x['value'] is not None for x in fields),
                 chart_pairing=dict(Counter(x['status'] for x in rendering)),
                 raw_files_unchanged=True,platform_decisions_modified=False)
    save('summary.json',summary)
    print(json.dumps(dict(output=str(out),**summary),ensure_ascii=False))


if __name__=='__main__':main()
