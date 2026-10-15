"""Independent country/context demand fits; python code/model_v2/country_demand.py."""
from datetime import datetime, timedelta, timezone
import shutil

from core import *
from context import tag
from demand import cv, prediction_rows


NAMES = ['price', 'general_total_proxy', 'designer_total_proxy', 'rd_curve']
# shortcut: archived competitor marketing is company-total only; use country spend when history is available.
CONFIGS = [dict(standardized=True, piecewise=False, rho=.5, penalty=p, loss=loss)
           for loss in ['log', 'share'] for p in PENALTIES]


def select(rows, params):
    path = []
    for config in CONFIGS:
        error, scales = cv(rows, params, config)
        path.append(dict(config=config, cv_share_mae_pp=100*error, fold_scales=scales))
    winner = min(path, key=lambda r: r['cv_share_mae_pp'])
    return winner['config'], path


def fit_country(rows, params):
    if len({r['country'] for r in rows}) != 1 or len({r['context_id'] for r in rows}) != 1:
        raise ValueError('A country model requires one country and one verified context')
    if not all(r['context_fit_eligible'] for r in rows):
        raise ValueError('Unverified or incomplete training rows')
    selected, path = select(rows, params)
    model = fit(rows, params, **selected)
    indices = [COUNTRIES.index(rows[0]['country']), 2, 3, 4]
    model.update(country=rows[0]['country'], context_id=rows[0]['context_id'],
                 coefficients=dict(zip(NAMES, [model['beta'][i] for i in indices])),
                 cv_path=path, selected_cv_share_mae_pp=min(r['cv_share_mae_pp'] for r in path),
                 parameter_count=4, marketing_input='company_total_proxy',
                 cv_interpretation='内部留队选参误差，不是独立验证成绩')
    return model


def predict_country(rows, model, params):
    if not rows or any(r['country'] != model['country'] or r['context_id'] != model['context_id'] for r in rows):
        raise ValueError('Prediction country/context does not match model')
    return predict(rows, features(rows, params, model['rho'], model['piecewise']), model['beta'])


def validate(models, rows, params):
    for model in models.values():
        rr = [r for r in rows if r['country'] == model['country'] and r['context_id'] == model['context_id']]
        assert all(k[4] == model['country'] and k[6] == model['context_id'] for k in model['training_keys'])
        other_price = 1 - COUNTRIES.index(model['country'])
        assert model['beta'][other_price] == 0
        p = predict_country(rr, model, params)
        assert np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))
        for ids in old.groups(rr).values():
            assert abs(sum(p[ids])-1) < 1e-12
        for config in [r['config'] for r in model['cv_path']]:
            assert config['rho'] == .5 and not config['piecewise']
        # A country's fitted coefficients must not depend on data from the other country.
        changed = [dict(r, general=r['general']+1000, demand=r['demand']+1)
                   if r['country'] != model['country'] else r for r in rows]
        sub = [r for r in changed if r['country'] == model['country'] and r['context_id'] == model['context_id']]
        replay = fit(sub, params, **{k:model[k] for k in CONFIGS[0]})
        assert np.allclose(replay['beta'], model['beta'], rtol=0, atol=1e-12)
        bumped = [dict(r, general=r['general']+1000) if i == 0 else r for i,r in enumerate(rr)]
        pp = predict_country(bumped, model, params)
        assert pp[0] >= p[0]-1e-12
        if model['coefficients']['general_total_proxy'] > 1e-7:
            assert pp[0] > p[0]
        try:
            predict_country([dict(rr[0], country=COUNTRIES[other_price])], model, params)
        except ValueError:
            pass
        else:
            raise AssertionError('Cross-country prediction accepted')
    return dict(country_training_isolation=True, replay=True, share_conservation=True,
                marketing_response=True, country_boundary_rejection=True,
                cv_train_test_disjoint='asserted by demand.cv on every fold')


