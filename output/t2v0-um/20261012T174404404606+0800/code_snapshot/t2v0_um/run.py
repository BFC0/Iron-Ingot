"""Isolated round-2 evidence gate, fits and guarded prediction. Never writes old runs."""
import argparse
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'code'), str(ROOT / 'code/model_v2')]
import numpy as np
from scipy.optimize import least_squares
import core
import unified_market as um
import country_demand
import formal_update_train as formal
import formal_update_state as state_reader
import operations_rho as ops
from archive_and_report import table_rows
from fit_chart_json import fit_points

MODEL_ID = 't2v0-um'
CONTEXT = 'T2_UNIFIED_MARKET_ASSUMPTION'
BACKGROUND = 'output/scenario_archive/20261011T195927898602+0800/background.json'
SECTIONS = ('production', 'investments', 'logistics', 'orders', 'finance')
SALES = ('price', 'general', 'designer', 'rd')


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def reference(ref):
    """Resolve only hashed local evidence; a manifest value cannot replace a source."""
    path = (ROOT / ref['file']).resolve()
    if not path.is_relative_to(ROOT) or core.digest(path) != ref['sha256']:
        raise ValueError('Evidence path/hash mismatch')
    value = json.loads(path.read_text(encoding='utf-8'))
    for part in ref.get('pointer', '').split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def period_identity(ref, phase):
    identity = reference(ref)
    if (identity.get('phase'), identity.get('round'), identity.get('market_id')) != (phase, 2, 5):
        raise ValueError('Need independently archived market5 phase/round identity')
    if identity.get('selection_verified') is not True or not identity.get('captured_at'):
        raise ValueError('Unverified capture identity')
    return identity


def required_items():
    background = core.read(BACKGROUND)
    result = {f'outlook/narrative/{i}': dict(unit='文字', source_line=r['line'])
              for i, r in enumerate(background['narratives'])}
    for i, row in enumerate(background['parameters']):
        result[f'outlook/parameter/{i}'] = dict(unit=row['unit'], label=row['cells'][0], section=row['section'])
    for name in ('rd', 'operations'):
        result[f'curve/{name}'] = dict(unit='有效投入千美元/无量纲')
    for country in core.COUNTRIES:
        for name in SALES:
            result[f'sales/{country}/{name}'] = dict(unit='无量纲')
    for section in SECTIONS:
        result[f'given/{section}'] = dict(unit='各字段注明单位', requires_full_given_parameter_inventory=True)
    return result


def practice_outlook():
    b = core.read(BACKGROUND)
    ref = dict(file=b['linked_dom']['file'], sha256=b['linked_dom']['sha256'], phase='practice', round=2)
    result = {f'outlook/narrative/{i}': dict(value=r['cells'][0], unit='文字', reference=dict(ref, line=r['line'], column=0))
              for i, r in enumerate(b['narratives'])}
    for i, r in enumerate(b['parameters']):
        result[f'outlook/parameter/{i}'] = dict(value=r['cells'][1], unit=r['unit'],
            reference=dict(ref, line=r['line'], column=1))
    return result


def load_period(bundle, phase):
    period_identity(bundle['identity'], phase)
    result = {}
    requirements = required_items()
    for key, item in bundle['items'].items():
        ref = item['reference']
        source = reference(ref)
        capture = reference(dict(ref, pointer=''))
        if (capture.get('phase'), capture.get('round'), capture.get('market_id')) != (phase, 2, 5):
            raise ValueError('Source capture itself must carry verified phase/round/market metadata')
        if capture.get('selection_verified') is not True or not capture.get('captured_at'):
            raise ValueError('Source capture identity is incomplete')
        if 'line' in ref:
            rows = table_rows(source['snapshot'])
            source = next(r['cells'][ref['column']] for r in rows if r['line'] == ref['line'])
        if source != item['value'] or item['phase'] != phase or item['round'] != 2:
            raise ValueError('Value/period not bound to original source')
        if key in requirements and item['unit'] != requirements[key]['unit']:
            raise ValueError('Evidence unit differs from required unit')
        if key.startswith('given/') and item.get('coverage') != 'ALL_VISIBLE_GIVEN_PARAMETERS_REVIEWED':
            raise ValueError('Given-parameter inventory has not been reviewed for completeness')
        result[key] = item
    return result


