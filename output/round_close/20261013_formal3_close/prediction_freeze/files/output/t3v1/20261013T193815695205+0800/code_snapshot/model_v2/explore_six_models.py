"""Supplement a frozen new_data_value run with six-model diagnostics (offline)."""
import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import new_data_value as nd


def shift_basis(q, capacity):
    if q <= 0 or capacity <= 0 or q > capacity + 1e-8:
        raise ValueError('工资训练要求0<产量<=产能')
    second = min(max(q-capacity/3, 0), capacity/3)
    third = max(q-2*capacity/3, 0)
    return np.array([second/q, third/q])


def origin_fit(x, y, markets):
    x, y = np.asarray(x, float), np.asarray(y, float)
    count = Counter(markets)
    w = np.sqrt([1/count[m] for m in markets])
    return np.linalg.lstsq(x*w[:, None], y*w, rcond=None)[0]


def summary(rows, baseline='baseline', candidate='candidate'):
    result = nd.paired_summary(rows, baseline, candidate)
    result['statistical_gate_passed'] = result.get('allowed_refit', False)
    result['allowed_refit'] = False
    result['allow_deployment'] = False
    result['interpretation'] = '诊断候选；已知当期实际产量/人数/交付；不作为事前经营预测'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    evidence, out = args.evidence.resolve(), args.out.resolve()
    if not out.is_relative_to(nd.ROOT/'output/six_model_exploration'):
        raise ValueError('输出必须在六模型研究目录')
    if not (out/'work_log.md').is_file():
        raise ValueError('先创建工作日志')
    verification = nd.read(evidence/'verification.json')
    if verification['status'] != 'COMPLETE':
        raise ValueError('增量实验未完成')
    for name, digest in verification['artifacts'].items():
        if nd.sha(evidence/name) != digest:
            raise ValueError('实验产物哈希不一致：'+name)
    frozen = nd.read(evidence/'manifest.json')
    input_hashes = dict(frozen['input_hashes'])
    input_hashes[str(Path(__file__).resolve())] = nd.sha(__file__)
    input_hashes.update({str(evidence/name): nd.sha(evidence/name) for name in verification['artifacts']})
    nd.assert_unchanged({'files': input_hashes})
    samples = nd.read(evidence/'样本资格.json')['samples']
    index = {tuple(s['key']): s for s in samples}
    groups = defaultdict(list)
    for s in samples:
        if s['phase'] != 'initial' and not s.get('invalid_fields'):
            groups[(s['phase'], s['round'], s['country'], s['product'])].append(s)
    ledger = {(r['phase'], r['round']): r['values'] for r in nd.read(evidence/'参数依据.json')}
    results, predictions, fits = {}, [], []
    checks = nd.read(evidence/'派生性检查.json')
    results['audit'] = {name: dict(count=len(c), passed=sum(r['pass_'] for r in c))
                        for name in sorted({r['check'] for r in checks})
                        for c in [[r for r in checks if r['check'] == name]]}
    cals = nd.read(evidence/'校准观测.json')
    by_id = {nd.key_string(s['key']): s for s in samples}
    ratios = [(r['q_interval'][1]-r['q_interval'][0]) /
              (2*by_id[r['sample_id']]['refs']['q']['display_half_unit']) for r in cals]
    results['A_precision'] = dict(cells=len(cals), exact_workers=sum(r['exact_workers'] for r in cals),
        median_output_interval_ratio=float(np.median(ratios)) if ratios else None,
        water_channel='未参与校准，但仍与产量相关，不是独立统计证据',
        latent_identification='无已知单位强度时k与q尺度不可分；无精确人数时q=Nη不能同时识别N与η')
    for scope, group in sorted(groups.items()):
        tag = '|'.join(map(str, scope))
        p = ledger.get(scope[:2])
        if not p:
            continue
        cost = [s for s in group if all(f in s['values'] for f in
                ('previous_workers_old', 'workers', 'hires_fires', 'severance'))]
        wage = [s for s in group if all(f in s['values'] for f in ('q', 'capacity', 'workers', 'wage'))
                and 0 < s['values']['q'] <= s['values']['capacity'] and s['values']['workers'] > 0]
        b_rows, c_rows = [], []
        for held in sorted({s['market'] for s in cost}):
            train = [s for s in cost if s['market'] != held]
            def cost_x(s):
                v = s['values']
                return [max((1-p['attrition'])*v['previous_workers_old']-v['workers'], 0)*p['base_wage'],
                        max(-v['hires_fires'], 0)*p['base_wage']]
            x = np.array([cost_x(s) for s in train])
            y = [s['values']['severance'] for s in train]
            coeff = [float(origin_fit(x[:, [i]], y, [s['market'] for s in train])[0]) for i in (0, 1)]
            fits.append(dict(experiment='B|'+tag, held_market=held, old_coefficient=coeff[0], event_coefficient=coeff[1],
                             train_ids=[nd.key_string(s['key']) for s in train]))
            for s in cost:
                if s['market'] != held:
                    continue
                old, event = cost_x(s)
                b_rows.append(dict(sample_id=nd.key_string(s['key']), market=held, actual=s['values']['severance'],
                    baseline=old*p['severance_ratio'], candidate=event*p['severance_ratio'],
                    old_fitted=old*coeff[0], event_fitted=event*coeff[1], metric='解聘费千美元'))
        results['B_fixed|'+tag] = summary(b_rows)
        results['B_fitted|'+tag] = summary(b_rows, 'old_fitted', 'event_fitted')
        results['B_events|'+tag] = dict(cells=len(cost), hiring=sum(s['values']['hires_fires']>0 for s in cost),
            firing=sum(s['values']['hires_fires']<0 for s in cost), zero=sum(s['values']['hires_fires']==0 for s in cost),
            hiring_cost='无独立招聘费标签，κ_H不识别', rounding_threshold='显示精度内误差不能识别τ_F')
        for held in sorted({s['market'] for s in wage}):
            train = [s for s in wage if s['market'] != held]
            x = np.array([shift_basis(s['values']['q'], s['values']['capacity']) for s in train])
            y = [s['values']['wage']/(p['base_wage']*s['values']['workers'])-1 for s in train]
            rank = int(np.linalg.matrix_rank(x))
            if rank < 2:
                fits.append(dict(experiment='C|'+tag, held_market=held, rank=rank, status='不可识别'))
                continue
            slopes = origin_fit(x, y, [s['market'] for s in train])
            sx = np.array([[max(3*s['values']['q']/s['values']['capacity']-1, 0),
                            max(3*s['values']['q']/s['values']['capacity']-2, 0)] for s in train])
            hinge = origin_fit(sx, y, [s['market'] for s in train])
            fits.append(dict(experiment='C|'+tag, held_market=held, rank=rank,
                second_multiplier=1+float(slopes[0]), third_multiplier=1+float(slopes[1]),
                hinge_slopes=hinge.tolist(), train_ids=[nd.key_string(s['key']) for s in train]))
            for s in wage:
                if s['market'] != held:
                    continue
                v = s['values']; basis = shift_basis(v['q'], v['capacity']); ns = 3*v['q']/v['capacity']
                scale = p['base_wage']*v['workers']
                c_rows.append(dict(sample_id=nd.key_string(s['key']), market=held, actual=v['wage'],
                    baseline=scale*(1+basis@np.array([p['second_shift']-1, p['third_shift']-1])),
                    candidate=float(scale*(1+basis@slopes)),
                    hinge=float(scale*(1+np.array([max(ns-1,0), max(ns-2,0)])@hinge)), metric='工资千美元'))
        results['C_weighted|'+tag] = summary(c_rows)
        results['C_hinge|'+tag] = summary(c_rows, 'baseline', 'hinge')
        bins = Counter(1 if 3*s['values']['q']/s['values']['capacity']<=1 else
                       2 if 3*s['values']['q']/s['values']['capacity']<=2 else 3 for s in wage)
        results['C_coverage|'+tag] = dict(cells=len(wage), shift_bins=dict(bins),
            formula='W/(wN)=1+(κ2−1)q2/q+(κ3−1)q3/q；平均工资按各班人数占比加权',
            warning='原候选max(s−1,0)未除以s，与平均工资机制不等价；本实验用于比较参数可识别性')
        predictions += [dict(r, experiment='B|'+tag) for r in b_rows]
        predictions += [dict(r, experiment='C|'+tag) for r in c_rows]
        for prefix, fields in [('E', ['co2', 'energy', 'water']), ('F', ['route_co2_TH', 'route_co2_ID'])]:
            for field in fields:
                intensity = field+'_intensity' if prefix=='E' else 'route_intensity_'+field.rsplit('_', 1)[1]
                quantity = 'q' if prefix=='E' else 'route_'+field.rsplit('_', 1)[1]
                ready = [s for s in group if all(f in s['values'] for f in (field, intensity, quantity))]
                rows, timeline, safe_timeline = [], [], []
                for held in sorted({s['market'] for s in ready}):
                    train = [s for s in ready if s['market'] != held]
                    if not train:
                        continue
                    k = float(origin_fit([[s['values'][quantity]] for s in train],
                        [s['values'][field] for s in train], [s['market'] for s in train])[0])
                    for s in ready:
                        if s['market'] == held:
                            v = s['values']
                            rows.append(dict(sample_id=nd.key_string(s['key']), market=held, actual=v[field],
                                baseline=v[quantity]*v[intensity], candidate=v[quantity]*k, metric=field))
                for s in ready:
                    prev = index.get(nd.previous_key(tuple(s['key'])))
                    if not prev or prev.get('invalid_fields') or intensity not in prev['values']:
                        continue
                    v, pv = s['values'], prev['values']
                    timeline.append(dict(sample_id=nd.key_string(s['key']), market=s['market'], actual=v[field],
                        baseline=v[quantity]*v[intensity], candidate=v[quantity]*pv[intensity], metric=field))
                    historical = [z['values'][intensity] for z in samples
                        if tuple(z['key'])[1:3] == tuple(prev['key'])[1:3]
                        and z['country'] == s['country'] and z['product'] == s['product']
                        and not z.get('invalid_fields') and z['values'].get(quantity, 0)>0
                        and z['values'].get(intensity, 0)>0]
                    if historical:
                        safe_timeline.append(dict(sample_id=nd.key_string(s['key']), market=s['market'], actual=v[field],
                            baseline=v[quantity]*v[intensity], candidate=v[quantity]*float(np.median(historical)), metric=field))
                result = summary(rows)
                result['coefficient_range'] = [min(s['values'][intensity] for s in ready),
                                                max(s['values'][intensity] for s in ready)] if ready else None
                results[prefix+'_shared|'+tag+'|'+field] = result
                results[prefix+'_previous|'+tag+'|'+field] = summary(timeline)
                if prefix == 'F':
                    results['F_positive_history|'+tag+'|'+field] = summary(safe_timeline)
                predictions += [dict(r, experiment=prefix+'_shared|'+tag+'|'+field) for r in rows]
                predictions += [dict(r, experiment=prefix+'_previous|'+tag+'|'+field) for r in timeline]
                if prefix == 'F':
                    predictions += [dict(r, experiment='F_positive_history|'+tag+'|'+field) for r in safe_timeline]
    # Fixed alternatives isolate personnel features from intercept/residual calibration.
    pairs = [(index[nd.previous_key(tuple(s['key']))], s) for s in samples
        if s['phase']=='formal' and s['round']==2 and nd.previous_key(tuple(s['key'])) in index]
    needed = ('q', 'workers', 'operations', 'previous_operations', 'co2', 'co2_intensity', 'energy', 'energy_intensity')
    pairs = [(p, s) for p, s in pairs if not p.get('invalid_fields') and not s.get('invalid_fields')
        and all(f in z['values'] for z in (p, s) for f in needed)
        and all(f in p['values'] for f in ('hires_fires', 'previous_workers'))
        and min(p['values']['workers'],s['values']['workers'],p['values']['previous_workers'],p['values']['q'],s['values']['q'])>0]
    base_model = nd.read(nd.FROZEN)
    alternatives = {'intercept': [], 'residual': [0], 'hire': [1], 'fire': [2],
                    'residual_hire': [0,1], 'residual_fire': [0,2], 'all': [0,1,2]}
    d_rows = []
    def residuals(training, testing):
        coeff = [nd.resource_coefficients([pair[i] for pair in training]) for i in (0,1)]
        cal = [[dict(pair[i], calibrated=nd.calibration(pair[i], coeff[i])) for pair in training] for i in (0,1)]
        if any(z['calibrated']['status']!='CALIBRATION_ONLY' for records in cal for z in records):
            raise ValueError('D训练观测冲突')
        scales = [nd.fit_scale(records, base_model, True) for records in cal]
        xx, yy = [], []
        for prev, nxt in testing:
            c = [nd.calibration(z, k) for z,k in zip((prev,nxt),coeff)]
            if any(z['status']!='CALIBRATION_ONLY' for z in c):
                raise ValueError('D验证观测冲突')
            v = prev['values']
            xx.append([math.log(c[0]['eta']/(scales[0]*nd.curve(prev,base_model))),
                       max(v['hires_fires'],0)/v['previous_workers'], max(-v['hires_fires'],0)/v['previous_workers']])
            yy.append(math.log(c[1]['eta']/(scales[1]*nd.curve(nxt,base_model))))
        return xx, yy, scales[1]
    for held in sorted({s['market'] for _,s in pairs}):
        train = [pair for pair in pairs if pair[1]['market']!=held]
        test = [pair for pair in pairs if pair[1]['market']==held]
        xx, yy, ms = [], [], []
        for inner in sorted({s['market'] for _,s in train}):
            tr = [pair for pair in train if pair[1]['market']!=inner]
            tt = [pair for pair in train if pair[1]['market']==inner]
            x, y, _ = residuals(tr, tt); xx += x; yy += y; ms += [inner]*len(y)
        xt, _, next_scale = residuals(train, test)
        corrections = {}
        for name, cols in alternatives.items():
            design = np.asarray(xx)[:,cols]
            if cols and np.linalg.matrix_rank(design-design.mean(axis=0))<len(cols):
                continue
            fit, predict = nd.select_ridge(design, yy, ms)
            corrections[name] = predict(fit, np.asarray(xt)[:,cols])
            fits.append(dict(experiment='D|'+name, held_market=held, columns=cols, fit=fit,
                train_ids=[nd.key_string(s['key']) for _,s in train]))
        for i,(_,s) in enumerate(test):
            base = next_scale*nd.curve(s,base_model)
            d_rows.append(dict(sample_id=nd.key_string(s['key']),market=held,
                actual=s['values']['q']/s['values']['workers'],baseline=base,
                **{name:base*math.exp(float(values[i])) for name,values in corrections.items()}))
    for name in alternatives:
        rows = [r for r in d_rows if name in r and 'residual' in r]
        results['D_base|'+name] = summary(rows, 'baseline', name)
        if name not in ('intercept','residual'):
            results['D_increment|'+name] = summary(rows, 'residual', name)
    predictions += [dict(r,experiment='D_fixed_alternatives',metric='效率千单位/人') for r in d_rows]
    splits = nd.read(evidence/'划分.json')
    temporal = [r for r in splits if r['experiment'].startswith('B4')]
    results['D_selection'] = dict(folds=len(temporal), selected_columns=dict(Counter(str(r['columns']) for r in temporal)),
        names={0:'上期残差', 1:'招聘率', 2:'裁员率'},
        warning='内层折外残差再选正则的更深层切分仍共享基准训练信息；外层整市场留出有效，但选型可能不稳。仅单一正式转移。')
    nd.save(out/'diagnostics.json', results)
    nd.save(out/'diagnostic_predictions.json', predictions)
    nd.save(out/'diagnostic_folds.json', fits)
    nd.save(out/'manifest.json', dict(evidence=str(evidence), input_hashes=input_hashes,
                                    scope='本地六模型研究；不部署', source_coverage=frozen['coverage']))
    nd.assert_unchanged({'files': input_hashes})
    print(json.dumps(dict(output=str(out), diagnostics=len(results), predictions=len(predictions)), ensure_ascii=False))


if __name__ == '__main__':
    np.testing.assert_allclose(shift_basis(10, 30), [0, 0])
    np.testing.assert_allclose(shift_basis(20, 30), [.5, 0])
    np.testing.assert_allclose(shift_basis(30, 30), [1/3, 1/3])
    np.testing.assert_allclose(origin_fit([[1], [2], [3]], [2, 4, 6], [1, 2, 2]), [2])
    assert summary([dict(market=m, actual=0, baseline=1, candidate=.5) for m in range(5)])['allow_deployment'] is False
    main()
