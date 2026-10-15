"""Archive the six user screenshots with field-level provenance; offline only."""
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from archive_and_report import table_rows, write_json
from audit_incremental import cells

ROOT = Path(__file__).resolve().parent.parent
PREFIX = '20261011_user_practice2_'
NOW = datetime.now(timezone.utc).isoformat()
IMAGES = [
    ('bulk', '4bd4578e-ea61-471f-b2b4-55649589a6b1'),
    ('demand', '11c85cad-1a6d-4556-843b-da85d5155089'),
    ('investments', 'e23b7d68-5d58-4b75-8b4c-9a95554199c1'),
    ('production', '892da374-2eb4-4404-a769-07e8f16df75f'),
    ('sales_thailand', '4ae163c3-24a3-4361-89ff-ee858a6dbfdb'),
    ('sales_indonesia', '7db39d4f-1e0d-4be8-9b7c-b4644dc6ef75'),
]
# K = known state/history, D = decision input, F = player forecast, B = platform budget.
DATA = {
 'bulk': [('可投标订单','千单位','2.0','0.0','K'), ('已获得大客户订单','千单位',None,'0.0','K'),
          ('每单位价格','美元','0.0','0.0','D'), ('设计师营销','千美元','0.0','0.0','D'),
          ('销售额','千美元','0','0','B')],
 'demand': [('泰国总市场需求','千单位',None,'46.38','K'), ('印尼总市场需求','千单位',None,'126.21','K'),
            ('泰国预计市场增长','%','10.00',None,'F'), ('印尼预计市场增长','%','5.00',None,'F'),
            ('泰国总需求预测','千单位','51.02',None,'B'), ('印尼总需求预测','千单位','132.52',None,'B'),
            ('泰国市场份额','%','39.20','1.02','B'), ('印尼市场份额','%','49.05','3.38','B'),
            ('泰国公司需求','千单位','20.00','0.39','F'), ('印尼公司需求','千单位','65.00','13.07','F')],
 'investments': [('复合梁需求预测','千单位','85.00',None,'B'), ('需求预测变化','%','50.00',None,'F'),
                 ('下回合需求预测','千单位','127.50',None,'B'), ('机器产能','千单位','26.45',None,'K'),
                 ('下回合机器产能','千单位','22.48',None,'B'), ('生产能力','千单位','26.45',None,'K'),
                 ('下回合生产能力','千单位','22.48',None,'B'), ('生产机器投资','千单位','12',None,'D'),
                 ('机器投资成本','千美元','1200',None,'B'), ('总投资成本','千美元','1200',None,'B')],
 'production': [('产能分配','%','20.0',None,'D'), ('每单位可变生产成本','美元','1219.2',None,'B'),
                ('生产','千单位','5.29',None,'B'), ('生产效率','千单位/人','0.17',None,'F'),
                ('产能','千单位','26.45',None,'K'), ('产能利用','%','20.0',None,'B'),
                ('生产策略','文本','需求驱动',None,'K'), ('换班班数','班','0.6',None,'B'),
                ('生产线人工数量','人','31.1',None,'B'), ('生产工资合计','千美元','871',None,'B'),
                ('研发','千美元','600','600','D'), ('运营改进','千美元','700','700','D')],
}
SALES_LABELS = ['预计销售额','每单位价格','总收入','原材料','生产工资','运输','毛利','一般营销','设计师营销','EBITDA']
SALES_UNITS = ['千单位','美元'] + ['千美元'] * 8
SALES = {
 'sales_thailand': [
    ['5.29','4000.0','21160','5578','871','159','14552','10','0','14542'],
    ['0.39','3000.0','1160','348','64','12','736','50','0','686'],
    ['-','-','100','26','4','1','69','0','0','69'],
    ['+1268','+33','+1724','+1501','+1267','+1268','+1877','-80','NA','+2020']],
 'sales_indonesia': [
    ['0.00','2000.0','0','0','0','0','0','200','150','-350'],
    ['3.01','2000.0','6027','2716','497','362','2453','200','150','2103'],
    ['-','-','0','0','0','0','0','0','0','0'],
    ['-100','+0','-100','-100','-100','-100','-100','+0','+0','-117']],
}
for page, (current, past, shares, changes) in SALES.items():
    DATA[page] = [(label, unit, a, b, 'D' if label in ['每单位价格','一般营销','设计师营销'] else 'B')
                  for label, unit, a, b in zip(SALES_LABELS, SALES_UNITS, current, past)]
    DATA[page] += [(label+'收入占比','%',v,None,'B') for label,v in zip(SALES_LABELS,shares)]
    DATA[page] += [(label+'变化','%',v,None,'B') for label,v in zip(SALES_LABELS,changes)]
    DATA[page] += [('需求','千单位','20.00' if page == 'sales_thailand' else '65.00',None,'F'),
                   ('全球可用产品','千单位','5.29',None,'B'), ('全球未满足需求','千单位','79.71',None,'B'),
                   ('全球期末库存','千单位','0.00',None,'B')]