def same_value(a, b):
    if a['unit'] != b['unit']:
        return False
    # Only explicitly archived display resolutions permit a rounding interval.
    if isinstance(a['value'], (float, int)) and not isinstance(a['value'], bool) and isinstance(b['value'], (float, int)):
        resolution_a, resolution_b = a.get('resolution', 0), b.get('resolution', 0)
        if not all(np.isfinite(v) for v in (a['value'], b['value'], resolution_a, resolution_b)):
            raise ValueError('Nonfinite value/resolution')
        if resolution_a < 0 or resolution_b < 0:
            raise ValueError('Negative resolution')
        return abs(a['value'] - b['value']) <= (resolution_a + resolution_b) / 2
    return a['value'] == b['value']


def compare(evidence=None):
    pools = {'practice': practice_outlook(), 'formal': {}}
    errors = []
    if evidence:
        for phase in pools:
            try:
                pools[phase] = load_period(evidence[phase], phase)
            except (KeyError, ValueError, TypeError, StopIteration, OSError) as exc:
                pools[phase] = {}
                errors.append(dict(phase=phase, error_type=type(exc).__name__, reason=str(exc)))
    rows = []
    for key, description in required_items().items():
        a, b = pools['practice'].get(key), pools['formal'].get(key)
        status = '证据不足'
        if a and b:
            status = '一致' if same_value(a, b) else '不同'
        rows.append(dict(key=key, **description, status=status, practice=a, formal=b))
    passed = bool(rows) and not errors and all(r['status'] == '一致' for r in rows)
    return dict(model_id=MODEL_ID, passed=passed, rows=rows, errors=errors,
                hidden_mechanism_equivalence='USER_AUTHORIZED_ASSUMPTION_NOT_VERIFIED',
                market_sharing='same round/context only; market5 evidence shared by user assumption'), pools


def validate_rows(rows, phase, country=None):
    if not rows or any(r['phase'] != phase or r['round'] != 2 or r['context_id'] != CONTEXT for r in rows):
        raise ValueError('Only the bound round2 context is accepted')
    if country and any(r['country'] != country for r in rows):
        raise ValueError('Country mismatch')
    if len({tuple(core.key(r)) for r in rows}) != len(rows):
        raise ValueError('Duplicate actual/prediction keys')
    for indices in core.old.groups(rows).values():
        if len(indices) != 10 or len({rows[i]['team_id'] for i in indices}) != 10:
            raise ValueError('Need all ten distinct competitors per market/country')
    for r in rows:
        names = ['price', 'initial_price', 'general', 'designer', 'rd', 'previous_rd']
        if any(r.get(k) is None or not np.isfinite(r[k]) for k in names):
            raise ValueError('Missing/nonfinite model input')
        if min(r['price'], r['initial_price']) <= 0 or min(r[k] for k in names[2:]) < 0:
            raise ValueError('Invalid model input')


