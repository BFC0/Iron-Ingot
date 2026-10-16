"""Save and verify the top-down t6v1n application without rerunning optimization."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'code/model_v2'))
import t6v1n as app
import numpy as np

BASE = ROOT/'output/t6v1/20261016T001633520'
INDUSTRY = ROOT/'output/t6v0/20261015T235330003362+0800/industry.json'
OUTLOOK = ROOT/'output/round_close/20261015_formal5_close/formal6_initial/published_outlook_five_parts.json'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def verify(out):
    m = app.ApplicationModel(out)
    old = app.base.ApplicationModel(BASE)
    x = m.validate(m.baseline)
    history = app.read(INDUSTRY)
    totals = np.array([[next(q['total'] for q in history if q['market'] == 5 and q['product'] == p and q['country'] == c)*(1+g)
                        for c, g in zip(app.COUNTRIES[:2], [.04, .05])]+[ph]
                       for p, ph in zip(app.PRODUCTS, [5., 105.])])
    assert np.allclose(m.market_forecast({}), totals, rtol=0, atol=1e-12)
    vectors = [x]+[np.array(p['x']) for p in app.read(BASE/'result.json')['candidates']]
    replay = []
    for i, vector in enumerate(vectors):
        for scenario in m.r['scenarios']:
            a = old.evaluate(vector, scenario, True)
            b = m.evaluate(vector, scenario, True)
            for key in a:
                if isinstance(a[key], (int, float)):
                    assert np.isclose(a[key], b[key], rtol=0, atol=1e-8), key
            for key in ['demand', 'shares', 'sales', 'production', 'closing_inventory', 'priorities']:
                assert np.allclose(a[key], b[key], rtol=0, atol=1e-10), key
            assert np.allclose(np.array(b['market_totals'])*b['own_shares'], b['demand'])
            assert np.allclose(np.array(b['shares']).sum(axis=2), 1.)
            assert abs(b['balance_error']) < 1e-7 and b['quantity_error'] < 1e-8
            replay.append(dict(vector=i, scenario=scenario['name'], profit=b['profit'], cash=b['cash']))
    demand, shares = m.demand(x, {})
    assert np.allclose((shares*totals[:, :, None, None]).sum(axis=2), totals[:, :, None])
    scaled, same_shares = m.demand(x, dict(market_scale=.9))
    assert np.allclose(scaled, demand*.9) and np.array_equal(shares, same_shares)
    growth = np.array(m.r['market_forecast']['growth_rates'])
    growth[0, 0] += .1
    changed, same_shares = m.demand(x, dict(market_growth=growth))
    assert np.array_equal(shares, same_shares)
    assert np.isclose(changed[0, 0, 0]/demand[0, 0, 0], 1.14/1.04)
    assert np.array_equal(changed[1], demand[1]) and np.array_equal(changed[0, 1:], demand[0, 1:])
    assert np.all(m.demand(x, dict(market_scale=0))[0] == 0)
    assert np.all(m.demand(x, dict(disable_ph=True))[0][:, 2] == 0)
    assert np.all(m.demand(x, dict(market_growth=np.full((2, 2), -1.)))[0][:, :2] == 0)
    for cfg in [dict(market_scale=-1), dict(market_scale=True), dict(market_scale='1'), dict(market_scale=np.nan),
                dict(market_growth=[.04, .05]), dict(market_growth=np.full((2, 2), -1.01)),
                dict(new_market_totals=[-1, 105]), dict(new_market_totals=[5, np.inf]), dict(rival_scale=0)]:
        try:
            m.demand(x, cfg)
        except ValueError:
            pass
        else:
            raise AssertionError(f'invalid market input accepted: {cfg}')
    for j, p in enumerate(app.PRODUCTS):
        for k in range(3):
            trial = x.copy()
            trial[j*3+k] *= 1.05
            own = m.r['own_indices'][p][app.COUNTRIES[min(k, 1)]]
            assert m.demand(trial, {})[1][j, k, own, 0] < shares[j, k, own, 0]
    for index in [6, 12, 18, 19]:
        trial = x.copy()
        trial[index] += 1.
        assert not np.array_equal(m.demand(trial, {})[1], shares)
    batch = np.column_stack(vectors)
    for i, vector in enumerate(vectors):
        assert np.allclose(m.evaluate(batch)[0][i], m.evaluate(vector)[0][0])
    result = dict(status='PASS', regression_cases=len(replay), top_down_conservation=True,
                  decision_dependent_shares=True, market_scenarios_and_invalid_inputs=True,
                  vectorized_financial_replay=True, training_performed=False,
                  optimization_performed=False, platform_verified=False, independent_forward_validation=False)
    return result, replay


def build(out):
    out = out.resolve()
    assert (out/'work_log.md').exists() and not (out/'models_full.json').exists()
    inputs = [p for p in BASE.rglob('*') if p.is_file()]+[INDUSTRY, OUTLOOK,
        ROOT/'code/model_v2/t6v1.py', ROOT/'code/model_v2/t6v1n.py',
        ROOT/'code/model_v2/t6v1n_README.md', Path(__file__).resolve()]
    sources = {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs}
    r = app.read(BASE/'models_full.json')
    history = app.read(INDUSTRY)
    previous = [[next(q['total'] for q in history if q['market'] == 5 and q['product'] == p and q['country'] == c)
                 for c in app.COUNTRIES[:2]] for p in app.PRODUCTS]
    r.update(version='t6v1n', base_version='t6v1', training_base_version='t6v0',
        market_forecast=dict(method='previous_actual_total_times_one_plus_growth', unit='千单位',
            product_order=app.PRODUCTS, country_order=app.COUNTRIES,
            previous_totals=previous, growth_rates=[[.04, .05], [.04, .05]], new_market_totals=[5., 105.],
            previous_source=INDUSTRY.relative_to(ROOT).as_posix(),
            outlook_source=OUTLOOK.relative_to(ROOT).as_posix(),
            previous_scope='市场5正式5十队真实需求汇总，非销量；继承旧汇总口径及舍入限制',
            growth_scope='前景约4%/5%取点估计，非已实现增长',
            new_market_scope='前景5000/105000单位换算千单位；无历史基数，不补零增长',
            share_scope='继承t6v1十队归一化效用；逐决策重算；菲律宾迁移印尼，营销合计代理未识别细分'))
    save(out/'models_full.json', r)
    m = app.ApplicationModel(out)
    assert np.allclose(m.market_forecast({}), r['market_totals'])
    for p in [ROOT/'code/model_v2/t6v1.py', ROOT/'code/model_v2/t6v1n.py', Path(__file__).resolve()]:
        shutil.copy2(p, out/p.name)
    baseline = m.evaluate(m.baseline, details=True)
    save(out/'baseline_forecast.json', baseline)
    save(out/'example_request.json', dict(version='t6v1n', round=6, decision_vector=m.baseline.tolist(), scenario='中性'))
    checks, replay = verify(out)
    save(out/'checks.json', checks)
    save(out/'regression_replay.json', replay)
    lines = ['# t6v1n 自上而下需求预估', '',
        '先按产品、国家计算市场总量，再根据本公司与对手的价格、营销、研发估计十队份额，需求＝市场总量×本公司份额。需求接入原生产、物流、财务链；销量仍受供给约束。', '',
        '旧市场总量＝上回合十队真实需求合计×(1＋前景增长率)；菲律宾直接采用前景新市场总量。六个产品/国家市场各自计算，不再额外分配产品比例。', '',
        '| 产品 | 国家 | 正式5需求总量（千单位） | 增长率 | 正式6总量（千单位） | 基准预计份额 | 基准公司需求（千单位） |',
        '|---|---|---:|---:|---:|---:|---:|']
    for j, p in enumerate(app.PRODUCTS):
        for k, c in enumerate(app.COUNTRIES):
            prev = f'{previous[j][k]:.6f}' if k < 2 else '无历史'
            growth = ['4%', '5%', '新市场前景直接估计'][k]
            lines.append(f"| {p} | {c} | {prev} | {growth} | {baseline['market_totals'][j][k]:.6f} | {baseline['own_shares'][j][k]:.4%} | {baseline['demand'][j][k]:.6f} |")
    lines += ['', '表中采用t6v1保存的运行基准，仅说明模型分解，不是新的推荐方案或实时平台草稿。默认假设相同，预估与t6v1一致；此次不是精度提升或重新训练。', '',
        '继承对手上回合价格、公司营销费用代理、菲律宾迁移、正式6终局和期初状态缺口。总量为外生情景，不随本公司价格单独扩张；竞争份额随方案重算。', '',
        '验证覆盖基准及旧两候选×9情景共27次回归、份额和需求守恒、六市场涨价响应、营销/研发响应、总量及增长率扰动、零市场和非法输入、批量财务复算。旧候选仅用于回归，不作为新版优化推荐。', '',
        '[分层预估与财务结果](baseline_forecast.json) · [模型和来源](models_full.json) · [检查](checks.json) · [旧输入回归](regression_replay.json) · [示例请求](example_request.json)', '',
        '未重跑优化、未重训、未操作平台、未作独立前向精度验证；投标、分包、细分营销及财务机制的原有限制保留。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    documents = {}
    for rel in ['README.md', 'code/model_v2/README.md']:
        path = ROOT/rel
        backup = out/'documents_before'/rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        before = path.read_text(encoding='utf-8-sig')
        if rel == 'README.md':
            anchor = '| 回合6终局条件应用 |'
            entry = f'| 自上而下需求应用 | **t6v1n**：[分层预估]({out.relative_to(ROOT).as_posix()}/report.md)、[运行说明](code/model_v2/t6v1n_README.md) | 在t6v1上显式拆分历史总量、增长、新市场总量及逐决策竞争份额；27次默认回归通过，未重训或重跑优化，不是精度验收。 |\n'
        else:
            anchor = '- [t6v1终局应用]'
            entry = '- [t6v1n自上而下需求](t6v1n_README.md)：市场总量先估，再按竞争份额计算需求，接入生产/物流/财务；默认与t6v1一致，未重新优化。\n\n'
        assert anchor in before and 't6v1n' not in before
        path.write_text(before.replace(anchor, entry+anchor, 1), encoding='utf-8')
        documents[rel] = dict(before_sha256=sha(backup), backup_sha256=sha(backup), after_sha256=sha(path))
    links = []
    for path in [ROOT/p for p in documents]+[ROOT/'code/model_v2/t6v1n_README.md', out/'report.md']:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8-sig')):
            if '://' in target or target.startswith('#'):
                continue
            if not (path.parent/target.strip('<>').split('#')[0]).exists():
                assert path.is_relative_to(ROOT) and path.relative_to(ROOT).as_posix() in documents
                backup = out/'documents_before'/path.relative_to(ROOT)
                assert ']('+target+')' in backup.read_text(encoding='utf-8-sig')
                links.append(dict(document=path.relative_to(ROOT).as_posix(), preexisting_missing_target=target))
    save(out/'document_changes.json', documents)
    save(out/'link_checks.json', dict(new_links_valid=True, preexisting_gaps=links))
    for rel, expected in sources.items():
        assert sha(ROOT/rel) == expected, rel
    with (out/'work_log.md').open('a', encoding='utf-8') as f:
        f.write('\n\n状态：已完成。北京时间：'+datetime.now(timezone(timedelta(hours=8))).isoformat()+'。\n'
                '保存独立t6v1n应用及总量来源，复用冻结份额与财务链；27次回归及扰动/边界检查通过。说明文档备份、改前/改后SHA256及链接检查已保存。旧版本全部文件哈希未变。未重新优化或访问平台，非前向精度验证。\n')
    save(out/'manifest.json', dict(version='t6v1n', source_hashes=sources, documents=documents,
        output_hashes={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()}))
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        manifest = app.read(args.out/'manifest.json')
        for rel, expected in manifest['source_hashes'].items():
            assert sha(ROOT/rel) == expected, rel
        for rel, expected in manifest['output_hashes'].items():
            assert sha(args.out/rel) == expected, rel
        for rel, rec in manifest['documents'].items():
            assert sha(ROOT/rel) == rec['after_sha256']
            assert sha(args.out/'documents_before'/rel) == rec['before_sha256'] == rec['backup_sha256']
        print(json.dumps(verify(args.out)[0], ensure_ascii=False))
    else:
        build(args.out)
