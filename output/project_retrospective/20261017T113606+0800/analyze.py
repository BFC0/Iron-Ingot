"""复算本地归档；不改原件。运行：python <本文件绝对路径>。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCES = [
    'output/round_close/20261012T221044.031+0800/raw/market05_initial0_summary.json',
    'output/round_close/20261012T221044.031+0800/raw/market05_formal1_summary.json',
    'output/round_close/20261012T221044.031+0800/raw/market05_formal2_summary.json',
    'output/round_close/20261014_resume_verified/raw/market5_formal3_summary_complete.json',
    'output/round_close/20261014_formal4_close/raw/market5_formal4_summary_complete.json',
    'output/round_close/20261015_formal5_close/raw/market5_formal5_summary_complete.json',
    'output/round_close/20261016_formal6_close/m05_summary_complete.json',
]
manifest = []


def read_rows(relative):
    path = ROOT / relative
    content = path.read_bytes()
    doc = json.loads(content.decode('utf-8-sig'))
    manifest.append({'path': relative, 'sha256': hashlib.sha256(content).hexdigest()})
    rows = []
    for ti, table in enumerate(doc['tables']):
        column = None
        for ri, row in enumerate(table):
            if '营销团队' in row:
                assert row.count('营销团队') == 1
                column = row.index('营销团队')
            elif len(row) == 11 and row[0].strip():
                assert column is not None, (relative, ti, ri)
                try:
                    values = [float(''.join(v.split()).replace(',', '').replace('−', '-')) for v in row[1:]]
                except ValueError:
                    continue
                rows.append({'label': row[0], 'value': values[column - 1], 'values': values,
                             'table': ti, 'row': ri, 'column': column})
    return rows


def unique(rows, label):
    matches = [r for r in rows if r['label'] == label]
    assert len(matches) == 1, (label, len(matches))
    return matches[0]


rounds = []
for number, source in enumerate(SOURCES):
    rows = read_rows(source)
    result = {'round': number, 'source': source}
    for label, key in [('营业收入净额', 'revenue'), ('本回合利润', 'profit'),
                       ('累计收益', 'cumulative'), ('现金及现金等价物', 'cash')]:
        row = unique(rows, label)
        result[key] = row['value']
        result[key + '_source_cell'] = {k: row[k] for k in ('table', 'row', 'column')}
        if key in ('profit', 'cumulative'):
            result[key + '_rank'] = 1 + sum(v > row['value'] for v in row['values'])
    if number:
        result['cumulative_rounding_residual'] = result['cumulative'] - rounds[-1]['cumulative'] - result['profit']
        assert abs(result['cumulative_rounding_residual']) <= 1.5
    rounds.append(result)

incomes = {5: read_rows('output/round_close/20261015_formal5_close/raw/market5_formal5_incomestatement.json'),
           6: read_rows('output/round_close/20261016_formal6_close/m05_incomestatement.json')}
labels = ['复合梁', '连接件', '净销售额', '可变成本总和', '毛利', '营销和销售成本总和',
          '行政管理成本', '解雇成本', '研发', '运营改进', '库存持有成本', '杂费成本总和',
          '税息折旧及摊销前利润（EBITDA）', '厂房', '机器', '息税前利润（EBIT）',
          '利息收入', '长期贷款利息', '短期贷款利息', '税前利润', '直接税', '本回合利润']
income = {label: {'round5': unique(incomes[5], label)['value'],
                  'round6': unique(incomes[6], label)['value']} for label in labels}
for values in income.values():
    values['change'] = values['round6'] - values['round5']
cash_rows = read_rows('output/round_close/20261016_formal6_close/m05_cashflow.json')
cash = {label: unique(cash_rows, label)['value'] for label in
        ['经营活动现金流', '资本支出总计', '融资总计', '流动资产变化', '1月1日的流动资产', '12月31日的流动资产']}
assert cash['经营活动现金流'] + cash['资本支出总计'] + cash['融资总计'] == cash['流动资产变化']
assert cash['1月1日的流动资产'] + cash['流动资产变化'] == cash['12月31日的流动资产']
six_profit = sum(r['profit'] for r in rounds[1:])
assert (rounds[0]['cumulative'], six_profit, rounds[6]['cumulative']) == (1293, 8003, 9295)
assert abs(rounds[0]['cumulative'] + six_profit - rounds[6]['cumulative']) <= 3.5
assert rounds[6]['profit_rank'] == 1 and rounds[6]['cumulative_rank'] == 4
assert income['本回合利润']['change'] == 4031
assert all(r['profit'] == unique(incomes[r['round']], '本回合利润')['value'] for r in rounds[5:])
result = {'unit': '千美元', 'market': 5, 'team': '本组', 'indexing': 'zero_based',
          'rank_definition': '1 + 同市场显示值严格高于本组的队数；非平台综合成绩',
          'initial_cumulative': rounds[0]['cumulative'], 'six_round_profit_sum': six_profit,
          'six_round_cumulative_increment': rounds[6]['cumulative'] - rounds[0]['cumulative'],
          'total_rounding_residual': rounds[6]['cumulative'] - rounds[0]['cumulative'] - six_profit,
          'rounds': rounds, 'income_comparison': income, 'round6_cash_bridge': cash, 'sources': manifest}
result['derived_metrics'] = {
    'round5_gross_margin_pct': income['毛利']['round5'] / income['净销售额']['round5'] * 100,
    'round6_gross_margin_pct': income['毛利']['round6'] / income['净销售额']['round6'] * 100,
    'round6_revenue_growth_pct': income['净销售额']['change'] / income['净销售额']['round5'] * 100,
    'beam_share_of_revenue_increase_pct': income['复合梁']['change'] / income['净销售额']['change'] * 100,
}
demand_path = ROOT / 'output/round_close/20261016_formal6_close/delivery/20261017T112539912574+0800/player_demand_estimate_errors.json'
demand_bytes = demand_path.read_bytes()
demand_errors = json.loads(demand_bytes.decode('utf-8-sig'))
assert len(demand_errors) == 6
result['player_demand_errors'] = [
    {k: r[k] for k in ('product', 'country', 'estimate', 'actual', 'unit')} |
    {'error': r['estimate'] - r['actual'], 'relative_error_pct': (r['estimate'] / r['actual'] - 1) * 100}
    for r in demand_errors
]
manifest.append({'path': demand_path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(demand_bytes).hexdigest()})
(OUT / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'rounds': [{k: r[k] for k in ('round', 'revenue', 'profit', 'cumulative', 'cash', 'profit_rank', 'cumulative_rank')} for r in rounds],
                  'six_profit': six_profit, 'income': income, 'cash': cash}, ensure_ascii=False, indent=2))