def dataset():
    all_rows, _, sources = core.old.load_dataset()
    lookup = {(r['market_id'], r['phase'], r['round'], r['team_column'], r['country']): r for r in all_rows}
    rows = []
    for r in all_rows:
        if (r['phase'], r['round']) != ('practice', 2):
            continue
        if not r['usable_for_fit']:
            raise ValueError('Incomplete practice2 actual history')
        prev = lookup[(r['market_id'], 'practice', 1, r['team_column'], r['country'])]
        initial = lookup[(r['market_id'], 'initial', 0, r['team_column'], r['country'])]
        clean = {k: v for k, v in r.items() if k not in ('team', 'team_id')}
        clean.update(team_id=f"M{r['market_id']}:T{r['team_column']}", context_id=CONTEXT,
            previous_operations=prev['operations'], previous_operations_source=prev['sources']['operations'],
            initial_price_source=initial['sources']['price'], assumption_id=MODEL_ID)
        rows.append(clean)
    validate_rows(rows, 'practice')
    if len(rows) != 200 or {r['market_id'] for r in rows} != set(range(1, 11)):
        raise ValueError('Need 200 actual rows across ten markets')
    kept = [dict(file=s['file'], sha256=s['sha256']) for s in sources
            if (s['phase'], s['round']) in [('initial', 0), ('practice', 1), ('practice', 2)]]
    return rows, kept


def curve_fit(item, form):
    value = item['value']
    if value['form'] != form:
        raise ValueError('Curve structure changed')
    x, y = np.asarray(value['x'], dtype=float), np.asarray(value['y'], dtype=float)
    if x.shape != y.shape or x.ndim != 1 or len(x) < 4 or not np.all(np.isfinite([x, y])):
        raise ValueError('Invalid curve points')
    if x[0] != 0 or not np.all(np.diff(x) > 0) or np.any(y <= 0) or np.any(np.diff(y) < 0):
        raise ValueError('Curve axes/order invalid')
    return dict(fit_points(x, y, form), axis_max=float(x[-1]), source=item['reference'], form=form)


def bound_prediction(rows, model, curve, phase):
    validate_rows(rows, phase, model['country'])
    if model['model_id'] != MODEL_ID or model['context_id'] != CONTEXT or model['curve_id'] != curve['curve_id']:
        raise ValueError('Wrong model/context/curve binding')
    if any(r.get('rd_curve_id') != curve['curve_id'] for r in rows):
        raise ValueError('Row is not bound to this curve')
    if curve['parameters_hash'] != parameter_hash(curve['parameters']):
        raise ValueError('Curve parameters changed after binding')
    if phase not in ('practice', 'formal') or not model['migration_gate_passed']:
        raise ValueError('Migration gate closed')
    return core.predict(rows, core.features(rows, curve['parameters'], model['rho'], model['piecewise']), model['beta'])


def parameter_hash(parameters):
    return hashlib.sha256(json.dumps(parameters, allow_nan=False).encode()).hexdigest()


def freeze_forecast(rows, model_path, totals):
    """Freeze a supplied complete competitor scenario; no automatic rival/total guesses."""
    model_path = Path(model_path).resolve()
    manifest = json.loads((model_path.parent / 'manifest.json').read_text(encoding='utf-8'))
    artifact = json.loads(model_path.read_text(encoding='utf-8'))
    if (manifest['status'] != 'TRAINED_FORMAL2_CANDIDATE' or not artifact['equivalence_gate']['passed']
            or core.digest(model_path) != manifest['output_hashes']['models.json']):
        raise ValueError('Not a verified enabled t2v0-um artifact')
    validate_rows(rows, 'formal')
    if any('demand' in r or r.get('kind') == 'actual_result' for r in rows):
        raise ValueError('Actual demand labels cannot enter a prospective forecast')
    states = state_reader.build(formal.SOURCE)['states']
    lookup = {(s['market_id'], s['team_column']): s['formal2_initial_state'] for s in states}
    for r in rows:
        state = lookup[(r['market_id'], r['team_column'])]
        if r['previous_rd'] != state['previous_rd'] or r['previous_operations'] != state['previous_operations']:
            raise ValueError('Formal2 must use formal1 closing history')
    predictions = []
    for country, model in artifact['demand'].items():
        pool = [r for r in rows if r['country'] == country]
        if not pool:
            continue
        shares = bound_prediction(pool, model, artifact['curves']['rd'], 'formal')
        for r, share in zip(pool, shares):
            total = totals[(r['market_id'], country)]
            if not np.isfinite(total) or total < 0:
                raise ValueError('Invalid explicit industry total scenario')
            predictions.append(dict(key=core.key(r, 'prospective_demand'), predicted_share=float(share),
                industry_total=total, demand=float(share * total), category='formal2_frozen_scenario_forecast',
                actual_rivals_used=False, actual_total_used=False))
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out = ROOT / 'output/t2v0-um' / (stamp + '_forecast')
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'frozen_forecast.json', dict(model_id=MODEL_ID, frozen_at=stamp,
        model_file=model_path.relative_to(ROOT).as_posix(), model_sha256=core.digest(model_path),
        scenario_rows=rows, predictions=predictions, formal1_state_source=str(formal.SOURCE.relative_to(ROOT)),
        limits='Provided rival decisions and industry totals are assumptions; full financial forecast not available'))
    return out


