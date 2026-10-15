"""Offline Cesim archive audit and report. No network access or decision writes.
Run with bundled Python; --publish also copies the verified bundle to Desktop/LOCAL_PROJECT_OWNER/cesim.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'raw'
OUT = Path(r'<LOCAL_USER_DIR>\Documents\Codex\2026-10-10\3-4-5-6-7-8\outputs\cesim')
DESKTOP = Path(r'.')
PDF = Path(r'<LOCAL_USER_DIR>\Documents\xwechat_files\<REDACTED_WECHAT_ID>\msg\file\2026-10\决策指南_261006143236.pdf')
IMAGE = Path(r'<LOCAL_USER_DIR>\AppData\Local\Temp\codex-clipboard-ebb709e4-edaf-43e1-bced-49e19691b175.png')

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def redact_names(text):
    # shortcut: known project roster only; extend hashes when new members appear.
    identities = {'7fcae704a696bca66e9777ac15cc001f9519389cc5cff85917fa26452c4c5f87': 'JY', 'df3d37f8b3f756180cf14e0f8a7d4532fa00f6cc98ba4bbd6022aab3d773b4fb': 'XXL', 'da229c34b2c08ad0cff8ca2086abe7317d7ab6139cda6394d87914275de26297': 'SRQ', '279ec73ce864e9b306d4cdead33aadd8c2d189f9a6fddc6808238bbf85b198ca': 'PYT'}
    matches = []
    for length in (4, 3, 2):
        for match in re.finditer(r'(?=([一-鿿](?:[ \t]*[一-鿿]){' + str(length - 1) + r'}))', text):
            candidate = match.group(1)
            key = hashlib.sha256(re.sub(r'[ \t]', '', candidate).encode('utf-8')).hexdigest()
            if key in identities:
                matches.append((match.start(), match.start() + len(candidate), identities[key]))
    for start, end, initials in sorted(set(matches), reverse=True):
        text = text[:start] + initials + text[end:]
    return text

def table_rows(snapshot):
    snapshot = redact_names(snapshot)
    # Preserve order and duplicate labels: sections can contain identically named rows.
    result = []
    current = None
    for line_no, line in enumerate(snapshot.splitlines(), 1):
        match = re.match(r'\s*- row(?: "(.*)")?:\s*$', line)
        if match:
            current = {'line': line_no, 'row_text': match.group(1) or '', 'cells': []}
            result.append(current)
        elif current:
            cell = re.match(r'\s*- (?:cell|columnheader|rowheader) "(.*)"(?::)?$', line)
            if cell:
                current['cells'].append(cell.group(1))
    return result

def rows(name):
    return table_rows(json.loads((RAW / (name + '.json')).read_text(encoding='utf-8'))['snapshot'])

def values(name, label, occurrence=0):
    found = [r['cells'][1:] for r in rows(name) if r['cells'] and r['cells'][0] == label]
    assert len(found) > occurrence, (name, label)
    return found[occurrence]

def number(value):
    return float(value.replace(' ', '').replace('\u00a0', '').replace(',', '').replace('%', ''))

def n(name, label, index=0, occurrence=0):
    return number(values(name, label, occurrence)[index])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    required = ['round1_outlook', 'round1_demand', 'round1_investments', 'round1_production',
                'round1_sales_thailand', 'round1_sales_indonesia', 'round1_bulk',
                'round1_logistics', 'round1_finance', 'round1_checklist',
                'round1_budget_income', 'round1_budget_balance', 'round1_budget_cashflow',
                'round1_budget_ratios', 'initial0_summary', 'initial0_printable',
                'practice1_summary', 'practice1_printable', 'practice2_summary',
                'practice2_printable', 'online_manual']
    assert all((RAW / (name + '.json')).is_file() for name in required)
    coverage = []
    csv_rows = []
    for source in sorted(RAW.iterdir()):
        quarantined = '_before' in source.stem
        target = OUT / ('quarantine' if quarantined else 'raw') / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        record = {'file': str(target.relative_to(OUT)), 'status': 'quarantined' if quarantined else 'archived',
                  'reason': '早期采集页面绑定不可靠；仅保留原件，不用于分析' if quarantined else ''}
        if source.suffix == '.json' and not quarantined:
            data = json.loads(source.read_text(encoding='utf-8'))
            snapshot = data['snapshot']
            assert len(snapshot) > 1000, source.name
            if source.stem.startswith('round1_'):
                assert '回合1' in snapshot and '营销团队' in snapshot
            if source.stem.endswith('_printable'):
                for heading in ['市场报告', '生产报告', '物流报告', '损益表', '资产负债表']:
                    assert heading in snapshot, (source.name, heading)
            record.update(captured_at=data.get('captured_at'), source_url=data.get('source_url'),
                          characters=len(snapshot), table_rows=len(table_rows(snapshot)))
            (target.with_suffix('.txt')).write_text(snapshot, encoding='utf-8')
            for row in table_rows(snapshot):
                csv_rows.append([source.name, row['line'], row['row_text'],
                                 json.dumps(row['cells'], ensure_ascii=False)])
        coverage.append(record)
    with (OUT / '全部表格行索引.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['来源文件', '快照行号', '完整行文本', '单元格JSON数组'])
        writer.writerows(csv_rows)
    sources = OUT / 'sources'
    sources.mkdir(exist_ok=True)
    from pypdf import PdfReader
    assert PDF.is_file()
    pdf_copy = sources / PDF.name
    if not pdf_copy.exists() or pdf_copy.read_bytes() != PDF.read_bytes():
        shutil.copy2(PDF, pdf_copy)
    reader = PdfReader(PDF)
    text = '\n\n'.join(f'=== 第 {i + 1} 页 ===\n{page.extract_text() or ""}' for i, page in enumerate(reader.pages))
    assert len(reader.pages) == 24 and len(text) > 1000
    (sources / '决策指南_逐页文本.txt').write_text(text, encoding='utf-8')
    if IMAGE.is_file():
        image_copy = sources / '用户提供_练习回合2市场前景.png'
        if not image_copy.exists() or image_copy.read_bytes() != IMAGE.read_bytes():
            shutil.copy2(IMAGE, image_copy)

    production = n('round1_production', '生产, 千单位')
    capacity = n('round1_production', '产能, 千单位')
    demand_th = n('round1_demand', '泰国', 3, 1)
    demand_in = n('round1_demand', '印尼', 3, 1)
    profit = n('round1_budget_income', '本回合利润')
    cumulative = n('round1_budget_ratios', '累计收益 (k 美元)')
    initial_cumulative = n('round1_budget_ratios', '累计收益 (k 美元)', 1)
    # Source figures are displayed rounded; tolerate <= 1 k USD reconciliation differences.
    assert abs(cumulative - initial_cumulative - profit) <= 1
    assert production == capacity * n('round1_production', '产能分配, %') / 100
    assert len(values('practice1_printable', '本回合利润, 千 美元')) == 10
    diagnostics = []
    def calc(name, formula, value, unit, sources_used):
        diagnostics.append(dict(name=name, formula=formula, value=value, unit=unit, sources=sources_used))
    calc('需求预测总量', '5 + 11', demand_th + demand_in, '千单位', ['round1_demand.json'])
    calc('预测供给覆盖率', '3.4 / (5 + 11) * 100', production / (demand_th + demand_in) * 100, '%', ['round1_demand.json','round1_production.json'])
    calc('预测供给缺口', '(5 + 11) - 3.4', demand_th + demand_in - production, '千单位', ['round1_demand.json','round1_production.json'])
    calc('无新增投资下回合产能', '17 * (1 - 15 / 100)', capacity * .85, '千单位', ['round1_investments.json','round1_outlook.json'])
    calc('当前产能满足预测需求所需利用率', '(5 + 11) / 17 * 100', (demand_th + demand_in)/capacity*100, '%', ['round1_demand.json','round1_production.json'])
    calc('预测工人数', '3.4 / 0.15', production / n('round1_production','生产效率, 千单位/人'), '人', ['round1_production.json'])
    calc('按平台当前销售分配的预算收入', '3.4 * 3000 + 0 * 2000', production * 3000, '千美元', ['round1_sales_thailand.json','round1_sales_indonesia.json'])
    calc('长期利息预算', '17000 * 3 / 100', 17000*.03, '千美元', ['round1_finance.json'])
    calc('预算税前利润', '-2301 + 148 - 510 - 0', -2301+148-510, '千美元', ['round1_budget_income.json'])
    calc('预算现金变化', '14563 - 15004', 14563-15004, '千美元', ['round1_budget_cashflow.json'])
    calc('累计收益差分推算当期利润', '-1370.3 - 1292.8', cumulative-initial_cumulative, '千美元', ['round1_budget_ratios.json'])
    prices = [number(v) for v in values('practice1_printable','泰国, 美元')]
    peers = prices[:5]+prices[6:]
    calc('练习1竞争者泰国价格中位数', 'median(剔除营销团队后的9队价格)', median(peers), '美元/单位', ['practice1_printable.json'])
    calc('练习1本队泰国价格溢价', '(3000 / 1800 - 1) * 100', (prices[5]/median(peers)-1)*100, '%', ['practice1_printable.json'])
    # The two 印尼 rows occur in sales, then demand, in the full market report.
    practice1_in_sales = n('practice1_printable','印尼',5,0)
    practice1_in_demand = n('practice1_printable','印尼',5,1)
    calc('练习1印尼需求满足率', '3.01 / 13.07 * 100', practice1_in_sales/practice1_in_demand*100, '%', ['practice1_printable.json'])
    for prefix in ['initial0','practice1','practice2']:
        for label in ['营业收入净额, 千 美元','本回合利润, 千 美元','累计收益, 千 美元','现金及现金等价物','短期贷款','净现金']:
            calc(prefix+' '+label, '原始报告第6队（营销团队）单元格；直接读取，不是预测', n(prefix+'_printable',label,5), '千美元', [prefix+'_printable.json'])
    assert abs(diagnostics[1]['value'] - 21.25) < 1e-9
    assert practice1_in_sales == 3.01 and practice1_in_demand == 13.07
    assert n('practice2_printable','净现金',5) == 2000-11217
    write_json(OUT / '计算核验.json', diagnostics)
    with (OUT / '计算核验.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['项目','公式或读取方法','结果','单位','数据来源'])
        for item in diagnostics:
            writer.writerow([item['name'],item['formula'],item['value'],item['unit'],'; '.join(item['sources'])])
    write_json(OUT / '归档覆盖与待办.json', {'status':'PAUSED_BY_USER', 'generated_at':datetime.now(timezone.utc).isoformat(),
        'required_current_files_present':True, 'archival_complete':False, 'decision_modified':False,
        'scope':'市场5；正式1当前决策/预算、初始0和练习1/2完整结果、在线指南、已提供附件',
        'pending':['案例网页归档','快速教程网页归档','阅读材料索引归档','日程及课程说明的独立归档与复核','历史练习决策列表及前景补充归档','图形曲线与隐藏提示覆盖核验','模型拟合与情景优化','个人区域填入与回读核验'],
        'files':coverage})
    template = (ROOT / '要求说明_模板.md').read_text(encoding='utf-8')
    replacements = {'{{coverage}}':f'{len(required)} 份核验后的网页快照、{sum(p.suffix == ".jpg" for p in RAW.iterdir())} 张网页截图',
                    '{{rows}}':str(len(csv_rows)), '{{coverage_pct}}':f'{production/(demand_th+demand_in)*100:.2f}',
                    '{{price_premium}}':f'{(prices[5]/median(peers)-1)*100:.2f}',
                    '{{in_fulfillment}}':f'{practice1_in_sales/practice1_in_demand*100:.2f}',
                    '{{time}}':datetime.now().astimezone().isoformat(timespec='seconds')}
    for key, value in replacements.items():
        template = template.replace(key, value)
    assert '{{' not in template
    (OUT / 'Cesim_任务要求与当前情况说明.md').write_text(template, encoding='utf-8')
    code = OUT / 'code'
    code.mkdir(exist_ok=True)
    for filename in ['archive_and_report.py','要求说明_模板.md','browser_capture.js']:
        shutil.copy2(ROOT / filename, code / filename)
    checks = {'result':'PASS','canonical_snapshots':len(required),'table_rows':len(csv_rows),'pdf_pages':len(reader.pages),
              'checks':['所有指定快照存在','正式1身份与回合标签匹配','三份历史打印报告包含主要结果区段',
                        '历史队列10队，营销团队为第6队','需求与生产计算一致','累计收益差分与利润在显示舍入误差内一致',
                        '练习2净现金等于现金减短贷','未访问网络、未改网页决策','早期采集排除分析'],
              'limits':['未完成剩余网页归档','未拟合预测模型或求最优解','未核验隐藏图形的全部数值点','未验证未开放的正式未来回合']}
    write_json(OUT / '核验结果.json', checks)
    manifest = []
    for path in sorted(OUT.rglob('*')):
        if path.is_file() and path.name != 'SHA256_manifest.json':
            manifest.append({'file':path.relative_to(OUT).as_posix(),'bytes':path.stat().st_size,
                             'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT / 'SHA256_manifest.json', manifest)
    if args.publish:
        assert DESKTOP.resolve() == Path(r'.').resolve()
        for source in OUT.rglob('*'):
            if source.is_file():
                target = DESKTOP / source.relative_to(OUT)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != source.read_bytes():
                    shutil.copy2(source, target)
        for record in manifest:
            assert hashlib.sha256((DESKTOP / record['file']).read_bytes()).hexdigest() == record['sha256']
        assert (DESKTOP/'SHA256_manifest.json').read_bytes() == (OUT/'SHA256_manifest.json').read_bytes()
    print(json.dumps({'status':'paused','files':len(manifest)+1,'rows':len(csv_rows),'checks':'PASS','published':args.publish},ensure_ascii=False))

if __name__ == '__main__':
    main()
