"""Generate a source-bound conditional decision, without opening t2 migration gates."""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'work/python_packages'), str(ROOT / 'code')]
from build_model_inputs import production_and_delivery

OUT = ROOT / 'output/decisions/20261012T215703118082+0800'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def main():
    inputs = read(str((OUT / '已核验输入.json').relative_to(ROOT)))
    components = read('output/t2v0-um/20261012T181028387320+0800/components.json')
    curves = read('output/visible_coefficients/20261012_round2_json/coefficients.json')
    p = components['published']['financial_parameters']
    state = inputs['opening_state']
    unit = p['material_cost'] * (1 + components['material_unit_cost']['parameter'])
    capacity = state['capacity'] * (1-p['machine_capacity_decline'])
    # shortcut: demands and efficiency are archived player scenarios; replace with bound trained outputs when available.
    scenarios = []
    for scale in [0.7, 1, 1.1]:
        demand = [4.5*scale, 13.5*scale]
        for label, prices in [('基准', [1800, 2000]), ('提价候选', [2200, 2000])]:
            prod = production_and_delivery(capacity, 100, .17, demand, [0, 1],
                p['wage'], p['second_shift'], p['third_shift'], state['workers'], p['attrition'], p['severance'])
            revenue = sum(q*v for q,v in zip(prod['sales'],prices))
            materials = prod['production']*unit
            transport = sum(q*v for q,v in zip(prod['sales'],p['transport']))
            operating = revenue-materials-transport-prod['payroll']-prod['firing']-500-p['marketing_fixed']-p['overhead_fixed']-600-760
            assert abs(sum(prod['sales'])-prod['production']) < 1e-9
            scenarios.append(dict(label=label,demand_scale=scale,demand=demand,efficiency=.17,
                prices=prices,**prod,revenue=revenue,materials=materials,transport=transport,
                ebitda=operating,profit=None,closing_cash=None,
                kind='ASSUMED_PLAYER_DEMAND_EFFICIENCY_SCENARIO_NOT_FORECAST'))
    relative=[]
    rd=curves['curves']['rd']['parameters']; ops=curves['curves']['operations']['parameters']
    for spending in [600,650,875]:
        x=spending+.5*state['previous_rd']
        relative.append(dict(kind='rd',spending=spending,effective_input=x,multiplier=rd[0]+rd[1]*(x+rd[2])**rd[3]))
    for spending in [600,760,1000]:
        x=spending+.5*state['previous_operations']
        relative.append(dict(kind='operations',spending=spending,effective_input=x,multiplier=ops[0]+ops[1]*x/(ops[2]+x)))
    decisions=[
        ('泰国价格',1800,2200,'美元/单位','条件候选；需提价后需求核验，942是固定手填需求预算'),
        ('印尼价格',2000,2000,'美元/单位','无有效当期价格响应样本，保留归档值'),
        ('泰国一般营销',100,100,'千美元','当期边际需求收益未识别，保留'),
        ('印尼一般营销',200,200,'千美元','当期边际需求收益未识别，保留'),
        ('泰国设计师营销',100,100,'千美元','当期边际需求收益未识别，保留'),
        ('印尼设计师营销',100,100,'千美元','当期边际需求收益未识别，保留'),
        ('研发',600,600,'千美元','使用正式2曲线；曲线收益未转化成需求或剩余五回合利润'),
        ('运营改进',760,760,'千美元','使用正式2曲线；效率尺度尚未训练，不据乘数直接填写效率'),
        ('产能分配',100,100,'%','若需求仍为18，衰减后产能15.3全部使用；需求下降时重算'),
        ('新增机器',0,0,'千单位','暂缓；18需求情景缺2.7产能，采购前核验需求及投资生效时点'),
        ('长期贷款变化',0,0,'千美元','期初现金16372，期末现金未算完整，不据期初现金决定还贷'),
        ('泰国物流优先级','第一','第一','顺序','2200−30高于2000−120，供给不足先满足较高单位净收入'),
        ('印尼物流优先级','第二','第二','顺序','与泰国顺序配对'),
        ('大客户报价',0,0,'美元/单位','暂不投标；当期公告2千单位、下一回合交付，条款未完整核验'),
        ('需求预估：泰国',4.5,None,'千单位','4.5是玩家输入；没有t2v0-um已训练需求模型，不生成推荐预测'),
        ('需求预估：印尼',13.5,None,'千单位','13.5是玩家输入；没有t2v0-um已训练需求模型，不生成推荐预测'),
        ('生产效率预估',.17,None,'千单位/人','0.17是玩家输入；曲线乘数不能替代效率尺度'),
        ('长期贷款利率预估',3,None,'%','t2v0-um需预测期末权益/资产联立，无法用基准2.5或玩家3冒充')]
    assert components['whole_model_trained'] is False
    assert components['formal2_prediction_enabled'] is False
    assert state['tax_loss'] is None and abs(capacity-15.3)<1e-10
    assert abs(unit-1054.457956)<.000001
    result=dict(status='CONDITIONAL_DECISION_DRAFT_FULL_FORECAST_UNAVAILABLE',phase='formal',round=2,
        market_id=5,person='PYT',components='t2v0-um/20261012T181028387320+0800',
        curves='formal2/20261012_round2_json',migration_gate_overridden=False,
        unit_material_cost=unit,capacity_after_decline=capacity,scenarios=scenarios,curve_diagnostics=relative,
        carry_assumption=.5,carry_status='t2v0-um historical approximation, not independently identified',
        decisions=[dict(item=a,archived=b,candidate=c,unit=d,reason=e) for a,b,c,d,e in decisions],
        sources=inputs['sources'],unresolved=['t2v0-um demand coefficients and efficiency scale not trained',
        'formal2 curve previous-investment binding incomplete','current round and personal inputs not live verified',
        'tax loss and complete financial branches unknown','no six-round joint optimization'])
    (OUT/'decision.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'决策表.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['决策项','归档基准','条件建议','单位','依据']); w.writerows(decisions)
    lines=['# 正式2条件决策草案','',
        '市场5、PYT。使用正式2研发/运营曲线，其余按最新t2v0-um版本。不要输出真名，姓名统一用首字母替代。',
        '', '**建议：泰国价格2200、印尼2000；四项营销100/200/100/100；研发600、运营760；产能分配100%；新增机器0、贷款变化0；泰国先交付。**',
        '', '这是一份可审阅的条件方案。t2v0-um没有训练好的需求系数和效率尺度，正式2完整预测仍关闭。需求、效率和贷款利率预估栏留空，不能把旧模型补入后称为t2v0-um结果。',
        '', '归档个人基准预算−479千美元；泰国2200试验预算942千美元，均依赖同一手填需求4.5/13.5和效率0.17，不能当作实际利润。3000试填缺保存回读，排除。',
        '', '| 决策项 | 归档值 | 条件建议 | 单位 | 依据 |','|---|---:|---:|---|---|']
    lines += [f'| {a} | {b} | {c if c is not None else "待计算"} | {d} | {e} |' for a,b,c,d,e in decisions]
    lines += ['', '正式1实际结转：现金16372、长期贷款15200、机器产能18千单位、上期研发650和运营760。正式2公布材料价1053、基准利率2.5%、最低现金2000。材料参考值1054.457956美元/单位来自t2v0-um练习2组件；迁移未验收，作为条件成本。',
        '', '产能按t2v0-um公式为18×0.85=15.3千单位。手填总需求18千单位情景下短缺2.7；若确认真实需求、投资立即生效且现金可行，再比较新增2.7千单位（条件购置额270千美元），当前不把该情景当已确认投资建议。',
        '', '| 需求情景 | 方案 | 泰国交付 | 印尼交付 | EBITDA，千美元 |','|---|---|---:|---:|---:|']
    lines += [f'| 手填需求×{r["demand_scale"]} | {r["label"]} | {r["sales"][0]:.3f} | {r["sales"][1]:.3f} | {r["ebitda"]:.2f} |' for r in scenarios]
    lines += ['', '上述仅为经营情景：收入−材料−运费−工资−解聘−营销及调研−行政−研发−运营。没有折旧、利息、税费与营运资金；EBITDA不能作为利润或可还贷现金。价格方案间保持同一需求只用于算术比较，未估计提价引起的销量变化。',
        '', '正式2曲线：研发a+b×(x+c)^d，运营a+b×x/(c+x)，参数及来源见decision.json引用的coefficients.json。有效投入暂按当期投入+0.5×上期实际投入计算，0.5是t2v0-um历史假设；乘数只作诊断，不是训练好的绝对需求/效率。',
        '', '剩余经营期为正式2至正式6。未来前景、投入延续收益及完整财务未识别，未宣称五回合累计利润最优。当前浏览器无Cesim页面，未实时核验回合、试验恢复或后续个人修改；未填写或提交平台。']
    (OUT/'决策报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert all(hashlib.sha256((ROOT/r['file']).read_bytes()).hexdigest()==r['sha256'] for r in inputs['sources'])
    with (OUT/'工作日志.md').open('a',encoding='utf-8') as f:
        f.write('\n用户澄清：需求与效率指正式2研发/运营曲线，其余采用t2v0-um；输入采用正式2已知数据。已生成决策表、条件生产情景和报告，未修改迁移门槛。已验收产能、材料单价、交付守恒及全部输入哈希不变。完整需求/效率/利润/现金预测未完成，输出明确留空。\n')
    print(OUT)


if __name__ == '__main__':
    main()
