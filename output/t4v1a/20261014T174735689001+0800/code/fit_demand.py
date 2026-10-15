"""Offline constrained demand fit. Run: python code/fit_demand.py."""
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import lsq_linear

from audit_incremental import ROOT
from archive_and_report import write_json, table_rows, number

COUNTRIES = ['泰国', '印尼']
NAMES = ['泰国截距', '印尼截距', '泰国价格弹性', '印尼价格弹性',
         '合计一般营销代理', '合计设计师营销代理', '研发投入代理']


def features(rows, persistence):
    """Prices in USD/unit; spend in thousand USD; reference scales are arbitrary."""
    assert 0 <= persistence <= 1
    x = np.zeros((len(rows), len(NAMES)))
    for i, row in enumerate(rows):
        country = COUNTRIES.index(row['market'])
        assert row['price'] > 0
        assert all(row[k] >= 0 for k in ['general', 'designer', 'rd', 'previous_rd'])
        x[i, country] = 1
        x[i, 2 + country] = -np.log(row['price'] / [1800, 2000][country])
        x[i, 4:] = np.log1p(np.array([row['general'], row['designer'],
                                    row['rd'] + persistence * row['previous_rd']]) / 1000)
    return x


def fit(x, y, penalty):
    assert len(y) == len(x) and np.all(y > 0) and penalty > 0
    assert np.all(np.isfinite(x)) and np.all(np.isfinite(y)) and np.isfinite(penalty)
    # Intercepts are free; all price elasticities and spend effects are nonnegative.
    regularizer = np.diag([0, 0] + [np.sqrt(penalty)] * 5)
    result = lsq_linear(np.vstack([x, regularizer]), np.r_[np.log(y), np.zeros(7)],
                        bounds=([-np.inf] * 2 + [0] * 5, np.full(7, np.inf)), tol=1e-12)
    assert result.success, result.message
    return result.x


def metrics(actual, predicted):
    assert len(actual) == len(predicted) and len(actual) > 0
    return dict(n=len(actual), MAE=float(np.mean(np.abs(actual - predicted))),
                WAPE=float(np.sum(np.abs(actual - predicted)) / np.sum(actual)))


def evaluate(rows, x, y, penalty, splits):
    out = []
    for name, train, test in splits:
        assert not set(train) & set(test)
        beta = fit(x[train], y[train], penalty)
        prediction = np.exp(x[test] @ beta)
        baseline = np.array([np.mean([y[j] for j in train
                                      if rows[j]['market'] == rows[i]['market']]) for i in test])
        records = [dict(team=rows[i]['team'], round=rows[i]['round'], market=rows[i]['market'], price=rows[i]['price'],
                        actual=float(y[i]), predicted=float(p), baseline=float(b),
                        supply_limited=rows[i]['supply_limited'], source=rows[i]['demand_source'])
                   for i, p, b in zip(test, prediction, baseline)]
        out.append(dict(fold=name, train_n=len(train), model=metrics(y[test], prediction),
                        baseline=metrics(y[test], baseline), coefficients=beta.tolist(), records=records))
    return out


def pooled(folds):
    records = [r for f in folds for r in f['records']]
    y = np.array([r['actual'] for r in records])
    p = np.array([r['predicted'] for r in records])
    b = np.array([r['baseline'] for r in records])
    return dict(model=metrics(y, p), baseline=metrics(y, b))


def nested_evaluate(rows, x, y, outer_splits):
    folds = []
    for name, train, test in outer_splits:
        inner_splits = [(team, [i for i in train if rows[i]['team'] != team],
                         [i for i in train if rows[i]['team'] == team])
                        for team in sorted({rows[i]['team'] for i in train})]
        scores = {penalty: pooled(evaluate(rows, x, y, penalty, inner_splits))['model']['WAPE']
                  for penalty in [.1, 1., 10.]}
        selected = min(scores, key=scores.get)
        fold = evaluate(rows, x, y, selected, [(name, train, test)])[0]
        fold.update(selected_penalty=selected, inner_scores=scores)
        folds.append(fold)
    return folds


