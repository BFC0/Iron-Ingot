"""Add provenance labels to active archive indexes without changing source files."""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from archive_and_report import table_rows
from audit_incremental import classify

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output/data_labels'
TYPES = {'actual': '期末真实值', 'known': '期初已知条件',
         'decision': '当前决策输入', 'forecast': '玩家预测', 'budget': '预算测算值'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def metadata(path, old):
    data = read(path)
    name = path.stem
    phase, rnd, kind = classify(name)
    match = re.search(r'(?:market|selection)_(\d+)_(initial|practice|formal)_?(\d+)', name)
    market = old.get('market_id', old.get('market', 5))
    if match:
        market, phase, rnd = int(match[1]), match[2], int(match[3])
        kind = 'actual_result' if name.startswith('market_') else 'context_or_selection'
    phase = data.get('phase', phase)
    rnd = data.get('round', rnd)
    if isinstance(rnd, str):
        rnd = int(re.search(r'\d+', rnd)[0])
    if name.startswith('formal'):
        phase = 'formal'
        rnd = int(re.search(r'formal(\d+)', name)[1])
    if data.get('kind') == 'actual_result':
        kind = 'actual_result'
    if 'selection' in name or name == 'current_decision_navigation':
        kind = 'context_or_selection'
    elif 'checklist' in name:
        kind = old.get('data_kind', 'decision_and_budget_mixed')
        if kind in ('course_context', 'context_or_selection'):
            kind = 'decision_and_budget_mixed'
    if 'outlook' in name:
        kind = 'scenario_parameters'
    if name == '20261012_round2_production_chart_code':
        phase, rnd, kind = 'formal', 2, 'published_chart_parameters'
    if market is None and 'user_practice2_' in name:
        market = 5  # User confirmed all six screenshots belong to market 5.
    if rnd is None and kind not in ('actual_result', 'context_or_selection', 'rules'):
        found = re.search(r'generic: 回合(\d+)', data.get('snapshot', ''))
        if found:
            phase, rnd = 'formal', int(found[1])
    item = dict(old, file=path.relative_to(ROOT).as_posix(), market=market,
                phase=phase, round=rnd, data_kind=kind,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    item.setdefault('captured_at', data.get('captured_at'))
    if 'user_practice2_' in name:
        item['market_identity_basis'] = '用户于2026-10-12确认六份练习2截图全部属于市场5'
    return item, data


def label(kind, rnd):
    return f'{rnd}回合{TYPES[kind]}' if rnd is not None else '回合待确认：' + TYPES[kind]


def budget_source(item):
    name = Path(item['file']).stem
    if 'probe_A' in name or 'baseline' in name:
        return '试验前基准预算', '预算销量 = min{决策填写的需求预估数量，产量}（用户2026-10-13更正）；须同时检查保存有效性'
    if 'probe_B' in name or 'modeltest_C_' in name or 'modeltest_D_' in name or 'native_25' in name:
        return '手填试验后网页预算', '预算销量 = min{决策填写的需求预估数量，产量}（用户2026-10-13更正）；须同时检查保存有效性'
    return '常规网页预算', '预算销量 = min{决策填写的需求预估数量，产量}（用户2026-10-13更正）；须同时检查保存有效性'


def cell_kinds(item, row, before, block):
    cells = row['cells']
    if not cells:
        return []
    field = cells[0]
    count = len(cells) - 1
    if item['data_kind'] == 'actual_result':
        return ['actual'] * count
    if item['data_kind'] == 'scenario_parameters':
        return ['known'] * count
    if len(cells) == 5 and cells[-1] in ('K', 'D', 'F', 'B'):
        kind = {'K': 'known', 'D': 'decision', 'F': 'forecast', 'B': 'budget'}[cells[-1]]
        if '去年' in cells[1]:
            kind = 'actual'
        return ['context', kind, 'context', 'context']
    if count == 0 or any(x in cells for x in ['今年', '去年', '下回合']):
        return ['context'] * count
    name = Path(item['file']).stem
    if item['data_kind'] in ('rules', 'context_or_selection', 'course_context', 'rendered_chart_geometry'):
        return ['context'] * count
    kind = 'budget'
    if 'checklist' in name:
        heads = re.findall(r'heading "([^"]+)" \[level=[23]\]', before)
        section = heads[-1] if heads else ''
        if section == '财务':
            kind = 'forecast'
        elif '回合预算' in section:
            kind = 'budget'
        elif any(x in section for x in ['需求', '增长', '效率']):
            kind = 'forecast'
        elif section:
            kind = 'decision'
        else:
            kind = 'context'
    elif re.search(r'(?:textbox|combobox|spinbutton|checkbox)', block):
        kind = 'forecast' if ('demand' in name or '生产效率' in field or '贷款利率' in field or
                              ('investments' in name and '需求预测' in before)) else 'decision'
    elif any(x in field for x in ['期初库存', '可投标订单', '已获得大客户订单', '1月1日']):
        kind = 'known'
    elif 'investments' in name and field in ('机器产能, 复合梁', '生产能力'):
        kind = 'known'
    elif 'production' in name and field == '产能, 千单位':
        kind = 'known'
    elif field.startswith('生产策略'):
        kind = 'known'
    elif field == '需求' and 'sales' in name:
        kind = 'forecast'
    result = [kind] * count
    if 'demand' in name and field in ('泰国', '印尼'):
        if count == 3:
            result = ['actual', 'forecast', 'budget']
        elif count == 4:
            result = ['actual', 'actual', 'budget', 'forecast']
    elif 'investments' in name and field == '复合梁' and count == 3:
        result = ['budget', 'forecast', 'budget']
    # Last-year columns carry previous results; outlook columns are published conditions.
    heads = re.findall(r'- row "([^"]*(?:今年|去年)[^"]*)"', before)
    if heads and heads[-1].endswith('去年') and '今年' in heads[-1] and count >= 2:
        result[-1] = 'actual'
    return result


def make_rows(item, data):
    snapshot = data.get('snapshot', '')
    lines = snapshot.splitlines()
    rows = table_rows(snapshot)
    result = []
    for pos, row in enumerate(rows):
        start = row['line'] - 1
        stop = rows[pos + 1]['line'] - 1 if pos + 1 < len(rows) else len(lines)
        before, block = '\n'.join(lines[:start]), '\n'.join(lines[start:stop])
        kinds = cell_kinds(item, row, before, block)
        cell_labels = []
        for col, (value, kind) in enumerate(zip(row['cells'][1:], kinds), 1):
            if kind == 'context':
                continue
            if item['data_kind'] == 'actual_result' and not re.search(r'\d', value):
                continue
            rnd = item['round']
            if kind == 'actual' and item['data_kind'] != 'actual_result' and rnd is not None:
                rnd -= 1
            tag = dict(column=col, value=value, category=kind, label=label(kind, rnd),
                       value_round=rnd, available_at_round=item['round'], phase=item['phase'])
            tag['value_phase'] = 'initial' if rnd == 0 else item['phase']
            if kind == 'actual' and item['data_kind'] != 'actual_result':
                tag['role'] = '上一回合历史值；本回合期初可知，不代表本回合期末值'
            if kind == 'budget':
                tag['budget_subtype'], tag['assumption'] = budget_source(item)
                tag['save_status'] = ('invalid' if item['data_kind'] == 'invalid_probe' else
                                      'verified' if item['data_kind'] == 'validated_budget_probe' else 'not_verified_here')
                tag['usable_as_actual'] = False
            if '下回合' in row['cells'][0] and rnd is not None:
                tag['target_round'] = rnd + 1
            cell_labels.append(tag)
        result.append(dict(source=item['file'], line=row['line'], market=item['market'],
                           phase=item['phase'], round=item['round'],
                           row_label='；'.join(sorted({x['label'] for x in cell_labels})) or '上下文/表头',
                           cells=cell_labels))
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = ROOT / '数据分组索引.json'
    old_index = read(index_path)
    old_by_path = {x['file']: x for x in old_index}
    paths = {ROOT / x['file'] for x in old_index}
    paths.update((ROOT / 'raw').rglob('*.json'))
    paths.update((ROOT / 'output/formal_update/20261011T223000+0800_sources').glob('*.json'))
    source_hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    index, labels = [], []
    for path in sorted(paths):
        item, data = metadata(path, old_by_path.get(path.relative_to(ROOT).as_posix(), {}))
        source_rows = make_rows(item, data)
        item['labels'] = sorted({c['label'] for r in source_rows for c in r['cells']})
        if item['data_kind'] == 'actual_result':
            item['data_label'] = label('actual', item['round'])
        elif item['data_kind'] in ('scenario_parameters', 'published_chart_parameters'):
            item['data_label'] = label('known', item['round'])
        else:
            item['data_label'] = '逐单元格区分' if item['labels'] else '上下文/规则/选择证据'
        if any(c['category'] == 'budget' for r in source_rows for c in r['cells']):
            item['budget_subtype'], item['budget_assumption'] = budget_source(item)
        index.append(item)
        labels.extend(source_rows)
    lookup = {(x['source'], str(x['line'])): x for x in labels}
    grouped_path = ROOT / '分组表格行索引.csv'
    with grouped_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, grouped = list(reader.fieldnames), list(reader)
    for field in ['编号市场', '数据标签', '单元格标签JSON']:
        if field not in fields:
            fields.append(field)
    for row in grouped:
        match = lookup.get((row['来源文件'], row['快照行号']))
        if match:
            row.update(编号市场=match['market'], 数据标签=match['row_label'],
                       单元格标签JSON=json.dumps(match['cells'], ensure_ascii=False))
        else:
            row.update(编号市场='', 数据标签='旧索引源行未匹配，待核验', 单元格标签JSON='[]')
    write(OUT / 'source_index_before.json', old_index) if not (OUT / 'source_index_before.json').exists() else None
    write(index_path, index)
    with grouped_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(grouped)
    write(OUT / 'cell_labels.json', labels)
    with (OUT / '数据标签.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['来源文件', '编号市场', '阶段', '回合', '快照行号', '数据标签', '单元格标签JSON'])
        writer.writerows([r['source'], r['market'], r['phase'], r['round'], r['line'], r['row_label'],
                          json.dumps(r['cells'], ensure_ascii=False)] for r in labels)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p, sha in source_hashes.items())
    actual = [x for x in index if x['data_kind'] == 'actual_result']
    assert {x['market'] for x in actual} == set(range(1, 11))
    assert all(x['data_label'] == label('actual', x['round']) for x in actual)
    assert all(isinstance(x['round'], int) for x in actual)
    assert not any('selection' in x['file'] for x in actual)
    demand = lookup[('raw/round1_demand.json', '121')]['cells']
    assert [x['category'] for x in demand] == ['actual', 'actual', 'budget', 'forecast']
    assert demand[0]['value_round'] == 0 and demand[-1]['value_round'] == 1
    screenshot = lookup[('raw/20261011_user_practice2_production.json', '13')]['cells']
    assert screenshot[0]['label'] == '2回合预算测算值'
    probe = lookup[('raw/20261011_user_probe_B_budget_income.json', '101')]['cells']
    assert '预算销量 = min{决策填写的需求预估数量，产量}' in probe[0]['assumption']
    assert probe[0]['save_status'] == 'verified' and probe[-1]['value_round'] == 0
    assert all(not c['usable_as_actual'] for r in labels for c in r['cells'] if c['category'] == 'budget')
    assert all(x['market'] == 5 for x in index if 'user_practice2_' in x['file'])
    verification = dict(status='PASS', source_files=len(index), indexed_rows=len(labels),
                        unchanged_source_hashes=True, actual_report_files=len(actual),
                        label_counts=dict(Counter(c['category'] for r in labels for c in r['cells'])),
                        unmatched_legacy_rows=sum(r['数据标签'].startswith('旧索引') for r in grouped))
    write(OUT / 'verification.json', verification)
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == '__main__':
    main()