def main():
    index = json.loads((ROOT/'数据分组索引.json').read_text(encoding='utf-8'))
    index = [x for x in index if not Path(x['file']).name.startswith(PREFIX)]
    field_rows, indexed_rows, plain_rows, added = [], [], [], []
    for page, image_id in IMAGES:
        original = Path('<LOCAL_USER_DIR>/AppData/Local/Temp') / f'codex-clipboard-{image_id}.png'
        target = ROOT/'sources'/f'用户提供_练习回合2_{page}.png'
        if original.exists():
            shutil.copy2(original, target)
        assert target.is_file(), target
        fields = []
        for label, unit, current, past, kind in DATA[page]:
            if current is not None:
                fields.append(dict(field=label, period='今年/下回合（字段名标识）', value=current, unit=unit, data_kind=kind))
            if past is not None:
                fields.append(dict(field=label, period='去年（练习1）', value=past, unit=unit, data_kind='K',
                                   known_subtype='historical_decision' if kind == 'D' else 'historical_result'))
        snapshot = '\n'.join('- row:\n'+ '\n'.join('  - cell '+json.dumps(str(f[k]),ensure_ascii=False)
                              for k in ['field','period','value','unit','data_kind']) for f in fields)
        source = target.relative_to(ROOT).as_posix()
        data = dict(phase='practice', round=2, market=None, data_kind='decision_and_budget_mixed', captured_at=None,
                    archived_at=NOW, source_url=None, source_image=source,
                    representation='manual screenshot transcription; snapshot uses table-row syntax for indexing, not DOM',
                    identity_basis='练习2由用户说明；截图无课程、市场、团队、个人区域及时间标签，未独立核验',
                    usable_for_demand_fit=False, fields=fields, snapshot=snapshot,
                    chart_policy='表格为精确读数；图形仅保留原图，不从坐标猜测精确需求乘数或曲线。',
                    classification={'K':'已知期初状态、历史结果/历史决策或固定策略', 'D':'当前决策输入，未确认实际提交',
                                    'F':'玩家手填预测，非已知事实', 'B':'平台派生预测/预算，非实际结果'},
                    notes=['今年已获得大客户订单单元格空白，不转录成0。'] if page=='bulk' else [])
        path = ROOT/'raw'/f'{PREFIX}{page}.json'
        write_json(path, data)
        path.with_suffix('.txt').write_text(snapshot,encoding='utf-8')
        item = dict(file=path.relative_to(ROOT).as_posix(),phase='practice',round=2,data_kind=data['data_kind'],
                    captured_at=None,archived_at=NOW,source_url=None,source_image=source,market=None,
                    usable_for_demand_fit=False, usage='用户截图逐字段分类；今年预测/预算禁止作实际需求标签；身份仅用户说明',
                    representation=data['representation'],sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        index.append(item)
        added.append(item)
        for row in table_rows(snapshot):
            indexed_rows.append([item['file'],'practice',2,item['data_kind'],'',row['line'],row['row_text'],json.dumps(row['cells'],ensure_ascii=False)])
            plain_rows.append([path.name,row['line'],row['row_text'],json.dumps(row['cells'],ensure_ascii=False)])
        field_rows.extend([[item['file'],source,f['field'],f['period'],f['value'],f['unit'],f['data_kind']] for f in fields])
    write_json(ROOT/'数据分组索引.json',index)
    for filename, extra in [('分组表格行索引.csv',indexed_rows),('全部表格行索引.csv',plain_rows)]:
        with (ROOT/filename).open(encoding='utf-8-sig',newline='') as stream:
            old = list(csv.reader(stream))
        old = [r for r in old if not Path(r[0]).name.startswith(PREFIX)]
        with (ROOT/filename).open('w',encoding='utf-8-sig',newline='') as stream:
            csv.writer(stream).writerows(old+extra)
    with (ROOT/'练习2截图_字段分类.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        csv.writer(stream).writerows([['来源JSON','原图','字段','时期','显示值','单位','类型K已知_D决策_F玩家预测_B平台预算']]+field_rows)
    coverage = json.loads((ROOT/'归档覆盖与待办.json').read_text(encoding='utf-8'))
    coverage['files'] = [x for x in coverage['files'] if not Path(x['file']).name.startswith(PREFIX)]+added
    coverage['user_practice2_screenshots'] = dict(archived_at=NOW,count=6,field_count=len(field_rows),
                                                classified_csv='练习2截图_字段分类.csv',comparison='练习与正式_已知数据差异.md')
    write_json(ROOT/'归档覆盖与待办.json',coverage)

    practice, formal = cells('20261011_practice2_outlook'),cells('20261011_round1_outlook')
    assert len(practice) == len(formal)
    parameter_diffs = [(a[0],a[1:],b[1:]) for a,b in zip(practice,formal) if len(a)==4 and a!=b]
    assert {x[0] for x in parameter_diffs} == {'基准利率','高于基准的短期利率溢价','复合梁','泰国'}
    assert cells('20261011_practice1_outlook') == formal
    assert abs(26.45*.2-5.29)<1e-9 and abs(85*1.5-127.5)<1e-9
    assert round(46.38*1.1,2)==51.02 and round(126.21*1.05,2)==132.52
    assert abs(85-5.29-79.71)<1e-9 and round(26.45*.85,2)==22.48
    assert len(added)==6 and all(not x['usable_for_demand_fit'] for x in added)
    assert len({x['file'] for x in index}) == len(index)
    history_th = [r for r in cells('practice1_printable') if r[0]=='泰国' and len(r)==11]
    history_in = [r for r in cells('practice1_printable') if r[0]=='印尼' and len(r)==11]
    assert history_th[0][6] == history_th[1][6] == '0.39'
    assert history_in[0][6]=='3.01' and history_in[1][6]=='13.07'
    checks = dict(result='PASS',archived_at=NOW,images=6,classified_fields=len(field_rows),
                  practice1_formal1_visible_outlook_equal=True,practice2_formal1_parameter_differences=parameter_diffs,
                  checks=['原图复制及SHA256','逐字段分类','需求/生产/缺口/下回合需求显示值核算','索引无重复','缺失值未补零','两国去年需求与销量与练习1本队结果一致'],
                  limits=['截图身份/时间仅用户说明','未独立核验截图全部历史值','图形不猜测精确坐标','没有正式2资料','不证明隐藏需求函数相同'],
                  browser_accessed=False,decision_modified=False)
    write_json(ROOT/'练习2截图归档核验.json',checks)
    manifest = []
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and path.name!='SHA256_manifest.json' and '__pycache__' not in path.parts and '.git' not in path.parts:
            manifest.append(dict(file=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,
                                 sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    write_json(ROOT/'SHA256_manifest.json',manifest)
    for _,image_id in IMAGES:
        original = Path('<LOCAL_USER_DIR>/AppData/Local/Temp')/f'codex-clipboard-{image_id}.png'
        if original.exists():
            page = next(p for p,i in IMAGES if i==image_id)
            assert hashlib.sha256(original.read_bytes()).digest()==hashlib.sha256((ROOT/'sources'/f'用户提供_练习回合2_{page}.png').read_bytes()).digest()
    print(json.dumps(checks,ensure_ascii=False))

if __name__ == '__main__':
    main()
