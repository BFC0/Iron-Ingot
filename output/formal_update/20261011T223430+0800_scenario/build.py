"""Read saved visible outlooks; append derived scenario evidence without replacing files."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import table_rows, number

OUT = Path(__file__).resolve().parent
SOURCES = ROOT / 'output/formal_update/20261011T223000+0800_sources'

def write(name, data):
    with (OUT / name).open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def parse(round_number):
    path = SOURCES / f'formal{round_number}_outlook.json'
    doc = json.loads(path.read_text(encoding='utf-8-sig'))
    assert doc['phase'] == 'formal' and doc['round'] == round_number
    assert '市场 5, SUIBE260928-LX-benke' in doc['snapshot']
    assert ('提醒！你目前在 回合1 的决策页面！' in doc['snapshot']) == (round_number == 1)
    source = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  captured_at=doc['captured_at'], source_round=round_number, market_id=5,
                  phase='formal', source_url=doc['source_url'])
    lines = doc['snapshot'].splitlines()
    active = False
    section = subsection = None
    parameters = []
    for row in table_rows(doc['snapshot']):
        if row['row_text'] == '参数':
            active = True
            continue
        if not active:
            continue
        cells = row['cells']
        if not cells:
            heading = lines[row['line']] if row['line'] < len(lines) else ''
            if '[level=3]' in heading:
                section, subsection = row['row_text'], None
            elif '[level=4]' in heading:
                subsection = row['row_text']
            continue
        if len(cells) != 4:
            continue
        label, current, delta, previous = cells
        item = dict(section=section, subsection=subsection, label=label,
                    this_year_raw=current, last_year_raw=previous, displayed_delta_raw=delta,
                    source_line=row['line'], source_round=round_number)
        try:
            now, before, shown = number(current), number(previous), number(delta)
        except ValueError:
            item.update(this_year=None, last_year=None, displayed_delta_percent=None,
                        arithmetic_check='NON_NUMERIC_UNIT_ROW')
        else:
            actual = (now / before - 1) * 100 if before else (0 if now == 0 else None)
            item.update(this_year=now, last_year=before, displayed_delta_percent=shown,
                        computed_delta_percent=actual,
                        arithmetic_check='DISPLAY_CONFLICT' if actual is not None and abs(actual-shown) > .51 else 'CONSISTENT_WITH_ROUNDING')
        parameters.append(item)
    return source, parameters

sources, rows = {}, {}
for round_number in [1, 2]:
    sources[round_number], rows[round_number] = parse(round_number)
key = lambda row: (row['section'], row['subsection'], row['label'])
previous = {key(row): row for row in rows[1]}
continuity = [dict(parameter=key(row), formal1_this_year=previous[key(row)]['this_year_raw'],
                   formal2_last_year=row['last_year_raw'],
                   consistent=previous[key(row)]['this_year_raw'] == row['last_year_raw']) for row in rows[2]]
assert all(item['consistent'] for item in continuity)
def current(label, subsection=None):
    matches = [r for r in rows[2] if r['label'] == label and (subsection is None or r['subsection'] == subsection)]
    assert len(matches) == 1, (label, subsection)
    return matches[0]['this_year']
assert current('复合梁', '原材料成本') == 1053
assert current('机器, 复合梁') == 100
assert current('基准利率') == 2.5 and current('高于基准的短期利率溢价') == 2
write('parameters.json', dict(sources=sources, formal1=rows[1], formal2=rows[2],
    prior_year_continuity=continuity,
    conflicts=[r for rr in rows.values() for r in rr if r['arithmetic_check']=='DISPLAY_CONFLICT'],
    applicability='Visible market 5 parameters only; other markets require their own outlook evidence.',
    formal2_inputs=dict(material_cost_usd_per_unit=1053, machine_unit_capex_usd=100,
        base_rate=.025, short_rate_premium=.02, deposit_rate=.01,
        derived_base_plus_short_premium=.045, derived_rate_scope='参数相加；实际利息金额、长期信用溢价尚待财务机制核验')))
events = [
 dict(topic='demand', source_round=1, time_anchor='不久的将来', effective_round=None,
      status='FORWARD_SIGNAL', statement='泰国难回升、印尼略增；建筑领域将普遍增长',
      followup_round=2, followup='正式2已发布两国需求增加5–10%的今年预测；不是已实现增长标签'),
 dict(topic='demand', source_round=2, time_anchor='今年', effective_round=2,
      status='CURRENT_FORECAST_NOT_OBSERVED_LABEL', countries=['Thailand','Indonesia'], growth_range=[.05,.10]),
 dict(topic='marketing', source_round=2, time_anchor='最近/今年', effective_round=2,
      status='CURRENT_QUALITATIVE_SIGNAL', statement='设计师促销、一般营销越来越重要',
      identifiable_coefficients=False),
 dict(topic='materials', source_round=1, time_anchor='预计上升', effective_round=None,
      status='FORWARD_SIGNAL', followup_round=2, followup='今年表价900→1053，+17%已确认'),
 dict(topic='materials', source_round=2, time_anchor='新技术相关未来变化', effective_round=None,
      status='UNCONFIRMED_FUTURE', narrative_increase_approximately=.20,
      current_price=1053, current_change=.17,
      conflict='未来叙述约20%与当期表格17%并列；不擅自追加20%或以1080代替1053'),
 dict(topic='machines', source_round=1, time_anchor='长远来看', effective_round=None,
      status='FORWARD_SIGNAL', statement='供应商竞争可能带来产品创新',
      followup_round=2, followup='正式2信号变为不久的将来可能降价，时间锚前移，但生效期仍未知'),
 dict(topic='machines', source_round=2, time_anchor='不久的将来', effective_round=None,
      status='UNCONFIRMED_FUTURE', price_decline_up_to=.40, current_price=100,
      hypothetical_lower_bound_price=60, hypothetical_price_is_current=False),
 dict(topic='bulk_order', source_round=1, time_anchor='本年度', effective_round=1,
      status='NO_CURRENT_ORDER', units=0),
 dict(topic='bulk_order', source_round=2, time_anchor='今年报价/明年交货',
      bid_round=2, delivery_round=3, status='OFFER_NOT_AWARDED_ORDER', location='Hong Kong',
      units=2000, bid_unit='USD/unit', full_tender_required=True, winner=None),
 dict(topic='interest', source_round=2, time_anchor='预计下降半个百分点', effective_round=2,
      status='BASE_RATE_TABLE_CONFIRMED_NOT_ALL_BORROWING', prior_base_rate=.03, base_rate=.025,
      prior_short_premium=.015, short_premium=.02, prior_base_plus_short=.045,
      current_base_plus_short=.045, caveat='基准下降被短期溢价上升抵消；长期实际借款成本尚未知')]
write('scenario_comparison.json', dict(sources=sources, events=events,
    horizon=dict(start_round=2,end_round=6,remaining_rounds=5,terminal_reward=None,
      unavailable_future_profit=None, preserve_terminal_state=True),
    rules=['保留正式1来源及当时相对时间锚；正式2更新追加而非抹除旧前瞻',
           '同可见前景不证明隐藏机制相同，不未经核验扩展到其他市场',
           '正式2市场5可与练习2相同可见情境作候选迁移，需正式1留出验证；不可作为已证实机制',
           '需求预测、报价邀请、未来价格信号均不能充当正式已实现训练标签']))
with (OUT/'report_fragment.md').open('x',encoding='utf-8') as handle:
    handle.write('正式2的时间锚已更新：正式1“不久的将来建筑业普遍增长”成为正式2“今年两国需求预计增长5–10%”。这是当前预测，不是销量标签。正式1的机械创新“长远来看”在正式2变为“近期可能降价”，但仍无确认生效回合。旧前瞻作为带来源的历史信号保留。\n\n材料当前表价900→1053（+17%），机器当前仍100。未来材料约增20%、机器最多降40%分别记录为未知生效期的情境，不追加到当前表价。营销的重要性上升可确认，但系数未知。香港2000单位为正式2报价邀请、正式3交货，尚不是已中标订单。\n\n基准利率3%→2.5%，短期溢价1.5%→2%，两者相加仍4.5%；不能把基准下降描述为全部借款成本下降。正式1溢价表显示1.50、去年0.60及+90%，算术应为+150%，该矛盾保留，采用表中当前绝对值。正式2全部“去年”列与正式1“今年”列一致。\n\n以上仅核验市场5。进入正式2后只累计2至6的五期利润，未知未来利润保留为空，不加终值，不自动清债或变现期末资产。\n')
write('self_check.json', dict(source_round_selection_verified=True,
    parameter_rows_per_round={k:len(v) for k,v in rows.items()},
    last_year_continuity_all=True, material_current_1053=True, machine_current_100=True,
    observed_labels_not_inferred=True, source_hashes=sources,
    code_sources=['code/archive_and_report.py','code/model_v2/context.py','code/model_v2/horizon.py']))
print(OUT)
