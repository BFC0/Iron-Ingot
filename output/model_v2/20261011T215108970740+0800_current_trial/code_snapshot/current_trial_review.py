"""Audit restored machine10→20→10 trial; never controls UI or builds HTML."""
import csv
import shutil
from datetime import datetime, timezone, timedelta
from core import *
from finance import accounts, parameters
from supplement import statement_values
from horizon import remaining_profit, self_check

LIVE_CURRENT='output/model_v2/20261011T211500_live_finance'


def tables(name):
    return read(LIVE_CURRENT+'/'+name+'.json')['data']['tables']


def checklist(name):
    return [[v.replace('\xa0',' ').strip() for v in r] for t in tables(name) for r in t
            if len(r)==6 and r[0] not in ['','进入决策区域','保存为小组决策','导入至我的决策区域']]


def review():
    before=checklist('checklist_operations400'); during=checklist('machine20_checklist')
    restored=checklist('restored_checklist_final')
    assert [r[0] for r in before]==[r[0] for r in during]==[r[0] for r in restored]
    assert [r[5] for r in before]==[r[5] for r in restored]
    assert [r[1] for r in before]==[r[1] for r in restored]
    own_changes=[dict(field=b[0],before=b[5],during=d[5]) for b,d in zip(before,during) if b[5]!=d[5]]
    assert {r['field'] for r in own_changes}=={'机器, 复合梁','利润, 千 美元'}
    get=lambda label,occ=0: old.numeric([r for r in before if r[0]==label][occ][5])
    decision=dict(prices=[get('泰国, 美元'),get('印尼, 美元')],general=[get('泰国'),get('印尼')],
        designer=[get('泰国',1),get('印尼',1)],rd=get('复合梁',1),operations=get('泰国',3),
        allocation=get('复合梁'),machine_investment=get('机器, 复合梁'),priority=[0,1],
        long_change=get('长期贷款变化(增加 + / 减少 -), 千 美元'),long_rate=get('长期贷款利率, %')/100)
    demand=[get('泰国',4),get('印尼',3)];efficiency=get('复合梁',3)
    assert decision['machine_investment']==10 and decision['operations']==400 and demand==[2.5,11] and efficiency==.15
    assert read(LIVE_CURRENT+'/machine20_reentry.json')['data']['controls'][1]['value']=='20'
    assert read(LIVE_CURRENT+'/restored_investment_reentry.json')['data']['controls'][1]['value']=='10'
    state=read('分步模型拟合与验证.json')['decisions']['current_inputs']['state']; p=parameters()
    income_labels=dict(revenue='净销售额',materials='原材料购买',transport='运输',marketing='营销和销售成本总和',
        overhead='杂费成本总和',ebitda='税息折旧及摊销前利润（EBITDA）',machine_depreciation='机器',
        building_depreciation='厂房',long_interest='长期贷款利息',cash_interest='利息收入',tax='直接税',profit='本回合利润')
    records=[];outputs={}
    def cell(name,label):
        matches=[(ti,ri,r) for ti,t in enumerate(tables(name)) for ri,r in enumerate(t) if len(r)>1 and r[0]==label and r[1].strip()]
        assert len(matches)==1,(name,label)
        ti,ri,r=matches[0]
        return old.numeric(r[1]),dict(file=LIVE_CURRENT+'/'+name+'.json',table=ti,row=ri,column=1,label=label,text=r[1])
    for prefix,inv in [('baseline400',10),('machine20',20)]:
        a=accounts(state,dict(decision,machine_investment=inv),demand,efficiency,p);outputs[prefix]=a
        mappings={'income':{label:a[metric] for metric,label in income_labels.items()},**statement_values(state,a)}
        for table,values in mappings.items():
            for label,value in values.items():
                observed,source=cell(prefix+'_'+table,label)
                records.append(dict(case=prefix,statement=table,metric=label,predicted=value,observed=observed,
                    error=value-observed,target_display_half_width=.5,inside_target_display_interval=abs(value-observed)<=.5,
                    unit='千美元',source=source,usage='固定既有参数的保留预算点，不用于校准；输入误差传播仍需条件核验'))
    plan=[r for t in tables('machine20_plan') for r in t]
    plan_checks=[]
    for label,value,tol in [('生产, 千单位',outputs['machine20']['production']['production'],.005),
                            ('产能, 千单位',outputs['machine20']['capacity'],.005),
                            ('生产线人工数量',outputs['machine20']['production']['workers'],.05),
                            ('生产工资合计, 千 美元',outputs['machine20']['production']['payroll'],.5)]:
        matched=[r for r in plan if len(r)>1 and r[0]==label];assert len(matched)==1
        observed=old.numeric(matched[0][1]);assert abs(value-observed)<=tol
        plan_checks.append(dict(metric=label,predicted=value,observed=observed,display_half_width=tol,passed=True))
    incident=read(LIVE_CURRENT+'/source_integrity_incident.json')
    return dict(status='RESTORED_PERSONAL_BUDGET_TRIAL_NOT_DEMAND_VALIDATION',decision=decision,demand=demand,
        efficiency=efficiency,state=state,parameters=p,outputs=outputs,records=records,production_checks=plan_checks,
        personal_restored=True,group_column_unchanged=True,personal_only_changes=own_changes,
        mutations=dict(test_changes=1,restorations=1,group_submissions=0,other_member_writes=0),
        own_trial_valid=True,calibration_performed=False,full_mechanism_gate_passed=False,
        interpretation='本人整列及小组列保持；其他成员各自列变化不影响本人预算，本点保留作独立参考',
        source_integrity_incident=incident,
        horizon_checks=self_check(),future_profit_path=remaining_profit(1,[dict(round=i,profit=None,in_scope=False,end_state=None) for i in range(1,7)]),
        limitations=['运营400成功保留，但效率0.15仍为玩家手填，不是真实效率标签',
                     '机器20不是推荐；班次边界、第三班、贷款现金触发及完整独立财务套件仍缺',
                     '正式仅6回合，未来前景和状态未知；不计第7以后收益或自动终值'])


