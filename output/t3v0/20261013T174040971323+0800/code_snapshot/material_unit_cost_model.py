"""Empirical raw-material cost model; train and predict without platform writes."""
import argparse
import csv
import hashlib
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/settlement_parameter_comparison/20261012_audit'
FORMS = ('published', 'additive', 'proportional')


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def fit(rows, form):
    if not rows or form not in FORMS:
        raise ValueError('Nonempty training rows and a supported form are required')
    if form == 'published':
        return dict(form=form, parameter=0, compatible_interval=None)
    x = [r['production'] * (r['published_material'] if form == 'proportional' else 1) for r in rows]
    y = [r['material_cost'] - r['production'] * r['published_material'] for r in rows]
    parameter = sum(a*b for a, b in zip(x, y)) / sum(a*a for a in x)
    intervals = [(r['implied_low']-r['published_material'], r['implied_high']-r['published_material']) for r in rows]
    if form == 'proportional':
        intervals = [(lo/r['published_material'], hi/r['published_material']) for r, (lo, hi) in zip(rows, intervals)]
    lo, hi = max(v[0] for v in intervals), min(v[1] for v in intervals)
    interval = [lo, hi] if lo <= hi else None
    if interval:
        parameter = min(max(parameter, lo), hi)
    return dict(form=form, parameter=parameter, compatible_interval=interval)


def predict(model, published_price, production):
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (published_price, production)) or published_price <= 0 or production < 0:
        raise ValueError('Published price must be positive and production nonnegative, finite numbers')
    form, p = model['form'], model['parameter']
    if form not in FORMS or not math.isfinite(p):
        raise ValueError('Invalid model')
    unit = published_price * (1+p) if form == 'proportional' else published_price+p
    if unit <= 0:
        raise ValueError('Nonpositive fitted unit cost')
    return dict(unit_cost_usd=unit, material_cost_kusd=production*unit,
                published_price_usd=published_price, production_kunits=production,
                scope='Empirical materials-purchase cost, not all variable production costs')


def evaluate(model, rows):
    details = []
    for r in rows:
        p = predict(model, r['published_material'], r['production'])
        tolerance = .5 + .005*p['unit_cost_usd']
        details.append(dict(phase=r['phase'], market=r['market'], team=r['team'],
            actual_cost_kusd=r['material_cost'], **p,
            error_kusd=p['material_cost_kusd']-r['material_cost'],
            display_tolerance_kusd=tolerance,
            display_compatible=abs(p['material_cost_kusd']-r['material_cost']) <= tolerance+1e-9))
    return dict(n=len(rows), mae_kusd=mean(abs(r['error_kusd']) for r in details),
                max_abs_error_kusd=max(abs(r['error_kusd']) for r in details),
                display_compatible_n=sum(r['display_compatible'] for r in details), records=details)


def select(rows):
    scores = {}
    for form in FORMS:
        details = []
        for market in sorted({r['market'] for r in rows}):
            train = [r for r in rows if r['market'] != market]
            test = [r for r in rows if r['market'] == market]
            assert not {r['market'] for r in train} & {r['market'] for r in test}
            details.extend(evaluate(fit(train, form), test)['records'])
        scores[form] = dict(mae_kusd=mean(abs(r['error_kusd']) for r in details),
                            display_compatible_n=sum(r['display_compatible'] for r in details))
    winner = min(FORMS, key=lambda f: (-scores[f]['display_compatible_n'], scores[f]['mae_kusd']))
    return winner, scores


def self_check():
    model = dict(form='proportional', parameter=.002)
    assert predict(model, 900, 10)['material_cost_kusd'] == 9018
    assert predict(model, 1053, 0)['material_cost_kusd'] == 0
    for price, q in [(0, 1), (900, -1), (float('nan'), 1), (900, float('inf')), (True, 1)]:
        try:
            predict(model, price, q)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid inputs accepted')
    synthetic = [dict(production=q, published_material=b, material_cost=q*b*1.002,
                      implied_low=b*1.002, implied_high=b*1.002)
                 for q, b in [(10, 900), (20, 1053)]]
    assert abs(fit(synthetic, 'proportional')['parameter']-.002) < 1e-12


