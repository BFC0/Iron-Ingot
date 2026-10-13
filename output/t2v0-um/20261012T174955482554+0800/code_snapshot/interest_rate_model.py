"""Fit actual Cesim borrowing rates; append-only outputs, no platform writes."""
import argparse
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

import formal_update_state as state_source
import formal_update_train as source

ROOT = Path(__file__).resolve().parents[1]
FORMS = ('solvency_exponential', 'leverage_power')


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def ratios(state):
    values = [state[k] for k in ('equity', 'assets', 'long_debt', 'short_debt')]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        raise ValueError('Financial inputs must be finite numbers in thousand USD')
    equity, assets, long, short = values
    if equity <= 0 or assets <= 0 or equity > assets or min(long, short) < 0 or long + short > assets - equity + 1:
        raise ValueError('Outside scope: positive equity/assets and consistent nonnegative debt required')
    return dict(equity_ratio=equity / assets, leverage=(long + short) / equity)


def premium(form, p, rows):
    if form == 'solvency_exponential':
        return p[0] * np.exp(-p[1] * np.array([r['equity_ratio'] for r in rows]))
    return p[0] * np.array([r['leverage'] for r in rows]) ** p[1]


def fit(form, rows):
    y = np.array([r['premium'] for r in rows])
    result = least_squares(lambda p: premium(form, p, rows) - y, [.02, 2],
                           bounds=([0, .000001], [10, 30]), max_nfev=4000)
    if not result.success:
        raise RuntimeError(result.message)
    return result.x.tolist()


def select(rows):
    scores = {}
    for form in FORMS:
        errors = []
        for market in sorted({r['market_id'] for r in rows}):
            train = [r for r in rows if r['market_id'] != market]
            test = [r for r in rows if r['market_id'] == market]
            errors.extend((premium(form, fit(form, train), test) - [r['premium'] for r in test]).tolist())
        scores[form] = float(np.mean(np.abs(errors)) * 10000)
    return min(scores, key=scores.get), scores


def predict(model, state, base_rate_percent, short_spread_percent):
    if not all(math.isfinite(v) and v >= 0 for v in (base_rate_percent, short_spread_percent)):
        raise ValueError('Rates must be finite nonnegative percentages')
    features = ratios(state)
    outside = [k for k, v in features.items() if not model['ranges'][k][0] <= v <= model['ranges'][k][1]]
    if outside:
        raise ValueError('Outside training range: ' + ', '.join(outside))
    long = base_rate_percent + float(premium(model['form'], model['parameters'], [features])[0]) * 100
    band = model['conditional_error_p90_basis_points'] / 100
    return dict(status='CONDITIONAL_FORECAST', long_rate_percent=long,
                short_rate_percent=long + short_spread_percent,
                long_rate_empirical_error_band_percent=[max(base_rate_percent, long - band), long + band],
                features=features, inputs=dict(predicted_closing_state=state,
                base_rate_percent=base_rate_percent, short_spread_percent=short_spread_percent),
                limitation='Band is empirical conditional residual spread, not a confidence interval; excludes financial-state forecast error and future rule changes')


def self_check():
    rows = [dict(equity_ratio=x, leverage=(1-x)/x) for x in np.linspace(.2, .8, 20)]
    for form in FORMS:
        y = premium(form, [.004, 2], rows)
        fitted = fit(form, [dict(r, premium=float(v)) for r, v in zip(rows, y)])
        assert np.max(abs(premium(form, fitted, rows) - y)) < 1e-6
        assert premium(form, [.004, 2], rows)[0] > premium(form, [.004, 2], rows)[-1]
    model = dict(form=FORMS[0], parameters=[.004, 2], ranges=dict(equity_ratio=[.2, .8], leverage=[.25, 4]), conditional_error_p90_basis_points=2)
    state = dict(equity=50, assets=100, long_debt=40, short_debt=10)
    p = predict(model, state, 3, 1.5)
    assert abs(p['short_rate_percent'] - p['long_rate_percent'] - 1.5) < 1e-12
    assert abs(predict(model, state, 2.5, 2)['long_rate_percent'] - p['long_rate_percent'] + .5) < 1e-12
    for bad in [dict(state, equity=0), dict(state, assets=float('nan')), dict(state, short_debt=-1), dict(state, long_debt=90), dict(state, equity=1)]:
        try:
            predict(model, bad, 3, 1.5)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid/out-of-range input accepted')