def main():
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out=ROOT/'output/model_v2'/(stamp+'_current_trial');out.mkdir()
    result=review();write(out/'review.json',result)
    with (out/'records.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['records'][0]));writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in result['records'])
    snapshot=out/'code_snapshot';snapshot.mkdir()
    for name in ['current_trial_review.py','horizon.py','finance.py','supplement.py','core.py','live_review.py']:
        shutil.copy2(Path(__file__).parent/name,snapshot/name)
    for name in ['build_model_inputs.py','stepwise_model.py','cross_market_validation.py','archive_and_report.py']:
        shutil.copy2(ROOT/'code'/name,snapshot/name)
    write(out/'manifest.json',dict(input_hashes={p.relative_to(ROOT).as_posix():digest(p) for p in (ROOT/LIVE_CURRENT).glob('*') if p.is_file()},
        code_hashes={p.name:digest(p) for p in snapshot.iterdir()},html_changes=0,calibration_performed=False))
    failures=[r for r in result['records'] if not r['inside_target_display_interval']]
    text=['# 最新个人预算试验与六回合期限补查','',
          '本人机器10→20→10已保存、重入及恢复，运营400保留；本人全部字段与最新基准一致，小组列未改。',
          '基准：售价2200/2400、机器10、分配60%、还贷10000、研发600、运营400、手填需求2.5/11、效率0.15、利率3%。',
          '平台基准利润5076，机器20试验利润5254千美元；固定手填需求下的预算参考，不作为推荐。',
          f"生产4项显示核验通过；三表{len(result['records'])}项名义比较中{len(failures)}项超目标±0.5千美元显示区间，保留差额，未重新校准。",'',
          '| 样本 | 财务表 | 指标 | 预测−显示（千美元） |','| --- | --- | --- | ---: |']
    text += [f"| {r['case']} | {r['statement']} | {r['metric']} | {r['error']:.6f} |" for r in failures]
    text += ['',*result['limitations'],'',
             '归档事故：本轮旧capture闭包将两份旧基准JSON覆盖；本次记录已复制到独立目录，原始旧基准无法完整恢复。冻结报告及派生记录保留，缺口明确标记，不冒充原始复原。详见source_integrity_incident.json。',
             '仅比较正式t至6回合利润，剩余7−t回合；未知利润不补零，不加终值，不强制清债，期末状态保留。horizon.py六种起点及越界/缺失检查通过；尚未产生六回合排名。']
    (out/'conclusions.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(out);print(dict(comparisons=len(result['records']),target_interval_failures=len(failures),restored=result['personal_restored']))


if __name__=='__main__': main()
