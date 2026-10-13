"""Inspect saved round 3 evidence; no platform access or model fitting."""
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'output/round_close/20261012T221044.031+0800'
NS = {'s': 'http://www.w3.org/2000/svg'}


def write(name, value):
    with (BASE / name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def redact(s):
    for pattern, initials in [(r'浦\s*语曈|浦语', 'PYT'), (r'金\s*晔', 'JY'),
                              (r'徐\s*昕岚|徐昕', 'XXL'), (r'沈\s*睿琦|沈睿', 'SRQ'),
                              (r'欣\s*刘', 'XL')]:
        s = re.sub(pattern, initials, s)
    return s


def main():
    evidence, charts, curves = [], [], []
    for file in sorted((BASE / 'raw').glob('round3_*.json')):
        doc = json.loads(file.read_text(encoding='utf-8-sig'))
        if not isinstance(doc, dict):
            continue
        sha = hashlib.sha256(file.read_bytes()).hexdigest()
        evidence.append(dict(file=str(file.relative_to(BASE)), sha256=sha,
                             captured_at=doc.get('captured_at'), kind=doc.get('kind'),
                             url=doc.get('url', doc.get('source_url')),
                             text=redact(doc.get('text', doc.get('snapshot', ''))),
                             tables=json.loads(redact(json.dumps(doc.get('tables', []), ensure_ascii=False))),
                             inputs=doc.get('inputs', []), svg_count=len(doc.get('svgs', []))))
        for line in [l for s in doc.get('scripts', []) for l in s.splitlines() if l.startswith('Chart.create(')]:
            m = re.fullmatch(r'Chart\.create\("([^"]+)", "([^"]+)", (\{.*\}), "([^"]+)"\);;', line)
            assert m, 'Chart format changed'
            data = json.loads(m[3])
            chart = dict(source=str(file.relative_to(BASE)), source_sha256=sha,
                         captured_at=doc['captured_at'], market=5, phase='formal', round=3,
                         area='PYT', id=m[1], type=m[2], container=m[4], data=data)
            charts.append(chart)
            if file.name != 'round3_productionplanning.json' or m[1] not in ('quality.control.chart', 'cost.efficiency.chart'):
                continue
            axis = '需求乘数' if m[1] == 'quality.control.chart' else '效率乘数'
            svg = next(s for s in doc['svgs'] if axis in s)
            tree = ET.fromstring(svg)
            plot = next(r for r in tree.findall('.//s:rect', NS) if r.get('fill') == '#eeeeee'
                        and float(r.get('width', 0)) > 500 and float(r.get('height', 0)) > 100)
            ymax = max(float(''.join(t.itertext())) for t in tree.findall('.//s:text', NS)
                       if t.get('x') == '35.4' and re.fullmatch(r'\d+(\.\d+)?', ''.join(t.itertext())))
            paths = [p for p in tree.findall('.//s:path', NS) if len(p.get('d', '')) > 500]
            x = [float(p['label']) for p in data['categories'][0]['category']]
            assert len(x) == 200 and all(a < b for a, b in zip(x, x[1:]))
            for series in data['dataset']:
                if not series['seriesname'].startswith('曲线'):
                    continue
                y = [float(p['value']) for p in series['data']]
                assert len(y) == 200 and all(math.isfinite(v) and v > 0 for v in y)
                candidates = []
                for p in paths:
                    pts = [(float(a), float(b)) for a, b in re.findall(r'[ML](-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', p.get('d'))
                           if float(a) >= float(plot.get('x'))]
                    if len(pts) != 200:
                        continue
                    sy = [(float(plot.get('y')) + float(plot.get('height')) - b) / float(plot.get('height')) * ymax for a, b in pts]
                    candidates.append((max(abs(a - b) for a, b in zip(y, sy)), p.get('stroke')))
                delta, color = min(candidates)
                assert delta < 1e-10, (series['seriesname'], delta)
                curves.append(dict(source=chart['source'], chart_id=m[1], series=series['seriesname'],
                                   points=200, json_svg_max_y_difference=delta, svg_color=color,
                                   independent_samples=200, svg_additional_samples=0,
                                   x_labels=x, y=y, x_precision='rounded displayed labels',
                                   previous_actual_inputs={'rd_beams':800,'rd_connectors':0,'operations_thailand':750},
                                   previous_actual_input_unit='thousand USD; displayed last year on same page'))
    write('round3_evidence_index_final.json', evidence)
    write('raw/round3_charts_extracted_final.json', charts)
    write('round3_curve_verification_final.json', curves)
    assert len(curves) == 3
    assert {'曲线, 复合梁', '曲线, 连接件', '曲线, 泰国'} == {c['series'] for c in curves}
    states = []
    for name in ['decisionchecklist', 'decisionchecklist_readback']:
        doc = json.loads((BASE / f'raw/round3_{name}.json').read_text(encoding='utf-8'))
        table = next(t for t in doc['tables'] if t and '营销团队' in t[0])
        columns = ['group', 'JY', 'XXL', 'SRQ', 'PYT']
        section, product, category = '', '', 'current_decision_input'
        rows = []
        for i, row in enumerate(table[4:], 4):
            if len(row) == 1:
                if row[0] in ['复合梁', '连接件', '泰国', '下回合']:
                    product = row[0]
                else:
                    section = row[0]
                    product = ''
                if row[0] == '回合预算':
                    category = 'budget'
                elif row[0] == '每单位价格':
                    category = 'current_decision_input'
                elif row[0] == '预估':
                    category = 'player_forecast'
            elif len(row) == 6:
                rows.append(dict(source_row=i, section=section, product_context=product,
                                 field=row[0], category=category,
                                 values=dict(zip(columns, row[1:]))))
        states.append(dict(source=f'raw/round3_{name}.json', captured_at=doc['captured_at'],
                           market=5, phase='formal', round=3, rows=rows))
    write('round3_decisions_by_area.json', states)
    pages = ['tutorial', 'outlook_full', 'demand', 'productioninvestments', 'productionplanning',
             'sales_domestic', 'sales_indonesia', 'sales_orders', 'logistics', 'corporate',
             'decisionchecklist', 'schedule']
    write('round3_complete.json', dict(status='PARTIAL_BUDGET_SUBPAGE_NAVIGATION_FAILED',
        detailed_decision_pages_collected=pages, market=5, phase='formal', round=3,
        team='营销团队', initial_area='PYT', deadline_beijing='2026-10-13T22:00:00+08:00',
        five_part_outlook_complete=True, curves_verified=curves,
        decisions_by_area='round3_decisions_by_area.json', evidence='round3_evidence_index_final.json',
        no_platform_input_mutations=True, no_results_access=True, no_training_or_recommendations=True,
        collected_budget=['income_statement'],
        gaps=['预算资产负债表：两次Playwright与一次原生点击均返回财务页且面板关闭，文件名budget_balance不代表取得资产负债表',
              '预算现金流量表：子栏切换后无可定位链接；未取得',
              '预算金融指标：未取得，不能用当前财务决策页代替',
              '采集期间PYT个人方案变化：早期销售原件与后期预算不能合并为同一方案',
              '正式2最终决策与实际由另一对话处理，本次当前草稿不能代替历史生效方案'],
        narrative_parameter_separation={'central_bank_narrative':'3%→5%', 'baseline_parameter':'4.00%',
            'player_interest_forecast':'3.00%'},
        last_observed_differences={'PYT':{'beam_price_thailand':'6600.0','beam_price_indonesia':'1500.0',
            'designer_marketing_thailand_thousand_usd':'1000','budget_profit_thousand_usd':'4513'},
            'group':{'beam_price_thailand':'1950.0','beam_price_indonesia':'2250.0',
            'designer_marketing_thailand_thousand_usd':'100','budget_profit_thousand_usd':'1252'}}))
    print(json.dumps({'evidence_files':len(evidence), 'charts':len(charts), 'verified_curves':len(curves)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
