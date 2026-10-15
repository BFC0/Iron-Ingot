"""Offline historical decision evidence audit; does not acquire or alter sources."""
import csv
import hashlib
import importlib.util
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
CLOSE = ROOT / 'output/round_close/20261013_formal3_close'
HISTORY = ROOT / 'output/round_close/20261012T221044.031+0800'
spec = importlib.util.spec_from_file_location('old_rules', HISTORY / 'audit/verify_archive.py')
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)
PERIODS = {'practice1':'练习回合1', 'practice2':'练习回合2', 'formal1':'回合1', 'formal2':'回合2', 'formal3':'回合3'}
PANELS = ['outlook','demand','productioninvestments','productionplanning','marketreportdomestic',
          'marketreportinternational1','marketreportbulk','logistics','corporate']


def reminder_period(text):
    match = re.search(r'你目前在\s*(练习回合[12]|回合[123])\s*的决策页面', text)
    return next((key for key, value in PERIODS.items() if match and match[1] == value), None)


def full_html(doc):
    html = doc.get('html', '')
    length = len(html.encode('utf-16-le')) // 2
    return bool(html and '[Truncated]' not in html and re.search(r'</html>\s*$', html, re.I) and
                doc.get('html_length') == length), length


def chart_ranges(charts):
    ranges = []
    for chart in charts:
        data = chart.get('data', {})
        for series in data.get('dataset', []):
            original = [p.get('value') for p in series.get('data', [])]
            values = []
            for value in original:
                try:
                    number = float(value)
                    if math.isfinite(number):
                        values.append(number)
                except (ValueError, TypeError):
                    pass
            ranges.append(dict(chart_id=chart['id'], series=series.get('seriesname'), points=len(original),
                               finite_points=len(values), nonfinite_or_missing=len(original)-len(values),
                               y_min=min(values) if values else None, y_max=max(values) if values else None,
                               original_values=original, categories=data.get('categories', [])))
    return ranges


def pair_curve_y(charts, svgs):
    results = []
    for chart in charts:
        axis = '需求乘数' if 'quality.control' in chart['id'] else '效率乘数' if 'cost.efficiency' in chart['id'] else None
        if not axis:
            continue
        for series in chart['data'].get('dataset', []):
            if not series.get('seriesname', '').startswith('曲线'):
                continue
            result = dict(chart_id=chart['id'], series=series['seriesname'], status='pending',
                          x_precision='rounded category labels; only y reconstructed numerically')
            try:
                values = [float(p['value']) for p in series['data']]
                candidates = []
                for svg_index, svg in enumerate(svgs):
                    if axis not in svg:
                        continue
                    tree = ET.fromstring(svg)
                    nodes = list(tree.iter())
                    rects = [e for e in nodes if e.tag.endswith('rect') and e.get('fill') == '#eeeeee'
                             and float(e.get('width', 0)) > 500 and float(e.get('height', 0)) > 100]
                    if not rects:
                        continue
                    plot = rects[0]
                    ticks = [float(''.join(e.itertext())) for e in nodes if e.tag.endswith('text') and
                             e.get('text-anchor') == 'end' and float(e.get('x','-1')) < float(plot.get('x')) and
                             re.fullmatch(r'\d+(?:\.\d+)?', ''.join(e.itertext()))]
                    if not ticks or min(ticks) != 0:
                        continue
                    ymax = max(ticks)
                    for e in nodes:
                        if not e.tag.endswith('path') or len(e.get('d','')) < 500:
                            continue
                        points = [(float(a),float(b)) for a,b in re.findall(r'[ML](-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)',e.get('d',''))
                                  if float(a) >= float(plot.get('x'))]
                        if len(points) != len(values) or len(points) < 2 or not all(a[0] < b[0] for a,b in zip(points,points[1:])):
                            continue
                        reconstructed = [(float(plot.get('y'))+float(plot.get('height'))-y)/float(plot.get('height'))*ymax for x,y in points]
                        candidates.append((max(abs(a-b) for a,b in zip(values,reconstructed)),svg_index,e.get('stroke')))
                if candidates:
                    delta, index, color = min(candidates)
                    result.update(status='pass_y_values' if delta < 1e-10 else 'fail_y_values',
                                  points=len(values), max_y_difference=delta, svg_index=index, stroke=color,
                                  independent_samples=len(values), svg_additional_samples=0)
                else:
                    result['reason'] = 'no_matching_monotonic_path_and_zero_based_plot_axis'
            except (ValueError, TypeError, KeyError, ET.ParseError) as error:
                result['reason'] = str(error)
            results.append(result)
    return results