def select(rows, curve):
    path = []
    for cfg in country_demand.CONFIGS:
        folds = []
        for held, train, test in um.grouped_folds(rows):
            m = core.fit(train, curve['parameters'], **cfg)
            p = core.predict(test, core.features(test, curve['parameters'], m['rho'], m['piecewise']), m['beta'])
            folds.append(dict(held_markets=held, training_keys=m['training_keys'],
                              mae_pp=100 * core.score(test, p), scale=m['scale']))
        path.append(dict(config=cfg, folds=folds, cv_share_mae_pp=float(np.mean([f['mae_pp'] for f in folds]))))
    winner = min(path, key=lambda p: (p['cv_share_mae_pp'], p['config']['loss'] != 'share', -p['config']['penalty']))
    return winner['config'], path


def train_country(rows, curve):
    validate_rows(rows, 'practice', rows[0]['country'])
    if any(r.get('rd_curve_id') != curve['curve_id'] for r in rows):
        raise ValueError('Training rows/curve mismatch')
    folds, predictions = [], []
    for held, train, test in um.grouped_folds(rows):
        cfg, path = select(train, curve)
        m = core.fit(train, curve['parameters'], **cfg)
        p = core.predict(test, core.features(test, curve['parameters'], m['rho'], m['piecewise']), m['beta'])
        folds.append(dict(held_markets=held, fitted=m, test_keys=[core.key(r) for r in test],
                          inner_cv_path=path, share_mae_pp=100 * core.score(test, p)))
        for i, r in enumerate(test):
            total = sum(q['demand'] for q in test if core.old.group_key(q) == core.old.group_key(r))
            predictions.append(dict(key=core.key(r), actual=r['demand'], predicted_share=float(p[i]),
                conditional_demand=float(p[i] * total), uses_realized_total=True, uses_realized_rivals=True,
                category='practice2_nested_market_holdout_conditional'))
        print('HOLDOUT', rows[0]['country'], held, flush=True)
    cfg, path = select(rows, curve)
    m = core.fit(rows, curve['parameters'], **cfg)
    ids = [core.COUNTRIES.index(rows[0]['country']), 2, 3, 4]
    m.update(model_id=MODEL_ID, country=rows[0]['country'], context_id=CONTEXT, curve_id=curve['curve_id'],
        training_phase='practice', training_round=2, target_phase='formal', target_round=2,
        migration_gate_passed=True, coefficients=dict(zip(country_demand.NAMES, [m['beta'][i] for i in ids])),
        outer_folds=folds, cv_path=path, nested_market_holdout_share_mae_pp=float(np.mean([f['share_mae_pp'] for f in folds])),
        coefficient_boundary=[country_demand.NAMES[j] for j, i in enumerate(ids) if m['beta'][i] < 1e-7],
        rd_extrapolation_count=sum(r['rd'] + m['rho'] * r['previous_rd'] > curve['axis_max'] for r in rows),
        retained_assumptions=['rd rho=.5', 'marketing scale=1000', 'company-total marketing proxy', 'industry total external'])
    return m, predictions


