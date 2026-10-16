"""Build a separate, reproducible rival-price scenario without training or platform writes."""
import copy
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'code/model_v2'))
import t5v2
import t5v3
from t5v2 import np

OUT = ROOT / 'output/t5v3/20261015_common_default_prices'
SOURCE = ROOT / 'output/t5v2/20261015_effective_investment'
MARKET = ROOT / 'output/round_close/20261014_formal4_close/raw/market5_formal4_marketdetails.json'
INITIAL = ROOT / 'output/round_close/20261014_formal4_close/formal5_initial/current_42_drafts_all_columns.json'
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def save(name, value):
    with (OUT / name).open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    assert (OUT / 'work_log.md').exists()
    preserved = {str(p.relative_to(ROOT)): sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    preserved['code/model_v2/t5v2.py'] = sha(ROOT / 'code/model_v2/t5v2.py')
    save('t5v2_before_hashes.json', preserved)
    old = read(SOURCE / 'models_full.json')
    reg = copy.deepcopy(old)
    table = read(MARKET)['tables'][0]
    assert len(table[1]) == 11 and len(set(table[1][1:])) == 10
    own = table[1].index('营销团队')
    num = lambda v: float(re.sub(r'\s', '', str(v)))
    prices = np.array([[[num(table[r][i]) for r in rows] for rows in [[3, 4], [6, 7]]]
                       for i in range(1, 11)])
    demand = np.array([[[num(table[r][i]) for r in rows] for rows in [[20, 21], [24, 25]]]
                       for i in range(1, 11)])
    assert np.isfinite(prices).all() and (prices > 0).all()
    assert np.isfinite(demand).all() and (demand >= 0).all()
    totals = demand.sum(axis=0)
    shares = demand / totals
    state = t5v2.decode(old['application_state'])
    assert np.allclose(totals, state['totals'], atol=1e-9)
    assert np.allclose(shares[own - 1], state['share'], atol=1e-10)
    defaults = [r for r in read(INITIAL) if r['column_identity'] == 'PYT' and r['row'] in [9, 10, 13, 14]]
    defaults.sort(key=lambda r: r['row'])
    assert len(defaults) == 4 and all(r['modified_state'] == 'notchanged' and r['round'] == 5 for r in defaults)
    default_prices = np.array([r['value'] for r in defaults]).reshape(2, 2)
    for r in defaults:
        assert sha(ROOT / r['source_path']) == r['sha256']
        assert num(read(ROOT / r['source_path'])['tables'][r['table']][r['row']][r['column']]) == r['value']
    assert np.array_equal(default_prices, state['baseprices'])
    assert np.array_equal(prices[own - 1], default_prices)
    rivals = [i for i in range(10) if i != own - 1]
    team_ids = ['M05-' + hashlib.sha256(re.sub(r'[\s?，,]', '', name).encode()).hexdigest()[:16]
                for name in table[1][1:]]
    competition = dict(team_ids=[team_ids[i] for i in rivals], own_team_id=team_ids[own - 1],
                       previous_prices=prices[rivals].tolist(), previous_shares=shares[rivals].tolist(),
                       assumed_prices=np.broadcast_to(default_prices, (9, 2, 2)).tolist(),
                       default_price_source_category='FORMAL5_OPENING_UNCHANGED_PERSONAL_PRICE',
                       previous_share_category='FORMAL4_ACTUAL_DEMAND_NORMALIZED_NOT_SALES_SHARE',
                       nonprice_assumption='FREEZE_EACH_RIVAL_FORMAL4_NONPRICE_ATTRACTIVENESS',
                       default_fields=[dict(row=r['row'], value=r['value'], source=r['source_path'],
                                            sha256=r['sha256'], modified_state=r['modified_state']) for r in defaults])
    reg.update(version='t5v3', base_version='t5v2', saved_plans=[],
               prediction_status='USER_ASSUMPTION_CONDITIONAL_NOT_NEW_TRAINING')
    reg['application_state']['competition'] = competition
    # Only use round5 neutral/country/competitive stress inputs, without implying a round6 forecast.
    reg['scenario_configs'] = copy.deepcopy(old['scenario_configs'][:3])
    save('competition_inputs.json', competition)
    save('models_full.json', reg)
    request = dict(version='t5v3', market_id=5, phase='formal', round=5, scenario='中性SHARE')
    save('example_request.json', request)
    save('example_prediction.json', t5v3.apply_request(reg, request))
    model = t5v3.ApplicationModel()
    model.__dict__.update(t5v2.decode(reg['application_state']))
    baseline = t5v2.ApplicationModel()
    baseline.__dict__.update(state)
    comparisons = []
    for cfg in reg['scenario_configs']:
        x = state['baseline'][:, None]
        forecast = model.forecast(x, cfg)
        old_demand = baseline.demand(x, cfg, 0)
        for j, product in enumerate(['复合梁', '连接件']):
            for k, country in enumerate(['泰国', '印尼']):
                total = forecast['market_total_kunits'][j, k]
                comparisons.append(dict(scenario=cfg['name'], product=product, country=country,
                    rival_price_usd=float(default_prices[j, k]),
                    old_share_pct=float(old_demand[j, k, 0] / total * 100),
                    new_share_pct=float(forecast['own_share'][j, k, 0] * 100),
                    old_demand_kunits=float(old_demand[j, k, 0]),
                    new_demand_kunits=float(forecast['own_demand_kunits'][j, k, 0]),
                    rival_attractiveness_ratio=float(forecast['rival_attractiveness_ratio'][j, k])))
    save('comparison.json', comparisons)
    lines = ['# t5v3：统一对手默认价格的市场份额情景', '',
        '用户确认其他九组统一使用本组正式5回合初默认价格。仅改进竞争输入的表达，不重训系数、不声称已验证精度提高。不要输出真名，姓名统一用首字母替代。', '',
        '## 同一归档本人决策的预测对照', '',
        '本人使用t5v2保存的“最新网页基准”（19:11归档，非实时状态），全部决策保持一致，仅替换竞争假设。下面是需求份额，不是受供应约束的销量份额，也不是新决策建议。', '',
        '| 情景 | 产品 | 国家 | 九组统一价，美元/单位 | t5v2份额，% | t5v3份额，% | t5v2需求，千单位 | t5v3需求，千单位 | 对手合计吸引力比 |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in comparisons:
        lines.append(f"| {r['scenario']} | {r['product']} | {r['country']} | {r['rival_price_usd']:g} | {r['old_share_pct']:.4f} | {r['new_share_pct']:.4f} | {r['old_demand_kunits']:.4f} | {r['new_demand_kunits']:.4f} | {r['rival_attractiveness_ratio']:.6f} |")
    lines += ['', '## 计算与证据', '',
        '1. 用正式4市场5十队的真实需求分别归一化，获得四个市场的需求份额锚点；不使用结果页按销量计算的市场份额。',
        '2. 对每个对手，以其正式4真实价格为基准，计算统一默认价引起的吸引力变化。沿用t5v2各产品/国家的价格弹性与分段阈值，价格重要性已包含在冻结系数中，不再次相乘。',
        '3. 令对手i的吸引力为 Aᵢ = sᵢ₄ × exp(−β × ln(P默认/Pᵢ₄) − 分段尾部变化)。其余营销、研发等非价格效果冻结在该队原份额锚点；这属于未验证的分析假设。',
        '4. 本组沿用t5v2价格、营销及有效研发的变化量Δ。本组份额 = s本组₄ × exp(Δ) / [s本组₄ × exp(Δ) + 压力系数 × ΣAᵢ]。每个产品/国家的十队份额加总为1。',
        '5. 需求 = 份额 × 正式4行业需求 × 正式5国家增长情景（泰国+7%、印尼−5%）；保留需求与供应截断后的销量的区别。', '',
        '本组四个默认价在正式5期初归档中均标为未修改，且与正式4本组价格吻合。其他九组采用这些价格是用户指定情景，不能标为其真实决策。复合梁分段阈值为泰国2700／印尼3000美元，连接件无尾部项。', '',
        '逐队输入、源行号及默认值原件哈希：[competition_inputs.json](competition_inputs.json)。市场结果原件使用第3/4/6/7行价格、第20/21/24/25行需求，零基索引；本组列为第6列。来源清单：[source_manifest.json](source_manifest.json)。', '',
        '## 验证及限制', '',
        '自检覆盖：九组价格输入、份额总和、历史锚点复现、价格单调性、批量与单条一致、分段阈值、压力情景、非法输入拒绝、t5v2哈希保留。验收结果见[validation.json](validation.json)。', '',
        '无新训练标签，未使用正式5实际结果或预算作标签，未进行跨回合精度验证。十队完整选择归一化及共同价格弹性是建模假设；营销细分、对手研发变化和供给不足后的转单尚未识别。正式6价格未知，默认拒绝外推；若调用继承的财务链，必须显式指定rival_prices_formal6=freeze_formal5_common_defaults，表示额外冻结假设，仍需重新优化和核验。', '',
        't5v2历史优化候选保留；本次没有重新优化，不将其利润或推荐直接迁移至t5v3。新版入口见[运行说明](../../../code/model_v2/t5v3_README.md)。']
    with (OUT / 'report.md').open('x', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    paths = [MARKET, INITIAL, SOURCE / 'models_full.json'] + [ROOT / r['source_path'] for r in defaults]
    save('source_manifest.json', {str(p.relative_to(ROOT)): sha(p) for p in paths})
    (OUT / 'code_snapshot').mkdir()
    for path in [Path(__file__), ROOT / 'code/model_v2/t5v3.py', ROOT / 'code/model_v2/verify_t5v3.py']:
        shutil.copy2(path, OUT / 'code_snapshot' / path.name)
    print(json.dumps(comparisons[:4], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