def main():
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out = ROOT/'output/country_demand'/stamp
    out.mkdir(parents=True, exist_ok=False)
    rows, cells, sources = old.load_dataset()
    context = tag(rows)
    params = read(FROZEN)['rd_curve_parameters']
    models, predictions = {}, []
    for context_id in sorted({r['context_id'] for r in rows if r['context_fit_eligible']}):
        for country in COUNTRIES:
            rr = [r for r in rows if r['context_fit_eligible'] and r['context_id'] == context_id and r['country'] == country]
            name = f'{context_id}/{country}'
            model = fit_country(rr, params)
            models[name] = model
            pr = prediction_rows(rr, model, params, name, rr)
            for r in pr:
                r.update(context_id=context_id, category='in_sample_independent_country_model', external_validation=False)
            predictions.extend(pr)
            print(name, model['coefficients'], flush=True)
    checks = validate(models, rows, params)
    snapshot = out/'code_snapshot'
    snapshot.mkdir()
    for path in [*Path(__file__).parent.glob('*.py'), ROOT/'code/cross_market_validation.py',
                 ROOT/'code/stepwise_model.py', ROOT/'code/archive_and_report.py']:
        shutil.copy2(path, snapshot/path.name)
    result = dict(model_id='COUNTRY_DEMAND_V1', status='INDEPENDENT_COUNTRY_CONTEXT_RESEARCH',
                  models=models, predictions=predictions, context=context,
                  formula='u_i,c=-e_c*ln(P_i/P0_i)+b_G,c*ln(1+G_total/1000)+b_H,c*ln(1+H_total/1000)+b_R,c*ln(f_R(R+.5*Rprev)); share=softmax(u); demand=T_c*share',
                  assumptions=['各国各情境系数与正则参数独立估计', '营销仍是两国合计代理，不能评估国别预算重新分配',
                               '研发曲线沿用冻结曲线；练习2适用性仍是假设', '行业总量外生给定，没有新增行业营销总量模型',
                               'rho=.5固定用于与既有模型比较；非因果模型'],
                  limitations=['每国每情境10队样本；内部选参误差与样本内成绩不能视为独立验证',
                               '其他市场未核情境隔离；无正式实际外部验证'],
                  sources=sources, frozen_curve_source=dict(file=FROZEN, sha256=digest(ROOT/FROZEN)),
                  code_hashes={p.name:digest(p) for p in snapshot.iterdir()}, validation=checks)
    write(out/'model.json', result)
    write(out/'validation.json', checks)
    lines = ['# 分国家独立需求模型', '', f'模型：COUNTRY_DEMAND_V1；运行：{stamp}。', '',
             '泰国、印尼在每个已核情境中单独训练，价格、一般营销、设计师营销、研发系数均不共享。旧模型不覆盖。', '',
             '营销投入仍为两国合计代理，不能识别国别支出分配效果；行业总需求为外生输入。研发延续权重固定0.5。', '',
             '每国每情境10队；按整队留出选择正则及log/share损失。下表为内部选参成绩，没有独立外部验证。', '',
             '| 情境 | 国家 | 价格 | 一般营销合计代理 | 设计师营销合计代理 | 研发 | 内部CV份额MAE(pp) |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for name, m in models.items():
        lines.append('| '+m['context_id']+' | '+m['country']+' | '+
                     ' | '.join(f'{m["coefficients"][k]:.6g}' for k in NAMES)+f' | {m["selected_cv_share_mae_pp"]:.4f} |')
    lines += ['', '公式：`u=-e_c ln(P/P0)+b_G,c ln(1+G_total/1000)+b_H,c ln(1+H_total/1000)+b_R,c ln(f_R(R+0.5Rprev))`；同编号市场、回合、国家内softmax归一；`D=T_c×share`。', '',
              '复现：`python code/model_v2/country_demand.py`。预测接口：`predict_country(rows, model, params)`；国家和情境必须匹配，完整竞争集合由调用方提供。', '',
              '核验通过：训练国家隔离、重算一致、份额守恒、营销响应、拒绝跨国预测、留队训练/验证键不重叠。', '',
              '完整参数、样本键、CV路径、来源哈希及样本内预测见同目录model.json；代码快照见code_snapshot。尚未验证正式实际结果。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('OUTPUT', out, flush=True)


if __name__ == '__main__':
    main()