def mechanism_rows(rows, base_rate, material_cost):
    result = []
    for r in rows:
        if r['country'] != core.COUNTRIES[0]:
            continue
        path, col = ROOT / r['sources']['demand']['file'], r['team_column']
        refs = {k: formal.field(path, label, col) for k, label in [('q', '生产规模, 千单位'),
            ('workers', '生产线人工数量'), ('assets', '资产总计'), ('equity', '股东权益合计'),
            ('long', '长期贷款'), ('short', '短期贷款'), ('rate', '长期贷款利率，%'), ('materials', '原材料购买')]}
        v = {k: ref['value'] for k, ref in refs.items()}
        if any(v[k] is None or not np.isfinite(v[k]) for k in v) or min(v[k] for k in ('q', 'workers', 'assets', 'equity')) <= 0:
            raise ValueError('Invalid actual mechanism input')
        result.append(dict(market_id=r['market_id'], team_id=r['team_id'], operations=r['operations'],
            previous_operations=r['previous_operations'], effective_observed=v['q'] / v['workers'], refs=refs,
            equity_ratio=v['equity'] / v['assets'], leverage=(v['long'] + v['short']) / v['equity'],
            premium=v['rate'] / 100 - base_rate, production=v['q'], material_cost=v['materials'],
            uplift=v['materials'] / v['q'] - material_cost))
    return result