def examine(path):
    payload = path.read_bytes()
    doc = json.loads(payload.decode('utf-8-sig'))
    if not isinstance(doc, dict):
        return None
    url = doc.get('url') or doc.get('source_url') or ''
    panel = parse_qs(urlparse(url).query).get('panel', [None])[0]
    if '/Decisions' not in url or panel not in PANELS:
        return None
    text = rules.redact_names(doc.get('text') or doc.get('snapshot') or '')
    period = reminder_period(text)
    declared = doc.get('selected_period', {})
    if isinstance(declared, str):
        declared = {'id':declared}
    expected = declared.get('id') if isinstance(declared, dict) else None
    complete, length = full_html(doc)
    identity = bool(period and expected in (None, period) and
                    (not declared.get('label') or declared['label'] == PERIODS[period]))
    area = bool(re.search(r'决策区域[\s:\\n"-]*(?:generic:\s*)?PYT', text))
    market = bool(re.search(r'市场\s*5\s*,', text))
    if doc.get('area') and doc['area'] != 'PYT':
        area = False
    if doc.get('market') and doc['market'] != 5:
        market = False
    charts, chart_errors = rules.charts(doc.get('html') or '\n'.join(doc.get('scripts', [])))
    if not charts:
        charts, chart_errors = rules.charts('\n'.join(doc.get('scripts', [])))
    svg_markup = re.findall(r'<svg\b[\s\S]*?</svg>', doc.get('html',''), re.I)
    if not svg_markup:
        svg_markup = doc.get('svgs', doc.get('svg', []))
    if not isinstance(svg_markup, list):
        svg_markup = [svg_markup] if svg_markup else []
    source = dict(source=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(payload).hexdigest(),
                  captured_at=doc.get('captured_at'), url=url, panel=panel, period=period,
                  declared_period=expected, period_from_reminder_verified=identity,
                  personal_area='PYT' if area else 'unverified', market5_verified=market,
                  category='historical_personal_input_and_outlook_not_group_decisions',
                  html_complete=complete, html_utf16_length=length, declared_html_length=doc.get('html_length'),
                  truncated='[Truncated]' in doc.get('html',''), chart_count=len(charts), chart_errors=chart_errors,
                  svg_count=len(svg_markup), valid_identity_and_html=bool(identity and area and market and complete),
                  chart_svg_status='co_present_not_numeric_verified' if charts and svg_markup else
                      'chart_json_without_svg' if charts else 'no_chart_initialized')
    if panel == 'productionplanning':
        ids = [c['id'] for c in charts]
        source['required_curve_charts_present'] = any('quality.control' in i for i in ids) and any('cost.efficiency' in i for i in ids)
        source['valid_identity_and_html'] &= bool(source['required_curve_charts_present'] and svg_markup and not chart_errors)
    tables, basis = rules.get_tables(doc)
    table_rows = []
    for ti, table in enumerate(tables):
        if isinstance(table, dict):
            table = table.get('rows', [])
        context = []
        for ri, cells in enumerate(table):
            clean = [rules.redact_names(str(cell)) for cell in cells]
            if len(clean) == 1 and clean[0] and len(clean[0]) < 100:
                context.append(clean[0])
            table_rows.append(dict(source=source['source'], source_sha256=source['sha256'],
                                   table_index=ti, row_index=ri, cells=clean, section_path=context.copy(),
                                   category=source['category'], period=period, panel=panel, basis=basis))
    source['table_rows'] = len(table_rows)
    pairings = pair_curve_y(charts, svg_markup)
    source['curve_y_pairing_counts'] = {status:sum(p['status']==status for p in pairings) for status in set(p['status'] for p in pairings)}
    return source, table_rows, charts, chart_ranges(charts), [dict(index=i, characters=len(svg),
        path_count=len(re.findall(r'<path\b',svg)), truncated='[Truncated]' in svg,
        path_line_points=[len(re.findall(r'[ML](-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', p))
                          for p in re.findall(r'\bd="([^"]+)"',svg)]) for i,svg in enumerate(svg_markup)], pairings