def train():
    self_check()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out = ROOT / 'output/material_unit_cost' / stamp
    out.mkdir(parents=True, exist_ok=False)
    log = out/'work_log.md'
    log.write_text(f'# 原材料单位费用模型\n\n开始：{stamp}。用户授权建立模型。不要输出真名，姓名统一用首字母替代。\n'
                   '复用已核验材料记录与原件哈希，独立产物；不替换旧模型、不改平台决策。\n', encoding='utf-8')
    audit = json.loads((SOURCE/'verification.json').read_text(encoding='utf-8'))
    hashes = audit['source_sha256']
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == sha for p, sha in hashes.items())
    csv_path = SOURCE/'逐队对照.csv'
    hashes = dict(hashes, **{csv_path.relative_to(ROOT).as_posix(): hashlib.sha256(csv_path.read_bytes()).hexdigest()})
    rows = list(csv.DictReader(csv_path.open(encoding='utf-8-sig')))
    for r in rows:
        for key in ('production', 'published_material', 'material_cost', 'implied_low', 'implied_high'):
            r[key] = float(r[key])
        r['market'] = int(r['market'])
        assert all(math.isfinite(r[k]) for k in ('production', 'published_material', 'material_cost'))
        assert r['production'] > .005 and r['published_material'] > 0 and r['material_cost'] >= 0
    assert len(rows) == 300 and len({(r['phase'], r['market'], r['column']) for r in rows}) == 300
    prior = [r for r in rows if r['phase'] != '正式1']
    held = [r for r in rows if r['phase'] == '正式1']
    assert len(prior) == 200 and len(held) == 100
    form, cv = select(prior)
    practice_model = fit(prior, form)
    historical_test = evaluate(practice_model, held)
    outer = []
    for market in range(1, 11):
        tr = [r for r in prior if r['market'] != market]
        te = [r for r in prior if r['market'] == market]
        selected, inner = select(tr)
        outer.append(dict(held_market=market, selected=selected, inner_scores=inner,
                          evaluation=evaluate(fit(tr, selected), te)))
    model = fit(rows, form)
    model.update(model_id='material_unit_cost_v1', training_n=300,
                 training_phases=['练习1', '练习2', '正式1'], published_price_range=[900, 1053],
                 formula='unit_cost = published_price * (1 + parameter)' if form == 'proportional' else 'unit_cost = published_price + parameter',
                 cost_formula='material_cost_kusd = production_kunits * unit_cost_usd',
                 validation_scope='Retrospective practice selection and formal1 holdout; no frozen prospective score',
                 assumption='Shared material adjustment across observed phases and markets; not a verified platform rule',
                 limitations=['前景基准仅独立采集市场5，跨市场共享为假设', '只建模原材料购买，不含工资、运输、库存或其他费用',
                              '跨回合稳定性只在已观察范围检验，正式2无实际标签',
                              '舍入区间不是置信区间，真实显示舍入模式未核实', '使用给定产量，产量预测误差未包括在条件误差内'])
    validation = dict(practice_selected=practice_model, selection_cv=cv, formal1_historical_holdout=historical_test,
                      nested_practice_market_holdouts=outer, all_data_fit=evaluate(model, rows),
                      candidate_fits={f: fit(prior, f) for f in FORMS})
    examples = {str(price): predict(model, price, 16.45) for price in (900, 1053)}
    lines = ['# 原材料单位费用模型', '',
        '**独立经验模型，不替换历史财务模型。** 参数范围与回合来源须在调用时核对。', '',
        f"选型：{form}；最终参数={model['parameter']:.12g}。", '',
        f"公式：`{model['formula']}`；`{model['cost_formula']}`。基础单价为当期前景美元/单位，产量为千单位，总费为千美元。", '',
        '| 基础价 | 预测单位费用（美元/单位） | 增加额 |', '| ---: | ---: | ---: |']
    for price, example in examples.items():
        lines.append(f"| {price} | {example['unit_cost_usd']:.6f} | {example['unit_cost_usd']-float(price):.6f} |")
    lines.extend(['', '| 候选 | 练习两轮整市场留出MAE（千美元） | 舍入兼容条数/200 |', '| --- | ---: | ---: |'])
    for name, score in cv.items():
        lines.append(f"| {name} | {score['mae_kusd']:.6f} | {score['display_compatible_n']} |")
    nested_mae = mean(abs(r['error_kusd']) for fold in outer for r in fold['evaluation']['records'])
    lines.extend(['', f"先用练习1/2共200条训练选型，再回溯核验正式1的100条：MAE={historical_test['mae_kusd']:.6f}千美元，最大绝对误差={historical_test['max_abs_error_kusd']:.6f}千美元，舍入兼容{historical_test['display_compatible_n']}/100。这次模型在结果已知后建立，不是冻结事前预测成绩。", '',
        f'练习嵌套整市场留出MAE={nested_mae:.6f}千美元；外层留出市场不会参与内层模型选择。最终300条重拟合后样本内舍入兼容{validation["all_data_fit"]["display_compatible_n"]}/300。', '',
        '拟合对总费用残差做最小二乘，不对低产量的反算单价等权拟合；若存在共同显示兼容区间，将参数限制在区间中。相同比例只有一个参数，可解释不同基础价下的不同单位差额；材料差额的内部原因仍未知。', '',
        f"全部300条比例参数显示兼容区间：{model['compatible_interval']}。区间只反映产量±0.005千单位、总费±0.5千美元的显示兼容性，不是统计置信区间。", '',
        '调用：`python code/material_unit_cost_model.py predict --model <本目录/model.json> --price 1053 --production 16.45`。训练：`python code/material_unit_cost_model.py train`，每次独立时间戳归档。', '',
        '限制：'+'；'.join(model['limitations'])+'。跨期共享是经验假设，不是由同期市场共享要求自动推导。未来原料价格或费用规则变化时，使用新回合实际重新校准。'])
    write(out/'model.json', model)
    write(out/'validation.json', validation)
    write(out/'inputs.json', rows)
    write(out/'examples.json', examples)
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    shutil.copy2(__file__, out/Path(__file__).name)
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == sha for p, sha in hashes.items())
    write(out/'verification.json', dict(source_sha256=hashes, source_hashes_unchanged=True,
        checks=['input validation', 'synthetic fit', '300 unique records', 'nested market isolation', 'original sources unchanged']))
    with log.open('a', encoding='utf-8') as f:
        f.write('\n完成：候选比较、嵌套整市场留出、正式1独立历史检验、全数据重拟合、调用示例与原件哈希检查通过。\n')
    print(json.dumps(dict(output=str(out), model=model, formal1_mae_kusd=historical_test['mae_kusd'],
                         formal1_display_compatible=historical_test['display_compatible_n']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('train')
    pred = sub.add_parser('predict')
    pred.add_argument('--model', type=Path, required=True)
    pred.add_argument('--price', type=float, required=True)
    pred.add_argument('--production', type=float, required=True)
    args = parser.parse_args()
    if args.command == 'train':
        train()
    else:
        model = json.loads(args.model.read_text(encoding='utf-8'))
        result = predict(model, args.price, args.production)
        result['published_price_outside_training_range'] = not model['published_price_range'][0] <= args.price <= model['published_price_range'][1]
        print(json.dumps(result, ensure_ascii=False, indent=2))