def train():
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out = ROOT / 'output/interest_rate' / stamp
    out.mkdir(parents=True, exist_ok=False)
    log = out / 'work_log.md'
    log.write_text(f'# 实际贷款利率模型工作日志\n\n北京时间：{stamp}。进行中。\n用户授权建立预测模型；读取正式1归档、独立训练，不修改平台或旧模型。不要输出真名，姓名统一用首字母替代。只输出市场和列编号。\n', encoding='utf-8')
    write(out / 'manifest.json', dict(status='RUNNING'))
    rows, hashes = [], {}
    outlook = source.SOURCE / 'formal1_outlook.json'
    cells = [r['cells'] for r in source.table_rows(source.read(outlook)['snapshot']) if r['cells'] and r['cells'][0] == '基准利率']
    assert len(cells) == 1 and source.old.numeric(cells[0][1]) == 3
    hashes[outlook.relative_to(ROOT).as_posix()] = source.core.digest(outlook)
    for market in range(1, 11):
        path = source.SOURCE / f'market_{market}_formal1.json'
        states = state_source.parse_state(path)
        doc = source.read(path)
        for p in (path, ROOT / doc['selection_file']):
            hashes[p.relative_to(ROOT).as_posix()] = source.core.digest(p)
        for item in states:
            state = item['formal1_end_state']
            rate = source.field(path, '长期贷款利率，%', item['team_column'])
            refs = {k: dict(item['fields'][k], file=path.relative_to(ROOT).as_posix()) for k in ('equity', 'assets', 'long_debt', 'short_debt')}
            rows.append(dict(market_id=market, team_column=item['team_column'], phase='formal', round=1,
                             **ratios(state), rate_percent=rate['value'], premium=rate['value']/100-.03,
                             state={k: state[k] for k in refs}, sources=dict(**refs, rate=rate)))
    assert len(rows) == 100 and len({(r['market_id'], r['team_column']) for r in rows}) == 100
    assert all(r['premium'] >= -.00005 for r in rows)
    write(out / 'dataset.json', dict(rows=rows, base_rate_source=dict(file=outlook.relative_to(ROOT).as_posix(), value_percent=3)))
    self_check()
    outer = []
    for market in range(1, 11):
        tr = [r for r in rows if r['market_id'] != market]
        te = [r for r in rows if r['market_id'] == market]
        form, scores = select(tr)
        params = fit(form, tr)
        for r, pred in zip(te, premium(form, params, te)):
            outer.append(dict(market_id=market, team_column=r['team_column'], form=form,
                              inner_scores_bp=scores, predicted_rate_percent=3+float(pred)*100,
                              actual_rate_percent=r['rate_percent'], error_bp=float(pred-r['premium'])*10000))
    form, scores = select(rows)
    errors = np.array([r['error_bp'] for r in outer])
    model = dict(form=form, parameters=fit(form, rows), candidate_cv_mae_basis_points=scores,
                 training_phase='formal', training_round=1, training_n=100, shared_market_assumption=True,
                 nested_market_holdout_mae_basis_points=float(np.mean(abs(errors))),
                 nested_market_holdout_max_error_basis_points=float(np.max(abs(errors))),
                 conditional_error_p90_basis_points=float(np.quantile(abs(errors), .9)),
                 ranges={k: [min(r[k] for r in rows), max(r[k] for r in rows)] for k in ('equity_ratio', 'leverage')},
                 formulas=dict(solvency_exponential='r_long = r_base + a * exp(-b * equity/assets)',
                               leverage_power='r_long = r_base + a * ((long_debt+short_debt)/equity)^b',
                               short='r_short = r_long + published_short_spread'),
                 units=dict(internal_rate='decimal', output_rate='percent', financial_state='thousand USD'),
                 validation_scope='Same-round conditional validation on actual closing states; not prospective round2 validation')
    write(out / 'model.json', model)
    write(out / 'validation.json', dict(self_checks_passed=True, nested_market_holdouts=outer))
    own = next(r for r in rows if r['market_id'] == 5 and r['team_column'] == 6)
    # shortcut: next-round closing state is unknown; replace unchanged-state scenario with a verified financial forecast when available.
    scenario = predict(model, own['state'], 2.5, 2)
    scenario.update(scenario_only=True, state_assumption='formal1 closing state held constant; not an actual round2 closing forecast',
                    rate_assumption='archived round2 outlook parameters', market_id=5, team_column=6)
    round2 = source.SOURCE / 'formal2_outlook.json'
    rr = source.table_rows(source.read(round2)['snapshot'])
    for label, value in [('基准利率', 2.5), ('高于基准的短期利率溢价', 2)]:
        cc = [r['cells'] for r in rr if r['cells'] and r['cells'][0] == label]
        assert len(cc) == 1 and source.old.numeric(cc[0][1]) == value
    scenario['rate_parameter_source'] = round2.relative_to(ROOT).as_posix()
    hashes[round2.relative_to(ROOT).as_posix()] = source.core.digest(round2)
    write(out / 'scenario.json', scenario)
    snapshot = out / 'code_snapshot'
    snapshot.mkdir()
    for p in [Path(__file__), * (ROOT/'code').glob('*.py'), * (ROOT/'code/model_v2').glob('*.py')]:
        target = snapshot / p.relative_to(ROOT/'code')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    report = f'''# 实际贷款利率预测模型\n\n“实际”指实际支付的贷款利率。规则来源：sources/决策指南_逐页文本.txt，第303–307行。预测栏是玩家估计，不能作为实际标签。\n\n正式1十市场100家公司，按用户已有同期市场共享假设合并。使用期末权益/资产或有息债务/权益解释风险溢价。候选函数通过内层整市场留出选择，外层每次留出一个市场，外层标签不参与选型。训练期基准利率3%。\n\n选定函数：{form}；参数：{model['parameters']}。公式和单位见model.json。短贷利率在长期利率上加当期公开溢价；短贷公式来自规则，并未独立拟合实际短贷利息。\n\n嵌套留出MAE：{model['nested_market_holdout_mae_basis_points']:.4f}基点；最大误差：{model['nested_market_holdout_max_error_basis_points']:.4f}基点；绝对误差90%分位：{model['conditional_error_p90_basis_points']:.4f}基点。1基点=0.01个百分点。这是给定实际期末财务状态的条件检验，不能当下一回合事前预测成绩。误差带不是置信区间，也不含期末状态预测误差。\n\n接口predict(model, predicted_closing_state, base_rate_percent, short_spread_percent)，财务单位千美元，利率参数用百分数，例如2.5。期末权益、资产、长贷、短贷须来自经营财务预测；不接受非有限数、非正权益、负债不一致或训练范围之外的数据。当前模型没有识别计息时点，不能直接证明还贷带来的因果节息。\n\n市场5第6列保持正式1期末状态不变，基准2.5%、短贷附加2个百分点的情景：长贷{scenario['long_rate_percent']:.4f}%，短贷{scenario['short_rate_percent']:.4f}%。这是状态不变情景，不能直接作为正式2建议填写值。参数来源：{scenario['rate_parameter_source']}。\n\n复现：运行code/interest_rate_model.py train；每次写入新的时间戳目录。预测：运行同脚本predict --model <model.json> --state <state.json> --base-rate 2.5 --short-spread 2。state.json包含equity、assets、long_debt、short_debt。运行self-check可执行合成恢复、风险单调、单位换算及非法输入检查。原件哈希和快照见manifest.json，字段行列见dataset.json。\n\n未覆盖：非正权益、训练范围之外、跨回合验证、未知未来基准利率、完整财务联立及计息机制。旧模型和平台决策未修改。\n'''
    (out / 'report.md').write_text(report, encoding='utf-8')
    assert all(source.core.digest(ROOT / p) == sha for p, sha in hashes.items())
    with log.open('a', encoding='utf-8') as f:
        f.write('\n完成：100条实际标签、嵌套整市场验证、自检、情景预测和来源哈希检查通过。当前网页未访问，身份/回合仅核验归档，不代表实时状态。旧证据及平台未改动；尚无事前跨回合验证。\n')
    write(out / 'manifest.json', dict(status='COMPLETE', input_hashes=hashes,
          output_hashes={p.relative_to(out).as_posix(): source.core.digest(p) for p in out.rglob('*') if p.is_file() and p.name != 'manifest.json'}))
    print(json.dumps(dict(output=str(out), form=form, mae_bp=model['nested_market_holdout_mae_basis_points'], scenario=scenario), ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('train')
    sub.add_parser('self-check')
    p = sub.add_parser('predict')
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--base-rate', type=float, required=True)
    p.add_argument('--short-spread', type=float, required=True)
    args = parser.parse_args()
    if args.command == 'train':
        train()
    elif args.command == 'self-check':
        self_check()
        print('Self-checks passed')
    else:
        print(json.dumps(predict(source.read(args.model), source.read(args.state), args.base_rate, args.short_spread), ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