def save(path, value):
    with path.open('x',encoding='utf-8') as stream:
        stream.write(rules.redact_names(json.dumps(value,ensure_ascii=False,indent=2)))


def main():
    assert reminder_period('提醒！你目前在 练习回合1 的决策页面！ 回合4') == 'practice1'
    assert reminder_period('回合4 当前页面') is None
    assert full_html({'html':'<html>😀</html>','html_length':15}) == (True,15)
    assert not full_html({'html':'<html>[Truncated]','html_length':17})[0]
    sample_chart = {'id':'quality.control.chart','data':{'dataset':[{'seriesname':'曲线, 测试',
                   'data':[{'value':1+i/199} for i in range(200)]}]}}
    sample_path = 'M' + 'L'.join(f'{i},{200-(1+i/199)*100}' for i in range(200))
    sample_svg = f'<svg><text>需求乘数</text><rect x="0" y="0" width="600" height="200" fill="#eeeeee"/><text x="-1" text-anchor="end">0</text><text x="-1" text-anchor="end">2</text><path d="{sample_path}"/></svg>'
    assert pair_curve_y([sample_chart],[sample_svg])[0]['status'] == 'pass_y_values'
    sample_chart['data']['dataset'][0]['data'][0]['value'] = 10
    assert pair_curve_y([sample_chart],[sample_svg])[0]['status'] == 'fail_y_values'
    output = Path(__file__).parent / datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S.%f+0800')
    output.mkdir(parents=True,exist_ok=False)
    roots = [ROOT/'raw', HISTORY/'raw', HISTORY/'resume/20261013T_goal/current_2026-10-13T082849281Z/raw',
             CLOSE/'historical_supplement/raw']
    paths = sorted({p for root in roots if root.exists() for p in root.rglob('*.json')})
    sources, rows, chart_records, errors = [], [], [], []
    for path in paths:
        try:
            result = examine(path)
        except (ValueError, TypeError, KeyError) as error:
            errors.append(dict(source=path.relative_to(ROOT).as_posix(),error=str(error)))
            continue
        if result:
            source, table_rows, charts, ranges, svgs, pairings = result
            sources.append(source)
            rows.extend(table_rows)
            chart_records.append(dict(source=source['source'],sha256=source['sha256'],charts=charts,
                series_ranges=ranges,svg_structure=svgs,curve_y_pairings=pairings,pairing_status=source['chart_svg_status']))
    matrix = []
    for period in PERIODS:
        for panel in PANELS:
            matching = [s for s in sources if s['period']==period and s['panel']==panel]
            valid = [s for s in matching if s['valid_identity_and_html']]
            matrix.append(dict(market=5,period=period,panel=panel,
                status='identity_html_complete' if valid else 'missing_complete_evidence',
                valid_sources=[s['source'] for s in valid],candidate_sources=[s['source'] for s in matching],
                missing_reasons=[] if valid else sorted({reason for s in matching for reason,flag in
                    [('html_missing_truncated_or_no_length_declaration',s['html_complete']),
                     ('historical_reminder_missing_or_period_conflict',s['period_from_reminder_verified']),
                     ('personal_area_unverified',s['personal_area']=='PYT'),('market5_unverified',s['market5_verified']),
                     ('production_curves_incomplete',s.get('required_curve_charts_present',True))] if not flag}) or ['no_verified_period_source']))
    hashes_changed = [s['source'] for s in sources if rules.sha(ROOT/s['source']) != s['sha256']]
    groups = CLOSE/'decision_history/historical_5_rounds'
    group_acceptance = json.loads((groups/'acceptance.json').read_text(encoding='utf-8-sig')) if (groups/'acceptance.json').exists() else None
    acceptance = dict(generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        status='COMPLETE_CAPTURE_WITH_PAIRING_LIMITS' if all(x['status']=='identity_html_complete' for x in matrix) else 'PARTIAL',
        scanned_files=len(paths),relevant_sources=len(sources),complete_history_personal_pages=sum(x['status']=='identity_html_complete' for x in matrix),
        required_base_pages=45,group_decision_lists='already_archived_separately_five_periods',
        group_list_acceptance_source=str((groups/'acceptance.json').relative_to(ROOT)),
        chart_svg_numeric_pairing='curve y reconstructed where plot calibration matches; x labels remain rounded; other charts co-presence and range only',
        raw_hash_changes=hashes_changed,parse_errors=errors,selfcheck_passed=True,raw_modified=False)
    for name,data in [('sources',sources),('coverage',matrix),('personal_rows',rows),('chart_ranges_and_svg',chart_records),
                      ('acceptance',acceptance),('group_list_acceptance_reference',group_acceptance)]:
        save(output/f'{name}.json',data)
    with (output/'coverage.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['market','period','panel','status','missing_reasons','valid_sources','candidate_sources'])
        for m in matrix:
            writer.writerow([m['market'],m['period'],m['panel'],m['status'],'; '.join(m['missing_reasons']),'; '.join(m['valid_sources']),'; '.join(m['candidate_sources'])])
    with (output/'report.md').open('x',encoding='utf-8') as stream:
        stream.write('# 历史个人子栏与前景补采核验\n\n不要输出真名，姓名统一用首字母替代。仅离线读取，未修改原件、决策或项目入口。\n\n'+
            f'已扫描{len(paths)}份旧及新原件，相关{len(sources)}份。五历史回合×九子栏，共45项；完整历史身份与HTML证据{acceptance["complete_history_personal_pages"]}/45。完整矩阵见coverage.csv。文件名不能证明回合，采用正文历史提醒与selected_period相互校验，PYT区域、市场5、URL panel及声明UTF16长度共同验收。开放回合4页眉不代替历史提醒。\n\n'+
            '五回合历史小组决策列表已单独归档于decision_history/historical_5_rounds，未列为缺失。其它决策子栏值为个人；前景/曲线为对应回合情境，不能从个人页假定小组生效值。\n\n'+
            '图表保留JSON原数与NaN、系列点数/最小最大范围、SVG路径结构；JSON与SVG同源，不增独立样本。研发/效率曲线在可校准的零基准纵轴与单调路径上逐点重构y，结果见curve_y_pairings；x轴显示标签已舍入，不宣称x精确配对。其它图表co_present_not_numeric_verified只表示二者存在。生产计划必须具备研发与效率曲线及SVG才计采集完整；完整HTML验收不是所有图表数学配对通过。\n\n'+
            '旧无历史提醒、无HTML或无长度声明的资料仍保留为候选，不能按名称升级完整归档。未知字段不补零。本轮市场5正式3实际15栏和财务验收属于另一矩阵，其它市场135页本轮仍待采。\n')
    print(json.dumps(dict(output=str(output),**acceptance),ensure_ascii=False))


if __name__=='__main__':
    main()
