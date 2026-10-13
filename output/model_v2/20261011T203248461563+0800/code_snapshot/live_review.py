"""Assess captured UI evidence without controlling the browser."""
from core import *
from archive_and_report import table_rows
from finance import accounts,parameters

LIVE='output/model_v2/20261011T195500_live'
MATERIAL_REVIEW='output/model_v2/materials_review/20261011T200759885512+0800/review.json'
SCENARIO_ARCHIVE='output/scenario_archive/20261011T195927898602+0800'


def rows(name):
    d=read(f'{LIVE}/{name}.json')
    if 'snapshot' in d:
        return [r['cells'] for r in table_rows(d['snapshot']) if len(r['cells'])==6]
    return [r for t in d['data']['tables'] for r in t if r and any(v.strip() for v in r)]


def review():
    needed=['outlook','checklist_before','production_before','baseline_income','baseline_balance','baseline_cashflow',
            'machine1_input','machine1_checklist','machine1_reentry','machine1_income','machine1_balance','machine1_cashflow',
            'machine1_plan','machine1_logistics','machine1_before_restore','machine1_restored_input','machine1_restored_checklist','machine1_restored_reentry']
    assert all((ROOT/LIVE/(n+'.json')).is_file() for n in needed)
    before=rows('checklist_before');test=rows('machine1_checklist');restored=rows('machine1_restored_checklist')
    before=[r for r in before if len(r)==6];test=[r for r in test if len(r)==6];restored=[r for r in restored if len(r)==6]
    normalize=lambda rr:[[c.replace('\xa0',' ').strip() for c in r] for r in rr]
    b,t,z=map(normalize,[before,test,restored])
    # Unique ordered field rows include duplicate labels; preserve source order, never join on label alone.
    b=[r for r in b if r[0] not in ['','进入决策区域','保存为小组决策','导入至我的决策区域']]
    t=[r for r in t if r[0] not in ['','进入决策区域','保存为小组决策','导入至我的决策区域']]
    z=[r for r in z if r[0] not in ['','进入决策区域','保存为小组决策','导入至我的决策区域']]
    assert [r[0] for r in b]==[r[0] for r in t]==[r[0] for r in z]
    own_diffs=[dict(label=bb[0],before=bb[5],during=tt[5],after=zz[5]) for bb,tt,zz in zip(b,t,z) if bb[5]!=tt[5] or bb[5]!=zz[5]]
    personal_restored=all(bb[5]==zz[5] for bb,zz in zip(b,z))
    assert personal_restored
    concurrent=[dict(label=bb[0],column=i,before=bb[i],during=tt[i],after=zz[i]) for bb,tt,zz in zip(b,t,z) for i in range(1,5) if bb[i]!=zz[i]]
    assert next(r for r in t if r[0]=='机器, 复合梁')[5]=='1'
    assert next(r for r in z if r[0]=='机器, 复合梁')[5]=='0'
    controls=read(LIVE+'/machine1_restored_reentry.json')['data']['controls']
    assert [c['value'] for c in controls]==['0.00','0']
    inp=read('分步模型拟合与验证.json')['decisions']['current_inputs']
    d=dict(inp['decision'],machine_investment=1,long_rate=inp['decision']['long_rate']/100)
    predicted=accounts(inp['state'],d,inp['demand'],inp['efficiency'],parameters())
    mapping={'revenue':'净销售额','materials':'原材料购买','transport':'运输','long_interest':'长期贷款利息',
             'cash_interest':'利息收入','profit':'本回合利润','machine_depreciation':'机器','building_depreciation':'厂房'}
    income=rows('machine1_income')
    checks=[]
    for metric,label in mapping.items():
        matches=[r for r in income if r[0]==label and len(r)>1 and r[1].strip()]
        assert len(matches)==1,(label,matches)
        value=old.numeric(matches[0][1])
        checks.append(dict(metric=metric,observed=value,predicted=predicted[metric],error=predicted[metric]-value,
                           source_file=f'{LIVE}/machine1_income.json',source_cells=matches[0],
                           usage='固定旧参数的独立预算参考；并发状态变化，不用于拟合'))
    return dict(identity=dict(market_id=5,team='营销团队',personal='PYT',phase='formal',round=1,deadline_beijing='2026-10-11 22:00'),
        personal_baseline_reconfirmed=True,personal_restored=personal_restored,personal_differences=own_diffs,
        concurrent_other_column_changes=concurrent,perturbation_stopped=bool(concurrent),
        tests=dict(field='机器投资，千单位',before=0,test=1,restored=0,legal_options=list(range(21)),
                   saved=True,reentry_verified=True,restored_reentry_verified=True,
                   complete_budget_captured=True,production_logistics_captured=True,
                   calibratable=False,validation_use='仅参考；未完成一套无并发变化且独立留点的机制验证'),
        mutations=dict(test_changes=1,restorations=1,group_submissions=0,other_member_writes=0),
        single_point_checks=checks,source_hashes={f'{LIVE}/{n}.json':digest(ROOT/LIVE/(n+'.json')) for n in needed},
        screenshot=f'{LIVE}/machine1_restored.png',remaining_tests=['机器10/20','班次/解聘两侧','现金触发两侧','贷款/计息/税亏'],
        stop_reason='恢复回读时其他成员列已变化；按边界停止后续扰动，保留最新成员决策')


def materials():
    m=read(MATERIAL_REVIEW)
    for path,h in m['input_hashes'].items():
        assert digest(ROOT/path)==h
    return dict(source_file=MATERIAL_REVIEW,source_sha256=digest(ROOT/MATERIAL_REVIEW),independent_review=m,
                conclusion='练习1与练习2共同加性单位差额可行区间不相交；单位更正通过，跨情境材料差额机制仍未识别')
