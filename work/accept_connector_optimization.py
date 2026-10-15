"""Replay experimental predictions, isolate changes, and write a Markdown delivery."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code'), str(ROOT/'code/model_v2')]
import numpy as np
import optimize_t4v1_connector as m


def main():
    out = Path(sys.argv[1]).resolve()
    result = m.read(out/'results.json')
    manifest = m.read(out/'manifest.json')
    for name, digest in manifest['sources'].items():
        assert m.t.nd.sha(ROOT/name) == digest, name
    for name, digest in manifest['outputs'].items():
        assert m.t.nd.sha(out/name) == digest, name
    history = m.read(out/'history.json')
    index = {(r['market_id'], r['team_id']):r for r in history}
    data = m.read(m.SOURCE/'dataset.json')
    models = m.read(m.SOURCE/'models_full.json')
    rows = copy.deepcopy(data['competitive_rows_by_product']['连接件'])
    params = models['curves']['rd/连接件']['parameters']
    for r in rows:
        r['history'] = {k:[v['value'] for v in refs] for k, refs in index[r['market_id'],r['team_id']]['refs'].items()}
        assert all(np.isfinite(v) and v >= 0 for values in r['history'].values() for v in values)
    # Label changes must not affect feature preparation; all labels remain confined to fitting/scoring.
    config = result['demand']['final_candidate']['config']
    x = m.demand_features(rows, params, config)
    poisoned = [dict(r, demand=r['demand']*123, sales=-999) for r in rows]
    assert np.array_equal(x, m.demand_features(poisoned, params, config))
    changed = copy.deepcopy(rows)
    changed[0]['price'] += 1
    higher = m.demand_features(changed, params, config)
    c = m.core.COUNTRIES.index(rows[0]['country'])
    assert higher[0, c] < x[0, c]
    synthetic = copy.deepcopy(rows[:1])
    synthetic[0].update(general=100, designer=100)
    synthetic[0]['history']['general'] = [400, 200]
    carried = m.demand_features(synthetic, params, dict(config, marketing_decay=.5))
    assert abs(carried[0, 2]-np.log1p((100+.5*200+.25*400)/1000)) < 1e-12
    ablations = {}
    for name, allowed in [('marketing_only', lambda c:c.get('price_form','log')=='log'),
                          ('price_only', lambda c:c.get('marketing_decay',0)==0)]:
        folds = []
        for original_fold in result['demand']['folds']:
            held = original_fold['market']
            candidates = [v for v in original_fold['inner_path'] if allowed(v['config'])]
            best = min(v['mae_pp'] for v in candidates)
            selected = min((v for v in candidates if v['mae_pp']<=best*1.01),
                           key=lambda v:(int(v['config'].get('marketing_decay',0)>0),
                                         int(v['config'].get('price_form','log')!='log'), v['mae_pp']))
            config = selected['config']
            tr = [i for i,r in enumerate(rows) if r['market_id']!=held]
            te = [i for i,r in enumerate(rows) if r['market_id']==held]
            x = m.demand_features(rows, params, config)
            fit = m.demand_fit(rows, params, x, tr, config)
            pred = m.core.predict([rows[i] for i in te], x[te], fit['beta'])
            folds.append(dict(market=held, config=config, model=fit,
                              mae_pp=100*m.core.score([rows[i] for i in te], pred)))
        ablations[name] = dict(folds=folds, mae_pp=float(np.mean([f['mae_pp'] for f in folds])))
    for fold in result['demand']['folds']:
        held = fold['market']
        tr = [i for i,r in enumerate(rows) if r['market_id']!=held]
        te = [i for i,r in enumerate(rows) if r['market_id']==held]
        assert {tuple(k) for k in fold['model']['training_keys']} == {tuple(m.core.key(rows[i])) for i in tr}
        x = m.demand_features(rows, params, fold['config'])
        rr = [rows[i] for i in te]
        pred = m.core.predict(rr, x[te], fold['model']['beta'])
        assert abs(100*m.core.score(rr, pred)-fold['mae_pp'])<1e-10
        saved = {tuple(r['key']):r for r in result['demand']['predictions']}
        assert np.allclose(pred, [saved[tuple(m.core.key(r))]['predicted_share'] for r in rr], atol=1e-12)
        for group in m.core.old.groups(rr).values():
            assert abs(sum(pred[group])-1)<1e-12
    personnel = []
    acceptance_sources = {str(p.relative_to(ROOT)):m.t.nd.sha(p) for p in
                          [Path(__file__), m.t.AUDIT/'rows.json', m.t.AUDIT/'validation.json']}
    actual = m.t.Actuals(m.t.load_previous()+m.t.nd.read(m.t.AUDIT/'rows.json'))
    for rnd in (1,2,3):
        refs = {label:actual.get(7, rnd, m.ANOMALY, 'productionhr', label) for label in
                ['生产人员数量, 上回合','生产人员数量, 本回合','招聘 + / 裁员 -','辞职','运营改进, 千 美元']}
        for ref in refs.values():
            assert m.t.nd.sha(ROOT/ref['source']) == ref['sha256']
            acceptance_sources[ref['source']] = ref['sha256']
        personnel.append(dict(market=7, team=m.ANOMALY, round=rnd, refs=refs,
                              basis='actual_result; personnel state not an identified efficiency coefficient'))
    m.save(out/'personnel_diagnosis.json', personnel)
    m.save(out/'acceptance_sources.json', acceptance_sources)
    m.save(out/'demand_isolation.json', ablations)
    acceptance = dict(source_and_output_hashes=True, demand_predictions_replayed=True,
        train_test_disjoint=True, share_conservation=True, history_values_nonnegative_finite=True,
        demand_features_independent_of_labels=True, higher_price_reduces_utility=True,
        marketing_stock_arithmetic=True, efficiency_synthetic_recovery=m.self_check(),
        deployment='NOT_DEPLOYED', formal4_validation='PENDING_ACTUAL_RESULTS')
    m.save(out/'acceptance.json', acceptance)
    original = result['demand']['original_mae_pp']
    new = result['demand']['mae_pp']
    lines = ['# 连接件模型逐步诊断与优化', '',
        '2026-10-14（北京时间）。不要输出真名，姓名统一用首字母替代。本报告仅使用匿名团队ID。', '',
        '**已完成离线历史补证、候选拟合和同集合留出比较。效率历史候选明显改善；需求只小幅改善，真实投入缺口仍未解决。原t4v1注册表保留，未部署或填写平台。**', '',
        '## 1. 补齐输入：核验现有证据，缺口保留', '',
        '恢复100队正式1、2的一般营销、设计师营销和运营实际投入，共600条带源行列及SHA256的引用。正式3仍使用原有实际投入、需求标签和竞争集合。', '',
        '分产品/国家营销及分产品研发仍只有本组4条国别产品记录（研发按产品去重）；其余99队缺少分配决策。公司合计不能唯一反推分配。本次未按比例拆分、未只替换本组、未以预算或销量替代真实需求。', '',
        '## 2. 真实投入与合计代理比较：尚不能执行', '',
        '因99队分配输入缺失，无法在同一竞争集合比较真实投入与代理。此步骤保持待补证；以下仅优化代理模型的表达，不声称修复输入口径。未访问平台，因此不把本地缺失解释为平台一定不提供。', '',
        '## 3. 价格与营销历史：训练折内选择，再留出整市场', '',
        '沿用10个外折，每折留出一个完整市场，两国竞争集合保持不变。每折仅用其他9市场逐市场内层验证，尺度仅从拟合训练折计算。研发ρ沿用0/0.25/0.5/0.75/1；正则沿用原11点。新增营销延续候选0/0.5/1，以及对数价格或线性价格效用（−售价/100）；系数仍非负。原外折训练内选出的基线配置也作为候选。误差相差1%内优先无营销延续、原价格形式。', '',
        '营销候选：G3+δG2+δ²G1、D3+δD2+δ²D1；全部仍是公司合计代理。新产品是否继承这些历史未知，候选仅作敏感性假设。线性价格是统计响应候选，没有使用27美元初始价或自造分段阈值。', '',
        '| 连接件SHARE | 外折MAE，份额百分点 |', '| --- | ---: |',
        f'| 原模型独立复算 | {original:.6f} |',
        f'| 只开放营销历史（原价格形式） | {ablations["marketing_only"]["mae_pp"]:.6f} |',
        f'| 只开放价格响应（无营销历史） | {ablations["price_only"]["mae_pp"]:.6f} |',
        f'| 联合选择 | {new:.6f} |', '',
        f'联合选择比原模型减少{original-new:.6f}个百分点（{100*(1-new/original):.2f}%）；'+
        f'{sum(f["mae_pp"]<f["original_mae_pp"] for f in result["demand"]["folds"])}/10市场改善。所有外折选择营销δ=0、线性价格；最终全样本内层选择同样如此。未发现公司营销历史代理带来稳定增益，不等于证明营销没有长期效应。', '',
        '| 市场 | 原MAE pp | 候选MAE pp |', '| --- | ---: | ---: |']
    lines += [f'| {f["market"]} | {f["original_mae_pp"]:.6f} | {f["mae_pp"]:.6f} |' for f in result['demand']['folds']]
    lines += ['', '本次候选设计已参考原数据诊断，因此这些仍是探索性同期条件回溯；嵌套选参不能让已见数据变成新的独立回合。未做显著性检验，3.15%的小幅变化不足以作为部署或定价依据。', '',
        '## 4. 市场7效率异常：发现被遗漏的正式1投入', '',
        '异常队`M07-71cb3f984d9d1ad8`正式1/2/3运营投入依次为900/0/0千美元。原式O3+ρO2丢失了900；新候选使用O3+ρO2+ρ²O1，即可递推状态S_t=O_t+ρS_(t−1)的已观测历史前缀。正式1之前的状态仍未知，未宣称完整历史从零开始。', '',
        '固定原正式3运营曲线、原策略加权损失、ρ网格0–1步长0.001；每个外折只在其余市场重估ρ和基础效率θ，不删异常队，不扩大舍入容差。两个产品独立拟合。', '',
        '| 产品 | 原逐队MAPE | 历史候选MAPE | 原策略加权MAE | 历史候选MAE |',
        '| --- | ---: | ---: | ---: | ---: |']
    for product,v in result['efficiency'].items():
        a,b = v['original_replay'],v['full_history']
        lines.append(f'| {product} | {a["team_mape_pct"]:.6f}% | {b["team_mape_pct"]:.6f}% | {a["market_strategy_mae"]:.8f} | {b["market_strategy_mae"]:.8f} |')
    lines += ['', 'MAE单位为千单位/人，不直接跨产品比较其绝对值。', '',
        '| 产品 | 异常队原误差 | 历史候选误差 | 全样本候选ρ | 候选θ | 舍入兼容数（原→新） |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for product,v in result['efficiency'].items():
        a,b = v['original_replay'],v['full_history']
        lines.append(f'| {product} | {a["anomaly"][0]["error_pct"]:.4f}% | {b["anomaly"][0]["error_pct"]:.4f}% | {b["fit"]["rho"]:.3f} | {b["fit"]["theta"]:.8f} | {a["compatible_n"]}→{b["compatible_n"]}/{b["n"]} |')
    lines += ['', '改善支持“更早运营投入遗漏”这一解释，但异常队新预测仍在舍入区间之外；不能将剩余误差归为舍入。更早历史、曲线条件和人员作用仍需核验。正式1–3人员数量、招聘/裁员、辞职记录已保存为独立诊断，未把人员变化直接拟合成未经证实的效率原因。', '',
        '## 5. 跨回合验收与使用范围', '',
        '本次仅使用截至正式3的实际结果。正式4实际尚未纳入，跨回合验证待结果发布后进行。候选没有接入需求决策、生产工资、完整利润或六回合优化；不能用本报告推荐投入或售价。材料模型未修改。', '',
        '验收通过：原需求/效率预测复算、训练键与市场隔离、同竞争集合、份额守恒、特征不读取需求/销量标签、价格方向、营销历史计算、合成运营历史参数恢复、历史源及原模型哈希不变。', '',
        '## 当前全部问题与不足（本次涉及范围）', '',
        '| 编号 | 状态、影响与下一步 |', '| --- | --- |',
        '| 4/5 | 代理口径未修复；99队真实分配缺失，需求误差仍高。补齐全竞争集合后重做真实投入对照。 |',
        '| 3/6 | 线性效用小幅改善；非线性机制与系数因果含义未确认，保留研究候选。 |',
        '| 9/12 | 更早运营历史候选改善；仍有超舍入残差，未知初始存量及人员作用保留。 |',
        '| 8/16/18 | 同期条件回溯，非正式4事前、完整财务或剩余回合最优验证。 |', '',
        '## 因缺乏数据而无法验证的问题', '',
        '- 99队正式3分产品/国家营销、分产品研发及连接件新产品投入继承规则。',
        '- 正式1之前有效运营存量、完整历史技术状态；人员变化对效率的独立作用。',
        '- 连接件初始实际价格、可支持固定分段机制的证据。',
        '- 正式4实际结果及独立跨回合预测成绩、完整端到端利润。', '',
        '## 文件与复现', '',
        '- `results.json`：全部候选参数、外折训练键、预测和指标；`demand_isolation.json`：价格/营销单独比较。',
        '- `history.json`、`personnel_diagnosis.json`：匿名队伍历史与来源引用；`coverage.json`：数据缺口。',
        '- `experiment_plan.json`：候选网格、公式及选择规则；`acceptance.json`与`manifest.json`：检查及哈希。',
        '- 复现：使用项目Python运行时执行`code/model_v2/optimize_t4v1_connector.py`，自动创建新目录；再执行`work/accept_connector_optimization.py <新目录>`。',
        '- 自检：同一运行时执行`code/model_v2/optimize_t4v1_connector.py --self-check`。', '',
        '未采集教程、未改平台或原模型；仅交付Markdown及JSON，没有新增HTML报告。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    with (out/'work_log.md').open('a', encoding='utf-8') as f:
        f.write('\n验收完成：价格/营销分离比较、逐折预测复算、训练键隔离、方向与历史计算断言通过；报告交付。真实分配与正式4验证仍待补证，未部署。\n')
    m.save(out/'delivery_manifest.json', {p.name:m.t.nd.sha(p) for p in out.iterdir()
                                         if p.is_file() and p.name!='delivery_manifest.json'})
    print(json.dumps(dict(output=str(out), demand_original=original, demand_candidate=new,
                          isolation={k:v['mae_pp'] for k,v in ablations.items()}, acceptance=acceptance), ensure_ascii=False))


if __name__ == '__main__':
    main()
