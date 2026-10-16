"""Publish source-linked final decisions and formal-6 conditions; no fitting."""
import importlib.util
import inspect
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
spec = importlib.util.spec_from_file_location('validation', BASE / 'validation/validate_market.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(folder, name, obj):
    folder.mkdir(parents=True, exist_ok=True)
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)
    with (folder / name).open('x', encoding='utf-8') as stream:
        stream.write(v.rules.redact_names(text))


def value(text):
    n = v.rules.num(str(text))
    return n[0] if n else text


def html(doc):
    return ''.join(doc['html_parts'])


def reference(path, ti=None, ri=None, ci=None):
    r = v.reference(path)
    if ti is not None:
        r.update(table=ti, row=ri, column=ci, indexing='zero_based')
        shown = read(path)['tables'][ti][ri][ci]
        r.update(display=shown, value=value(shown))
    return r


def actual(panel, row):
    return reference(BASE / f'raw/market5_formal5_{panel}.json', 0, row, 6)


def main():
    history = BASE / 'decision_history'
    initial = BASE / 'formal6_initial'
    source = BASE / 'own_formal5_decisionchecklist.json'
    d = read(source)
    assert d['selects'][0]['selected'] == '回合5'
    assert v.formal.full_html(html(d), d['html_length'])
    table = d['tables'][1]
    assert table[0][1] == '营销团队' and 'current' in d['cell_styles'][1][0][5]['class'].split()
    candidates_path = ROOT / 'output/formal5_two_policies_t5v2/20261015T214235442505+0800/decisions.json'
    candidates = read(candidates_path)
    plans = list(dict.fromkeys(r['plan'] for r in candidates))
    definitions = [r for r in candidates if r['plan'] == plans[0]]
    assert len(definitions) == 42
    fields = []
    for r in definitions:
        row = r['row'] - 2
        assert table[row][0] == r['label'], (row, r['key'])
        for col in range(1, 6):
            style = d['cell_styles'][1][row][col]
            fields.append(dict(key=r['key'], section=r['section'], product=r['product'], label=r['label'], unit=r['unit'],
                value=value(table[row][col]), player_estimate=row > 53, column=col,
                identity='GROUP_FINAL' if col == 1 else 'PYT' if col == 5 else f'MEMBER_COL_{col}',
                category=('FINAL_GROUP_PLAYER_ESTIMATE' if row > 53 else 'FINAL_GROUP_DECISION') if col == 1 else 'HISTORICAL_PERSONAL_NOT_GROUP_FINAL',
                style=style, round=5, market=5, source=reference(source, 1, row, col)))
    group = [r for r in fields if r['column'] == 1]
    assert len(group) == 42 and len({r['key'] for r in group}) == 42
    bykey = {r['key']:r for r in group}
    comparisons = []
    for r in candidates:
        a, b = bykey[r['key']]['value'], r['suggested']
        same = abs(a - b) < 1e-8 if isinstance(a, (int, float)) and isinstance(b, (int, float)) else str(a).lower() == str(b).lower()
        comparisons.append(dict(plan=r['plan'], key=r['key'], final=a, frozen_suggested=b, matched=same))
    adopted = {p:dict(matched=sum(r['matched'] for r in comparisons if r['plan']==p),
                    mismatched=sum(not r['matched'] for r in comparisons if r['plan']==p)) for p in plans}
    budgets = [dict(column=col, category='HISTORICAL_BUDGET_NOT_ACTUAL', source=reference(source,1,row,col))
               for row in (3,4) for col in range(1,6)]
    cross = []
    for submitted, result in [(7,3),(8,4),(11,6),(12,7)]:
        ref = actual('marketdetails', result)
        assert abs(value(table[submitted][1])-ref['value']) <= v.rules.num(ref['display'])[1] + 1e-9
        cross.append(dict(kind='retail_price',submitted=reference(source,1,submitted,1),actual=ref,status='pass'))
    for rows, result in [([16,17,19,20],30),([23,24,25,27,28,29],31),([49,50],38),([47],39)]:
        ref = actual('incomestatement', result)
        inputs = [reference(source,1,row,1) for row in rows]
        assert abs(sum(r['value'] for r in inputs)-ref['value']) <= v.rules.num(ref['display'])[1] + 1e-9
        cross.append(dict(kind='expenditure_sum',inputs=inputs,actual=ref,status='pass'))
    save(history,'group_final_42.json',group)
    save(history,'all_historical_columns.json',fields)
    save(history,'budget_summary.json',budgets)
    save(history,'candidate_comparison.json',dict(source=reference(candidates_path),counts=adopted,fields=comparisons))
    save(history,'actual_crosschecks.json',cross)
    estimates=[]
    for dr, ar in [(56,20),(57,21),(59,24),(60,25)]:
        a=actual('marketdetails',ar); forecast=value(table[dr][1])
        estimates.append(dict(source=reference(source,1,dr,1),actual=a,error=forecast-a['value'],category='FINAL_GROUP_PLAYER_ESTIMATE_ERROR_NOT_MODEL_SCORE'))
    save(history,'player_demand_estimate_errors.json',estimates)
    save(history,'report.md','# 回合5最终小组方案\n\n42字段：29项决策、13项玩家预估；另存168项历史个人输入和10项预算摘要。小组列按历史选择器读取，个人列不作为生效方案。8组零售价格及费用交叉核对通过。\n\n'
         + '最新冻结候选逐字段配对：'+str(adopted)+'。配对涉及本组最终方案，不代表模型已验证。玩家需求预估误差另存，不计模型事前成绩；本次不重训、不开展完整经营复盘。\n\n'
         + '[最终42项](group_final_42.json) · [冻结候选配对](candidate_comparison.json) · [实际交叉核对](actual_crosschecks.json) · [玩家预估误差](player_demand_estimate_errors.json)\n')

    names=['decisionchecklist','decisionchecklist_readback','decisionchecklist_final_readback','outlook','demand',
           'productioninvestments','productionplanning','marketreportdomestic','marketreportinternational1',
           'marketreportinternational2','marketreportbulk','logistics','corporate','schedule']
    docs={p:read(BASE/f'own_formal6_{p}.json') for p in names}
    sources=[reference(BASE/f'own_formal6_{p}.json') for p in names]
    for p,doc in docs.items():
        assert v.formal.full_html(html(doc),doc['html_length']),p
        assert '2026-10-16 22:00' in doc['text'],p
        assert ('市场 5' in doc['text'] or '市场5' in doc['text']),p
    check=docs['decisionchecklist']
    for name in ['decisionchecklist_readback','decisionchecklist_final_readback']:
        assert check['tables'][1]==docs[name]['tables'][1]
        assert check['cell_styles'][1]==docs[name]['cell_styles'][1]
        assert docs[name]['selects'][0]['selected']=='回合6'
    current=[]; section='';product=''; estimate=False
    main_sections={'每单位价格','一般营销, 千 美元','设计师营销, 千 美元','物流决策','产能分配, %','投资决策, 千单位',
                   '运营改进, 千 美元','研发, 千 美元','财务决策','需求, 千单位','预计市场增长，%','总市场需求, 千单位',
                   '需求增长预估, %','生产效率, 千单位/人','财务'}
    for ri,row in enumerate(check['tables'][1]):
        if ri<7 or not row:continue
        if len(row)==1:
            if row[0]=='预估':estimate=True
            elif row[0] in main_sections:section=row[0];product=''
            else:product=row[0]
        elif len(row)==6:
            key='|'.join([section,product,row[0]])
            for ci in range(1,6):
                current.append(dict(key=key,section=section,product=product,label=row[0],value=value(row[ci]),column=ci,
                    category='CURRENT_PLAYER_ESTIMATE_NOT_ACTUAL' if estimate else 'CURRENT_DRAFT_NOT_FINAL',
                    source=reference(BASE/'own_formal6_decisionchecklist.json',1,ri,ci),style=check['cell_styles'][1][ri][ci]))
    per_column=len(current)//5
    assert len(current)==5*per_column and len({(r['key'],r['column']) for r in current})==len(current)
    narrative=docs['outlook']['tables'][1]
    conditions=[dict(section=narrative[ri][0],text=narrative[ri+1][0],source=reference(BASE/'own_formal6_outlook.json',1,ri+1,0)) for ri in range(1,len(narrative),2)]
    assert {r['section'] for r in conditions}=={'需求','大客户订单','生产','货币','财务'}
    params=[];headers=[]
    for ri,row in enumerate(docs['outlook']['tables'][2]):
        if len(row)==1:headers.append(row[0])
        if len(row)==4 and ri>1:params.append(dict(label=row[0],section_headers=headers.copy(),current=row[1],change=row[2],previous=row[3],source=reference(BASE/'own_formal6_outlook.json',2,ri,1)))
    curve_rule=ROOT/'output/round_close/20261013_formal3_close/historical_supplement/audit/verify_historical_supplement.py'
    spec=importlib.util.spec_from_file_location('curves',curve_rule);rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules)
    charts,errors=rules.rules.charts(html(docs['productionplanning']));assert not errors
    charts=[c for c in charts if 'quality.control' in c['id'] or 'cost.efficiency' in c['id']]
    svgs=re.findall(r'<svg\b[\s\S]*?</svg>',html(docs['productionplanning']),re.I)
    pairing_source=inspect.getsource(rules.pair_curve_y)
    assert pairing_source.count('> 500')==1
    namespace=dict(rules.__dict__);exec(pairing_source.replace('> 500','> 400'),namespace)
    pairs=namespace['pair_curve_y'](charts,svgs)
    assert len(pairs)==3 and all(p['status']=='pass_y_values' and p['points']==200 for p in pairs)
    previous=[]
    for ti,ri,section,label in [(4,2,'研发, 千 美元','复合梁'),(4,3,'研发, 千 美元','连接件'),(5,2,'运营改进, 千 美元','泰国')]:
        ref=reference(BASE/'own_formal6_productionplanning.json',ti,ri,2)
        match=[r for r in group if r['section']==section and r['label']==label]
        assert len(match)==1 and ref['value']==match[0]['value']
        previous.append(dict(label=label,previous_actual=ref,final_group=match[0]['source']))
    carry=[]
    def add(metric,ending,opening=None,status='UNKNOWN_NO_INDEPENDENT_OPENING',note='期末已知；预算投影不作为独立期初披露。'):
        carry.append(dict(metric=metric,ending=ending,opening=opening,status=status,note=note))
    for product,ti,ri in [('复合梁',1,44),('连接件',2,45)]:
        a=actual('marketdetails',ri);b=reference(BASE/'own_formal6_logistics.json',ti,10,1)
        assert a['value']==b['value'];add(product+'库存数量',a,b,'MATCHED_EXPLICIT_OPENING','千单位；数量不等于账面价值。')
    a=actual('balancesheet',30);b=reference(BASE/'own_formal6_corporate.json',1,5,2)
    assert a['value']==b['value'];add('长期贷款',a,b,'MATCHED_LAST_YEAR_REFERENCE','千美元；去年余额，不是今年最终融资方案。')
    for product,ari,ri in [('复合梁',2,3),('连接件',3,4)]:
        a=actual('productiondetails',ari);b=reference(BASE/'own_formal6_productioninvestments.json',3,ri,2)
        assert abs(a['value']*.85-b['value'])<=.005*.85+.005+1e-9
        add(product+'机器可用产能',a,b,'MATCHED_CONDITIONAL_DECAY','千单位；当前个人投资0，容量与公布15%衰减相容。')
    for metric,ri in [('现金及现金等价物',17),('短期贷款',32),('机器账面价值',12),('厂房账面价值',11),('库存账面价值',15),('应收账款',16),('应付账款',34),('已收预付款',33),('留存收益',25)]:add(metric,actual('balancesheet',ri))
    add('生产人员',dict(value=sum(actual('productiondetails',ri)['value'] for ri in (7,14)),inputs=[actual('productiondetails',ri) for ri in (7,14)]))
    for metric in ['税亏结转余额','研发持续存量','运营持续存量']:add(metric,None,note='未披露真实存量，不能用上期投入或历史权重补零或补造。')
    for product,ri in [('复合梁',41),('连接件',42)]:add(product+'下期大客户承诺',actual('marketdetails',ri),note='上期结果下一回合订单数量已保存；本期真实合同和收付款衔接尚未独立核验。')
    assert len(carry)==20
    for name,obj in [('current_drafts_all_columns.json',current),('current_group_draft.json',[r for r in current if r['column']==1]),
                     ('published_outlook_five_parts.json',conditions),('published_parameters.json',params),('curve_original_literals.json',charts),
                     ('curve_pairings.json',pairs),('previous_actual_inputs.json',previous),('carryover_comparison.json',carry),('source_manifest.json',sources)]:save(initial,name,obj)
    for i in sorted({p['svg_index'] for p in pairs}):save(initial,f'curve_source_{i}.svg',svgs[i])
    summary=dict(status='PASS_WITH_EXPLICIT_UNKNOWN_OPENING_STATES',sources=len(sources),draft_fields_per_column=per_column,
                 current_drafts=len(current),outlook_parts=5,parameters=len(params),curves=3,curve_points=600,
                 upstream_actual_inputs=[r['previous_actual']['value'] for r in previous],carryover_status_counts=dict(Counter(r['status'] for r in carry)),
                 final_round=6,next_round7_forecast_created=False,training_performed=False)
    save(initial,'acceptance.json',summary)
    save(initial,'report.md',f'# 正式6初始资料\n\n14份完整原件；{per_column}项字段×5列（含预估、零值和选择项），三次列表回读值和样式一致。五部分前景、{len(params)}项公布参数及3条投入曲线600点已保存，JSON/SVG纵轴同点配对通过；横轴为舍入显示标签，SVG不增加独立样本。\n\n'
         '新增菲律宾市场与印尼机器投资字段，已保存菲律宾销售子页。上期研发2600/231、运营754千美元与回合5最终小组决策一致；它们是上期投入，不代表完整持续存量。\n\n'
         '20项结转中：两项库存数量直接匹配、长期贷款上期余额匹配、两项机器产能在零个人投资条件下与15%衰减相容；其余15项缺独立期初核验，保留未知。当前个人产量、现金和费用预算不能当期初实际。\n\n'
         '正式6截止：2026-10-16 22:00（北京时间）。平台有第7回合生产提示，仅保留为来源文本；本项目正式6为终局，不创建第7回合预测。未填写或提交方案，未重训。\n\n'
         '[当前字段清单](current_group_draft.json) · [前景](published_outlook_five_parts.json) · [公布参数](published_parameters.json) · [曲线JSON](curve_original_literals.json) · [配对](curve_pairings.json) · [状态结转](carryover_comparison.json) · [验收](acceptance.json)\n')
    print(json.dumps(dict(history=adopted,initial=summary),ensure_ascii=False))


if __name__=='__main__':
    assert value('1\u00a0234.50')==1234.5 and value('FALSE')=='FALSE'
    main()
