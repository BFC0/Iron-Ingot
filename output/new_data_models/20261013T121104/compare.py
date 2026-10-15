"""Compare fixed archive snapshot with old training fields and paired originals."""
import csv
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import table_rows

AUDIT = ROOT / 'output/round_close/20261012T221044.031+0800/audit/20261013T120552.995614+0800'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def norm(label):
    return re.sub(r'[\s?？，,]', '', label)

def number(value):
    try:
        result = float(re.sub(r'\s', '', str(value)).replace(',', '').replace('%', ''))
        return result if math.isfinite(result) else None
    except ValueError:
        return None

assert norm('已收预付款\n ?') == norm('已收预付款')
assert norm('本回合 复合梁') == norm('本回合复合梁')
assert number('1\u00a0355.32') == 1355.32
assert number('NaN') is None and number('-') is None

refs = read(AUDIT / 'printable_references.json')
old_by_period, old_union = {}, set()
for ref in refs:
    cells = table_rows(read(ROOT / ref['source']).get('snapshot', ''))
    labels = {norm(r['cells'][0]) for r in cells if r['cells']}
    old_by_period[tuple(ref['key'])] = labels
    old_union.update(labels)

new_rows = read(AUDIT / 'rows.json')
groups = defaultdict(list)
for row in new_rows:
    if row['identity_status'] == 'verified':
        groups[(row['source'], row['table_index'])].append(row)

# Keep section headings: repeated product/route labels otherwise hide environmental types.
samples = []
for rows in groups.values():
    heading = ''
    for row in sorted(rows, key=lambda r: r['row_index']):
        cells = row['cells']
        if not cells:
            continue
        label = cells[0].strip()
        if len(cells) <= 2 and label:
            heading = label
        if len(cells) != 11 or not label or len(label) > 90:
            continue
        vals = [number(v) for v in cells[1:]]
        if not any(v is not None for v in vals):
            continue
        samples.append({**{k: row[k] for k in ('source', 'market', 'phase', 'round', 'panel', 'table_index', 'row_index')},
                        'label': label, 'heading': heading, 'values': vals})

new_label_groups = defaultdict(list)
for row in samples:
    new_label_groups[(row['panel'], norm(row['label']), norm(row['heading']))].append(row)
diff = []
for (panel, label, heading), rows in sorted(new_label_groups.items()):
    paired = [r for r in rows if (r['market'], r['phase'], r['round']) in old_by_period]
    present = sum(label in old_by_period[(r['market'], r['phase'], r['round'])] for r in paired)
    diff.append({'panel': panel, 'label': rows[0]['label'], 'heading': rows[0]['heading'],
                 'new_row_count': len(rows), 'paired_rows': len(paired),
                 'normalized_label_present_in_paired_old': present,
                 'normalized_label_present_any_old': label in old_union,
                 'comparison_limit': 'label presence only; product, unit and section semantics require review',
                 'example_source': rows[0]['source'], 'example_table': rows[0]['table_index'], 'example_row': rows[0]['row_index']})
with (OUT / '字段逐项对比.csv').open('x', encoding='utf-8-sig', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(diff[0]))
    writer.writeheader()
    writer.writerows(diff)

old_train_path = ROOT / 'output/formal_update/20261011T225637591747+0800_training/dataset.json'
old_train_fields = sorted({k for row in read(old_train_path)['rows'] for k in row})
old_struct_path = ROOT / '结构化模型输入.json'
old_struct_fields = sorted({k for row in read(old_struct_path)['history'] for k in row['fields']})

def stats(rows):
    values = [v for r in rows for v in r['values'] if v is not None]
    varying = 0
    for row in rows:
        vals = [v for v in row['values'] if v is not None]
        # shortcut: display precision only; exact mechanism inference needs raw graph values.
        if vals and max(vals) - min(vals) > max(0.02, 1e-5 * max(abs(v) for v in vals)):
            varying += 1
    return {'rows': len(rows), 'numeric_cells': len(values), 'nonzero_cells': sum(v != 0 for v in values),
            'min': min(values) if values else None, 'max': max(values) if values else None,
            'rows_varying_between_teams_beyond_display_tolerance': varying,
            'examples': [{k: r[k] for k in ('source', 'table_index', 'row_index', 'label', 'heading')} for r in rows[:2]]}

