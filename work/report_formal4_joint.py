"""Render audited joint scenarios without claiming unsupported inputs were optimized."""
import csv
import hashlib
import json
import math
import re
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/Path((ROOT/'work/formal4_all_active.txt').read_text(encoding='utf-8'))
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    result=read(OUT/'joint_result.json');inputs=read(OUT/'inputs.json');stress=read(OUT/'stress_2000.json')
    fields=inputs['original_fields'];plans=result['comparisons'][:2];countries=['泰国','印尼']
    units={};decisions=[];tenders=[]
    for plan in plans:
        v=plan['x'];p4=plan['evaluations'][0]['periods'][0];p5=plan['evaluations'][0]['periods'][1]
        updates={9:v[0],10:v[1],13:v[2],14:v[3],18:v[4],19:v[5],21:v[6],22:v[7],25:v[8],26:v[9],29:v[10],30:v[11],
                 51:v[12],52:v[13],49:v[14],46:v[15],47:20*v[16],42:v[17],43:v[18],54:100*v[19],
                 58:round(p4['demand'][0][0],2),59:round(p4['demand'][0][1],2),61:round(p4['demand'][1][0],2),62:round(p4['demand'][1][1],2),
                 65:-17.5,66:-17.5,68:5.,69:5.,72:0.,73:5.,76:round(p4['efficiency'][0],6),77:round(p4['efficiency'][1],6),79:round(p4['rate']*100,2)}
        for j in range(2):
            net=[v[2*j]-[30,.5][j],v[2*j+1]-[90,2][j]]
            for k,i in enumerate(([34,35] if j==0 else [37,38])):updates[i]='第一' if net[k]>=net[1-k] else '第二'
        for x in fields:
            i=int(x['source_row']);s=updates.get(i,x['PYT_value'])
            if i in [11,15,27,31,41]:status='机制缺失／未求解';reason='保留当前值；未识别分包成本或投标中标函数，不能标为优化完成'
            elif i in [34,35,37,38]:status='由边际贡献推导';reason='售价减运输费确定优先级'
            elif i in [58,59,61,62,76,77,79]:status='模型预估';reason='正式4曲线条件情景输出；预算输入不是真实结果'
            elif i in [65,66,68,69,72,73]:status='外生情景';reason='当期前景中值／正式5显式假设，增长预估不是可操纵的行业增长'
            else:status='参与联合搜索';reason='中性累计收益或不利累计收益目标；受曲线、投资、现金与代理范围约束'
            unit='美元/单位' if x['section']=='每单位价格' else '千美元' if any(w in x['section'] for w in ['营销','研发','运营','财务决策']) else '千单位/人' if '效率' in x['section'] else '千单位' if '千单位' in x['section'] else '%' if '%' in x['section'] or i==79 else '选择'
            if i==41:unit='选择'
            try:changed=not math.isclose(float(s),float(x['PYT_value'].replace('\xa0','').replace(' ','')),abs_tol=1e-9)
            except ValueError:changed=str(s)!=x['PYT_value']
            decisions.append(dict(plan=plan['name'],key=x['key'],source_row=i,section=x['section'],product_or_location=x['subsection'],label=x['label'],unit=unit,current=x['PYT_value'],suggested=s,changed=changed,status=status,reason=reason))
        # Conditional award floors include retail displacement; no award probability or bid optimum is invented.
        for j,quantity in enumerate([3.,200.]):
            cap=p5['capacity'][j];eff=p5['efficiency'][j];opening=p4['closing_inventory'][j]
            demand=p5['demand'][j];price=v[2*j:2*j+2];freight=([30.,90.] if j==0 else [.5,2.]);mat=[1054.4433828854374,14.219685952996382][j]
            retained=p4['workers'][j]*.9
            def contribution(q,order):
                available=opening+q-order
                if available < -1e-8:return None
                sold=[0.,0.]
                for k in sorted(range(2),key=lambda k:price[k]-freight[k],reverse=True):
                    sold[k]=min(demand[k],max(available,0));available-=sold[k]
                payroll=(min(q,cap/3)+1.65*min(max(q-cap/3,0),cap/3)+2.56*max(q-2*cap/3,0))*33/eff
                severance=max(retained-q/eff,0)*33*.35
                return sum(sold[k]*(price[k]-freight[k]) for k in range(2))-q*mat-payroll-severance-.6*max(available,0)
            before=contribution(p5['production'][j],0)
            qmin=max(0,quantity-opening)
            points=[qmin,cap,cap/3,2*cap/3,retained*eff,p5['production'][j],quantity+sum(demand)-opening]
            points += [quantity+d-opening for d in demand]
            feasible=[(contribution(q,quantity),q) for q in points if qmin<=q<=cap]
            if feasible:
                zero_bid_contribution,needed_q=max(feasible)
                floor=(before-zero_bid_contribution)/quantity
            else:floor,needed_q=None,None
            tenders.append(dict(plan=plan['name'],product=['复合梁','连接件'][j],award_quantity=quantity,
                fixed_round5_capacity=cap,full_award_deliverable=bool(feasible),incremental_cash_contribution_break_even_bid=floor,
                round5_recourse_production=needed_q,status='CONDITIONAL_FULL_AWARD_FLOOR_NOT_OPTIMAL_BID',
                limitation='仅中性正式5生产支出与零售挤占比较；不含投标努力费、税、跨期库存价值或中标概率。假设中标后可调整正式5产量，未承诺原生产配比不变。'))
    assert len(decisions)==84 and all(len({x['key'] for x in decisions if x['plan']==p['name']})==42 for p in plans)
    assert all(e['max_balance_error']<1e-6 for p in result['comparisons'] for e in p['evaluations'])
    for p in plans:
        for e in p['evaluations']:
            opening=[0.,0.]
            for period in e['periods']:
                for j in range(2):
                    assert abs(opening[j]+period['production'][j]-sum(period['sales'][j])-period['closing_inventory'][j])<1e-6
                    assert all(period['sales'][j][k]<=period['demand'][j][k]+1e-9 for k in range(2))
                opening=period['closing_inventory']
    with (OUT/'decisions.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(decisions[0]));w.writeheader();w.writerows(decisions)
    (OUT/'decisions.json').write_text(json.dumps(decisions,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'tender_thresholds.json').write_text(json.dumps(tenders,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 正式4全项联合情景比较（t4v1a基础，正式4曲线）','', '不要输出真名，姓名统一用首字母替代。','',
        '**20个可计算决策变量已联合搜索，另推导4项物流优先级；5项机制缺失的输入未求得最优，不能宣称全部优化完成。** 两套候选均为研究情景，未经平台预算或独立前向验证，未填写或提交。',
        '', '## 建议如何使用结果','',
        '中性收益优先方案在本次三种响应假设的较低累计收益上较好，但营销集中、扩产及库存显著，需要新增贷款。不利收益优先方案降低投入并还贷，但大量营销接近零，位于训练支持范围以外。这两套方案均不具备直接称为正式最优推荐的依据；新增贷款、集中营销或清零营销都依赖未识别机制。',
        '与上一版不同，本次把四国别售价、八项营销、两项研发、运营、两项机器投资、两项产能分配、长期贷款变化放入同一次搜索。预估字段由模型或外生情景产生，不当作增加真实需求、效率或降低真实利率的手段。',
        '', '## 曲线与搜索口径','',
        '- **所有新增研发、运营决策效果均使用正式4三条曲线。** 正式3冻结需求份额仅作基准锚点；不使用正式3曲线给新增研发或运营支出计算响应。',
        '- 主情景把当期支出视作正式4有效横轴；另测冻结ρ加上期投入的横轴情景。两者都是未核实映射，已配对上期投入不代表必须再加历史作用。',
        '- 正式4研发有效横轴为0—2000千美元、运营为0—1296千美元；搜索及三期前推均在曲线范围内。曲线是乘数，效率以当前0.17/16.77为锚点乘正式4曲线比值，技术尺度迁移仍未验证。',
        '- 六回合目标只比较正式4—6新增收益；此前已实现收益是共同基准。这里只优化正式4输入，正式5/6采用同价、同名义投入和同产能分配的固定政策，机器及贷款变化只发生正式4；未来滚动控制没有求解，不能称完整4—6最优策略。',
        '- 未知正式5/6曲线明确假设沿用正式4；中性复合梁行业后续增长0%、连接件每期5%，不利后续分别−15%和0%；它们不是已公布前景。',
        '- 新机器按指南本期立即可用；复合梁0—20千单位（步长1）、连接件0—400千单位（步长20）来自归档控件。产能后续衰减15%。',
        '- 中性目标取三种响应假设累计情景利润的较低值，同时要求联合不利现金达标；另以联合不利收益为目标搜索。每目标两随机种子；收敛容差为相对0.1%加绝对2.5千美元，不能解释为全局最优证明。',
        '', '## 完整输入表（42项，按平台列表顺序）','',
        '| 产品/地区 | 项目 | 单位 | 归档当前 | 中性收益优先 | 不利收益优先 | 调整（中性/不利） | 处理状态 |',
        '|---|---|---|---:|---:|---:|---|---|']
    for a,b in zip(decisions[:42],decisions[42:]):
        fmt=lambda z:f'{z:g}' if isinstance(z,(int,float)) else str(z)
        lines.append(f'| {a["product_or_location"]} | {a["section"]} / {a["label"]} | {a["unit"]} | {a["current"]} | {fmt(a["suggested"])} | {fmt(b["suggested"])} | {"是" if a["changed"] else "否"}/{"是" if b["changed"] else "否"} | {a["status"]} |')
    lines+=['','完整逐字段理由、唯一键和来源行见[CSV](decisions.csv)及[JSON](decisions.json)。归档当前值未实时回读；下一回合增长预估0%/5%是本次显式情景，替换原玩家7.5%/4%不代表得到正式5前景。',
        '', '## 情景结果（金额：千美元）','',
        '**下表是未核实机制下的情景利润，不是平台预算、已实现利润或可用于正式累计排名的完整预测。** 税亏、周转、厂房、计息与库存计价均有假设。',
        '', '| 方案 | 国别响应中性4—6利润 | 合计代理中性4—6利润 | 联合不利4—6利润 | 联合不利最低现金 |','|---|---:|---:|---:|---:|']
    for p in result['comparisons']:
        e=p['evaluations'];lines.append(f'| {p["name"]} | {e[0]["scenario_profit_4_to_6"]:.2f} | {e[1]["scenario_profit_4_to_6"]:.2f} | {e[3]["scenario_profit_4_to_6"]:.2f} | {e[3]["minimum_cash"]:.2f} |')
    lines+=['','所有方案在联合不利中仍可能出现累计亏损。现金约束采用2050千美元，含官方最低2000之外50千美元的取整缓冲；基准出现不足时只标记失败，不自动补造短贷。',
        '', '| 方案 | 正式4情景利润 | 复合梁产量 | 连接件产量 | 连接件期末库存 | 正式6期末库存 |','|---|---:|---:|---:|---:|---:|']
    for p in plans:
        a=p['evaluations'][0]['periods'][0];b=p['evaluations'][0]['periods'][2]
        lines.append(f'| {p["name"]} | {a["profit"]:.2f} | {a["production"][0]:.3f} | {a["production"][1]:.3f} | {a["closing_inventory"][1]:.3f} | {b["closing_inventory"][1]:.3f} |')
    lines+=['','产量与库存为千单位。库存以加权平均生产成本结转；终局库存保留账面状态，不人为变现或加终值奖励。未售成本资本化可能使情景利润和现金表现分离，不能把库存账面利润当已收现金。',
        '', '## 投标与分包：尚未求解的5项输入','',
        '两项大客户报价、两项大客户设计师营销及分包选择没有可靠的中标函数或成本机制，保留当前0/关闭并明确未优化。招标数量为复合梁3、连接件200千单位；中标后下回合优先交付，10%当期预收、90%交付收款。没有把机会记为中标，也未为未中标合同虚构收入。',
        '', '| 方案 | 产品 | 全额中标量（千单位） | 固定正式5容量内可交付 | 中性增量生产现金贡献报价门槛（美元/单位） |','|---|---|---:|---|---:|']
    for a in tenders:
        floor='无法求值' if a['incremental_cash_contribution_break_even_bid'] is None else f'{a["incremental_cash_contribution_break_even_bid"]:.2f}'
        lines.append(f'| {a["plan"]} | {a["product"]} | {a["award_quantity"]:g} | {"是，需重排正式5产量" if a["full_award_deliverable"] else "否，需新增产能"} | {floor} |')
    lines+=['','报价门槛只比较中性正式5的生产支出及挤占零售收益，不含投标努力费、税和库存跨期价值；它不是最优投标价。高于门槛也不代表一定中标或值得投标。详见[门槛计算](tender_thresholds.json)。',
        '', '## 每方案2000组分层压力测试','',
        '固定种子20261014，覆盖营销口径、有效横轴映射、后续复合梁增长、工资增长、材料价格、对手售价、效率及应收天数。联合不利的对手营销+50%和利率+1个百分点另作确定性检查，未把较轻随机集合冒称涵盖全部组合。分位数和失败占比只描述该测试集合，不是真实概率或置信区间。',
        '', '| 方案 | 情景利润P5 | 中位数 | P95 | 样本最低现金 | 现金/模型范围失败占比 |','|---|---:|---:|---:|---:|---:|']
    for s in stress['summary']:
        q=s['profit_quantiles'];lines.append(f'| {s["name"]} | {q[0]:.2f} | {q[1]:.2f} | {q[2]:.2f} | {s["minimum_cash_min"]:.2f} | {s["scope_failure_fraction"]:.2%} |')
    lines+=['','## 当前问题与不足','',
        '1. t4v1a原接口明确禁止完整利润和收益排名；本次新增独立研究入口，没有解除该门槛，`remaining_profit_ranking=false`。',
        '2. 20变量参与搜索不等于29项经营输入全部已优化：5项缺机制，4项物流为派生排序；另外13项是模型预估或外生情景。',
        '3. 国别营销、产品研发响应没有99队真实分配支持；中性候选营销集中、保守候选接近零，均可能涉及联合策略外推。',
        '4. 机器本期可用得到指南支持，新增产能与厂房容量、自动厂房支出及完整时序仍未用实时试验核验。',
        '5. 仅搜索固定未来政策，没有优化正式5/6逐期的价格、投资、融资和中标后的履约再决策。',
        '6. 双种子收敛和数学守恒只验证数值实现，不验证响应因果性、实际利润或全局最优。',
        '', '## 因缺乏数据而无法验证的问题','',
        '- 正式4支出→有效横轴映射、完整研发运营与营销存量、其他团队真实国别产品投入。',
        '- 期初税亏、实际风险与计息时点、真实应收应付周转、厂房自动支出和库存计价。',
        '- 分包成本与生效方式、当前未披露合同、招标的获胜条件、分单及违约成本。',
        '- 正式5/6前景与响应曲线；正式4实时个人和小组值尚未读取，浏览器页面读取超时。',
        '', '历史20项问题编号与完整要求继续见[建模重审与验收要求](../../../建模重审与验收要求.md)，本报告不将其整体标为关闭。',
        '', '## 验证与复现','',
        '正式4曲线版本、基准需求锚定、批量/单点一致、三期数量守恒、情景财务恒等式、曲线范围、四次搜索收敛、42项唯一键覆盖通过。原始显示初值资产与负债权益相差1千美元，作为显示舍入残差单列结转，未改写原始余额。',
        '入口：[联合搜索代码](../../../code/model_v2/formal4_joint_scenarios.py)；运行使用 `work/formal4_all_active.txt` 指向新的独立空目录，输出以排他创建防止覆盖。报告生成：[report_formal4_joint.py](../../../work/report_formal4_joint.py)。',
        '', '[完整结果](joint_result.json) · [输入与正式4曲线](inputs.json) · [搜索领先候选](search_leaders.json) · [2000组压力明细](stress_2000.json)',
        '', '未进行实时预算回读、平台保存或提交。风险：上述候选依赖未识别映射和未来假设，不能宣称正式4或正式4—6完整最优。']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    sourcepaths=[ROOT/'code/model_v2/formal4_joint_scenarios.py',Path(__file__),ROOT/'output/t4v1a/20261014T175143627079+0800/models_full.json',ROOT/'output/t4v1a/20261014T175143627079+0800/example_request.json',ROOT/'output/t4v1a/20261014T175143627079+0800/inputs.json',ROOT/'sources/决策指南_逐页文本.txt',ROOT/'output/round_close/20261013_formal3_close/formal4_initial/raw/market5_formal4_productioninvestments.json']
    for p in sourcepaths[:2]:shutil.copyfile(p,OUT/p.name)
    (OUT/'source_hashes.json').write_text(json.dumps({str(p.relative_to(ROOT)):sha(p) for p in sourcepaths},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (OUT/'work_log.md').open('a',encoding='utf-8') as f:f.write('\n已完成：20变量双目标/双种子联合情景搜索、4物流派生、5缺机制项明确未求解、42项双候选完整输出及4方案各2000压力样本；全部新增响应使用正式4曲线，未知未来仅是假设。数量和附舍入残差的财务守恒通过，未伪称完整最优。\n')
    print('REPORT',OUT/'report.md')


if __name__=='__main__':main()
