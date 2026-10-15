"""Label historical group decisions and compare existing frozen candidates."""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'output/round_close/20261014_formal4_close'
RAW=BASE/'raw'
JOINT=ROOT/'output/formal4_all/20261014T211634211494+0800'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def value(text):
    clean=re.sub(r'\s+','',str(text))
    return float(clean) if re.fullmatch(r'-?\d+(?:\.\d+)?',clean) else clean


def main():
    now=datetime.now(timezone(timedelta(hours=8)))
    out=BASE/'decision_history'/now.strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True,exist_ok=False)
    (out/'work_log.md').write_text('# 正式4最终决策配对\n\n不要输出真名，姓名统一用首字母替代。\n\n开始：'+now.isoformat()+'\n授权：回合结束只读采集与冻结复盘，不重训、不修改平台。\n',encoding='utf-8')
    p=RAW/'own_formal4_decisionchecklist.json';d=read(p);table=d['tables'][1]
    assert any(s.get('selected')=='回合4' for s in d['selects'])
    assert table[0][1]=='营销团队' and len(table)==78
    assert '市场 5' in d['text'] or '市场5' in d['text']
    html=''.join(d['html_parts'])
    assert len(html.encode('utf-16-le',errors='surrogatepass'))//2==d['html_length']
    assert '</html>' in html[-100:].lower()
    styles=d['cell_styles'][1]
    current_cols=[i for i,s in enumerate(styles[0]) if 'current' in (s.get('class') or '').split()]
    assert current_cols==[5]
    candidates=read(JOINT/'decisions.json')
    definitions={r['key']:r for r in candidates}
    assert len(definitions)==42
    fields,budgets,bykey=[],[],{}
    for key,definition in definitions.items():
        row=definition['source_row']-2
        assert row>4 and len(table[row])==6 and value(table[row][0])==value(definition['label'])
        bykey[key]=row
        estimate=row>=53
        for col in range(1,6):
            style=styles[row][col]
            cls=(style.get('class') or '').split()
            fields.append(dict(market_id=5,phase='formal',round=4,team='营销团队',
                team_id='M5_C6',key=key,section=definition['section'],product_or_location=definition['product_or_location'],
                label=definition['label'],unit=definition['unit'],value=value(table[row][col]),display=table[row][col],
                category=('ROUND_4_GROUP_FINAL_PLAYER_ESTIMATE' if estimate else 'ROUND_4_GROUP_FINAL_DECISION') if col==1 else ('HISTORICAL_PERSONAL_PLAYER_ESTIMATE' if estimate else 'HISTORICAL_PERSONAL_DRAFT_NOT_GROUP_FINAL'),
                column_identity='营销团队' if col==1 else ('PYT' if col==5 else f'MEMBER_COL_{col}'),
                modified_state='changed' if 'changed' in cls else 'notchanged' if 'notchanged' in cls else 'unknown',
                cell_style=style,source_path=p.relative_to(ROOT).as_posix(),sha256=sha(p),table=1,row=row,column=col,indexing='zero_based'))
    assert len(fields)==210 and len({(r['key'],r['column']) for r in fields})==210
    for row in (3,4):
        for col in range(1,6):
            budgets.append(dict(market_id=5,phase='formal',round=4,metric=table[row][0],value=value(table[row][col]),display=table[row][col],
                category='HISTORICAL_PLATFORM_BUDGET_NOT_ACTUAL_NOT_MODEL_FORECAST',
                column_identity='营销团队' if col==1 else ('PYT' if col==5 else f'MEMBER_COL_{col}'),
                source_path=p.relative_to(ROOT).as_posix(),sha256=sha(p),table=1,row=row,column=col,indexing='zero_based',cell_style=styles[row][col]))
    group={r['key']:r for r in fields if r['column']==1}
    mismatches=[]
    for candidate in candidates:
        actual=group[candidate['key']]['value'];suggested=value(candidate['suggested'])
        identical=abs(actual-suggested)<1e-9 if isinstance(actual,(int,float)) and isinstance(suggested,(int,float)) else actual==suggested
        mismatches.append(dict(plan=candidate['plan'],key=candidate['key'],unit=candidate['unit'],
            final_group_value=actual,frozen_suggested_value=suggested,matched=identical,
            final_source=group[candidate['key']]))
    counts={plan:dict(matched=sum(r['matched'] for r in mismatches if r['plan']==plan),
                    mismatched=sum(not r['matched'] for r in mismatches if r['plan']==plan)) for plan in {r['plan'] for r in mismatches}}
    crosschecks=[]
    def source(name,row,col=6):
        path=RAW/name;doc=read(path)
        for t in doc['tables']:
            if any('营销团队' in r for r in t):
                assert any(len(r)>6 and r[6]=='营销团队' for r in t)
        r=doc['tables'][0][row];num=value(r[col]);clean=re.sub(r'\s+','',r[col]);half=.5*10**(-len(clean.split('.')[1])) if '.' in clean else .5
        return dict(value=num,display=r[col],half_step=half,source_path=path.relative_to(ROOT).as_posix(),sha256=sha(path),table=0,row=row,column=col,indexing='zero_based',label=r[0])
    def cross(label,submitted,actual,inputs):
        assert abs(submitted-actual['value'])<=actual['half_step']+1e-9
        crosschecks.append(dict(field=label,submitted=submitted,actual=actual,inputs=inputs,passed=True))
    def inputs(rows):
        return [r for r in fields if r['column']==1 and r['row'] in rows]
    for dr,ar in [(7,3),(8,4),(11,6),(12,7)]:
        cross('零售价格',value(table[dr][1]),source('market5_formal4_marketdetails.json',ar),inputs([dr]))
    for label,drs,ar in [('一般营销',[16,17,19,20],30),('设计师营销',[23,24,25,27,28,29],31),('研发',[49,50],38),('运营改进',[47],39)]:
        cross(label,sum(value(table[r][1]) for r in drs),source('market5_formal4_incomestatement.json',ar),inputs(drs))
    cross('长期贷款变化',value(table[52][1]),source('market5_formal4_cashflow.json',29),inputs([52]))
    for label,print_row,page_name,page_row in [
        ('复合梁泰国零售价格',38,'market5_formal4_marketdetails.json',3),
        ('复合梁印尼零售价格',39,'market5_formal4_marketdetails.json',4),
        ('连接件泰国零售价格',41,'market5_formal4_marketdetails.json',6),
        ('连接件印尼零售价格',42,'market5_formal4_marketdetails.json',7),
        ('复合梁生产人员',88,'market5_formal4_productiondetails.json',7),
        ('复合梁实际产量',90,'market5_formal4_productiondetails.json',9),
        ('复合梁实际效率',91,'market5_formal4_productiondetails.json',10),
        ('连接件生产人员',94,'market5_formal4_productiondetails.json',14),
        ('连接件实际产量',96,'market5_formal4_productiondetails.json',16),
        ('连接件实际效率',97,'market5_formal4_productiondetails.json',17)]:
        printed=source('market5_formal4_print_complete.json',print_row)
        actual=source(page_name,page_row)
        assert abs(printed['value']-actual['value'])<=printed['half_step']+actual['half_step']+1e-9
        crosschecks.append(dict(field=label,printed_actual=printed,page_actual=actual,
                               check_type='PRINT_VS_WEB_ACTUAL_NOT_PLAYER_ESTIMATE',passed=True))
    for decision_row,capacity_row,production_row in [(40,2,9),(41,3,16)]:
        allocation=value(table[decision_row][1]);capacity=source('market5_formal4_productiondetails.json',capacity_row)
        produced=source('market5_formal4_productiondetails.json',production_row)
        limit=capacity['value']*allocation/100
        assert produced['value'] <= limit+capacity['half_step']*allocation/100+produced['half_step']+1e-9
        crosschecks.append(dict(field='产品实际产量不超过最终分配机器产能',allocation_percent=allocation,
            allocated_capacity_kunits=limit,capacity_actual=capacity,production_actual=produced,
            submitted_source=inputs([decision_row])[0],passed=True,
            limitation='仅验证供给上界相容；需求约束使产量不必等于分配产能，不能反推唯一分配决策'))
    estimates=[]
    for dr,ar in [(56,20),(57,21),(59,24),(60,25)]:
        actual=source('market5_formal4_marketdetails.json',ar)
        estimates.append(dict(field=table[dr][0],key=next(k for k,r in bykey.items() if r==dr),
            value_type='PLAYER_ESTIMATE_EVALUATION_NOT_MODEL_FORECAST',player_estimate=value(table[dr][1]),
            actual=actual,error=value(table[dr][1])-actual['value'],estimate_source=inputs([dr])[0]))
    actual_profit=source('market5_formal4_incomestatement.json',55)
    verdict=dict(status='NO_MATCHING_PROSPECTIVE_CANDIDATE_FORECAST',scored_model_n=0,
        market_id=5,phase='formal',round=4,team='营销团队',team_id='M5_C6',candidate_field_matches=counts,
        reason='最终小组方案与两套冻结候选均不一致，四项零售售价全部不同；不将候选预测直接评分为本次方案事前成绩。',
        final_group_fields=42,personal_fields=168,budget_summaries=10,
        personal_current_column='PYT',other_personal_columns='MEMBER_COL_2至4（仅保留来源列编号，未推断姓名映射）',
        crosschecks_passed=len(crosschecks),no_training=True,
        group_budget_profit=next(r['value'] for r in budgets if r['row']==3 and r['column']==1),
        actual_profit=actual_profit,profit_comparison_type='BUDGET_VS_ACTUAL_NOT_MODEL_PROSPECTIVE_SCORE',
        limitations=['候选完整利润未独立前向验证','销量截断不能代替真实需求','色值未从浏览器重新计算，保留原class/style及changed状态','投入分项合计与实际核对，不能据总额辨认其他市场逐国投入'])
    assert all(v['mismatched']>0 for v in counts.values())
    for name,data in [('all_fields.json',fields),('group_final_42.json',list(group.values())),('budgets.json',budgets),
        ('candidate_pairing.json',mismatches),('actual_crosschecks.json',crosschecks),('player_estimate_comparison.json',estimates),('frozen_score_verdict.json',verdict)]:
        with (out/name).open('x',encoding='utf-8') as stream:json.dump(data,stream,ensure_ascii=False,indent=2,allow_nan=False)
    with (out/'work_log.md').open('a',encoding='utf-8') as stream:stream.write('\n完成：42小组字段、168个人字段、10预算摘要分类及候选/实际核验；冻结模型评分0项，无配对事前候选。\n')
    print(json.dumps(dict(output=out.relative_to(ROOT).as_posix(),**verdict),ensure_ascii=False))


if __name__=='__main__':main()