selected = {}
selectors = {
    'production_co2_total': lambda r: r['panel']=='productionenvironmental' and '公吨' in r['heading'],
    'production_co2_intensity': lambda r: r['panel']=='productionenvironmental' and '二氧化碳' in r['heading'] and '公吨' not in r['heading'],
    'energy_total': lambda r: r['panel']=='productionenvironmental' and 'MWh' in r['heading'],
    'energy_intensity': lambda r: r['panel']=='productionenvironmental' and 'kWh' in r['heading'],
    'water_total': lambda r: r['panel']=='productionenvironmental' and 'm3' in r['heading'],
    'water_intensity': lambda r: r['panel']=='productionenvironmental' and '用水量' in r['heading'] and 'm3' not in r['heading'],
    'transport_emissions': lambda r: r['panel']=='logisticsemissions',
    'previous_workers': lambda r: r['panel']=='productionhr' and '生产人员数量, 上回合'==r['label'],
    'current_workers': lambda r: r['panel']=='productionhr' and '生产人员数量, 本回合'==r['label'],
    'quits': lambda r: r['panel']=='productionhr' and r['label']=='辞职',
    'hires_fires': lambda r: r['panel']=='productionhr' and r['label']=='招聘 + / 裁员 -',
    'layoff_percent': lambda r: r['panel']=='productionhr' and r['label']=='裁员, %',
    'average_wage': lambda r: r['panel']=='productionhr' and r['label']=='每人平均工资, 千 美元',
    'advance_balance': lambda r: r['panel']=='balancesheet' and '已收预付款' in r['label'],
    'share_transaction_cash': lambda r: r['panel']=='cashflow' and ('股票发行' in r['label'] or '股息支付'==r['label']),
}
for name, select in selectors.items():
    selected[name] = stats([r for r in samples if select(r)])

hr = defaultdict(dict)
for row in samples:
    if row['panel']=='productionhr':
        hr[(row['market'],row['phase'],row['round'])][row['label']] = row
rates, identities = [], []
for fields in hr.values():
    labels = ['生产人员数量, 上回合','辞职','招聘 + / 裁员 -','生产人员数量, 本回合']
    if not all(k in fields for k in labels):
        continue
    for prev, quit_, hire, current in zip(*(fields[k]['values'] for k in labels)):
        if all(v is not None for v in (prev,quit_,hire,current)):
            identities.append(abs(prev+quit_+hire-current))
            if prev>0:
                rates.append(-quit_/prev)
assert selected['production_co2_total']['numeric_cells'] > 0
assert selected['quits']['numeric_cells'] > 0
result = {'fixed_audit': str(AUDIT.relative_to(ROOT)), 'coverage': read(AUDIT/'validation.json')['coverage_counts'],
          'paired_old_periods': len(refs), 'old_training_fields': old_train_fields,
          'old_structured_history_fields': old_struct_fields, 'comparison_rows': len(diff),
          'type_stats': selected, 'workforce_identity': {'cells': len(identities), 'max_abs_display_residual_people': max(identities),
          'quits_rate_min': min(rates), 'quits_rate_max': max(rates)},
          'not_trained': True, 'selfchecks': 'passed',
          'source_hashes': [{'path':str(p.relative_to(ROOT)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                            for p in [AUDIT/'rows.json',AUDIT/'validation.json',AUDIT/'printable_references.json',old_train_path,old_struct_path]+[ROOT/ref['source'] for ref in refs]]}
with (OUT/'对比核验.json').open('x',encoding='utf-8') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({k:result[k] for k in ('coverage','paired_old_periods','comparison_rows','workforce_identity')},ensure_ascii=False))
for name, stat in selected.items():
    print(name, {k:v for k,v in stat.items() if k!='examples'})
print('NORMALIZED NEW LABELS', sorted({r['label'] for r in diff if r['paired_rows'] and not r['normalized_label_present_any_old']}))