def self_check():
    rng = np.random.default_rng(7)
    x = rng.normal(size=(100, 7))
    expected = np.array([1., 2., .4, .8, .2, .3, .5])
    assert np.max(np.abs(fit(x, np.exp(x @ expected), 1e-8) - expected)) < 1e-6
    row = dict(market='泰国', price=1800., general=400., designer=300., rd=600., previous_rd=0.)
    a = features([row], .5) @ expected
    assert (features([dict(row, price=1980.)], .5) @ expected)[0] < a[0]
    assert (features([dict(row, general=800.)], .5) @ expected)[0] > a[0]
    assert metrics(np.array([1., 3.]), np.array([2., 2.])) == dict(n=2, MAE=1., WAPE=.5)
    try:
        features([dict(row, price=0)], .5)
    except AssertionError:
        pass
    else:
        raise AssertionError('zero price was accepted')


def main():
    self_check()
    path = ROOT / '结构化模型输入.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    history = {(r['round'], r['team']): r for r in data['history'] if r['phase'] == 'practice'}
    rows = []
    for m in data['markets']:
        if not m['usable_for_fit']:
            continue
        assert m['phase'] == 'practice' and m['round'] in [1, 2]
        h = history[m['round'], m['team']]
        assert h['kind'] == 'actual_result'
        previous = history.get((m['round'] - 1, m['team']))
        fields = h['fields']
        rows.append(dict(team=m['team'], round=m['round'], market=m['market'],
                         price=m['price']['value'], demand=m['demand']['value'],
                         general=fields['general_marketing']['value'],
                         designer=fields['designer_marketing']['value'], rd=fields['rd']['value'],
                         previous_rd=previous['fields']['rd']['value'] if previous else 0.,
                         supply_limited=m['supply_limited'], demand_source=m['demand'],
                         price_source=m['price'], spend_sources={k: fields[k] for k in
                             ['general_marketing', 'designer_marketing', 'rd']},
                         previous_rd_source=previous['fields']['rd'] if previous else None))
    assert len(rows) == 40 and len({(r['round'], r['team'], r['market']) for r in rows}) == 40
    parsed = {}
    checked_sources = set()
    for row in rows:
        sources = [row['demand_source'], row['price_source'], *row['spend_sources'].values()]
        if row['previous_rd_source']:
            sources.append(row['previous_rd_source'])
        for source in sources:
            name = source['file']
            if name not in parsed:
                raw = json.loads((ROOT / name).read_text(encoding='utf-8'))
                parsed[name] = {r['line']: r for r in table_rows(raw['snapshot'])}
            original = parsed[name][source['line']]
            assert original['cells'][0] == source['label']
            assert number(original['cells'][source['column']]) == source['value']
            checked_sources.add((name, source['line'], source['column']))
    y = np.array([r['demand'] for r in rows])
    teams = sorted({r['team'] for r in rows})
    team_splits = [(team, [i for i, r in enumerate(rows) if r['team'] != team],
                    [i for i, r in enumerate(rows) if r['team'] == team]) for team in teams]
    round_splits = [('练习1训练→练习2验证', [i for i, r in enumerate(rows) if r['round'] == 1],
                     [i for i, r in enumerate(rows) if r['round'] == 2]),
                    ('练习2训练→练习1回看', [i for i, r in enumerate(rows) if r['round'] == 2],
                     [i for i, r in enumerate(rows) if r['round'] == 1])]
    # shortcut: total marketing is a proxy, replace when rival country allocations are available.
    x = features(rows, .5)
    beta = fit(x, y, 1.)
    team_folds = evaluate(rows, x, y, 1., team_splits)
    round_folds = evaluate(rows, x, y, 1., round_splits)
    nested_teams = nested_evaluate(rows, x, y, team_splits)
    nested_forward = nested_evaluate(rows, x, y, round_splits[:1])[0]
    price_only = x.copy()
    price_only[:, 4:] = 0
    ablation = dict(team_holdout=pooled(evaluate(rows, price_only, y, 1., team_splits)),
                    forward_holdout=evaluate(rows, price_only, y, 1., round_splits[:1])[0])
    assert all(len(f['records']) == 4 for f in team_folds)
    sensitivity = []
    for persistence in [0., .5, 1.]:
        xx = features(rows, persistence)
        for penalty in [.1, 1., 10.]:
            sensitivity.append(dict(rd_persistence=persistence, penalty=penalty,
                                    coefficients=fit(xx, y, penalty).tolist(),
                                    team_holdout=pooled(evaluate(rows, xx, y, penalty, team_splits)),
                                    forward_holdout=evaluate(rows, xx, y, penalty, round_splits[:1])[0]['model']))
    residuals = []
    records = [r for f in team_folds for r in f['records']]
    for country in COUNTRIES:
        for supply_limited in [False, True]:
            rr = [r for r in records if r['market'] == country and r['supply_limited'] == supply_limited]
            if rr:
                actual = np.array([r['actual'] for r in rr])
                predicted = np.array([r['predicted'] for r in rr])
                residuals.append(dict(market=country, supply_limited=supply_limited,
                                      **metrics(actual, predicted),
                                      mean_error=float(np.mean(predicted - actual))))
    price_groups = []
    for country, reference in zip(COUNTRIES, [1800, 2000]):
        for high in [False, True]:
            rr = [r for r in records if r['market'] == country and (r['price'] > reference) == high]
            if rr:
                actual = np.array([r['actual'] for r in rr])
                predicted = np.array([r['predicted'] for r in rr])
                price_groups.append(dict(market=country, price_band='高于初始价' if high else '不高于初始价',
                                         **metrics(actual, predicted)))
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()}
    for source in sorted({r['demand_source']['file'] for r in rows}):
        hashes[source] = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    result = dict(generated_at=datetime.now(timezone.utc).isoformat(), status='EXPLORATORY_NOT_DECISION_READY',
                  coefficient_names=NAMES, coefficients=beta.tolist(), penalty=1., rd_persistence=.5,
                  formula='D=exp(country_intercept - country_elasticity*log(P/P0) + bg*log1p(G/1000) + bd*log1p(M/1000) + br*log1p((R+rho*Rprev)/1000))',
                  reference_prices=dict(泰国=1800, 印尼=2000),
                  units=dict(demand='千单位', price='美元/单位', spend='千美元'),
                  objective='sum((log(D)-Xb)^2)+lambda*sum(b[2:]^2)',
                  source_hashes=hashes, source_cell_check_count=len(checked_sources), input_rows=rows,
                  training=metrics(y, np.exp(x @ beta)), team_holdout=team_folds,
                  team_holdout_pooled=pooled(team_folds), round_holdout=round_folds,
                  nested_team_holdout=nested_teams, nested_team_pooled=pooled(nested_teams),
                  nested_forward_holdout=nested_forward,
                  residual_groups=residuals, price_groups=price_groups, price_only_ablation=ablation,
                  sensitivity=sensitivity,
                  self_checks='synthetic recovery, monotonicity, metrics, invalid input and fold disjointness passed',
                  limitations=['营销为两国合计代理，不是国别实际投入；不得用于国别营销优化',
                      '研发延续仅用已知练习投入，不代表完整历史存量；rho是假设',
                      '团队留出仍共享市场环境；只有两个回合，非独立市场泛化证明',
                      '回合2研发滞后使用预测时已发生的回合1投入，不使用回合2需求',
                      '回看验证使用后期样本，不是未来预测；前向验证仅一个时间切分',
                      '未建模行业需求增长、竞争者投入、营销延续和市场份额约束',
                      '截距代表训练环境；正式1重置状态，不能直接用全练习拟合预测',
                      '参数为关联而非因果；约束不证明平台真实机制；敏感性网格不用于择优报分',
                      '嵌套验证只在外层训练样本内选lambda；rho固定0.5，未从验证集选择',
                      '未采集正式实际结果，未修改网页，未建立六回合优化器'])
    write_json(ROOT / '需求拟合与留出核验.json', result)
    print(json.dumps(dict(training=result['training'], team_holdout=result['team_holdout_pooled'],
                          forward=round_folds[0]['model'], forward_baseline=round_folds[0]['baseline'],
                          coefficients=dict(zip(NAMES, beta.tolist()))), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
