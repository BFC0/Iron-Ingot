"""Conditional rounding propagation; no demand refit, HTML or live writes."""
import csv
import shutil
from itertools import product
from datetime import datetime, timezone, timedelta
from core import *
from finance import accounts, parameters, parameter_sources
from supplement import financial_review, statement_values


def review():
    inp=read('分步模型拟合与验证.json')['decisions']['current_inputs']
    state,p=inp['state'],parameters()
    fields=[('capacity','生产能力, 千单位',0,.005),('workers','生产线人工数量',0,.005),
            ('cash','现金及现金等价物',1,.5),('ar','应收帐款',0,.5),('ap','应付账款',0,.5),
            ('machine_book','机器',1,.5),('building_book','厂房',1,.5),('long_debt','长期贷款',0,.5)]
    inputs={name:dict(value=state[name],half_width=half,source=step.source('initial0_printable',label,6,occ))
            for name,label,occ,half in fields}
    assert all(r['source']['value']==r['value'] for r in inputs.values())
    reference=financial_review(); records=[]; maximum_error=0
    for case,inv in [('baseline',0),('machine1',1)]:
        decision=dict(inp['decision'],machine_investment=inv,long_rate=inp['decision']['long_rate']/100)
        def evaluate(offsets):
            s=dict(state)
            for (name,_,_,half),offset in zip(fields,offsets): s[name]+=half*offset
            s['equity']=s['machine_book']+s['building_book']+s['ar']+s['cash']-s['ap']-s['long_debt']
            a=accounts(s,decision,inp['demand'],inp['efficiency'],p)
            # The propagation is affine only inside this first-shift, firing, loss, no-short-debt branch.
            assert a['production']['production']<a['capacity']/3 and a['production']['firing']>0
            assert a['production']['production']>inp['demand'][0] and a['production']['production']<sum(inp['demand'])
            assert a['pretax']<0 and a['tax']==0 and a['fully_computed_in_scope']
            return {(table,label):v for table,vals in statement_values(s,a).items() for label,v in vals.items()}
        center=evaluate([0]*len(fields)); effects=[]
        for i in range(len(fields)):
            plus=[0]*len(fields);plus[i]=1
            minus=[0]*len(fields);minus[i]=-1
            hi,lo=evaluate(plus),evaluate(minus)
            assert max(abs((hi[k]+lo[k])/2-center[k]) for k in center)<1e-6
            effects.append({k:(hi[k]-lo[k])/2 for k in center})
        bounds={k:sum(abs(e[k]) for e in effects) for k in center}
        for offsets in product([-1,1],repeat=len(fields)):
            values=evaluate(offsets)
            for k,v in values.items():
                expected=center[k]+sum(e[k]*offset for e,offset in zip(effects,offsets))
                maximum_error=max(maximum_error,abs(v-expected))
                assert abs(v-expected)<1e-6 and abs(v-center[k])<=bounds[k]+1e-6
        for r in reference['records']:
            if r['case']!=case: continue
            table='balance' if r['source']['file'].endswith('_balance.json') else 'cashflow'
            k=(table,r['metric']);half=bounds[k]
            assert abs(center[k]-r['predicted'])<1e-9
            target=[r['actual']-.5,r['actual']+.5];interval=[center[k]-half,center[k]+half]
            records.append(dict(r,predicted_interval=interval,target_interval=target,
                intervals_overlap=interval[0]<=target[1] and target[0]<=interval[1],
                contributions={name:abs(e[k]) for (name,_,_,_),e in zip(fields,effects)}))
    return dict(status='CONDITIONAL_ROUNDING_DIAGNOSTIC_NOT_MECHANISM_VALIDATION',records=records,input_intervals=inputs,
        parameters=parameter_sources(),checks=dict(corner_cases=512,affine_max_error=maximum_error,
            comparisons=len(records),interval_overlaps=sum(r['intervals_overlap'] for r in records)),
        live_mutations=0,html_changes=0,gate_passed=False,
        assumptions=['整数金额显示为最近整数±0.5千美元；两位小数数量为±0.005千单位，显示舍入规则尚未独立证明',
            '当前玩家输入需求/效率/利率及官方参数固定；经验材料差额、厂房800、折旧率和周转天数也固定',
            '期初权益从会计恒等式推导；未额外施加其显示区间，独立输入盒范围为保守外包络',
            '仅当前两个历史预算点的一班、正解聘、亏损无税、无短贷分支；不延伸跨期'],
        limitations=['区间相交只说明在所列条件舍入范围下不能排除；不能证明隐藏机制、唯一校准或真实概率',
            '经验参数及未识别分支误差没有包含；正式需求、独立低运营投入及完整无并发预算验证仍缺'])


def main():
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out=ROOT/'output/model_v2'/(stamp+'_rounding_review');out.mkdir()
    result=review();write(out/'review.json',result)
    with (out/'records.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['records'][0]));writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in result['records'])
    snapshot=out/'code_snapshot';snapshot.mkdir()
    for name in ['rounding_review.py','supplement.py','finance.py','core.py','live_review.py']:
        shutil.copy2(Path(__file__).parent/name,snapshot/name)
    sources={'分步模型拟合与验证.json','结构化模型输入.json','raw/initial0_printable.json',
        *[r['source']['file'] for r in result['records']]}
    write(out/'manifest.json',dict(input_hashes={s:digest(ROOT/s) for s in sources},
        code_hashes={p.name:digest(p) for p in snapshot.iterdir()},live_mutations=0,html_changes=0))
    (out/'conclusions.md').write_text('# 财务舍入传播补查\n\n34项三表参考按来源显示精度传播期初量的舍入区间。'+
        f"512个端点组合核验通过，仿射最大误差{result['checks']['affine_max_error']:.3g}千美元；"+
        f"{result['checks']['interval_overlaps']}/34项与目标显示区间相交。\n\n"+
        '\n'.join('- '+s for s in result['assumptions']+result['limitations'])+'\n\n未操作比赛页面、未修改HTML，独立预算机制验收仍未通过。\n',encoding='utf-8')
    print(out);print(result['checks'])


if __name__=='__main__': main()
