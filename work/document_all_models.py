"""Document saved models without importing or executing training code."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '模型说明'
OUT.mkdir(exist_ok=True)
CAT = ROOT / 'output/model_catalog/20261012T122718963696+0800/model_versions.json'
records = json.loads(CAT.read_text(encoding='utf-8'))
sources = {ROOT / r['source'] for r in records}
sources.update(ROOT.glob('output/interest_rate/*/model.json'))
sources.update(ROOT.glob('output/material_unit_cost/*/model.json'))
COMP = ROOT / 'output/t2v0-um/20261012T181028387320+0800/components.json'
sources.add(COMP)
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
component = json.loads(COMP.read_text(encoding='utf-8'))
unified_path = ROOT / 'output/unified-market/20261012T114145124558+0800/models.json'
unified = json.loads(unified_path.read_text(encoding='utf-8'))

def link(path, label):
    return f'[{label}]({Path(path).as_posix()})'

def table(headers, rows):
    def cell(v):
        return str(v).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows])

def v(symbol, meaning, unit, kind='可控决策；对手对应值为情景假设'):
    return (symbol, meaning, unit, kind)

spend = [v('P_i,c', '队伍i在国家c的售价', '美元/单位'),
         v('P0_i,c', '同队同国家的初始参考价格', '美元/单位', '已知历史基准；旧分步版按国别固定1800/2000'),
         v('G_i', '公司两国合计一般营销投入代理', '千美元'),
         v('H_i', '公司两国合计设计师营销投入代理', '千美元'),
         v('R_i,t', '当期研发投入', '千美元'),
         v('R_i,t−1', '上期实际研发投入', '千美元', '已实现历史输入')]
group = [v('J_m,h,t,c', '同编号市场m、阶段h、回合t、国家c的竞争队集合', '集合', '分组定位，不能跨市场归一化'),
         v('T̂_m,h,t,c', '外部给定的当期行业总需求', '千单位', '行业预测或显式情景；验证时实际总量须另标')]
share_out = [v('u_i,c', '模型内部相对吸引力得分', '无量纲', '中间计算输出'),
             v('ŝ_i,c', '预测公司需求份额', '0至1小数', '不确定模型输出'),
             v('D̂_i,c', '预测公司需求', '千单位', '不确定模型输出，非交付销量')]
share_formula = ['x_R=R_i,t+ρ_R R_i,t−1',
 'u_i,c=−e_c ln(P_i,c/P0_i,c)+b_G ln(1+G_i/σ_M)+b_H ln(1+H_i/σ_M)+b_R ln(f_R(x_R))',
 '分段版本：u_i,c再减k_c max(ln(P_i,c/(1.5P0_i,c)),0)',
 'ŝ_i,c=exp(u_i,c)/Σ_(j∈J) exp(u_j,c)；D̂_i,c=T̂_m,h,t,c ŝ_i,c']
coef = [('e_c', '国家c相对价格得分系数', '见本页逐版本系数', '训练参数'),
 ('b_G / b_H / b_R', '一般营销、设计师营销、研发特征得分系数', '见本页逐版本系数', '训练参数'),
 ('k_c', '高价区间追加惩罚系数，仅分段版存在', '非分段版不使用；分段版见beta末两列', '训练参数'),
 ('σ_M', '投入对数变换尺度', '1000千美元', '模型结构常数'),
 ('ρ_R', '上期研发延续代理权重', '旧A/B与unified-market为0.5；情境版按rho字段', '固定假设或候选选择值，按版本区分'),
 ('1.5', '分段价格阈值倍数', '1.5', '结构假设，仅分段版'),
 ('λ', '正则惩罚系数', '各版本penalty字段', '训练配置，不是预测作用参数')]
docs = []

def doc(code, name, formulas, inputs, outputs, params, scope, source, family=None, extra=''):
    docs.append(dict(code=code, name=name, formulas=formulas, inputs=inputs, outputs=outputs,
                     params=params, scope=scope, source=source, family=family, extra=extra))

doc('ABS', '绝对对数需求模型',
 ['D̂_i,c=exp(α_c−e_c ln(P_i,c/P0_i,c)+b_G ln(1+G_i/σ_M)+b_H ln(1+H_i/σ_M)+b_R z_R)',
  '原fit_demand版：z_R=ln(1+(R_i,t+ρ_R R_i,t−1)/σ_M)',
  '跨市场own_only版：z_R=ln(f_R(R_i,t+ρ_R R_i,t−1))'], spend,
 [v('D̂_i,c','本公司在国家c的绝对需求预测','千单位','不确定模型输出')],
 [('α_TH / α_ID','泰国/印尼对数需求截距','见coefficients或beta前两项','训练参数')]+coef,
 '历史对照模型，不保证行业总量守恒。两种研发特征必须绑定各自源码和系数，不能互换。价格与曲线乘数必须为正。',
 ['code/fit_demand.py','code/cross_market_validation.py'], 'ABS',
 '七维向量顺序：α_TH、α_ID、e_TH、e_ID、b_G、b_H、b_R；价格消融/单国/标准化诊断须按原档特征定义使用。')
doc('SHARE','双国竞争份额模型',share_formula,spend+group,share_out,coef,
 '两国价格各自一列，三项投入系数联合训练；同一竞争组份额合计1。当前真实对手策略未知时使用情景。',
 ['code/cross_market_validation.py','code/model_v2/core.py'],'SHARE',
 '五维beta顺序：e_TH、e_ID、b_G、b_H、b_R；分段版七维再加k_TH、k_ID。scale只用于训练标准化，beta已还原时不可再除scale。')
doc('COUNTRY','国别独立竞争份额模型',share_formula,spend+group,share_out,coef,
 '每个国家单独训练四项作用系数。unified-market正式1版允许同期编号市场共享，属于用户假设；未获得正式2需求训练系数。',
 ['code/model_v2/country_demand.py','code/unified_market.py'],'COUNTRY',
 'coefficients命名字典：price=e_c、general_total_proxy=b_G、designer_total_proxy=b_H、rd_curve=b_R。底层beta仍为五列，另一国家价格列为0；它不是估计另一国家作用为0。')
doc('RD','研发需求乘数曲线',['x_R=max(R_t+ρ_R R_t−1,0)','f_R(x_R)=a_R+b_R,curve (x_R+c_R)^d_R'],
 [v('R_t','当期研发投入','千美元'),v('R_t−1','上期实际研发投入','千美元','历史实际输入'),v('x_R','直接调用曲线时的有效研发横轴','千美元','由投入代理计算；直接曲线接口只需此量')],
 [v('f_R','研发需求乘数','无量纲','网页曲线拟合输出，非公司需求')],
 [('a_R','曲线纵向偏移','parameters[0]','训练参数'),('b_R,curve','曲线幅度，与需求b_R不同','parameters[1]','训练参数'),('c_R','横轴偏移','parameters[2]，千美元','训练参数'),('d_R','幂指数','parameters[3]','训练参数'),('ρ_R','历史投入延续代理','调用需求模型的rho；不是曲线拟合系数','假设或选择值')],
 '曲线只对应其来源阶段/回合。正式2曲线不能自动替代练习2训练曲线；图形拟合误差不是实际需求误差。',
 ['code/fit_chart_json.py','code/stepwise_model.py'],'RD')
doc('OPS','运营效率乘数曲线',['x_O=max(O_t+ρ_O O_t−1,0)','f_O(x_O)=a_O+b_O,curve x_O/(c_O+x_O)'],
 [v('O_t','当期运营投入','千美元'),v('O_t−1','上期实际运营投入','千美元','历史实际输入'),v('x_O','直接调用曲线时的有效运营横轴','千美元','有效投入代理')],
 [v('f_O','运营效率乘数','无量纲','曲线拟合输出，尚未乘技术尺度')],
 [('a_O','零投入乘数','parameters[0]','训练参数'),('b_O,curve','饱和增量幅度','parameters[1]','训练参数'),('c_O','饱和投入尺度','parameters[2]，千美元','训练参数'),('ρ_O','运营延续权重','调用效率版本给定，见EFF','不是曲线自身参数')],
 '运营图纵轴是效率乘数；它不能直接当作千单位/人的生产效率。', ['code/fit_chart_json.py','code/stepwise_model.py'],'OPS')
doc('EFF','生产效率与运营延续模型',['η̂=θ f_O(O_t+ρ_O O_t−1)','训练实际效率：η_obs=q_actual/N_actual'],
 [v('O_t','当期运营投入','千美元'),v('O_t−1','上期实际运营投入','千美元','历史实际输入'),v('f_O','绑定回合的运营乘数函数','函数','已拟合曲线依赖')],
 [v('η̂','预测生产效率，即人均产量','千单位/人','不确定模型输出')],
 [('θ','技术生产尺度','theta / technology_scale / strategy_balanced_scale','训练参数，不同估计器不得合并'),('ρ_O','运营历史延续权重','按rho字段；unified-market正式1为0.562','假设或网格训练选择值')],
 '实际标签q/N。均值、策略等权均值、加权最小二乘各有保存版本；t2v0-um练习2效率尚未实际重训。',
 ['code/operations_rho.py','code/model_v2/finance.py'],'EFF')
for key, title, formula, inp in [
 ('RISK_POWER','杠杆幂函数风险溢价模型','π_r=a_r ((L+L_S)/E)^b_r',[v('L','期末长期贷款','千美元','历史实际或预测状态'),v('L_S','期末短期贷款','千美元','历史实际或预测状态'),v('E','期末权益','千美元','历史实际或预测状态')]),
 ('RISK_EXP','权益比指数风险溢价模型','π_r=a_r exp(−b_r E/A)',[v('E','期末权益','千美元','历史实际或预测状态'),v('A','期末资产总额','千美元','历史实际或预测状态')])]:
    doc(key,title,[formula,'r_L=r_base+π_r'],inp+[v('r_base','对应回合基准利率','小数','当期给定或明确假设')],
        [v('π_r','预测风险溢价','利率小数','不确定模型输出'),v('r_L','预测长期贷款利率','利率小数','不确定模型输出')],
        [('a_r','风险幅度','parameters[0]','训练参数'),('b_r','风险形状','parameters[1]','训练参数'),('r_base','基准利率','正式1归档0.03；练习2归档0.025','当期给定输入，不是训练系数')],
        '各候选单独拟合；条件验证使用实际期末财务状态，事前使用预测状态并联立。E>0，指数版另需A>0；独立利率接口还核对债务一致性及训练范围。',
        ['code/interest_rate_model.py','code/model_v2/finance.py'],key)
doc('MATERIAL','原材料单位差额校准',['v_eff=v+Δv','B=q v_eff'],
 [v('v','当期公布原材料基准单价','美元/单位','当期给定输入'),v('q','生产量','千单位','实际量或条件预测量')],
 [v('v_eff','校准后的原材料单位费用','美元/单位','经验模型输出'),v('B','原材料购买总费','千美元','给定产量的条件输出')],
 [('Δv','相对公布价的单位残差','uplift_usd_per_unit等字段；见版本表','训练校准，非官方加价')],
 '旧加法校准；正式1unified-market的差额为1.2422839506172636。新版比例模型单列，不将两个差额叠加。',
 ['code/unified_market.py','code/stepwise_model.py'],'MATERIAL')
doc('MATERIAL_PROP','原材料单位费用比例模型',['v_eff=v(1+α_v)','B=q v_eff',
 '候选published：α_v=0；候选additive：v_eff=v+Δv；已选比例版按上式'],
 [v('v','当期公布原材料单价','美元/单位','当期给定输入'),v('q','生产量','千单位','实际量或预测量')],
 [v('v_eff','预计原材料单位费用，对应unit_cost_usd','美元/单位','不确定模型输出'),v('B','材料购买总费，对应material_cost_kusd','千美元','条件计算输出')],
 [('α_v','比例调整系数','全300条版0.0013798365755954614；练习2专用版0.0013845739435914967','各自训练参数'),('v','练习2公布单价','1053','给定输入')],
 '全样本版训练练习1、练习2、正式1共300条；练习2专用版只训练100条，单一价位无法识别跨价格形状。两版独立保留，正式2实际验证未取得。',
 ['code/material_unit_cost_model.py','code/t2v0_um/calibrated.py'])
doc('INTEREST','实际贷款利率独立模型',['指数候选：r_L=r_base+a_r exp(−b_r E/A)',
 '幂候选：r_L=r_base+a_r ((L+L_S)/E)^b_r','r_S=r_L+Δr_S','百分数接口返回100 r_L、100 r_S'],
 [v('E / A / L / L_S','预测期末权益、资产、长贷、短贷','千美元','预测状态；回溯验证可给实际状态'),v('r_base','当期基准年利率','接口用百分数','当期给定'),v('Δr_S','公布短贷加点','接口用百分点','当期给定')],
 [v('r_L / r_S','长贷/短贷预测年利率','接口用百分数','不确定模型输出及规则加点'),v('I_r','长贷经验残差带','百分数上下界','条件残差范围，非置信区间')],
 [('a_r / b_r','风险幅度/形状','正式1选幂版[0.0020160670186389353,2.303289953297536]；练习2选指数版[0.12281068318353833,8.180868311208613]','独立训练参数'),('Δr_S','短贷加点','练习2为2个百分点，即内部0.02','给定规则'),('ε90','绝对条件误差90%分位','各版conditional_error_p90_basis_points','评价衍生值，非作用参数')],
 '正式1独立模型选中幂函数；练习2专用组件选中指数函数，不能据日期把两版当成同一训练集。接口拒绝超训练范围；残差带不包括期末状态预测误差。',
 ['code/interest_rate_model.py','code/t2v0_um/calibrated.py'])

doc('TOTAL','行业总需求与增长情景',['T_t,c=Σ_(i∈J) D_actual,i,t,c','g_T=T_t−1,c/T_t−2,c−1',
 'T̂_t,c=T_t−1,c²/T_t−2,c，或T̂_t,c=T_t−1,c(1+g_T)'],
 [v('D_actual,i,t,c','同市场同回合同国实际公司需求','千单位','已结算标签，用于历史总量汇总'),v('T_t−1,c / T_t−2,c','前两回合同口径行业实际需求','千单位','已实现历史输入'),v('g_T','给定未来行业增长情景','小数','显式假设输入；不得用当期期末值作为已知')],
 [v('T̂_t,c','预测行业总需求','千单位','外推或情景输出'),v('g_T','历史推导或未来设定增长率','小数','按使用方向区分输入与输出')],
 [('训练系数','独立行业回归尚未建成','无','非拟合计算'),('g_T','增长情景值','逐情景给定；练习2叙述5%至10%只是预期','假设输入')],
 '历史分母须为正。同市场实际需求汇总不能用销量、预算或玩家预测替代。', ['code/cross_market_validation.py'])
doc('BASELINE','等份额基线与实际总量诊断',['ŝ_i=1/n_J；D̂_i=T̂_c/n_J','诊断：D̂_i,oracle=T_actual,c ŝ_i'],
 [v('n_J','同组竞争团队数','个','组集合计算值，完整十队组为10'),v('T̂_c / T_actual,c','情景行业规模/事后实际总量','千单位','前者情景；后者验证标签'),v('ŝ_i','竞争模型给出的份额，oracle分支使用','小数','上游模型输出')],
 [v('ŝ_i','等份额基线','小数','基线输出'),v('D̂_i / D̂_i,oracle','基线需求/实际总量条件需求','千单位','情景输出/事后诊断')],
 [('训练系数','不拟合','无','基线计算'),('n_J','完整组团队数','10；实现按实际组大小读取','分组输入')],
 'oracle使用未来实际总量，只能诊断份额，不能当事前需求预测成绩。', ['code/cross_market_validation.py'])
doc('CAPACITY','产能产量与交付模型',['C=(1−δ_C)C0+I；K_M=p_I I','q=min(C a/100,Σ_c D̂_c)',
 '按π依次：S_c=min(D̂_c,Q_rem)；Q_rem←Q_rem−S_c；初始Q_rem=q',
 '一般库存守恒：Inv_end=Inv0+q−Σ_c S_c−Q_order；旧实现仅覆盖Inv0=Q_order=0'],
 [v('C0','期初机器产能','千单位','已知期初状态'),v('I','投资新增产能','千单位'),v('a','产能分配比例','百分数0至100'),v('D̂_c','各国家需求','千单位','上游预测'),v('π','各国家交付先后顺序','排列','可控决策'),v('Inv0 / Q_order','期初库存/订单交付量','千单位','仅守恒解释；旧实现要求零')],
 [v('C','当期可用产能','千单位','条件计算'),v('K_M','机器投资金额','千美元','条件计算'),v('q / S_c','生产量/各国可交付销量','千单位','条件计算'),v('Inv_end','期末库存','千单位','旧范围为0')],
 [('δ_C','产能下降率','0.15','归档场景给定'),('p_I','机器单位投资金额','100千美元/千单位','归档场景给定'),('100','分配百分数转小数','100','单位换算')],
 '需求驱动、零期初库存、零大客户。投资当回合生效按已核场景。一般库存式未表示程序已覆盖非零库存。', ['code/build_model_inputs.py','code/model_v2/finance.py'])
doc('LABOR','用工班次工资与解聘模型',['q1=min(q,C/3)；q2=min(max(q−C/3,0),C/3)；q3=max(q−2C/3,0)',
 'N=q/η̂；W=(q1+κ2 q2+κ3 q3)w/η̂；F=max((1−δ_N)N0−N,0)wσ_F'],
 [v('q / C','生产量/产能','千单位','上游条件计算'),v('η̂','生产效率','千单位/人','上游模型预测'),v('N0','期初生产员工人数','人','已知期初状态')],
 [v('q1 / q2 / q3','第一/第二/第三班产量','千单位','条件计算'),v('N','所需人数','人','连续人数近似'),v('W / F','生产工资/解聘费用','千美元','条件计算')],
 [('w','基础人均工资','28千美元/人','当期归档给定'),('κ2 / κ3','第二/第三班工资乘数','1.65 / 2.56','当期归档给定'),('δ_N','自然离职率','0.10','当期归档给定'),('σ_F','解聘补偿工资比例','0.35','当期归档给定'),('3','班次数量','3','实现结构')],
 'η̂>0，q≤C；不包含整数人员排班优化。以上数值绑定所列归档，不自动用于未来回合。', ['code/build_model_inputs.py'])
doc('OPERATING','收入成本与经营利润模型',['V=Σ_c P_c S_c；Z=Σ_c k_c S_c；B=q v_eff',
 'M=G+H+M0；H_O=H0+F+R+O','EBITDA=V−B−W−Z−M−H_O',
 'Dep_M=d_M(Book_M0+K_M)；Dep_B=d_B Book_B0；EBIT=EBITDA−Dep_M−Dep_B'],
 [v('P_c / S_c','售价/交付销量','美元/单位；千单位','决策/上游交付计算'),v('q / v_eff','产量/材料单位费用','千单位；美元/单位','上游计算/校准'),v('G / H / R / O','一般营销/设计师营销/研发/运营投入','千美元'),v('W / F','工资/解聘费','千美元','上游计算'),v('Book_M0 / Book_B0','期初机器/厂房账面资产','千美元','已知期初状态'),v('K_M','当期机器投资额','千美元','上游投资计算')],
 [v('V / B / Z / M / H_O','收入/材料/运输/营销/其他经营费','千美元','条件计算'),v('Dep_M / Dep_B','机器/厂房折旧','千美元','条件计算'),v('EBITDA / EBIT','折旧前经营利润/息税前利润','千美元','条件计算')],
 [('k_TH / k_ID','泰国/印尼运输单价','30 / 120美元/单位','当期归档给定'),('M0 / H0','固定市场调研/管理费','50 / 4000千美元','当期归档给定'),('d_M / d_B','机器/厂房折旧率','0.15 / 0.07','前者给定；后者旧经验关系'),('v_eff','材料单位费用','由MATERIAL或MATERIAL_PROP单一版本给定','模型输出，避免重复加价')],
 '价格乘交付销量，不乘潜在需求。千单位×美元/单位=千美元。厂房折旧时序和参数仍为旧条件假设。', ['code/model_v2/finance.py'])
doc('FINANCE','利息税利润现金与资产负债联立模型',
 ['L=L0+ΔL；J_L=(L0+L)r_L/2；AR=V d_AR/365；AP=B d_AP/365',
 'Cash_pre=Cash0+EBITDA−J_L+(AR0−AR)+(AP−AP0)−K_M−K_B+ΔL',
 'J_C=max((Cash0+Cash)/2,0)r_C；PBT=EBIT+J_C−J_L',
 'Tax=max(PBT−Loss0,0)τ；Π=PBT−Tax；Cash=Cash_pre+J_C−Tax',
 'E=E0+Π；Book_M=Book_M0+K_M−Dep_M；Book_B=Book_B0+K_B−Dep_B',
 'A=Book_M+Book_B+AR+Cash；ε_balance=A−(L+AP+E)',
 'Loss_end=max(Loss0−max(PBT,0),0)+max(−PBT,0)；L_S,needed=max(Cash_min−Cash,0)'],
 [v('Cash0 / AR0 / AP0 / L0 / E0 / Loss0','期初现金/应收/应付/长贷/权益/税亏','千美元','已知期初状态'),v('Book_M0 / Book_B0','期初机器/厂房账面资产','千美元','已知期初状态'),v('ΔL','长期贷款增减','千美元'),v('K_M / K_B','机器/厂房投资额','千美元','上游计算/当期条件'),v('V / B / EBITDA / EBIT / Dep_M / Dep_B','收入/材料费/经营利润及折旧','千美元','上游条件计算'),v('r_L','长期贷款利率','小数','归档给定或上游风险预测')],
 [v('L / AR / AP','期末长贷/应收/应付','千美元','条件计算'),v('J_L / J_C','长贷利息/现金利息收入','千美元','条件计算'),v('PBT / Tax / Π','税前利润/所得税/税后利润','千美元','条件计算'),v('Cash_pre / Cash','计息税前现金/期末现金','千美元','联立条件计算'),v('E / A / Book_M / Book_B','期末权益/资产/机器/厂房账面额','千美元','条件计算'),v('Loss_end / L_S,needed','期末税亏/最低现金短贷缺口','千美元','条件计算；缺口不是完整短贷融资'),v('ε_balance','资产负债平衡差','千美元','一致性自检输出')],
 [('d_AR / d_AP','应收/应付天数','旧版30 / 30','经验条件；练习2新组件未核实'),('r_C','现金年利率','0.01','当期归档给定'),('τ','所得税率','0.29','当期归档给定'),('Cash_min','最低现金','2000千美元','当期归档给定'),('K_B / d_B','厂房投资/折旧率','旧版800千美元 / 0.07','经验条件；练习2新组件仍需显式输入'),('365','年天数','365','实现换算口径')],
 '旧链要求期初库存、短贷为0且权益为正。现金利息/税迭代，风险利率联动时另与期末状态迭代。低现金缺口不含完整短贷利息；税亏、厂房规则及计息时点仍待独立核验。',
 ['code/model_v2/finance.py','code/t2v0_um/calibrated.py'])
doc('GROWTH','下回合公司需求增长模型',['D̂_total,t=Σ_c D̂_t,c','g_D=(D̂_total,t+1 / D̂_total,t) − 1'],
 [v('D̂_t,c / D̂_t+1,c','本回合/下回合各国需求预测','千单位','上游需求预测；未来前景与对手策略须显式假设')],
 [v('g_D','下一回合公司总需求增长率','小数','情景传播输出')],
 [('独立训练系数','增长由两期预测相除','无','非独立增长回归')],
 '分母必须为正。情景端点不称为置信区间。', ['code/stepwise_model.py'])
doc('HORIZON','六回合剩余利润与候选比较',
 ['n_rem=7−t；Π_remaining=Σ_(k=t..6) Π_k','Π_cumulative,t=Π_cumulative,t−1+Π_t',
 '单回合稳健候选评分（部分旧网格）：score(d)=min_(ω∈Ω) Π(d,ω)'],
 [v('t','当前正式回合','整数1至6','已知回合'),v('Π_k','每个剩余回合条件税后利润','千美元','模型路径；缺失不能按0'),v('X_end,6','第6回合结束的状态','状态对象','上游结转结果'),v('d / Ω','候选决策/假定情景集合','对象/集合','决策与明确假设'),v('Π_cumulative,t−1','上回合累计收益','千美元','已实现状态或条件路径')],
 [v('n_rem / Π_remaining','剩余回合数/利润小计','回合；千美元','条件计算'),v('Π_cumulative,t','当期累计收益','千美元','条件计算'),v('X_end,6','保留的终局状态','对象','不自动变现'),v('score(d)','已覆盖场景中的最差单回合利润','千美元','旧候选评分，不是完整六回合最优解')],
 [('终止回合','正式结束回合','6','用户明确期限'),('终值奖励','未识别时不加收益','None，不是已知0','规则缺口'),('未来情景','行业、对手、成本等','各运行档案定义，无统一固定值','假设输入')],
 'horizon实现只做剩余利润小计，ranking_eligible=False。未完成六回合动态优化，不加入第7回合收益或自动清债。', ['code/model_v2/horizon.py','code/joint_scenarios.py'])
doc('METRICS','模型误差评价计算',['MAE=Σ_n |y_n−ŷ_n|/n；RMSE=sqrt(Σ_n(y_n−ŷ_n)²/n)',
 'WAPE=Σ_n |y_n−ŷ_n|/Σ_n y_n','份额MAE_pp=100 mean(|s_n−ŝ_n|)；利率MAE_bp=10000 mean(|r_n−r̂_n|)',
 '加权MAE=Σ_n w_n |y_n−ŷ_n|，其中Σ_n w_n=1'],
 [v('y_n / ŷ_n','实际标签/预测值','随目标变量','已实现标签/冻结或留出预测'),v('s_n / ŝ_n','实际份额/预测份额','小数','标签/模型输出'),v('r_n / r̂_n','实际利率/预测利率','小数','标签/模型输出'),v('n / w_n','有效样本数/归一化评价权重','个/小数','评价配置')],
 [v('MAE / RMSE','平均绝对误差/均方根误差','与目标相同','评价输出'),v('WAPE','总绝对误差比例','小数','评价输出'),v('MAE_pp / MAE_bp','份额百分点误差/利率基点误差','百分点/基点','评价输出')],
 [('训练系数','评价式无需训练','无','评价计算'),('w_n','逐团队、市场或策略权重','按版本；unified需求每市场每国家等权','评价口径'),('100 / 10000','小数转百分点/基点','100 / 10000','换算常数')],
 'WAPE分母须为正，MAE样本须非空；份额分组和评价切分须一致。指标和λ不是模型预测作用参数。', ['code/fit_demand.py','code/operations_rho.py','code/interest_rate_model.py'])

bundle_in = spend+group+[v('O_t / O_t−1','当期/上期运营投入','千美元','决策/历史实际'),v('X0','当期期初产能、人员、财务与历史投入状态','混合单位','已知输入'),v('d','生产、投资、物流、贷款候选决策','对象','可控输入')]
bundle_out = [v('D̂_c / ŝ_c / η̂','国别需求/份额/生产效率','千单位/小数/千单位每人','组件预测'),v('r_L / v_eff','贷款利率/材料单价','小数/美元每单位','组件预测'),v('Π / Cash / X_end','利润/现金/期末状态','千美元/千美元/对象','仅已覆盖范围的条件计算')]
doc('UNIFIED','unified-market正式1模型组合',['需求按COUNTRY；曲线按RD、OPS；效率按EFF；风险按RISK_POWER与RISK_EXP；材料按MATERIAL','生产与财务按CAPACITY→LABOR→OPERATING→FINANCE'],
 bundle_in,bundle_out,[('训练期','独立训练标签','formal / 1','实际历史'),('σ_M / ρ_R','营销尺度/研发延续','1000 / 0.5','结构假设'),('ρ_O / θ','运营延续/效率尺度','0.562 / 0.17001715019534525','训练参数')],
 '原运行20261012T114145124558+0800。同期市场共享是用户假设，非已核平台规则；正式2只登记新曲线，不表示正式2需求已训练。模型组合不等于完整财务已验证。',
 ['code/unified_market.py',str(unified_path.relative_to(ROOT))])
doc('T2V0','t2v0-um练习2组件及正式2迁移组合',
 ['已训练组件：r_L=r_base+0.12281068318353833 exp(−8.180868311208613 E/A)',
 'v_eff=v(1+0.0013845739435914967)；B=q v_eff',
 '需求/效率目标结构分别按COUNTRY/EFF；未获得本版本实际拟合系数'],bundle_in,bundle_out,
 [('训练/目标期','标签/预测目标','practice / 2 → formal / 2','迁移边界'),('r_base / Δr_S','基准利率/短贷加点','0.025 / 0.02','练习2给定值'),('whole_model_trained','整套模型训练完成标志',component['whole_model_trained'],'状态'),('migration_gate_passed / formal2_prediction_enabled','迁移/预测门槛',str(component['migration_gate_passed'])+' / '+str(component['formal2_prediction_enabled']),'状态')],
 '只有实际利率和材料两组件已用练习2训练。需求/效率没有实际新系数，完整正式2预测关闭；28项给定值与正式2归档一致仍不足以通过全部配对门槛。',
 ['code/t2v0_um/README.md','code/t2v0_um/calibrated.py',str(COMP.relative_to(ROOT))])

def values(r):
    return json.dumps(r['parameters'],ensure_ascii=False,separators=(',',':'))

descriptions = {
    'T_t−1,c / T_t−2,c': ['上一回合同口径行业实际需求','上上回合同口径行业实际需求'],
    'E / A / L / L_S': ['预测期末权益','预测期末资产总额','预测期末长期贷款','预测期末短期贷款'],
    'V / B / EBITDA / EBIT / Dep_M / Dep_B': ['营业收入','原材料购买费用','折旧前经营利润','息税前利润','机器折旧','厂房折旧'],
}
def expand_variables(rows):
    expanded=[]
    for symbol,meaning,unit,kind in rows:
        symbols=symbol.split(' / ')
        if len(symbols)==1:
            expanded.append((symbol,meaning,unit,kind))
            continue
        meanings=descriptions.get(symbol,meaning.split('/'))
        assert len(symbols)==len(meanings),(symbol,meaning)
        units=unit.split('；')
        if len(units)==1 and '/' in unit and '美元/' not in unit:
            units=unit.split('/')
        if len(units)!=len(symbols):
            units=[unit]*len(symbols)
        expanded.extend((s,m,u,kind) for s,m,u in zip(symbols,meanings,units))
    return expanded

written=[]
for d in docs:
    d['inputs']=expand_variables(d['inputs'])
    d['outputs']=expand_variables(d['outputs'])
    body = [f"# {d['code']} · {d['name']}", '', '核对日期：2026-10-12（北京时间）。每类模型独立说明；其保存版本在本页分列，不混合参数。', '',
        '参数说明：'+link(ROOT/'预测模型与训练参数汇总.md','输入类别、参数含义与训练口径')+'；'+link(ROOT/'参数细化与六回合期限要求.md','逐回合给定参数与期限')+'。', '',
        '版本关联：'+link(ROOT/'训练拟合模型与版本清单.md','全部保存版本及来源')+'；'+link(OUT/'README.md','全部模型文档索引')+'。', '',
        '## 公式', '', '\n\n'.join('`'+f+'`' for f in d['formulas']), '',
        '## 输入变量（字母与文字描述）','',table(['字母符号','文字描述','单位','输入类别/来源'],d['inputs']), '',
        '## 输出变量（字母与文字描述）','',table(['字母符号','文字描述','单位','输出类别'],d['outputs']), '',
        '## 参数定义与取值','',table(['参数字母/字段','文字描述','值或取值位置','类别'],d['params']), '', d['extra'], '',
        '## 适用版本与限制','',d['scope'], '',
        '下标：i/j为队伍，c为国家（TH泰国、ID印尼），m为编号市场，h为阶段，t为回合；0为期初，t−1为上一回合；帽号表示预测，不能当作已实现实际值。', '',
        '## 实现与原始参数来源', '', *['- '+link(ROOT/p,p) for p in d['source']], '']
    if d['family']:
        main=[r for r in records if r['model_code']==d['family'] and r['role']=='保存参数版本' and not r['copy_of']]
        body += ['## 已保存主版本的完整精度参数','',
            '下表保留原参数字段及数组顺序；本页上方给出字母映射。配置与训练参数分别列示；本页不自动选定部署版本。', '',
            table(['版本名称与JSON定位','参数值（完整精度）','配置/假设','参数原档'],
                  [(r['version_name'],values(r),json.dumps(r['config'],ensure_ascii=False,separators=(',',':')),link(ROOT/r['source'],'原档')) for r in main]), '',
            '诊断子拟合、保存副本及候选评分关联：'+link(CAT,'全部参数位置与完整精度配置')+'；'+link(CAT.parent/'全部参数位置.md','逐项定位清单')+'。诊断系数不拼成部署参数。','']
    if d['code'] in ('RD','OPS'):
        key='rd' if d['code']=='RD' else 'operations'
        rows=[]
        for period,reg in unified['curve_registry'].items():
            cur=reg['curves'][key]
            rows.append((period,json.dumps(cur['parameters']),link(unified_path,'曲线登记原档')))
        body += ['## unified-market逐回合曲线值','',table(['阶段/回合','参数数组（按上方顺序）','来源'],rows),'']
    if d['code']=='COUNTRY':
        body += ['## unified-market正式1国别参数','',table(['国家','e_c','b_G','b_H','b_R','ρ_R','λ'],
            [(country,*model['coefficients'].values(),model['rho'],model['penalty']) for country,model in unified['demand'].items()]),'']
    if d['code'] in ('INTEREST','RISK_EXP','MATERIAL_PROP','T2V0'):
        selected = [('interest_rate','a_r、b_r'),('material_unit_cost','α_v')] if d['code']=='T2V0' else (
            [('material_unit_cost','α_v')] if d['code']=='MATERIAL_PROP' else [('interest_rate','a_r、b_r')])
        body += ['## 练习2专用组件值与来源','']
        for key,label in selected:
            m=component[key]
            body += [f"{label} = `{json.dumps(m.get('parameters',m.get('parameter')),ensure_ascii=False)}`；来源："+link(COMP,'components.json')+f'，JSON定位 `/{key}`。', '']
    if d['code'] in ('INTEREST','MATERIAL_PROP'):
        pattern='output/interest_rate/*/model.json' if d['code']=='INTEREST' else 'output/material_unit_cost/*/model.json'
        rows=[]
        for path in sorted(ROOT.glob(pattern)):
            m=json.loads(path.read_text(encoding='utf-8'))
            rows.append((path.parent.name,m['form'],json.dumps(m.get('parameters',m.get('parameter'))),link(path,'原档')))
        body += ['## 独立训练版本值','',table(['版本','函数类型','参数值','来源'],rows),'']
    if d['code']=='T2V0':
        body += ['## 本版本财务给定输入值','',
            '给定参数是公式输入，不是新训练系数。字段与字母的对应见生产、工资、经营和财务文档；缺项不套旧值。','',
            table(['字段','给定值'],component['published']['financial_parameters'].items()),'',
            '仍未核实：`'+', '.join(component['published']['unknown_financial_parameters'])+'`。','']
    path=OUT/(d['code']+'_'+d['name']+'.md')
    path.write_text('\n'.join(body),encoding='utf-8')
    written.append(path)

index=['# 全部模型独立说明文档','',
 '核对日期：2026-10-12（北京时间）。按模型类型一份文档，各保存版本在文档内分列；训练、诊断、组合流程与确定计算明确区分。每份均列公式、输入字母及文字描述、输出字母及文字描述、单位、参数值和来源。','',
 '参数说明入口：'+link(ROOT/'预测模型与训练参数汇总.md','参数含义与输入分类')+'；'+link(ROOT/'训练拟合模型与版本清单.md','完整参数版本')+'；'+link(ROOT/'参数细化与六回合期限要求.md','当期参数与六回合要求')+'。','',
 table(['代码','模型名称','独立文档'],[(d['code'],d['name'],link(p,'打开')) for d,p in zip(docs,written)]),'',
 '历史目录中的代码快照和JSON副本在模型文档中关联原版本，不重复建相同公式文档。没有已建成函数的项目（行业影响独立回归、大客户中标概率、完整非零库存/短贷财务、六回合动态优化）保持缺口，不补造系数。','',
 '参数读法：原始JSON保留完整精度；普通输入的具体数值随决策/情景变化，所以给出符号、单位与来源，不伪造统一输入值。λ、误差指标与模型作用参数分别记录。','']
(OUT/'README.md').write_text('\n'.join(index),encoding='utf-8')
for path in [ROOT/'README.md',ROOT/'预测模型与训练参数汇总.md',ROOT/'预测模型与变量说明.md',ROOT/'训练拟合模型与版本清单.md',ROOT/'训练拟合模型与版本清单_文字说明版.md']:
    text=path.read_text(encoding='utf-8')
    entry='独立模型文档入口：'+link(OUT/'README.md','每个模型的公式、输入/输出变量字母与文字描述、参数值及来源')+'。'
    if entry not in text:
        first,rest=text.split('\n',1)
        path.write_text(first+'\n\n'+entry+'\n'+rest,encoding='utf-8')

# Check coverage, links and original parameter values without rerunning any model.
assert {d['family'] for d in docs if d['family']} == {r['model_code'] for r in records}
for d,p in zip(docs,written):
    text=p.read_text(encoding='utf-8')
    assert all(d[k] for k in ['inputs','outputs','params','formulas'])
    assert all(len(row)==4 and all(str(x) for x in row) for row in d['inputs']+d['outputs'])
    for target in re.findall(r'\]\(([^\n]+?)\)',text):
        assert Path(target).exists(),(p,target)
    for r in records:
        if r['model_code']==d['family'] and r['role']=='保存参数版本' and not r['copy_of']:
            assert values(r) in text
            original=json.loads((ROOT/r['source']).read_text(encoding='utf-8-sig'))
            for token in r['json_pointer'].split('/')[1:]:
                token=token.replace('~1','/').replace('~0','~')
                original=original[int(token)] if isinstance(original,list) else original[token]
            for key,value in r['parameters'].items():
                assert (original[key] if isinstance(original,dict) else original)==value
for p,digest in before.items():
    assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest,p
result=dict(date='2026-10-12',documents=len(written),model_families=sorted({r['model_code'] for r in records}),
    source_parameter_files_unchanged=len(before),input_output_symbols_and_descriptions_checked=True,
    main_version_parameter_values_included=True,links_checked=True,training_executed=False,
    files=[p.relative_to(ROOT).as_posix() for p in written])
(OUT/'核验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
