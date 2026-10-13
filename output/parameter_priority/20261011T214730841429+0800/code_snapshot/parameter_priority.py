"""Append-only parameter research; existing models and browser decisions stay unchanged."""
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code/model_v2'))
import core as c
from context import tag
from finance import efficiency_and_risk, parameter_sources

BASE = dict(rho=.5, scale=1000., standardized=True, piecewise=False)
PENALTIES = [1e-5, 1e-4, .001, .01, .1, 1]


def transform(rows, config):
    # Company-total proxies only; scaling cannot recover missing country allocations.
    assert config['scale'] > 0
    return [dict(r, general=r['general'] * 1000 / config['scale'],
                 designer=r['designer'] * 1000 / config['scale']) for r in rows]


def fit(rows, params, config):
    return c.fit(transform(rows, config), params, **{k: v for k, v in config.items() if k != 'scale'})


def prediction(rows, params, config, fitted):
    rr = transform(rows, config)
    return c.predict(rr, c.features(rr, params, config['rho'], config['piecewise']), fitted['beta'])


def cv(rows, params, config):
    errors = []
    target = c.actual_shares(rows)
    for i, row in enumerate(rows):
        train = [r for r in rows if r['team_column'] != row['team_column']]
        assert not any(c.key(r) == c.key(row) for r in train)
        model = fit(train, params, config)
        errors.append(abs(float(prediction(rows, params, config, model)[i]) - target[i]))
    return float(np.mean(errors)) * 100


import numpy as np


def search(rows, params, configs):
    path = [dict(config=config, mae_pp=cv(rows, params, config)) for config in configs]
    winner = min(path, key=lambda r: (r['mae_pp'], abs(r['config']['rho']-.5), abs(np.log(r['config']['scale']/1000))))
    return winner['config'], path


def select(rows, params):
    baseline, base_path = search(rows, params, [dict(BASE, penalty=p, loss=loss) for p in PENALTIES for loss in ['log', 'share']])
    coarse, coarse_path = search(rows, params, [dict(BASE, rho=rho, penalty=p, loss=loss)
                                              for rho in [0, .25, .5, .75, 1]
                                              for p in PENALTIES for loss in ['log', 'share']])
    # Fine rho selection is local and conditional on coarse-selected loss/penalty; no global optimum claim.
    rhos = sorted(set(round(float(v), 3) for v in np.arange(max(0, coarse['rho']-.125), min(1, coarse['rho']+.125)+.0001, .025)))
    refined, fine_path = search(rows, params, [dict(coarse, rho=rho) for rho in rhos] + [coarse])
    marketing, scale_path = search(rows, params, [dict(refined, scale=s, penalty=p)
                                                for s in [250, 500, 1000, 2000, 4000] for p in PENALTIES])
    return dict(baseline=baseline, rd_rho=refined, marketing_scale=marketing), dict(
        baseline=base_path, coarse_rho=coarse_path, fine_rho=fine_path, marketing_scale=scale_path)


def nested(rows, params):
    target = c.actual_shares(rows)
    records = []
    for i, held in enumerate(rows):
        train = [r for r in rows if r['team_column'] != held['team_column']]
        configs, _ = select(train, params)
        values = {}
        for name, config in configs.items():
            model = fit(train, params, config)
            assert c.key(held) not in model['training_keys']
            p = prediction(rows, params, config, model)
            assert abs(sum(p)-1) < 1e-12
            values[name] = dict(config=config, predicted_share=float(p[i]),
                               error_pp=float(100*abs(p[i]-target[i])))
        records.append(dict(held_key=c.key(held), train_keys=[c.key(r) for r in train], actual_share=float(target[i]), models=values))
        print('NESTED', held['country'], held['team_column'], flush=True)
    return dict(records=records, mae_pp={name: float(np.mean([r['models'][name]['error_pp'] for r in records]))
                                        for name in ['baseline', 'rd_rho', 'marketing_scale']},
                interpretation='训练内嵌套留队，已知竞争者特征与行业总量条件下的份额诊断；非正式事前需求验证')