def fit_mechanisms(rows, params, material_cost):
    result = dict(operations_efficiency=dict(chosen=ops.select(rows, params), curve_parameters=params,
        market_holdouts=[]), risk={}, materials={})
    for market in range(1, 11):
        tr, te = [r for r in rows if r['market_id'] != market], [r for r in rows if r['market_id'] == market]
        fitted = ops.select(tr, params)
        result['operations_efficiency']['market_holdouts'].append(dict(held_market=market, fitted=fitted,
            metrics=ops.metrics(te, ops.predict(te, params, fitted))))
    for form in ('solvency_exponential', 'leverage_power'):
        def pred(p, rr):
            return p[0] * np.exp(-p[1] * np.array([r['equity_ratio'] for r in rr])) if form == 'solvency_exponential' else p[0] * np.array([r['leverage'] for r in rr]) ** p[1]
        def fit(rr):
            fitted = least_squares(lambda p: pred(p, rr) - [r['premium'] for r in rr], [.05, 1], bounds=([0, 0], [10, 30]), max_nfev=2000)
            if not fitted.success:
                raise RuntimeError('Risk fit failed')
            return fitted.x
        held = []
        for market in range(1, 11):
            tr, te = [r for r in rows if r['market_id'] != market], [r for r in rows if r['market_id'] == market]
            p = fit(tr)
            held.append(dict(held_market=market, parameters=p.tolist(), mae_basis_points=float(np.mean(abs(pred(p, te) - [r['premium'] for r in te]))) * 10000))
        result['risk'][form] = dict(parameters=fit(rows).tolist(), market_holdouts=held, forecast=False,
            interpretation='conditional actual end-state association; interest timing not identified')
    uplift = float(np.median([r['uplift'] for r in rows]))
    held = []
    for market in range(1, 11):
        tr, te = [r for r in rows if r['market_id'] != market], [r for r in rows if r['market_id'] == market]
        u = float(np.median([r['uplift'] for r in tr]))
        held.append(dict(held_market=market, uplift=u, mae_kusd=float(np.mean([abs(r['production'] * (material_cost + u) - r['material_cost']) for r in te]))))
    result['materials'] = dict(published_material_cost=material_cost, uplift_usd_per_unit=uplift, market_holdouts=held,
        interpretation='displayed-cost residual, not a published markup')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, help='Source-bound complete practice2/formal2 evidence manifest')
    args = parser.parse_args()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out = ROOT / 'output/t2v0-um' / stamp
    out.mkdir(parents=True, exist_ok=False)
    log = out / 'work_log.md'
    log.write_text(f'# t2v0-um工作日志\n\n北京时间：{stamp}。进行中。\n不要输出真名，姓名统一用首字母替代。\n旧模型与原件不覆盖，不修改平台；门槛通过后才训练。\n', encoding='utf-8')
    protected = [p for folder in ('raw', 'sources', 'quarantine', 'output') for p in (ROOT / folder).rglob('*')
                 if p.is_file() and not p.is_relative_to(ROOT / 'output/t2v0-um')]
    protected += [p for p in (ROOT / 'code').rglob('*') if p.is_file() and p.suffix != '.pyc'
                  and not p.is_relative_to(Path(__file__).parent)]
    before = {p.relative_to(ROOT).as_posix(): core.digest(p) for p in protected}
    snapshot = out / 'code_snapshot'
    snapshot.mkdir()
    for p in (ROOT / 'code').rglob('*.py'):
        destination = snapshot / p.relative_to(ROOT / 'code')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, destination)
    manifest = dict(model_id=MODEL_ID, run_id=stamp, status='RUNNING', training_period='practice/2', target_period='formal/2')
    try:
        rows, sources = dataset()
        write(out / 'dataset.json', dict(rows=rows, sources=sources, training_labels='practice2 actual demand only'))
        states = state_reader.build(formal.SOURCE)
        for state in states['states']:
            state.pop('team', None)
            state['team_id'] = f"M{state['market_id']}:T{state['team_column']}"
        write(out / 'formal2_initial_state.json', states)
        candidates = [dict(file='raw/20261012_round2_production_chart_code.json',
            sha256=core.digest(ROOT / 'raw/20261012_round2_production_chart_code.json'),
            round=2, phase=None, status='ROUND2_PRESENT_PHASE_IDENTITY_NOT_INDEPENDENTLY_ARCHIVED',
            use='candidate only; cannot satisfy equivalence gate'),
            dict(file=BACKGROUND, sha256=core.digest(ROOT / BACKGROUND), phase='practice', round=2,
                 use='practice2 visible outlook and screenshot linkage; not formal2 evidence')]
        write(out / 'available_evidence.json', candidates)
        evidence = json.loads(args.evidence.read_text(encoding='utf-8')) if args.evidence else None
        if args.evidence:
            write(out / 'evidence_manifest.json', evidence)
        gate, pools = compare(evidence)
        write(out / 'comparison.json', gate)
        with (out / 'comparison.csv').open('x', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['key', 'unit', 'status', 'practice_value', 'formal_value', 'practice_source', 'formal_source'])
            for r in gate['rows']:
                writer.writerow([r['key'], r['unit'], r['status'], *[json.dumps((r[phase] or {}).get('value'), ensure_ascii=False) for phase in ('practice', 'formal')],
                                 *[json.dumps((r[phase] or {}).get('reference'), ensure_ascii=False) for phase in ('practice', 'formal')]])
        write(out / 'evidence_template.json', dict(model_id=MODEL_ID, required_items=required_items(),
            practice=dict(identity=None, items=pools['practice']), formal=dict(identity=None, items=pools['formal'])))
        if not gate['passed']:
            manifest.update(status='AWAITING_EQUIVALENCE_EVIDENCE', trained=False, prediction_enabled=False)
        else:
            curves = {}
            for name, form in [('rd', 'power'), ('operations', 'saturation')]:
                curves[name] = curve_fit(pools['practice'][f'curve/{name}'], form)
                curves[name]['curve_id'] = hashlib.sha256(json.dumps(pools['practice'][f'curve/{name}']['value'], sort_keys=True).encode()).hexdigest()
                curves[name]['parameters_hash'] = parameter_hash(curves[name]['parameters'])
            for row in rows:
                row['rd_curve_id'] = curves['rd']['curve_id']
                row['operations_curve_id'] = curves['operations']['curve_id']
            write(out / 'curve_bound_dataset.json', rows)
            models, predictions = {}, []
            for country in core.COUNTRIES:
                m, pr = train_country([r for r in rows if r['country'] == country], curves['rd'])
                models[country] = m
                predictions.extend(pr)
            b = core.read(BACKGROUND)['parameters']
            base_index = next(i for i, r in enumerate(b) if r['cells'][0] == '基准利率')
            cost_index = next(i for i, r in enumerate(b) if r['section'] == '原材料成本')
            base = core.old.numeric(str(pools['practice'][f'outlook/parameter/{base_index}']['value'])) / 100
            cost = core.old.numeric(str(pools['practice'][f'outlook/parameter/{cost_index}']['value']))
            mr = mechanism_rows(rows, base, cost)
            mechanisms = fit_mechanisms(mr, curves['operations']['parameters'], cost)
            write(out / 'mechanism_dataset.json', mr)
            write(out / 'models.json', dict(model_id=MODEL_ID, demand=models, mechanisms=mechanisms, curves=curves,
                equivalence_gate=gate, base_rate=base, material_cost=cost, target_period='formal/2',
                finance='existing structure preserved; incomplete branches remain unavailable',
                formal2_prediction_status='NOT_FROZEN_NO_FORECAST_INPUTS',
                hidden_mechanism_equivalence='USER_AUTHORIZED_ASSUMPTION_NOT_VERIFIED'))
            write(out / 'predictions.json', predictions)
            manifest.update(status='TRAINED_FORMAL2_CANDIDATE', trained=True, prediction_enabled=True)
        from self_check import self_check
        checks = self_check()
        checks['protected_hashes_unchanged'] = all(core.digest(ROOT / p) == h for p, h in before.items())
        if not checks['protected_hashes_unchanged']:
            raise RuntimeError('Protected source/model changed')
        write(out / 'checks.json', checks)
        manifest['protected_hashes'] = before
        manifest['input_hashes'] = {s['file']: s['sha256'] for s in sources}
        manifest['code_hashes'] = {p.relative_to(snapshot).as_posix(): core.digest(p) for p in snapshot.rglob('*.py')}
        missing = [r['key'] for r in gate['rows'] if r['status'] != '一致']
        (out / 'report.md').write_text('# t2v0-um 独立版本\n\n'
            + f"状态：{manifest['status']}。练习2实际200条，10市场100队；正式2期初状态来自正式1实际。\n\n"
            + ('一致性门槛未通过；没有训练参数，没有启用正式2迁移。\n\n' if missing else '可见一致性门槛通过；隐藏机制相同仍是假设。验证为同回合条件验证。\n\n')
            + '逐项结果见comparison.csv/JSON；代码自检与旧资料保护见checks.json及manifest.json。\n\n'
            + f"尚未通过：{len(missing)}项。" + ('\n\n' + '\n'.join('- ' + key for key in missing) if missing else '')
            + '\n\n正式2完整财务、税亏、订单条款及存量未识别处保留缺口；第3回合及以后不适用。没有平台改动。\n', encoding='utf-8')
        with log.open('a', encoding='utf-8') as stream:
            stream.write(f"\n完成本地运行：{manifest['status']}；自检通过，原件和旧模型哈希不变。\n")
    except Exception as exc:
        manifest.update(status='FAILED', error_type=type(exc).__name__, prediction_enabled=False)
        with log.open('a', encoding='utf-8') as stream:
            stream.write(f'\n失败：{type(exc).__name__}；保留运行证据，不启用。\n')
        raise
    finally:
        manifest['output_hashes'] = {p.relative_to(out).as_posix(): core.digest(p) for p in out.rglob('*') if p.is_file()}
        write(out / 'manifest.json', manifest)
    print('OUTPUT', out, flush=True)


if __name__ == '__main__':
    main()
