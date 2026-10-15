"""Read-only reproduction of t5v0 material nested validation."""
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'code'))
import material_unit_cost_model as mat

SOURCE = ROOT / 'output/t5v0/20261015T085218049188+0800'
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
out = ROOT / 'output/t5_material_diagnosis' / stamp
out.mkdir(parents=True, exist_ok=False)
(out / 'work_log.md').write_text('# 材料误差诊断\n\n开始：'+stamp+'。用户要求分析复合梁材料嵌套留出MAE偏大原因。\n不要输出真名，姓名统一用首字母替代。仅复用正式4归档，独立诊断，不替换模型或操作平台。\n', encoding='utf-8')
paths = [SOURCE/'dataset.json', SOURCE/'models_full.json', ROOT/'code/material_unit_cost_model.py', Path(__file__)]
hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
data = json.loads(paths[0].read_text(encoding='utf-8'))
registry = json.loads(paths[1].read_text(encoding='utf-8'))
mat.self_check()
summary = {}
details = []
for product, rows in data['materials'].items():
    saved = registry['materials'][product]
    folds = []
    records = []
    for fold in saved['nested_market_validation']:
        m = fold['held_market']
        train = [r for r in rows if r['market'] != m]
        test = [r for r in rows if r['market'] == m]
        assert not {r['market'] for r in train} & {r['market'] for r in test}
        selected, inner = mat.select(train)
        model = mat.fit(train, selected)
        ev = mat.evaluate(model, test)
        assert selected == fold['selected']
        assert abs(ev['mae_kusd'] - fold['evaluation']['mae_kusd']) < 1e-10
        unit = mat.predict(model, test[0]['published_material'], 1)['unit_cost_usd']
        folds.append(dict(market=m, selected=selected, parameter=model['parameter'], unit=unit,
                          mae=ev['mae_kusd'], max_error=ev['max_abs_error_kusd'], compatible=ev['display_compatible_n']))
        for row, rec in zip(test, ev['records']):
            qhalf = row['sources']['q']['half']
            chalf = row['sources']['cost']['half']
            assert abs(qhalf-.005) < 1e-12 and abs(chalf-.5) < 1e-12
            rec = dict(rec, product=product, market=m, production=row['production'],
                       relative_abs_pct=100*abs(rec['error_kusd'])/row['material_cost'],
                       implied_unit=row['material_cost']/row['production'],
                       implied_low=row['implied_low'], implied_high=row['implied_high'],
                       excess_over_rounding=max(0,abs(rec['error_kusd'])-rec['display_tolerance_kusd']))
            records.append(rec)
    assert len(records) == len(rows)
    final = saved['models'][saved['selected']]
    final_ev = mat.evaluate(final, rows)
    candidates = {f: dict(fit=mat.fit(rows,f), cv=saved['holdout_scores'][f], train=mat.evaluate(mat.fit(rows,f),rows)['mae_kusd']) for f in mat.FORMS}
    lo, hi = max(r['implied_low'] for r in rows), min(r['implied_high'] for r in rows)
    units = [f['unit'] for f in folds]
    qmean = mean(r['production'] for r in rows)
    s = dict(n=len(rows), published_prices=sorted({r['published_material'] for r in rows}),
             nested_mae=mean(abs(r['error_kusd']) for r in records), market_mean_mae=mean(f['mae'] for f in folds),
             max_error=max(abs(r['error_kusd']) for r in records), compatible=sum(r['display_compatible'] for r in records),
             train_mae=final_ev['mae_kusd'], mean_cost=mean(r['material_cost'] for r in rows),
             wape_pct=100*sum(abs(r['error_kusd']) for r in records)/sum(r['material_cost'] for r in rows),
             mean_row_ape_pct=mean(r['relative_abs_pct'] for r in records),
             mean_tolerance=mean(r['display_tolerance_kusd'] for r in records),
             common_unit_interval=[lo,hi] if lo<=hi else None,
             unit_range=[min(units),max(units)], unit_range_at_mean_q=(max(units)-min(units))*qmean,
             q_range=[min(r['production'] for r in rows),max(r['production'] for r in rows)],
             excess_over_rounding=sum(r['excess_over_rounding'] for r in records),
             signed_error_mean=mean(r['error_kusd'] for r in records),
             positive=sum(r['error_kusd']>0 for r in records), negative=sum(r['error_kusd']<0 for r in records),
             candidates=candidates, folds=folds,
             largest=sorted(records,key=lambda r:abs(r['error_kusd']),reverse=True)[:5],
             distinct_costs=len({r['material_cost'] for r in rows}),
             distinct_quantities=len({r['production'] for r in rows}))
    assert s['compatible'] == len(rows) or s['excess_over_rounding'] > 0
    summary[product]=s
    details.extend(records)
source_hashes = {}
for rows in data['materials'].values():
    for row in rows:
        for source in row['sources'].values():
            p = source.get('source_path', source.get('source'))
            sha = source.get('sha256')
            if p and sha:
                assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == sha
                source_hashes[p]=sha
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in hashes.items())
(out/'diagnosis.json').write_text(json.dumps(dict(summary=summary,input_hashes=hashes,raw_source_hashes=source_hashes),ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'residuals.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(details[0]));writer.writeheader();writer.writerows(details)
(out/'diagnose_t5_materials.py').write_bytes(Path(__file__).read_bytes())
with (out/'work_log.md').open('a',encoding='utf-8') as f:
    f.write('\n完成：双产品全部外层折选型与MAE复现、市场隔离、显示半格和源哈希检查通过。原模型及原数据未改。\n')
print(out)
print(json.dumps(summary,ensure_ascii=False,indent=2))