def checks(rows, params):
    config = dict(BASE, penalty=.001, loss='log')
    original = c.fit(rows, params, penalty=.001, standardized=True, rho=.5, piecewise=False, loss='log')
    assert np.allclose(fit(rows, params, config)['beta'], original['beta'], atol=1e-12, rtol=0)
    assert np.allclose(transform(rows, config)[0]['general'], rows[0]['general'])
    before = rows[0]['general']
    transform(rows, dict(config, scale=250))
    assert rows[0]['general'] == before
    synthetic = [dict(r, general=rows[0]['general'], designer=rows[0]['designer'],
                      rd=600, previous_rd=600) for r in rows]
    weak = fit(synthetic, params, config)
    assert weak['beta'][4] == 0
    p = prediction(rows, params, config, original)
    assert abs(sum(p)-1) < 1e-12 and all(np.isfinite(p))
    return dict(baseline_replay=True, original_rows_immutable=True, inactive_rd_rejected=True, share_conservation=True)


def main():
    out = ROOT / 'output/parameter_priority' / datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True, exist_ok=False)
    print('OUTPUT', out, flush=True)
    rows, _, sources = c.old.load_dataset()
    contexts = tag(rows)
    params = c.read(c.FROZEN)['rd_curve_parameters']
    eligible = [r for r in rows if r['context_fit_eligible']]
    protected = {ROOT / s['file']: c.digest(ROOT / s['file']) for s in sources}
    for path in [ROOT/c.FROZEN, ROOT/'分步模型拟合与验证.json', ROOT/'结构化模型输入.json']:
        protected[path] = c.digest(path)
    snapshot = out/'code_snapshot'; snapshot.mkdir()
    for path in [Path(__file__), *list((ROOT/'code/model_v2').glob('*.py')),
                 ROOT/'code/cross_market_validation.py', ROOT/'code/stepwise_model.py',
                 ROOT/'code/build_model_inputs.py', ROOT/'code/archive_and_report.py', ROOT/'code/audit_incremental.py']:
        shutil.copy2(path, snapshot/path.name)
    c.write(out/'inputs.json', dict(rows=eligible, context=contexts, frozen_rd_curve=params, sources=sources))
    results = {}
    for context in sorted({r['context_id'] for r in eligible}):
        for country in c.COUNTRIES:
            rr = [r for r in eligible if r['context_id']==context and r['country']==country]
            assert len(rr)==10 and len({r['team_column'] for r in rr})==10
            validation = checks(rr, params)
            selected, path = select(rr, params)
            models = {name: dict(config=config, fitted=fit(rr, params, config)) for name, config in selected.items()}
            price_support = []
            for threshold in [1.25, 1.5, 1.75, 2.0]:
                below = [r for r in rr if r['price']/r['initial_price'] <= threshold]
                above = [r for r in rr if r['price']/r['initial_price'] > threshold]
                price_support.append(dict(threshold=threshold, below_n=len(below), above_n=len(above),
                                          above_unique_prices=len({r['price'] for r in above}),
                                          status='SPARSE_TAIL_NO_THRESHOLD_OPTIMIZATION' if len(above)<3 else 'EXPLORATORY_ONLY_NO_NESTED_THRESHOLD_SEARCH'))
            formal = context=='M5_P1_FORMAL1_VISIBLE'
            value = dict(selected=selected, paths=path, models=models, checks=validation,
                         price_threshold_support=price_support, rd_previous_values=sorted({r['previous_rd'] for r in rr}),
                         marketing_allocation_identified=False, full_training_n=len(rr),
                         nested=nested(rr, params) if formal else None,
                         status='NESTED_WITHIN_CONTEXT_RESEARCH' if formal else 'PRACTICE2_SEPARATE_RETROSPECTIVE_PROFILE_ONLY')
            results[context+'/'+country] = value
            c.write(out/'demand_results.json', results)
            print('COUNTRY DONE', context, country, selected, flush=True)
    finance = efficiency_and_risk()
    for model in finance['risk']:
        model['leave_team_out_mae_bp'] = float(np.mean([abs(r['heldout_error_bp']) for r in model['leave_team_out']]))
    result = dict(version='PARAMETER_PRIORITY_V1', horizon_end_round=6,
                  selection_scope='separate country/context; nested validation for practice1 only',
                  adopted_in_production=False, models=results, finance_diagnostics=finance,
                  finance_parameter_provenance=parameter_sources(),
                  limitations=['研发ρ局部细化条件于粗筛损失和惩罚，非全部参数联合精确最优',
                    '营销尺度仅共用一个尺度候选，国别营销原数据缺失；不是投入因果回报',
                    '每国每情境10队；研发/营销共变和固定上期投入影响识别',
                    '完整六回合收益需要各回合前景、存量和状态结转；本版仅参数研究，不填补未知未来',
                    '利率的留队误差给定实际期末状态，尚未证明贷款干预的因果节息',
                    '更早研发/运营存量和跨期技术趋势尚未识别'])
    c.write(out/'results.json', result)
    lines = ['# 参数优先级处理 PARAMETER_PRIORITY_V1', '',
             '独立版本；原模型不替换、不修改网页。评估期限止于正式6，本版不输出六回合利润排名。', '',
             '## 优先级1：研发ρ与营销响应尺度', '',
             '按国家及情境独立拟合；正式1可见情境使用外层留队、内层选参。固定0.5基线也在训练内重选损失和惩罚。',
             '研发先比较0/.25/.5/.75/1，再在领先点±.125内以.025细化（损失/惩罚条件固定）。营销尺度比较250/500/1000/2000/4000，并重选惩罚。', '',
             '| 情境/国家 | 全样本研发ρ | 营销尺度 | 基线嵌套MAE(pp) | 研发细化MAE(pp) | 营销细化MAE(pp) |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name, value in results.items():
        n = value['nested']; scores = n['mae_pp'] if n else {}
        fmt = lambda k: f'{scores[k]:.5f}' if n else '未计算（单列回溯）'
        lines.append(f'| {name} | {value["selected"]["rd_rho"]["rho"]} | {value["selected"]["marketing_scale"]["scale"]} | {fmt("baseline")} | {fmt("rd_rho")} | {fmt("marketing_scale")} |')
    lines += ['', '全样本参数不是外层独立验证成绩。模型升级只有在嵌套误差改善及参数稳定性支持时才有依据；本次不自动部署。', '',
              '## 优先级2：风险利率与财务参数', '',
              '| 风险函数 | 留队MAE（基点） | 适用边界 |', '| --- | ---: | --- |']
    for model in finance['risk']:
        lines.append(f'| {model["form"]} | {model["leave_team_out_mae_bp"]:.4f} | 给定实际期末状态的关联验证，非还贷干预验证 |')
    lines += ['', '两函数已有连续参数拟合；关键不足是适用范围及计息机制，继续加密参数网格不能解决。应收/应付30天、厂房800/折旧7%和材料差额保持经验标签；缺独立预算证据不升级为官方参数。', '',
              '## 优先级3：价格阈值与长期状态', '',
              '已统计各国各情境在1.25/1.5/1.75/2倍初始价格阈值两侧样本。稀疏高价尾部不新增自由阈值；完整计数见demand_results.json。',
              '运营ρ独立版本继续保留；技术尺度、存量及未来行业总量不能从少量历史识别为已知长期机制。',
              '研发/运营延续、投资回报及节息只评价正式6以前；未知终局计分、订单及债务不自行清零或赋予收益。', '',
              '## 仍需证据', '', *['- '+text for text in result['limitations']], '',
              '复现：`python code/parameter_priority.py`。来源、行列、训练键、每折配置、候选路径、代码快照和源/输出哈希随目录保存。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    assert all(c.digest(path)==digest for path,digest in protected.items())
    c.write(out/'manifest.json', dict(version=result['version'], protected_source_hashes={str(p.relative_to(ROOT)):h for p,h in protected.items()},
                                    sources_unchanged=True, code_hashes={p.name:c.digest(p) for p in snapshot.iterdir()},
                                    output_hashes={p.name:c.digest(p) for p in out.iterdir() if p.is_file()}))
    print('COMPLETE', out, flush=True)


if __name__=='__main__':
    main()
