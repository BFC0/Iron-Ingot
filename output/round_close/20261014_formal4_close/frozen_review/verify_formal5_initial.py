"""Extract formal5 given conditions and conditional carryover without refitting."""
import hashlib
import importlib.util
import inspect
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs,urlparse

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'output/round_close/20261014_formal4_close'
RAW=BASE/'raw';OUT=BASE/'formal5_initial'
RULE=ROOT/'output/round_close/20261013_formal3_close/historical_supplement/audit/verify_historical_supplement.py'
spec=importlib.util.spec_from_file_location('historical_curves',RULE)
rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules)


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def num(v):
    try:
        x=float(re.sub(r'\s+','',str(v)));return x if math.isfinite(x) else None
    except ValueError:return None
def html(d):return ''.join(d['html_parts']) if d.get('html_parts') else d.get('html','')
def save(name,d):
    with (OUT/name).open('x',encoding='utf-8') as s:json.dump(d,s,ensure_ascii=False,indent=2,allow_nan=False)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    run_log=OUT/('work_log_'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f')+'.md')
    with run_log.open('x',encoding='utf-8') as s:s.write('# 正式5期初条件核验\n\n不要输出真名，姓名统一用首字母替代。\n\n开始：'+datetime.now(timezone(timedelta(hours=8))).isoformat()+'\n授权：回合4结束后按流程只读采集、结转核验；不重训，不填写或提交。\n')
    panels='decisionchecklist outlook demand productioninvestments productionplanning marketreportdomestic marketreportinternational1 marketreportbulk logistics corporate'.split()
    docs={};sources=[]
    for panel in panels:
        p=RAW/f'own_formal5_{panel}.json';d=read(p);h=html(d)
        assert len(h.encode('utf-16-le',errors='surrogatepass'))//2==d['html_length'] and '</html>' in h[-100:].lower()
        assert parse_qs(urlparse(d['url']).query).get('panel')==[panel]
        assert '市场 5' in d['text'] or '市场5' in d['text']
        if panel=='decisionchecklist':assert any(s.get('selected')=='回合5' for s in d['selects'])
        docs[panel]=d
        sources.append(dict(panel=panel,path=p.relative_to(ROOT).as_posix(),sha256=sha(p),url=d['url'],captured_at=d['captured_at'],html_complete=True,
                            identity_basis='历史选择器回合5，市场5页脚；所有页为本次同一正式5采集阶段，个人页保持草稿分类'))
    def ref(panel,ti,ri,ci,category='PUBLISHED_GIVEN_OR_REFERENCE_NOT_AUTOMATIC_OPENING'):
        d=docs[panel];p=RAW/f'own_formal5_{panel}.json';v=d['tables'][ti][ri][ci]
        return dict(display=v,value=num(v),source_path=p.relative_to(ROOT).as_posix(),sha256=sha(p),table=ti,row=ri,column=ci,indexing='zero_based',category=category)
    definitions={r['key']:r for r in read(ROOT/'output/formal4_all/20261014T211634211494+0800/decisions.json')}
    check=docs['decisionchecklist'];t=check['tables'][1];assert len(t)==80 and t[0][1]=='营销团队'
    drafts=[]
    for key,r in definitions.items():
        ri=r['source_row'];assert len(t[ri])==6 and re.sub(r'\s+','',t[ri][0])==re.sub(r'\s+','',r['label'])
        for ci in range(1,6):
            style=check['cell_styles'][1][ri][ci];cls=(style.get('class') or '').split()
            drafts.append(dict(key=key,market_id=5,phase='formal',round=5,section=r['section'],product_or_location=r['product_or_location'],label=r['label'],unit=r['unit'],
                estimate_attribute=ri>=55,column_identity='营销团队' if ci==1 else 'PYT' if ci==5 else f'MEMBER_COL_{ci}',
                modified_state='changed' if 'changed' in cls else 'notchanged' if 'notchanged' in cls else 'unknown',cell_style=style,
                **ref('decisionchecklist',1,ri,ci,'CURRENT_GROUP_DRAFT_NOT_FINAL' if ci==1 else 'CURRENT_PERSONAL_DRAFT_NOT_GROUP_FINAL')))
            if drafts[-1]['value'] is None:drafts[-1]['value']=t[ri][ci]
    assert len(drafts)==210 and len({(r['key'],r['column_identity']) for r in drafts})==210
    budgets=[dict(metric=t[ri][0],column_identity='营销团队' if ci==1 else 'PYT' if ci==5 else f'MEMBER_COL_{ci}',
                  **ref('decisionchecklist',1,ri,ci,'CURRENT_PLATFORM_BUDGET_NOT_ACTUAL_NOT_OPENING_STATE')) for ri in (5,6) for ci in range(1,6)]
    narrative=docs['outlook']['tables'][1]
    conditions=[dict(section=narrative[ri][0],text=narrative[ri+1][0],source=ref('outlook',1,ri+1,0,'PUBLISHED_FORMAL5_OUTLOOK')) for ri in range(1,len(narrative),2)]
    assert {r['section'] for r in conditions}=={'需求','大客户订单','生产','货币','财务'}
    params=[];headers=[]
    for ri,row in enumerate(docs['outlook']['tables'][2]):
        if len(row)==1:headers.append(row[0])
        if len(row)==4 and ri>1:
            params.append(dict(label=row[0],preceding_section_headers=headers.copy(),current=row[1],current_numeric=num(row[1]),change=row[2],previous=row[3],
                               **ref('outlook',2,ri,1,'PUBLISHED_FORMAL5_PARAMETER')))
    final4=read(BASE/'decision_history/20261014T233043761904+0800/group_final_42.json')
    upstream={}
    for section,label,ti,ri in [('研发, 千 美元','复合梁',4,2),('研发, 千 美元','连接件',4,3),('运营改进, 千 美元','泰国',5,2)]:
        previous=ref('productionplanning',ti,ri,2,'PREVIOUS_FORMAL4_GROUP_ACTUAL_INPUT')
        matching=[r for r in final4 if r['section']==section and r['label']==label]
        assert len(matching)==1 and previous['value']==matching[0]['value']
        upstream[label]=dict(previous_formal4_actual_input=previous,final_group_source=matching[0])
    charts,errors=rules.rules.charts(html(docs['productionplanning']));assert not errors
    selected=[c for c in charts if 'quality.control' in c['id'] or 'cost.efficiency' in c['id']]
    svgs=re.findall(r'<svg\b[\s\S]*?</svg>',html(docs['productionplanning']),re.I)
    # The new captured viewport has 467.6 px plots; keep all old ordinate checks.
    pairing_source=inspect.getsource(rules.pair_curve_y)
    assert pairing_source.count('> 500')==1
    namespace=dict(rules.__dict__)
    exec(pairing_source.replace('> 500','> 400'),namespace)
    pairings=namespace['pair_curve_y'](selected,svgs)
    for pairing in pairings:pairing['viewport_width_rule']='原核验最低图宽500调整为400，实际467.6；其余纵轴/单调点/数量/误差检查未变'
    assert len(pairings)==3 and all(p['status']=='pass_y_values' and p['points']==200 for p in pairings)
    curves=[]
    for c in selected:
        labels=[x['label'] for x in c['data']['categories'][0]['category']]
        for s in c['data'].get('dataset',[]):
            if not s.get('seriesname','').startswith('曲线'):continue
            label=s['seriesname'].split(', ')[1];ys=[x['value'] for x in s['data']]
            assert len(labels)==len(ys)==200 and all(num(v) is not None for v in ys)
            pairing=next(p for p in pairings if p['chart_id']==c['id'] and p['series']==s['seriesname'])
            curves.append(dict(valid_period='formal5',market_id=5,chart_id=c['id'],series=s['seriesname'],x_labels=labels,original_y_values=ys,
                x_axis='本回合有效投资，千美元',x_precision='原显示标签已舍入，不是精确自动支出映射',upstream_condition=upstream[label],pairing=pairing,
                points=200,independent_samples=200,svg_additional_samples=0,source_path=sources[4]['path'],source_sha256=sources[4]['sha256']))
    assert len(curves)==3 and sum(c['points'] for c in curves)==600
    save('formal5_curves.json',curves);save('curve_pairings.json',pairings)
    save('curves_original_chart_literals.json',selected)
    for i in sorted({p['svg_index'] for p in pairings}):
        with (OUT/f'curve_source_svg_{i}.svg').open('x',encoding='utf-8') as s:s.write(svgs[i])
    def actual(name,ri,ci=6):
        p=RAW/f'market5_formal4_{name}.json';d=read(p);r=d['tables'][0][ri]
        return dict(value=num(r[ci]),display=r[ci],label=r[0],source_path=p.relative_to(ROOT).as_posix(),sha256=sha(p),table=0,row=ri,column=ci,indexing='zero_based',category='FORMAL4_ACTUAL_ENDING_STATE')
    carry=[]
    def add(metric,unit,ending,opening=None,status='UNKNOWN_NO_IDENTICAL_OPENING_FIELD',note='未知不补零'):
        carry.append(dict(metric=metric,unit=unit,formal4_ending=ending,formal5_opening=opening,status=status,note=note))
    for product,ti,pri in [('复合梁',1,44),('连接件',2,45)]:
        ending=actual('marketdetails',pri);opening=ref('logistics',ti,9,1,'EXPLICIT_OPENING_INVENTORY')
        assert abs(ending['value']-opening['value'])<.011
        add(f'{product}期初库存数量','千单位',ending,opening,'MATCHED_EXPLICIT_OPENING_INVENTORY','期初库存栏，保持产品与生产国泰国；不能把库存数量当账面价值')
    add('长期贷款','千美元',actual('balancesheet',30),ref('corporate',1,5,2,'FORMAL4_LAST_YEAR_DEBT_REFERENCE'),'MATCHED_LAST_YEAR_DEBT_REFERENCE','去年长期贷款与正式4期末一致；今年长期贷款10200且本人贷款变化0，仅为当前输入条件下投影，不把草稿称最终方案')
    for product,ari,ri in [('复合梁',2,3),('连接件',3,4)]:
        ending=actual('productiondetails',ari);reported=ref('productioninvestments',3,ri,2,'CURRENT_ZERO_PERSONAL_INVESTMENT_CAPACITY_PROJECTION')
        investment=[x for x in docs['productioninvestments']['inputs'] if x.get('tag')=='SELECT' and ('r:10:' in x.get('name','') if product=='复合梁' else 'r:11:' in x.get('name',''))]
        assert len(investment)==1 and num(investment[0]['value'])==0
        expected=ending['value']*.85
        assert abs(expected-reported['value'])<=.005*.85+.005+1e-9
        add(f'{product}机器可用产能','千单位',ending,reported,'MATCHED_CONDITIONAL_15_PERCENT_CAPACITY_DECAY','正式5公布年产能下降15%，个人机器投资0；当前容量投影与上期容量衰减相容，不能重复加入正式4投资，也不能泛化投资生效时点')
    for metric,unit,ri in [('现金及现金等价物','千美元',17),('短期贷款','千美元',32),('机器账面价值','千美元',12),('厂房账面价值','千美元',11),('库存账面价值','千美元',15),('应收账款','千美元',16),('应付账款','千美元',34),('已收预付款','千美元',33),('留存收益','千美元',25)]:
        add(metric,unit,actual('balancesheet',ri),note='已知正式4期末余额；当前正式5个人预算期末值不是独立期初余额，未发现同口径期初披露')
    people=[actual('productiondetails',ri) for ri in (7,14)]
    add('生产人员','人',dict(value=sum(r['value'] for r in people),inputs=people),note='正式4两生产线人员合计117.94人；正式5生产计划人员随需求预估和产量计算，不能代替开期在职人员')
    for metric in ['税亏结转余额','研发持续存量','运营持续存量']:
        add(metric,'千美元' if metric=='税亏结转余额' else '未知',None,note='未披露真实存量；上期研发900/1300和运营750是已核投入条件，不能用投入或rho补造存量')
    for product,ari in [('复合梁',41),('连接件',42)]:
        ending=actual('marketdetails',ari)
        add(f'{product}下一期大客户承诺','千单位',ending,None,'UNKNOWN_NEXT_OPENING_COMMITMENT_NOT_CONFIRMED','正式4下一回合订单实际0已知；正式5没有新招标。当前个人物流订单投影0不是独立合同/收付款披露，订单状态仍分类保留')
    controls=[]
    for panel,d in docs.items():
        if panel=='decisionchecklist':continue
        for item in d.get('inputs',[]):
            controls.append(dict(panel=panel,control=item,category='CURRENT_PERSONAL_EDITABLE_OR_DISABLED_CONTROL_NOT_FINAL',source_path=next(s['path'] for s in sources if s['panel']==panel),source_sha256=next(s['sha256'] for s in sources if s['panel']==panel)))
    readback_path=RAW/'own_formal5_decisionchecklist_readback.json';readback=read(readback_path)
    assert any(s.get('selected')=='回合5' for s in readback['selects'])
    assert len(html(readback).encode('utf-16-le',errors='surrogatepass'))//2==readback['html_length']
    assert check['tables'][1]==readback['tables'][1] and check['cell_styles'][1]==readback['cell_styles'][1], 'Current draft changed during acquisition'
    sources.append(dict(panel='decisionchecklist_readback',path=readback_path.relative_to(ROOT).as_posix(),sha256=sha(readback_path),captured_at=readback['captured_at'],url=readback['url'],draft_and_styles_stable=True))
    schedule_path=RAW/'own_formal5_schedule.json';schedule=read(schedule_path)
    assert len(html(schedule).encode('utf-16-le',errors='surrogatepass'))//2==schedule['html_length']
    deadlines=[dict(cells=r,source_table=ti,source_row=ri,source_path=schedule_path.relative_to(ROOT).as_posix(),sha256=sha(schedule_path)) for ti,tb in enumerate(schedule['tables']) for ri,r in enumerate(tb) if r and r[0]=='回合5 - 截止日期']
    assert len(deadlines)==1 and deadlines[0]['cells'][1:]==['2026-10-15 22:00','2026-10-15 22:00']
    save('schedule.json',dict(formal5_deadline='2026-10-15 22:00',timezone='Asia/Shanghai',source=deadlines[0]))
    sources.append(dict(panel='schedule',path=schedule_path.relative_to(ROOT).as_posix(),sha256=sha(schedule_path),captured_at=schedule['captured_at'],url=schedule['url']))
    save('current_42_drafts_all_columns.json',drafts);save('current_group_42_draft.json',[r for r in drafts if r['column_identity']=='营销团队'])
    save('current_budget_summary.json',budgets);save('published_outlook_five_parts.json',conditions);save('published_parameters.json',params)
    save('current_personal_controls.json',controls);save('carryover_comparison.json',carry);save('source_manifest.json',sources)
    manifest=dict(valid_period='formal5',market_id=5,source_manifest='source_manifest.json',captured_at=[s['captured_at'] for s in sources],
        curve_file='formal5_curves.json',curves=3,curve_points=600,svg_additional_samples=0,upstream_formal4_actual_inputs={k:v['previous_formal4_actual_input']['value'] for k,v in upstream.items()},
        parameters=len(params),outlook_parts=5,draft_fields_per_column=42,group_final=False,training_performed=False,
        carryover_status_counts={status:sum(r['status']==status for r in carry) for status in {r['status'] for r in carry}},
        sources=[dict(path=s['path'],sha256=s['sha256']) for s in sources],code_path=Path(__file__).relative_to(ROOT).as_posix(),code_sha256=sha(Path(__file__)),
        reused_rules_path=RULE.relative_to(ROOT).as_posix(),reused_rules_sha256=sha(RULE))
    save('version_manifest.json',manifest)
    with run_log.open('a',encoding='utf-8') as s:s.write('\n完成：12份原件、42项5列草稿及回读稳定、五部分前景及'+str(len(params))+'参数、3曲线600点与SVG同源配对、上期实际投入900/1300/750核对、'+str(len(carry))+'项结转分项及正式5日程；未重训。旧图宽规则适配窄视口，其余条件未变。\n')
    print(json.dumps(dict(output=OUT.relative_to(ROOT).as_posix(),**{k:manifest[k] for k in ['parameters','curve_points','upstream_formal4_actual_inputs','carryover_status_counts']}),ensure_ascii=False))


if __name__=='__main__':main()
