"""Render all formal5 decisions, assumptions, and sensitivity into Markdown."""
import csv
import json
import math
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import solve_formal5_full as s
import numpy as np
from scipy.optimize import differential_evolution

OUT=s.OUT;ROOT=s.ROOT
fmt=lambda v:f'{v:,.4f}'.rstrip('0').rstrip('.') if isinstance(v,(int,float)) else str(v)


def main():
    m=s.ScenarioModel();result=s.read(OUT/'full_result.json');plans=result['comparisons'];cfgs=result['configs']
    sensitivities=s.read(OUT/'sensitivity_all_fields.json');searches=s.read(OUT/'searches.json')
    records=[]
    for plan in plans[1:]:
        x=plan['x'];p5=plan['evaluations'][0]['periods'][0]
        update={row:x[j]*(20 if row==47 else 100 if row==54 else 1) for j,row in enumerate(s.ROWS)}
        update.update({65:7.,66:-5.,68:7.,69:-5.,72:0.,73:0.,76:round(p5['efficiency'][0],6),77:round(p5['efficiency'][1],6),79:round(p5['rate']*100,2)})
        for j,rows in enumerate([[58,59],[61,62]]):
            for k,row in enumerate(rows):update[row]=round(p5['demand'][j][k],2)
        for j,rows in enumerate([[34,35],[37,38]]):
            for k,row in enumerate(rows):update[row]='第一' if p5['priority'][j]==k else '第二'
        for f in m.fields:
            row=f['row'];v=update.get(row,m.current[row])
            if row in s.ROWS:
                status='联合求解';reason='20个独立可控量共同搜索；两种物流顺序按净价推导；两随机种子、显示精度取整和离散扫描复核'
                if row in [9,10,13,14]:reason+='；正式3价格响应迁移、正式4本组需求锚定，正价历史范围约束'
                elif row in [18,19,21,22,25,26,29,30]:reason+='；存在前向营销响应，零值是范围内结果，非预先固定；国别真实响应未验证'
                elif row in [49,51,52]:reason+='；支出直接映射正式5曲线横轴，未再加历史存量'
                elif row in [46,47]:reason+='；当期容量立即增加，扩产也可减少高工资班次，计投资现金和折旧'
                elif row==42:reason='联合求解的需求驱动产能上限；收益平台内保留当前70%，不代表必产70%容量'
                elif row==43:reason+='；连接件自由生产，计期初202.40库存及下一期库存结转'
                elif row==54:reason+='；本金不记费用，只影响现金、债务、利息；三核心情景采样现金≥3000'
            elif row in [34,35,37,38]:status='联合推导';reason='每产品比较两国售价减运输费，优先净收益较高国家；物流切换另做敏感性'
            elif row in [11,15,27,31]:status='无可用新招标';reason='当期招标数量0，报价/投标营销控件禁用，保留0；非任意固定可用决策'
            elif row==41:status='不适用／机制未解';reason='当前FALSE，生产页未提供可用分包控件，不能虚构分包供给或成本；敏感性N/A'
            elif row in [65,66,68,69]:status='当期外生预估';reason='按t5v0b两产品泰国+7%／印尼−5%假设；不是可操作的实际市场增长'
            elif row in [72,73]:status='正式6情景预估';reason='正式6市场总量中性持平，±5%及−10%压力，不是已公布正式6前景'
            elif row in [58,59,61,62]:status='随方案重算';reason='价格/营销/RD前向响应与份额分母一致更新；需求不是交付，可能供给不足'
            elif row in [76,77]:status='随方案重算';reason='正式4实际q/n锚定，乘正式5运营曲线相对750投入的倍率；非任意效率旋钮'
            elif row==79:status='随财务状态推断';reason='正式5基准5%＋t5v0b风险加点；贷款变化后状态估计，计息时点另压力检验'
            else:raise AssertionError(row)
            records.append(dict(plan=plan['name'],key=f['key'],row=row,section=f['section'],product=f['product_or_location'],
                label=f['label'],unit=f['unit'],current=m.current[row],suggested=v,changed=v!=m.current[row],status=status,reason=reason))
    s.save('decisions.json',records)
    with (OUT/'decisions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    assert len(records)==84
    rows_by_plan=[{x['row']:x for x in records if x['plan']==p['name']} for p in plans[1:]]
    sections=[('需求／复合梁',[65,66,58,59]),('需求／连接件',[68,69,61,62]),
        ('生产／投资：下回合预估、两产品机器',[72,73,46,47]),('生产／计划：配比和效率',[41,42,43,76,77]),
        ('生产／计划：研发与运营',[51,52,49]),('销售／泰国：复合梁',[9,18,25]),
        ('销售／泰国：连接件',[13,21,29]),('销售／印尼：复合梁',[10,19,26]),
        ('销售／印尼：连接件',[14,22,30]),('销售／大客户：复合梁',[11,27]),('销售／大客户：连接件',[15,31]),
        ('物流／复合梁',[34,35]),('物流／连接件',[37,38]),('财务',[54,79])]
    allrows=[row for _,rr in sections for row in rr]
    assert len(allrows)==42 and set(allrows)==set(m.current)
    lines=['# 正式5全项联合决策与敏感性分析','',
        '不要输出真名，姓名统一用首字母替代。','',
        '**按用户最终要求保留价格与营销前向响应，全部实际可用决策一起求解。建议在本报告假设成立且预算复核后，优先考虑稳健利润候选。** 价格和营销没有固定，机器投资当回合立即生效，研发/运营支出全额直接映射最新曲线横轴。',
        '',
        '最新平台回合：市场5、正式5、PYT，截止2026-10-15 22:00（北京时间）；本次只读采集16:13—16:34，其中本人决策列表读取于16:13。本人42项与此前归档逐项一致，已保存最新列表、生产、投资、前景、融资、物流及三份预算证据。之后的网页变化不在本报告基准内。未修改、保存或提交平台决策。',
        '',
        '**解的范围：20个独立数值决策联合搜索＋2个物流选择推导，对应24个可用列表决策行（物流4行联动）；4项无新招标输入不适用，1项分包不可用／未求解；13项预估随方案重算，合计42行全部覆盖。** 因需求系数跨回合迁移、未来曲线和财务时点有假设，这属于条件联合候选，不能称已验证的全参数全局最优。',
        '',
        '## 完整建议：按页面顺序','',
        '中性候选最大化中性正式5—6情景税后利润，同时要求三核心情景现金可行；稳健候选最大化三核心情景的较低利润。两者都采用官方最低2000千美元之外1000千美元缓冲，即采样现金下限3000。研发、运营及营销的单位均为千美元，投资量为千单位。']
    for title,rr in sections:
        lines+=['',f'### {title}','','| 产品／国家／项目 | 单位 | 最新当前 | 中性候选 | 稳健候选（建议） | 稳健调整 | 状态及依据 |',
            '| --- | --- | ---: | ---: | ---: | --- | --- |']
        for row in rr:
            a,b=[d[row] for d in rows_by_plan]
            label='／'.join(v for v in [b['product'],b['label']] if v)
            lines.append(f'| {label} | {b["unit"]} | {fmt(b["current"])} | {fmt(a["suggested"])} | {fmt(b["suggested"])} | {"是" if b["changed"] else "否"} | {b["status"]}：{b["reason"]} |')
    lines+=['','[逐字段CSV](decisions.csv) · [唯一键与来源对应JSON](decisions.json)。物流两国两行对应同一个排序选择；分包只在列表存在，未发现可用控件，不当作已解决。预估按网页显示取整，计算使用未舍入数。',
        '','## 同期限、同基准的方案比较','',
        '**金额均为千美元，利润为本次推断财务链的条件税后利润，不是平台候选预算、已实现成绩或独立预测保证。** 正式4及以前收益作为共同常数，目标仅正式5—6；没有加入正式7、资产残值、库存变卖或债务清偿收益。',
        '','| 方案 | 中性5—6利润 | 较基准增量 | COUNTRY利润 | 联合不利利润 | 不利采样最低现金 | 长贷变化 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for p in plans:
        e=p['evaluations']
        lines.append(f'| {p["name"]} | {e[0]["profit_5_to_6"]:,.2f} | {e[0]["profit_5_to_6"]-plans[0]["evaluations"][0]["profit_5_to_6"]:,.2f} | {e[1]["profit_5_to_6"]:,.2f} | {e[2]["profit_5_to_6"]:,.2f} | {e[2]["sampled_minimum_cash"]:,.2f} | {100*p["x"][19]:,.0f} |')
    lines+=['','三核心情景为中性SHARE、国别COUNTRY、联合不利；稳健方案在它们之间取较低利润，不将15个扩展压力情景全部等权混为概率分布。基准在联合不利下出现现金不足，不补造自动短贷。',
        '','| 方案（中性情景） | 正式5利润 | 正式6利润 | 复合梁产量5 | 连接件产量5 | 连接件期末库存5 | 连接件未满足需求5 | 期末库存6 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for p in plans:
        y,z=p['evaluations'][0]['periods']
        unmet=sum(y['demand'][1])-sum(y['sales'][1])
        lines.append(f'| {p["name"]} | {y["profit"]:,.2f} | {z["profit"]:,.2f} | {y["production"][0]:.4f} | {y["production"][1]:.4f} | {y["closing_inventory"][1]:.4f} | {unmet:.4f} | {sum(z["closing_inventory"]):.4f} |')
    robust=plans[2];nominal=plans[1];eb=robust['evaluations'];ea=nominal['evaluations']
    lines+=['','### 推荐理由与代价','',
        f'稳健候选相对中性候选，牺牲中性两期情景利润{ea[0]["profit_5_to_6"]-eb[0]["profit_5_to_6"]:,.2f}千美元，把联合不利损失减少{eb[2]["profit_5_to_6"]-ea[2]["profit_5_to_6"]:,.2f}千美元。它降低研发、运营及部分营销支出，控制正式5连接件自由生产数量；这会在中性需求下留下缺货，而不是全面改善所有指标。',
        '','连接件机器投资400千单位虽然远高于净补产缺口，仍在本次模型内有价值：新增机器当期生效，使既定产量更多落在低工资班次，并支持正式6生产。机器投资不是当期费用全额扣除，计入的是现金支出和两期折旧；其终局账面价值没有当收益奖励。复合梁投资也主要通过班次成本和后续容量共同获益。',
        '','零营销建议来自本次迁移的国别边际回报；复合梁一般营销较弱、连接件一般营销较强，搜索因此集中投放。真实99队产品/国别投入缺失，集中投放和零值最依赖响应迁移，不应当成已经验证的经营规律。',
        '','## 每项决策敏感性','',
        '下面以建议的稳健方案为中心，每次只改一项、其余策略固定，列中性5—6利润变化（千美元）。价格±10%，营销/RD/运营±10%且至少50千美元，生产配比±5个百分点，投资按可选档位，贷款变化±10%且至少1000千美元；触及合法分析边界时截断。物流切换两国顺序。13项预估按外生/预测误差冲击分析，不把改填预估误称改变实际经营。',
        '','| 按页面顺序的字段 | 减少／另一选项及利润变化 | 增加／另一选项及利润变化 | 解释 |',
        '| --- | --- | --- | --- |']
    for row in allrows:
        f=next(x for x in m.fields if x['row']==row)
        sr=[x for x in sensitivities if x['plan']==robust['name'] and x['row']==row]
        cells=[]
        for z in sr:
            cells.append('N/A' if z['delta_profit_5_to_6'] is None else f'{fmt(z["test"])} → {z["delta_profit_5_to_6"]:+,.2f}'+('（现金约束失效）' if not z.get('feasible',True) else ''))
        if len(cells)==1:cells.append('—')
        explanation=sr[0]['category']
        label='／'.join(v for v in [f['section'],f['product_or_location'],f['label']] if v)
        lines.append(f'| {label} | {cells[0]} | {cells[1]} | {explanation} |')
    lines+=['','两套候选的完整敏感性：[CSV](sensitivity_all_fields.csv)、[JSON](sensitivity_all_fields.json)。两个机器投资和贷款的所有可选分析档位另有[中性扫描](neutral_discrete_frontier.json)与[稳健扫描](robust_discrete_frontier.json)；投资扫描按其余决策固定，不等于该档位下全面重优化。',
        '','### 全局假设敏感性','',
        '| 假设情景 | 基准5—6利润 | 中性候选 | 稳健候选 | 稳健采样最低现金 |',
        '| --- | ---: | ---: | ---: | ---: |']
    for i,c in enumerate(cfgs):
        values=[p['evaluations'][i] for p in plans]
        lines.append(f'| {c["name"]} | {values[0]["profit_5_to_6"]:,.2f} | {values[1]["profit_5_to_6"]:,.2f} | {values[2]["profit_5_to_6"]:,.2f} | {values[2]["sampled_minimum_cash"]:,.2f} |')
    lines+=['','## 模型、推断与假设','',
        '### 数据与曲线','',
        '- 最新42项本人输入逐项与归档对应；最新市场5正式5三条曲线各200点，完整categories和dataset逐项与原件一致，600个有效点没有变化。原始脚本和SVG保存在latest目录；未重复采集快速教程。采用正式5曲线拟合参数，研发横轴0—2600、运营0—1620千美元，不外推。',
        '- 用户最终口径：价格营销均纳入前向响应，不固定；机器投资当期立即生效；研发/运营支出全额直接作为横轴，不再把上期投入重复加一次。t5v0b国别行业变化仍为两产品泰国+7%／印尼−5%。这些分析假设独立保存，未覆盖冻结注册表。',
        '- 修正上一份局部报告的运费：正式5复合梁泰国→印尼是120美元/单位，上一份局部搜索误沿用90美元。本次使用最新公布120，重新计算物流、利润和敏感性。',
        '','### 价格、营销、研发→需求','',
        '正式4本组各国真实需求除以相应市场总需求，作为锚定份额s₀。设自身相对吸引力变化为Δ，则`s = s₀·exp(Δ) / [(1−s₀)·R + s₀·exp(Δ)]`，`需求 = s × 正式5市场总量`。R中性为1，不利为1.25，代表其余竞争者合计吸引力的显式冲击；没有伪造99队最终输入。',
        '','Δ使用正式3已训练SHARE或COUNTRY系数：国别价格对数变化、一般/设计师营销`ln[(1000+新投入)/(1000+旧投入)]`，以及正式5研发曲线相对900/1300投入的乘数对数。复合梁保留历史1.5倍初始价的高价尾段；连接件主模型无尾段。需求重新归一化，不将销量当需求，也不把行业增长二次相乘。',
        '','正式3公司合计营销曾作为产品/国别代理，迁移到本次实际国别决策存在误差，因此另测营销系数减半和营销合计代理。正式4需求重训仍暂停；本次是受用户授权的条件推断，不写成已通过跨期验证的新训练模型。',
        '','### 运营、生产、库存→成本','',
        '- 效率以正式4实际产量/人员锚定，复合梁约0.170078、连接件约17.003984千单位/人，再乘`正式5运营曲线(新支出)/正式5运营曲线(750)`；不把运营乘数直接当绝对效率。',
        '- 当前零投资容量41.67/412.25，新增机器投资当期直接相加；正式6容量按15%衰减。两产品班次分别按容量三等分，工资倍数1/1.65/2.56，基础工资43.5千美元/人。总人员自然离职10%后与新总需求比较计35%解聘费，按产品计解聘另测。',
        '- 正式5库存0/202.40千单位；成本账面结转采用0/3516千美元。复合梁按需求驱动，连接件按配比自由生产；已读最新物流，当期大客户交付为0。先满足净价较高国，销量受需求和可用量双重约束。',
        '- 最新草稿预算的连接件期末库存1888、数量140.18与本期生产单位成本相容，采用期末库存按当期单位生产成本计价；加权平均另列压力。原材料主情景用t5v0b比例迁移，公布价和固定加价也测试；没有因本次利润目标再拟合材料系数。',
        '','### 预算与财务推断','',
        '- 最新现金流预算明确1月1日现金12202，资产负债表去年列再次与正式4实际对齐。期初机器7367、厂房12724、应收3361、应付1867、长贷10200、权益27102作为结转情景；资产构成和显示总额差−1千美元作为已记录舍入项，不拟合成经营收益。',
        '- 根据最新预算：全年应收约销售×30/365、应付约材料×30/365；厂房支出800由预算资本支出与厂房结转推断，厂房折旧7%，机器折旧15%；现金利息按期初/期末均值×1%。当前税费与29%且无可用税亏相容，主情景不补造税盾。',
        '- 长贷利率用正式5基准5%加t5v0b风险模型，给定贷款变化后的财务状态推断。主情景按期初/期末长债均值计息，另测按旧债、按期末债；本金变化只进现金和负债，不进利润。',
        '- 采样现金检查两个回合年末及各回合初投资/融资之后，不代表全年任意时刻流动性。官方下限2000，分析增加1000缓冲，所有候选在三核心情景这些采样点至少3000；未识别的自动短贷分支不补零或凭空融资。',
        '','### 正式6政策与期限','',
        '仅优化正式5当期可填控制量。正式6采用同价、同名义营销/RD/运营、无新增机器和无追加长贷变化；中性市场总量持平，三条正式5曲线暂延用为明确情景。正式6生产可观察需求后重排至可用产能，另测继续固定生产配比。没有声称求解正式6全部未来控制策略，更没有正式7收益。',
        '','### 搜索范围、边界与验收','',
        f'- 价格边界取正式4十市场100队实际正价范围：复合梁泰国{fmt(m.bounds[0][0])}—{fmt(m.bounds[0][1])}、印尼{fmt(m.bounds[1][0])}—{fmt(m.bounds[1][1])}；连接件泰国{fmt(m.bounds[2][0])}—{fmt(m.bounds[2][1])}、印尼{fmt(m.bounds[3][0])}—{fmt(m.bounds[3][1])}美元。停售0价剔除，禁止对数价格为0。这是历史支持分析域，不是平台强制上下限。',
        '- 一般营销合计分析上限2700、设计师合计3840千美元，复用原正式4联合研究的支出支持范围，不称平台规则；单项0至对应上限。研发两产品各0—2600、运营0—1620；机器投资0—20和0—400（步长20）；配比0—100%；贷款变化−10200至+10000（步长100）千美元。',
        '- 两目标各随机种子11/29，差分进化联合搜索全部20数值量；机器与长贷使用整数约束，随后按页面精度取整，逐坐标复查并完整扫描两项机器和贷款的可选档位。两国物流按当期净价排序是这个模型下的解析最优。收敛不构成非凸全局最优证明。',
        '- 研发到2600、机器到400、连接件一般营销到2700等边界项须作为约束敏感结果解读；增加投资或研发的上界不能凭现有曲线支持任意扩展。零营销是模型候选，响应误差可能改变推荐。',
        '','| 目标／种子 | 收敛 | 迭代 | 取整前目标值 |','| --- | --- | ---: | ---: |']
    for z in searches:lines.append(f'| {z["objective"]}／{z["seed"]} | {z["success"]} | {z["iterations"]} | {z["score"]:,.4f} |')
    replay=s.read(OUT/'budget_replay.json')
    lines+=['',f'最新整套草稿损益预算回放：平台本回合利润{replay["display_profit"]:,.0f}千美元，模型{replay["model"]["periods"][0]["profit"]:,.4f}，差{replay["error_kusd"]:+.4f}千美元；现金模型{replay["model"]["periods"][0]["cash"]:,.4f}，平台18097。误差为显示舍入量级，属于同草稿预算一致性检查，不能等同独立前向预测验证。',
        '',
        '所有方案各压力情景的数量守恒、销量上限和资产负债恒等式通过。源文件、曲线精确比对、字段唯一性与文件链接另有验收。本次原件来自只读访问，未在平台填入候选，也未用改填需求/效率美化预算。',
        '','## 交付与复现','',
        '[全部计算结果](full_result.json) · [逐字段敏感性](sensitivity_all_fields.csv) · [离散全档扫描](robust_discrete_frontier.json) · [输入及范围](input_manifest.json) · [预算复算](budget_replay.json) · [工作日志](work_log.md) · [来源哈希](source_hashes.json) · [验证](validation.json)',
        '',
        '代码：[联合求解](solve_formal5_full.py)、[报告生成](report_formal5_full.py)。使用项目Python3.12，源模型及历史档案仍由本项目相对路径引用；不能仅复制单份脚本离线独立运行。完整结果JSON保存两回合现金、利润、库存、供给、成本和约束，未把情景结果登记为实际成绩。']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    shutil.copy2(Path(__file__),OUT/Path(__file__).name)
    s.save('field_coverage.json',dict(fields=42,unique_fields=42,records=84,active_numeric_controls=20,
        derived_priority_controls=2,linked_logistics_rows=4,unavailable_tender_rows=4,subcontract_unavailable=1,estimates=13,
        sensitivity_per_candidate=len(set(x['key'] for x in sensitivities if x['plan']==robust['name']))))
    print('REPORT',str(OUT/'report.md'))


if __name__=='__main__':main()
