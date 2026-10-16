"""Explain A/B Indonesia price coefficients without changing frozen models."""
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import lsq_linear

from audit_incremental import ROOT
from cross_market_validation import (load_dataset, feature_matrix, fit, groups, weights,
                                     predict_shares, choose_penalty, metric, PENALTIES)


def centered(rows, params):
    rows = [r for r in rows if r['demand'] > 0]
    x = feature_matrix(rows, params)
    y = np.log([r['demand'] for r in rows])
    for ids in groups(rows).values():
        x[ids] -= x[ids].mean(axis=0)
        y[ids] -= y[ids].mean()
    return rows, x, y


def solve(rows, x, y, penalty, fixed=None):
    w = np.sqrt(weights(rows))
    keep = list(range(x.shape[1]))
    if fixed is not None:
        keep.remove(1)
        y = y - x[:, 1] * fixed
    result = lsq_linear(np.vstack([x[:, keep] * w[:, None], np.sqrt(penalty) * np.eye(len(keep))]),
                       np.r_[y * w, np.zeros(len(keep))], bounds=(0, np.inf), tol=1e-12)
    assert result.success
    beta = np.zeros(x.shape[1]); beta[keep] = result.x
    if fixed is not None:
        beta[1] = fixed
    return beta


def main():
    frozen_path = ROOT/'output/cross_market/parameters_20261011T081705179804Z.json'
    frozen = json.loads(frozen_path.read_text(encoding='utf-8'))
    rows, _, sources = load_dataset()
    rows = [r for r in rows if r['usable_for_fit']]
    assert {r['phase'] for r in rows} == {'practice'}, 'New formal data requires explicit diagnostic scope'
    params = frozen['rd_curve_parameters']
    pools = {'A': [r for r in rows if r['market_id'] == 5], 'B': rows}
    result = dict(generated_at=datetime.now(timezone.utc).isoformat(), pools={}, checks={},
                  interpretation='EXPLORATORY_COEFFICIENT_DIAGNOSTICS_NOT_CAUSAL_OR_FORMAL_VALIDATION')
    rng = np.random.default_rng(20261011)
    for name, pool in pools.items():
        rr, x, y = centered(pool, params)
        penalty = frozen['models'][name]['competitive']['penalty']
        beta = fit(pool, feature_matrix(pool, params), penalty)
        assert np.max(abs(beta - frozen['models'][name]['competitive']['coefficients'])) < 1e-9
        assert np.max(abs(solve(rr, x, y, penalty) - beta)) < 1e-8
        ind = [i for i, r in enumerate(rr) if r['country'] == '印尼']
        xx = x[ind][:, [1, 2, 3, 4]]
        price = xx[:, 0]
        residual = price - xx[:, 1:] @ np.linalg.lstsq(xx[:, 1:], price, rcond=None)[0]
        w = weights(rr)
        curvature = float(sum(w*x[:, 1]**2))
        correlations = np.corrcoef(np.c_[xx, y[ind]].T)
        diagnostics = dict(n=len(rr), indonesia_n=len(ind),
                           indonesia_price_min=min(rr[i]['price'] for i in ind),
                           indonesia_price_max=max(rr[i]['price'] for i in ind),
                           indonesia_unique_prices=len({rr[i]['price'] for i in ind}),
                           centered_log_price_sd=float(np.std(price)),
                           indonesia_price_weighted_curvature=curvature,
                           ridge_relative_to_price_curvature=penalty/curvature,
                           price_variance_remaining_after_other_inputs=float(sum(residual**2)/sum(price**2)),
                           correlations=correlations.tolist(), correlation_order=['negative_log_price','general','designer','rd','log_demand'],
                           frozen_beta=beta.tolist(), penalty=penalty)
        diagnostics['penalty_path'] = [dict(penalty=p, beta=fit(pool, feature_matrix(pool, params), p).tolist())
                                       for p in [0, .0001, .001, .003, .01, .03, .1]]
        # Scale-aware ridge is a model-design ablation; it does not replace the frozen specification.
        sd = np.sqrt(np.sum(w[:, None]*x*x, axis=0))
        assert np.all(sd > 0)
        scaled = solve(rr, x/sd, y, penalty)/sd
        diagnostics['standardized_ridge_beta'] = scaled.tolist()
        diagnostics['indonesia_only_beta'] = solve([rr[i] for i in ind], xx, y[ind], penalty).tolist()
        loss = lambda b: float(sum(w*(y-x@b)**2)+penalty*sum(b*b))
        diagnostics['profile'] = [dict(indonesia_beta=float(p), optimized_other_beta=(b:=solve(rr,x,y,penalty,float(p))).tolist(),
                                       objective=loss(b), excess_objective=loss(b)-loss(beta))
                                  for p in sorted(set([0., .5, .7345809474305045, 1., 1.5, 2., 2.212104723721293, 2.5, 3., 4.]))]
        delete = []
        units = sorted({r['team_id'] for r in pool}) if name == 'A' else sorted({r['market_id'] for r in pool})
        for unit in units:
            sub = [r for r in pool if (r['team_id'] if name == 'A' else r['market_id']) != unit]
            delete.append(dict(removed=unit, beta=fit(sub,feature_matrix(sub,params),penalty).tolist()))
        diagnostics['leave_one_cluster_out'] = delete
        samples = []
        for _ in range(200):
            selected = rng.choice(units, len(units), replace=True)
            sample = []
            for i, unit in enumerate(selected):
                cluster = [r for r in pool if (r['team_id'] if name == 'A' else r['market_id']) == unit]
                sample.extend(dict(r, market_id=i+100) if name == 'B' else dict(r) for r in cluster)
            samples.append(float(fit(sample, feature_matrix(sample, params), penalty)[1]))
        diagnostics['cluster_resampling'] = dict(unit='team_history' if name=='A' else 'whole_market', n=200,
                                                quantiles=np.quantile(samples,[.05,.5,.95]).tolist(), values=samples,
                                                limit='固定正则与模型的描述性重采样范围，不是平台弹性的置信区间')
        diagnostics['rounds'] = [dict(round=rnd, beta=fit(sub,feature_matrix(sub,params),penalty).tolist())
                                 for rnd in [1,2] for sub in [[r for r in pool if r['round']==rnd]]]
        # Retrospective only: model selection has already seen both practice rounds.
        original_penalties = PENALTIES[:]
        PENALTIES[:] = [.0001, .001, .003, .01, .03, .1]
        try:
            chosen, scores = choose_penalty(pool, feature_matrix(pool, params), 'competitive')
        finally:
            PENALTIES[:] = original_penalties
        diagnostics['expanded_training_cv'] = dict(chosen_penalty=chosen, scores=scores,
                                                   selected_beta=fit(pool,feature_matrix(pool,params),chosen).tolist(),
                                                   limit='扩展原网格的事后诊断，不改变部署冻结参数')
        result['pools'][name] = diagnostics
    result['per_market'] = []
    for market in sorted({r['market_id'] for r in rows}):
        pool = [r for r in rows if r['market_id']==market]
        rr, x, y = centered(pool, params)
        result['per_market'].append(dict(market=market, beta=fit(pool,feature_matrix(pool,params),.01).tolist(),
                                         indonesia_curvature=float(sum(weights(rr)*x[:,1]**2))))
    result['support_ablations'] = []
    for label, pool in [
        ('B保留印尼价格1888至2900，泰国全留', [r for r in rows if r['country']!='印尼' or 1888<=r['price']<=2900]),
        ('B仅去掉四条印尼极端高价记录', [r for r in rows if r['country']!='印尼' or r['price']<=2900]),
        ('B排除市场2、3、9', [r for r in rows if r['market_id'] not in [2,3,9]]),
        ('B排除市场3', [r for r in rows if r['market_id']!=3]),
    ]:
        rr, x, y = centered(pool,params)
        result['support_ablations'].append(dict(label=label, n=len(rr), indonesia_n=sum(r['country']=='印尼' for r in rr),
                                                beta=fit(pool,feature_matrix(pool,params),.01).tolist(),
                                                low_penalty_beta=fit(pool,feature_matrix(pool,params),.0001).tolist(),
                                                unpenalized_beta=fit(pool,feature_matrix(pool,params),0).tolist(),
                                                price_curvature=float(sum(weights(rr)*x[:,1]**2)),
                                                limit='删样本会改变竞争组和训练分布，仅用于诊断，不是新的可比验证分数'))
    result['high_price_rows'] = [{k:r[k] for k in ['market_id','team','round','price','demand','sources']}
                                 for r in rows if r['country']=='印尼' and r['price']>2900]
    result['nuisance_swaps'] = []
    for name, pool in pools.items():
        rr, x, y = centered(pool,params)
        w = weights(rr); other = result['pools']['B' if name=='A' else 'A']['frozen_beta']
        nuisance = np.array(other); nuisance[1] = 0
        partial = y-x@nuisance
        value = max(float(sum(w*x[:,1]*partial)/(sum(w*x[:,1]**2)+.01)),0)
        result['nuisance_swaps'].append(dict(pool=name, other_coefficients_from='B' if name=='A' else 'A', indonesia_beta=value))
    rr, x, _ = centered(rows, params)
    weighted_information = weights(rr)*x[:,1]**2
    result['high_price_information_fraction'] = float(sum(v for r,v in zip(rr,weighted_information)
                                                        if r['country']=='印尼' and r['price']>2900)/sum(weighted_information))
    result['forward_indonesia'] = []
    test = [r for r in rows if r['market_id']==5 and r['round']==2]
    for name, pool in pools.items():
        train = [r for r in pool if r['round']==1]
        chosen, _ = choose_penalty(train,feature_matrix(train,params),'competitive')
        beta = fit(train,feature_matrix(train,params),chosen)
        pred = predict_shares(test,feature_matrix(test,params),beta)
        ids = [i for i,r in enumerate(test) if r['country']=='印尼']
        actual = np.array([test[i]['demand'] for i in ids]); total = sum(actual)
        result['forward_indonesia'].append(dict(model=name, training_indonesia_beta=float(beta[1]),penalty=chosen,
                                               share_mae_pp=float(np.mean(abs(pred[ids]-actual/total))*100),
                                               oracle_total_wape=metric(actual,pred[ids]*total)['WAPE'],
                                               limit='练习1训练→市场5练习2，已实现对手策略及真实总量条件诊断'))
    market5_indonesia = [r for r in pools['A'] if r['country']=='印尼']
    result['market5_indonesia_rows'] = [{k:r[k] for k in ['team','round','price','demand','general','designer','rd','previous_rd','sources']}
                                      for r in market5_indonesia]
    paths = [frozen_path, ROOT/'code/price_diagnostics.py', ROOT/'code/cross_market_validation.py']
    paths += [ROOT/s['file'] for s in sources]
    result['source_hashes'] = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['checks'] = dict(frozen_beta_reproduced=True, objective_solver_reproduced=True,
                            profile_minimum_respected=all(min(r['excess_objective'] for r in d['profile'])>=-1e-8 for d in result['pools'].values()),
                            frozen_parameters_unchanged=hashlib.sha256(frozen_path.read_bytes()).hexdigest()==result['source_hashes'][frozen_path.relative_to(ROOT).as_posix()])
    assert all(result['checks'].values())
    out = ROOT/'output/price_diagnostics'; out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    a, b = result['pools']['A'], result['pools']['B']
    lines = ['# 印尼价格系数差异诊断', '',
             '结论：当前A=0.7346、B=2.2121的差异同时受价格覆盖范围和未标准化正则惩罚影响。'
             'A的低系数不能直接解释为市场5消费者对价格不敏感；B的高系数也不能直接当作普通价格区间的真实弹性。', '',
             '本研究仅读取归档。A是市场5；B汇总市场1至10、按市场等权；两国价格系数不同，但营销/研发系数共享。'
             '正式1冻结使用两个练习回合；下方前向诊断另用练习1训练、练习2检验。', '',
             '| 指标 | A | B |', '| --- | ---: | ---: |',
             f'| 正需求拟合记录（两国） | {a["n"]} | {b["n"]} |',
             f'| 印尼记录 | {a["indonesia_n"]} | {b["indonesia_n"]} |',
             f'| 印尼价格范围，美元 | {a["indonesia_price_min"]:.0f}–{a["indonesia_price_max"]:.0f} | {b["indonesia_price_min"]:.0f}–{b["indonesia_price_max"]:.0f} |',
             f'| 不同印尼价格数 | {a["indonesia_unique_prices"]} | {b["indonesia_unique_prices"]} |',
             f'| 组内对数价格标准差 | {a["centered_log_price_sd"]:.4f} | {b["centered_log_price_sd"]:.4f} |',
             '', 'B原训练有400条，两国合计4条零需求从对数拟合排除；印尼200条均为正需求。', '',
             '## 正则惩罚并非同等强度', '',
             '当前目标是“市场等权的组内对数需求残差平方和 + λ×系数平方和”，λ=0.01。'
             '价格、营销、研发特征没有标准化，且权重和为1；样本增多不会自动使惩罚按样本数减弱。',
             f'印尼价格项加权平方和A={a["indonesia_price_weighted_curvature"]:.6f}、B={b["indonesia_price_weighted_curvature"]:.6f}；'
             f'λ与该项之比A={a["ridge_relative_to_price_curvature"]:.2f}、B={b["ridge_relative_to_price_curvature"]:.2f}。'
             '这是惩罚相对价格信息量的诊断，不是完整多变量收缩率；其他系数也随惩罚重新估计。', '',
             '| λ | A印尼系数 | B印尼系数 |', '| --- | ---: | ---: |']
    for aa, bb in zip(a['penalty_path'], b['penalty_path']):
        lines.append(f'| {aa["penalty"]} | {aa["beta"][1]:.4f} | {bb["beta"][1]:.4f} |')
    lines += ['', f'按特征尺度标准化后用λ=0.01诊断，A={a["standardized_ridge_beta"][1]:.3f}、B={b["standardized_ridge_beta"][1]:.3f}。'
              '这改变了模型的惩罚定义，仅作消融，不是新的部署版本。',
              '原选参网格只有0.01、0.1、1、10，两套最终模型都选在最小值0.01。扩展到更小惩罚后：', '',
              '| 模型 | 事后扩展网格所选λ | 印尼系数 | 原/新训练内留队份额MAE，百分点 |', '| --- | ---: | ---: | --- |']
    for name, d in result['pools'].items():
        cv = d['expanded_training_cv']
        lines.append(f'| {name} | {cv["chosen_penalty"]} | {cv["selected_beta"][1]:.3f} | '
                     f'{cv["scores"][.01]*100:.3f} / {min(cv["scores"].values())*100:.3f} |')
    lines += ['', '这说明原网格需要重新研究；以上已看过两个练习回合，不构成正式事前成绩。', '',
              '## B由少量极端高价提供大量价格信息', '',
              f'以下4条仅占印尼记录2%，却占组内印尼价格加权平方和的{result["high_price_information_fraction"]*100:.1f}%。'
              '这不是“解释了73%的需求”或因果贡献，而是回归价格特征的变动贡献。', '',
              '| 市场 | 团队 | 练习回合 | 价格，美元 | 实际需求，千单位 |', '| --- | --- | ---: | ---: | ---: |']
    lines += [f'| {r["market_id"]} | {r["team"]} | {r["round"]} | {r["price"]} | {r["demand"]} |' for r in result['high_price_rows']]
    lines += ['', '| 样本处理 | λ=0.01 | λ=0.0001 | 无正则 |', '| --- | ---: | ---: | ---: |']
    lines += [f'| {r["label"]} | {r["beta"][1]:.3f} | {r["low_penalty_beta"][1]:.3f} | {r["unpenalized_beta"][1]:.3f} |'
              for r in result['support_ablations']]
    lines += ['', '去掉高价样本后，仍用0.01会把变动较小的价格项强烈压低；不能据0.46宣称普通价格区间没有价格效应。'
              '同取0.0001时，A约2.49、B去高价约2.18；无正则时A约2.57、B去高价约2.27，而B全样本约3.91。'
              '这支持极端价格覆盖与正则化的交互解释，也提示一条固定价格系数可能无法兼顾普通区间和极端区间。'
              '非线性、隐藏机制异质性和遗漏变量仍未被这些删样本结果唯一分离。', '',
              '## A的少数样本依赖与投入混杂', '',
              '市场5练习1“市不可挡”价格2900、需求4.96；练习2同时降价至2100、设计师营销合计从400增至820，需求13.35。'
              '不能把这段需求变化全归因于降价。去掉该队两回合、两国历史后，A印尼系数从0.735降到0.260；'
              '该删除也改变了共享投入系数和竞争组，是影响诊断，不是单点因果检验。',
              f'A组内一般营销与设计师营销相关系数={a["correlations"][1][2]:.3f}，一般营销与研发={a["correlations"][1][3]:.3f}。'
              '投入经常一起变化，贡献难以分别识别；且国别营销缺失，合计投入是代理。',
              f'但价格项在剔除其他投入的线性关系后仍保留A={a["price_variance_remaining_after_other_inputs"]*100:.1f}%、'
              f'B={b["price_variance_remaining_after_other_inputs"]*100:.1f}%的变动；不是价格与营销几乎完全共线。',
              '将其他系数固定为另一模型的值后仅重估价格，A约0.798、B约2.253；因此共享营销/研发系数差异不是差距的主要直接解释。', '',
              '固定正则、固定模型的200次描述性簇重采样（A按团队历史，B按整个市场）5%–95%范围：',
              f'A={a["cluster_resampling"]["quantiles"][0]:.3f}–{a["cluster_resampling"]["quantiles"][2]:.3f}；'
              f'B={b["cluster_resampling"]["quantiles"][0]:.3f}–{b["cluster_resampling"]["quantiles"][2]:.3f}。'
              '两个重采样单位不同，只用于各自稳定性观察；固定惩罚下范围窄也不能消除正则偏差，不是平台弹性的置信区间。', '',
              '## 哪个更可信、对决策有什么影响', '',
              '| 练习1训练→市场5练习2印尼 | 训练价格系数 | 份额MAE，百分点 | 给定真实总量需求WAPE |',
              '| --- | ---: | ---: | ---: |']
    lines += [f'| {r["model"]} | {r["training_indonesia_beta"]:.3f} | {r["share_mae_pp"]:.3f} | '
              f'{r["oracle_total_wape"]*100:.2f}% |' for r in result['forward_indonesia']]
    lines += ['', 'B在这一条件回溯上较好，但不证明2.21就是真实弹性；上述训练系数与两个练习回合重训的正式1冻结系数不是同一版本。',
              '在softmax份额模型、行业规模固定且对手不变时，自身需求局部弹性为−e×(1−自身份额)。'
              'e本身并不等于需求弹性；行业价格影响总需求的机制也未识别。',
              '例如自身份额10%、单独涨价10%，用原A/B冻结系数，需求分别约下降6.1%/17.4%。'
              '它们是模型推算，并非实验测得；低系数A会给涨价更乐观的需求预测。',
              '下一步应比较扩展正则网格、按尺度惩罚、普通/极端价格分段候选，并用同一信息条件的留出或正式结果检验。'
              '不能因为消融系数看起来接近，就直接替换冻结档案或把先前2500/2400候选视为已经验证。', '',
              '## 复现和证据', '',
              '运行：`python code/price_diagnostics.py`。完整参数路径、剖面目标、删队/删市场、重采样、原始行列来源与哈希均见`results.json`。'
              '两套冻结参数和原未来预测未改变。断言通过：冻结系数复现、独立目标求解复现、剖面损失最小值、冻结原件哈希。']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({name:{k:d[k] for k in ['n','indonesia_n','centered_log_price_sd','ridge_relative_to_price_curvature',
                                          'price_variance_remaining_after_other_inputs','standardized_ridge_beta','indonesia_only_beta',
                                          'expanded_training_cv']} for name,d in result['pools'].items()},ensure_ascii=False))


if __name__ == '__main__':
    main()
