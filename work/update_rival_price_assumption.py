"""Save round-specific carry-forward prices and replay the archived demand estimate."""
import copy
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'code/model_v2'))
import t5v2
import t5v3
from t5v2 import np

read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out = ROOT / 'output/rival_previous_prices' / stamp
    out.mkdir(parents=True, exist_ok=False)
    log = out / 'work_log.md'
    log.write_text('# 竞争价格假设更新\n\n进行中。用户要求九组分别沿用各自上回合价格。不要输出真名，姓名统一用首字母替代。仅使用已有本地归档，保存旧情景。\n', encoding='utf-8')
    old_dir = ROOT / 'output/t5v3/20261015_common_default_prices'
    preserved = {str(p.relative_to(ROOT)): sha(p) for p in old_dir.rglob('*') if p.is_file()}
    preserved['code/model_v2/t5v3.py'] = sha(ROOT / 'code/model_v2/t5v3.py')
    source = ROOT / 'output/round_close/20261015_formal5_close/m05_marketdetails.json'
    raw = read(source)
    assert raw['round'] == 5
    table = raw['tables'][0]
    own = table[1].index('营销团队')
    num = lambda v: float(re.sub(r'\s', '', str(v)))
    rivals = [i for i in range(1, 11) if i != own]
    ids = ['M05-' + hashlib.sha256(re.sub(r'[\s?，,]', '', table[1][i]).encode()).hexdigest()[:16] for i in rivals]
    prices = np.array([[[num(table[r][i]) for r in rows] for rows in [[3, 4], [6, 7]]] for i in rivals])
    assert prices.shape == (9, 2, 2) and np.isfinite(prices).all() and (prices > 0).all()
    config = dict(market_id=5, phase='formal', application_round=6, source_round=5,
                  assumption='其他九组分别沿用各自上回合实际价格；非价格行为另行假设',
                  products=['复合梁', '连接件'], countries=['泰国', '印尼'], team_ids=ids,
                  assumed_prices_usd=prices.tolist(), source=str(source.relative_to(ROOT)),
                  source_sha256=sha(source), source_rows_zero_based=[[3, 4], [6, 7]],
                  new_market_prices={'菲律宾': None},
                  missing_price_policy='新增市场无上回合价格，保持未知；不得套用本组价格或补零',
                  category='USER_ASSUMPTION_NOT_OBSERVED_FORMAL6_DECISIONS')
    (out / 'formal6_competition_inputs.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    reg = read(old_dir / 'models_full.json')
    model = t5v3.ApplicationModel()
    model.__dict__.update(t5v2.decode(reg['application_state']))
    revised = copy.deepcopy(model)
    revised.competition['assumed_prices'] = copy.deepcopy(model.competition['previous_prices'])
    base = t5v2.ApplicationModel()
    base.__dict__.update(t5v2.decode(reg['application_state']))
    comparison = []
    for cfg in reg['scenario_configs']:
        old = model.forecast(model.baseline, cfg)
        new = revised.forecast(model.baseline, cfg)
        assert np.allclose(new['own_demand_kunits'], base.demand(model.baseline[:, None], cfg, 0), atol=1e-10)
        assert np.allclose(new['own_share'] + new['rival_shares'].sum(axis=0), 1, atol=1e-12)
        assert np.allclose(new['rival_attractiveness_ratio'], 1)
        for j, product in enumerate(config['products']):
            for k, country in enumerate(config['countries']):
                comparison.append(dict(scenario=cfg['name'], product=product, country=country,
                    old_share_pct=float(old['own_share'][j,k,0]*100), new_share_pct=float(new['own_share'][j,k,0]*100),
                    old_demand_kunits=float(old['own_demand_kunits'][j,k,0]), new_demand_kunits=float(new['own_demand_kunits'][j,k,0])))
    (out / 'formal5_replay.json').write_text(json.dumps(dict(application_round=5, source_round=4,
        competition=revised.competition, comparison=comparison), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# 其他九组沿用各自上回合价格', '',
        '当前采用：正式6中，各竞争组的泰国、印尼价格分别沿用该组正式5实际价格。不是统一采用本组价格。此为用户指定假设，不是已知正式6决策。菲律宾为新增市场，无上回合价格，保持未知。不要输出真名，姓名统一用首字母替代。', '',
        '## 正式6价格输入', '',
        '| 对手编号 | 复合梁泰国，美元/单位 | 复合梁印尼，美元/单位 | 连接件泰国，美元/单位 | 连接件印尼，美元/单位 |',
        '| --- | ---: | ---: | ---: | ---: |']
    for team, p in zip(ids, prices):
        lines.append('| ' + team + ' | ' + ' | '.join(f'{v:g}' for v in p.ravel()) + ' |')
    lines += ['', '[正式6逐队输入及原件哈希](formal6_competition_inputs.json)。九组36个价格与正式5原件逐项配对。', '',
        '## 历史正式5估计的同条件重算', '',
        '为修正原t5v3“九组同价”估计，使用各组正式4价格重算正式5；本组仍用原归档基准、原系数及原非价格假设。下面不是正式6预测，也不是正式5实际结果。', '',
        '| 情景 | 产品 | 国家 | 旧同价份额，% | 新沿用份额，% | 旧需求，千单位 | 新需求，千单位 |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: |']
    for r in comparison:
        lines.append(f"| {r['scenario']} | {r['product']} | {r['country']} | {r['old_share_pct']:.4f} | {r['new_share_pct']:.4f} | {r['old_demand_kunits']:.4f} | {r['new_demand_kunits']:.4f} |")
    lines += ['', '各组价格变化为零，价格吸引力变化也为零；冻结非价格影响后，正式5重算与t5v2需求基准一致。12个情景市场的十队份额归一化通过。[完整重算数据](formal5_replay.json)。', '',
        '正式6仅更新竞争价格输入，尚未接入完整正式6模型或重做决策优化；新增市场价格及竞争队非价格行为仍未知。历史t5v3同价包、代码和哈希保持不变，不能将其旧输出当作当前假设结果。']
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    rel = out.relative_to(ROOT).as_posix()
    docs = ['README.md', 'code/model_v2/README.md', 'code/README.md', 'code/model_v2/t5v3_README.md', 'Cesim_任务要求与当前情况说明.md']
    changes = {}
    for name in docs:
        path = ROOT / name
        text = path.read_text(encoding='utf-8-sig')
        backup = out / 'before' / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        before = sha(path)
        link = ('../../' if name.startswith('code/model_v2/') else '../' if name == 'code/README.md' else '') + rel + '/report.md'
        note = f'当前竞争价格假设：其他九组分别沿用各自上回合实际价格；正式6沿用各组正式5价格，新增菲律宾价格未知。[输入及估计重算]({link})。历史统一同价情景保留。'
        if name == 'README.md':
            rows = text.splitlines()
            index = next(i for i, row in enumerate(rows) if row.startswith('| 最新需求竞争情景 |'))
            rows[index] = f'| 最新需求竞争情景 | [各组沿用上回合价格]({link}) | 正式6采用各组正式5实际价格，九组36项；菲律宾未知。原正式5同价估计已按正式4各组价格重算；未重做优化。 |'
            text = '\n'.join(rows) + '\n'
        else:
            pos = text.index('\n') + 1
            text = text[:pos] + '\n' + note + '\n' + text[pos:]
        path.write_text(text, encoding='utf-8')
        assert (path.parent / link).resolve().is_file()
        changes[name] = dict(before=before, after=sha(path), backup=str(backup.relative_to(ROOT)), new_link_verified=True)
    (out / 'document_changes.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert all(sha(ROOT / p) == h for p, h in preserved.items())
    validation = dict(status='PASS', formal6_prices=36, formal5_replay_markets=12,
        normalized_shares=True, t5v2_replay_matches=True, historical_bundle_preserved=True,
        document_backups_and_hashes=True, new_links_verified=True, formal6_forecast_generated=False)
    (out / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n', encoding='utf-8')
    shutil.copy2(Path(__file__), out / Path(__file__).name)
    with log.open('a', encoding='utf-8') as f:
        f.write('\n完成：正式6九组36价格输入、正式5历史12项重算、五份文档改前备份及前后哈希、新链接核验；旧情景包及代码哈希未变。未操作平台、未采集教程、未生成完整正式6预测或优化建议。\n')
    print(out)
    print(json.dumps(validation))


if __name__ == '__main__':
    main()
