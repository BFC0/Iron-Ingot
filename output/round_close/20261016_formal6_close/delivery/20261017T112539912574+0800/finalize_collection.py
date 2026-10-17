"""Publish formal-6 data and provenance; no training or platform writes."""
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import audit_collection as a

BASE, ROOT, rules = a.BASE, a.ROOT, a.rules


def same(x, y):
    nx, ny = rules.num(str(x)), rules.num(str(y))
    return abs(nx[0]-ny[0]) <= nx[1]+ny[1]+1e-9 if nx and ny else str(x).strip()==str(y).strip()


def main():
    now=datetime.now(timezone(timedelta(hours=8)))
    out=BASE/'delivery'/now.strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True,exist_ok=False)
    audit=next(p for p in sorted((BASE/'validation').iterdir(),reverse=True)
               if (p/'summary.json').exists() and a.read(p/'summary.json').get('chart_pairing')=={'pass':300})
    checks=a.read(audit/'summary.json')
    assert checks['coverage']=={'complete':140}

    def save(name,obj):
        text=obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)
        with (out/name).open('x',encoding='utf-8') as f:f.write(rules.redact_names(text))

    def ref(path,ti=None,ri=None,ci=None):return a.reference(path,ti,ri,ci)

    # Reuse the complete fifteen-panel market-5 comparison for every unchanged result layout.
    template=[]; rows_all=[]; coverage=[]; alias_checks=[]
    m5_print=a.read(a.source(5,'print'))['tables'][0]
    for panel in rules.PANELS:
        path=a.source(5,panel);doc=a.read(path)
        assert a.prior.formal.full_html(a.html(doc),doc.get('html_length'))
        records,reviews,_=a.prior.formal.rows_for(doc,dict(ref(path),market=5,panel=panel))
        assert not reviews, (panel,reviews)
        last_print=-1
        for row in records:
            if not row['numeric_by_team'] or not any(x['value'] is not None for x in row['numeric_by_team']):continue
            item=dict(requirement_id=f"{panel}:{row['table_index']}:{row['row_index']}",panel=panel,
                      table=row['table_index'],row=row['row_index'],label=row['label'],
                      section_path=row['section_path'],unit_context=row['unit_context'])
            if panel in ('ratios','logisticsdetails'):
                candidates=[ri for ri,r in enumerate(m5_print) if len(r)==11
                            and rules.label_key(r[0])==rules.label_key(row['label'])
                            and all(same(x,y) for x,y in zip(r[1:],row['cells'][1:]))
                            and (panel!='logisticsdetails' or ri>last_print)]
                assert candidates, item
                if panel=='ratios':assert len(candidates)==1,item
                item['print_row']=candidates[0];last_print=candidates[0]
                alias_checks.append(dict(item,web_source=ref(path,row['table_index'],row['row_index']),
                                         print_source=ref(a.source(5,'print'),0,last_print)))
            template.append(item)
    for m in range(1,11):
        header=a.read(a.source(m,'print'))['tables'][0][1][1:]
        for panel in a.PANELS:
            path=a.source(m,panel);doc=a.read(path)
            records,reviews,_=a.prior.formal.rows_for(doc,dict(ref(path),market=m,panel=panel))
            assert not reviews,(m,panel,reviews)
            for row in records:
                if row['numeric_by_team'] and any(x['value'] is not None for x in row['numeric_by_team']):
                    row.update(round=6)
                    assert row['team_order']==header
                    rows_all.append(row)
        for item in template:
            path=a.source(m,item['panel'])
            if path:
                ti,ri=item['table'],item['row'];r=a.read(path)['tables'][ti][ri];status='web_direct'
            else:
                assert item['panel'] in ('ratios','logisticsdetails')
                path=a.source(m,'print');ti,ri=0,item['print_row'];r=a.read(path)['tables'][ti][ri];status='print_direct_reused'
            assert len(r)==11 and rules.label_key(r[0])==rules.label_key(item['label']), (m,item,r)
            coverage.append(dict(item,market=m,phase='formal',round=6,status=status,source=ref(path,ti,ri),
                                 cells=r,teams=header))
    assert len(coverage)==10*len(template) and len({(r['market'],r['requirement_id']) for r in coverage})==len(coverage)
    save('field_requirements.json',template);save('field_coverage.json',coverage)
    save('normalized_web_rows.json',rows_all);save('print_alias_checks.json',alias_checks)

    # The historical list has one fewer decorative row than the earlier captured HTML parser.
    dp=BASE/'own_formal6_decisionchecklist.json';d=a.read(dp);table=d['tables'][1]
    assert a.selected(d)==['回合6'] and a.prior.formal.full_html(a.html(d)) and table[0][1]=='营销团队'
    styles=a.read(BASE/'own_formal6_cell_styles.json')
    definitions_path=ROOT/'output/t6v1n2/20261016_ph30_310/current_fields.json'
    definitions=a.read(definitions_path)
    plan_path=ROOT/'output/t6v1n2/20261016_ph30_310/field_coverage.json'
    plans={r['key']:r for r in a.read(plan_path)}
    assert len(definitions)==len(plans)==56
    final=[];all_columns=[]
    for definition in definitions:
        ri=definition['source']['row']-1
        assert table[ri][0]==definition['label'],(ri,definition['label'],table[ri])
        for col,identity in enumerate(['GROUP_FINAL','JY','XXL','SRQ','PYT'],1):
            shown=table[ri][col];n=rules.num(shown)
            item=dict(key=definition['key'],section=definition['section'],product=definition['product'],label=definition['label'],
                      value=n[0] if n else shown,display=shown,unit=plans[definition['key']]['unit'],round=6,market=5,
                      identity=identity,column=col,player_estimate=ri>=65,style=styles[1][ri][col],
                      category=('FINAL_GROUP_PLAYER_ESTIMATE' if ri>=65 else 'FINAL_GROUP_DECISION') if col==1 else 'HISTORICAL_PERSONAL_NOT_GROUP_FINAL',
                      source=ref(dp,1,ri,col))
            all_columns.append(item)
            if col==1:final.append(item)
    assert len(final)==56 and len(all_columns)==280 and len({r['key'] for r in final})==56
    assert sum(len(r)==6 and bool(r[0]) for r in table[6:])==56
    save('group_final_56.json',final);save('historical_personal_columns.json',[r for r in all_columns if r['column']!=1])
    budgets=[dict(identity=identity,column=col,label=table[ri][0],display=table[ri][col],
                  value=rules.num(table[ri][col])[0],category='HISTORICAL_BUDGET_NOT_ACTUAL',source=ref(dp,1,ri,col))
             for ri in (4,5) for col,identity in enumerate(['GROUP_FINAL','JY','XXL','SRQ','PYT'],1)]
    save('historical_budget_summary.json',budgets)

    mp=a.source(5,'marketdetails');mt=a.read(mp)['tables'][0];cross=[]
    for dr,mr in [(8,3),(9,4),(10,5),(13,7),(14,8),(15,9)]:
        assert same(table[dr][1],mt[mr][6])
        cross.append(dict(kind='retail_price',decision=ref(dp,1,dr,1),actual=ref(mp,0,mr,6),passed=True))
    ip=a.source(5,'incomestatement');it=a.read(ip)['tables'][0]
    for inputs,label in [([19,20,21,23,24,25],'一般营销'),([28,29,30,31,33,34,35,36],'设计师营销'),([61,62],'研发'),([59],'运营改进')]:
        ri=next(i for i,r in enumerate(it) if len(r)==11 and r[0]==label)
        val=sum(rules.num(table[i][1])[0] for i in inputs)
        assert abs(val-rules.num(it[ri][6])[0])<=rules.num(it[ri][6])[1]+1e-9
        cross.append(dict(kind=label,inputs=[ref(dp,1,i,1) for i in inputs],actual=ref(ip,0,ri,6),passed=True))
    save('decision_actual_crosschecks.json',cross)
    errors=[]
    for dr,ar in [(68,24),(69,25),(70,26),(72,29),(73,30),(74,31)]:
        estimate=rules.num(table[dr][1])[0];actual=rules.num(mt[ar][6])[0]
        errors.append(dict(product='复合梁' if dr<71 else '连接件',country=table[dr][0],estimate=estimate,actual=actual,
                           error=estimate-actual,unit='千单位',category='PLAYER_ESTIMATE_ERROR_NOT_MODEL_SCORE',
                           forecast_source=ref(dp,1,dr,1),actual_source=ref(mp,0,ar,6)))
    save('player_demand_estimate_errors.json',errors)
    comparison=[]
    for f in final:
        for plan,suggested in plans[f['key']]['plans'].items():
            n=rules.num(f['display'])
            matched=abs(f['value']-suggested)<=n[1]+1e-9 if n and isinstance(suggested,(float,int)) else str(f['value']).upper()==str(suggested).upper()
            comparison.append(dict(plan=plan,key=f['key'],final=f['value'],frozen_suggested=suggested,matched=matched))
    counts={p:dict(matched=sum(x['matched'] for x in comparison if x['plan']==p),total=56) for p in plans[final[0]['key']]['plans']}
    assert all(v['matched']<56 for v in counts.values())
    save('frozen_candidate_pairing.json',dict(source=ref(plan_path),counts=counts,fields=comparison,
         model_forecast_items_scored_against_actual=0,reason='Final group inputs differ from every complete frozen candidate; player estimate errors are separate.'))

    rankings=a.read(audit/'rankings.json');own=next(x for x in rankings if x['market']==5 and x['team']=='营销团队')
    states=[]
    state_rows={'cash_kusd':193,'short_debt_kusd':208,'long_debt_kusd':206,'assets_kusd':194,'equity_kusd':202,
                'receivables_kusd':192,'payables_kusd':210,'advance_received_kusd':209,'factory_kusd':187,'machine_kusd':188,
                'finished_inventory_kusd':191,'beam_inventory_kunits':86,'connector_inventory_kunits':87,
                'next_delivery_beam_displayed_kunits':82,'next_delivery_connector_displayed_kunits':83}
    for m in range(1,11):
        pp=a.source(m,'print');pt=a.read(pp)['tables'][0]
        for col,team in enumerate(pt[1][1:],1):
            states.append(dict(market=m,phase='formal',round=6,team=team,column=col,
                fields={key:dict(value=rules.num(pt[ri][col])[0],display=pt[ri][col],source=ref(pp,0,ri,col)) for key,ri in state_rows.items()},
                undisclosed_tax_loss_balance=None,unidentified_rd_operating_stock=None,
                terminal_interpretation='Keep displayed commitments; no round-7 forecast, liquidation, debt settlement or invented terminal value.'))
    save('terminal_states_100.json',states);save('rankings_100.json',rankings)
    save('validation_summary.json',dict(checks,field_requirements_per_market=len(template),field_coverage=len(coverage),
        field_status_counts=dict(Counter(x['status'] for x in coverage)),final_group_fields=56,
        group_decisions=sum(not f['player_estimate'] for f in final),group_player_estimates=sum(f['player_estimate'] for f in final),
        historical_personal_fields=224,historical_budget_values=10,decision_actual_crosschecks=len(cross),model_forecasts_scored=0))
    lines=['# 正式6终局数据采集与验收','',f'完成：{now.isoformat()}（北京时间）。10市场100队，10份打印版及130个必要结果网页来源完整；市场5另存财务指标、物流明细作结构对照。300个原始图表JSON/SVG配对、1900项财务等式、100项累计衔接通过。',
           '', '| 本组指标 | 正式6实际值 |','| --- | ---: |',
           f"| 本轮利润，千美元 | {own['profit_kusd']:g} |",f"| 累计收益，千美元 | {own['cumulative_kusd']:g} |",
           f"| 终局现金，千美元 | {own['cash_kusd']:g} |",f"| 短期贷款，千美元 | {own['short_debt_kusd']:g} |",f"| 长期贷款，千美元 | {own['long_debt_kusd']:g} |",
           f"| 市场5累计收益排名（计算值） | {own['rank_by_cumulative_in_market']} / 10 |",f"| 市场5本轮利润排名（计算值） | {own['rank_by_profit_in_market']} / 10 |",
           '', '排名公式为 `1 + 同市场该指标严格高于本组的队数`；并列同名次，不视作平台另设成绩。财务校验使用源显示值半步舍入误差之和作为容差；累计核验为 `正式6累计 − 正式5累计 − 正式6利润`。未改写原始值。',
           '',f'按正式6完整子栏对照建立每市场{len(template)}项字段要求，共{len(coverage)}项；[覆盖矩阵](field_coverage.json)保留国家/产品上下文、单位、表行列和哈希。财务指标与物流明细已由打印版覆盖，[对照证据](print_alias_checks.json)保留市场5独立网页配对，不把打印版虚算成15网页。本次业务缺项无需计算值补充；图表与重复表格不增加独立样本。',
           '', '[结构化网页字段](normalized_web_rows.json) · [100队利润与累计排名](rankings_100.json) · [100队终局状态](terminal_states_100.json) · [完整验收](validation_summary.json)',
           '', '本组最终56项、四位成员224项历史个人字段及10项预算摘要分别保留。小组历史预算利润2530千美元，实际3112千美元；差582千美元只表示两种口径差异，不能据此判断模型精度。六项需求预估误差另列。',
           '', '[最终56项](group_final_56.json) · [历史个人列](historical_personal_columns.json) · [历史预算](historical_budget_summary.json) · [实际交叉核对](decision_actual_crosschecks.json) · [玩家预估误差](player_demand_estimate_errors.json)',
           '', '最新菲律宾30/310假设分支的五个冻结候选均与实际最终方案不同，整套模型事前评分0项；[逐字段配对](frozen_candidate_pairing.json)保留匹配数量，不把未采用候选预测计为实际方案成绩。本次未重训、未做完整偏差归因。',
           '', '终局状态按真实显示保留现金、资产、债务、应收应付、库存及页面仍显示的后续订单；税亏余额和研发运营完整存量未披露处保持未知。不创建正式7预测，也不假设资产变现、清债或额外终值。正式6前景、参数和曲线复用既有归档，快速教程未重复采集。',
           '', '原件完整性更正：早期长HTML曾被工具截断，旧件保留，完整分段原件以 `_complete` 优先；来源验收排除截断版本。浏览器超时后的落盘与实际选择均重新核对。[原件清单](source_manifest.json)明确完整性和是否被采用。',
           '', '原始证据可能含人员信息，不直接分享；交付文件使用首字母。未修改或提交平台决策，未上传GitHub。']
    save('report.md','\n'.join(lines)+'\n')
    decision_lines=['# 回合6小组最终决策','', '小组历史列为最终方案；预估与预算均不作为实际标签。字段顺序沿用历史决策列表，非新增推荐。','']
    previous=None
    for f in final:
        if f['section']!=previous:
            decision_lines.extend(['',f"## {f['section']}",'','| 产品/区域 | 字段 | 单位 | 小组最终值 | 类别 |','| --- | --- | --- | ---: | --- |'])
            previous=f['section']
        decision_lines.append(f"| {f['product']} | {f['label']} | {f['unit']} | {f['display']} | {'玩家预估' if f['player_estimate'] else '最终决策'} |")
    save('group_final_56.md','\n'.join(decision_lines)+'\n')

    backup=out/'document_backup';backup.mkdir()
    readme=ROOT/'README.md';shutil.copy2(readme,backup/'README.md');before=rules.sha(readme)
    text=readme.read_text(encoding='utf-8');entry=out.relative_to(ROOT).as_posix()+'/report.md'
    first=(f'更新：2026-10-17（北京时间）。正式6已结算，平台显示游戏结束。10市场100队终局结果归档通过：10打印＋130必要网页，300图配对、1900财务等式与100累计衔接通过；本组最终56项已保存，正式6利润3112、累计9295千美元，按市场5累计收益排序第{own["rank_by_cumulative_in_market"]}/10。'
           f'[终局采集与验收]({entry})。本次未重训或完整复盘，不创建正式7预测。本文集中维护当前状态、版本入口、问题和下一步；再次操作平台前仍须核验实时状态。')
    text=re.sub(r'更新：[^\n]+',first,text,count=1)
    marker='| 初始0、练习1/2、正式1/2结果 |'
    assert marker in text
    text=re.sub(r'^\| 正式6终局实际及最终方案 \|[^\n]*\n','',text,flags=re.M)
    text=text.replace(marker,f'| 正式6终局实际及最终方案 | 10市场100队；140必要结果来源、300图配对、1900财务等式与100累计衔接通过；本组最终56项、四人224项历史个人字段已归档 | [终局验收]({entry})；本组利润3112、累计9295千美元，市场5累计收益排名（计算值）{own["rank_by_cumulative_in_market"]}/10；税亏及完整投入存量未披露处保持未知，未重训 |\n'+marker,1)
    text=text.replace('| 正式6已知条件及当前草稿 |','| 正式6历史期初条件及草稿 |')
    readme.write_text(text,encoding='utf-8')
    save('document_changes.json',dict(path='README.md',before=before,after=rules.sha(readme),backup=str((backup/'README.md').relative_to(ROOT))))
    links=[]
    for path in (out/'report.md',out/'group_final_56.md',readme):
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):continue
            exists=(path.parent/target.split('#')[0]).exists()
            links.append(dict(document=path.relative_to(ROOT).as_posix(),target=target,exists=exists))
    # The manifest itself is created immediately after link checking.
    assert all(r['exists'] or r['target']=='source_manifest.json' for r in links), [r for r in links if not r['exists']]
    manifest=[]
    adopted={a.source(m,p) for m in range(1,11) for p in ['print']+a.PANELS}
    for path in sorted(BASE.glob('*.json')):
        doc=a.read(path)
        if not isinstance(doc,dict) or not ('html' in doc or 'html_parts' in doc):continue
        complete=a.prior.formal.full_html(a.html(doc),doc.get('html_length'))
        manifest.append(dict(ref(path),complete_html=complete,captured_at=doc.get('captured_at'),url=doc.get('url'),
                             selected=a.selected(doc),adopted_for_results=path in adopted,source_class='raw_evidence_not_for_direct_sharing'))
    assert sum(r['adopted_for_results'] for r in manifest)==140
    save('source_manifest.json',manifest)
    for r in links:
        if r['target']=='source_manifest.json':r['exists']=(out/'source_manifest.json').exists()
    save('link_checks.json',links)
    assert all(r['exists'] for r in links)
    save('code_hashes.json',[ref(p) for p in [Path(__file__),BASE/'audit_collection.py',a.prior.__file__ and Path(a.prior.__file__),Path(a.pair.__file__)]])
    for p in [Path(__file__),BASE/'audit_collection.py']:shutil.copy2(p,out/p.name)
    with (BASE/'work_log.md').open('a',encoding='utf-8') as f:
        f.write(f'\n验收：{now.isoformat()}。完成10市场100队，140必要结果来源、300图JSON/SVG、1900财务等式、100累计衔接通过；字段要求{len(coverage)}项全部配对。本组56字段、224个人字段、10预算值、10组实际交叉检查；候选不同不评分为实际方案成绩。README磁盘备份、改前改后哈希、链接核验通过。报告：{(out/"report.md").relative_to(ROOT).as_posix()}。未改平台、未重训、未生成正式7或HTML报告、未上传。\n')
    print(json.dumps(dict(report=str(out/'report.md'),fields=len(coverage),own=own,candidate_matches=counts),ensure_ascii=False))


if __name__=='__main__':main()
