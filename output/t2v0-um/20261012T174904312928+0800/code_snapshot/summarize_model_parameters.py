"""Summarize saved model parameters without fitting or modifying source results."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2 = 'output/model_v2/20261011T200419239887+0800'
OLD_V2 = 'output/model_v2/20261011T194918540163+0800'
FROZEN = 'output/cross_market/parameters_20261011T081705179804Z.json'
OUTPUT = ROOT / '预测模型与训练参数汇总.md'
sources = {}
lines = []


def read(name):
    path = ROOT / name
    sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text(encoding='utf-8'))


def add(text):
    lines.append(text.strip() + '\n')


def link(name):
    return f'[{name}]({(ROOT / name).as_posix()})'


def number(value):
    return format(value, '.15g') if isinstance(value, float) else str(value)


def table(headers, rows):
    rows = list(rows)
    assert all(len(row) == len(headers) for row in rows)
    add('| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(['---'] * len(headers)) + ' |\n' +
        '\n'.join('| ' + ' | '.join(number(v) for v in row) + ' |' for row in rows))


def beta_table(names, models):
    assert all(len(beta) == len(names) for beta in models.values())
    table(['参数', *models], [[name, *[beta[i] for beta in models.values()]] for i, name in enumerate(names)])


def main():
    step = read('分步模型拟合与验证.json')
    hist = read('需求拟合与留出核验.json')
    frozen = read(FROZEN)
    latest = read(V2 + '/demand.json')
    mechanisms = read(V2 + '/mechanisms.json')
    old_v2 = read(OLD_V2 + '/demand.json')
    names = ['e_TH：泰国价格系数', 'e_ID：印尼价格系数', 'b_G：一般营销系数', 'b_H：设计师营销系数', 'b_R：研发曲线系数']
    seven = ['α_TH：泰国截距', 'α_ID：印尼截距', *names]
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    add(f'''# Cesim预测模型、训练参数与输入变量汇总

整理时间：{now}（北京时间）。读取已有JSON与Python实现，未重新训练、未覆盖冻结文件、未修改网页。新版截止于运行`20261011T200419239887+0800`；后续运行需单独比较。

## 阅读范围与口径

### 数据、模型参数与训练指标的统一分类（2026-10-12更新）

以正在决策的第t回合为目标回合。数据的类别按来源和是否已实现判断，不能仅凭变量名称、是否带帽号或是否能写成公式判断。

| 类别 | 子类 | 定义与例子 |
| --- | --- | --- |
| 已知数据 | 基于t−1回合终值（实际值）的已知条件 | 已公布的实际需求、销量、产量、现金、负债、库存、人数等；按状态结转规则形成t回合期初条件。须区分上一回合终值与结转后的期初值，不能默认两者相等。 |
| 已知数据 | t回合新增的初值条件 | 当期已公布、已核验的工资、材料价格、基准利率、税率、订单条件和其他前景条件。增长预期或定性提示本身是已知信息，其对应的未来实际数值仍未知。 |
| 推测的数据 | 不确定模型输出 | 自行设定并训练的需求、份额、效率、风险加点等模型的预测值；模型可能近似比赛隐藏机制、拟合网页曲线，或额外建立若干量之间的关系。输出仍是估计值，不是平台实际值。 |
| 推测的数据 | 确定计算等式的输出 | 按会计、财务等确定等式计算的收入、成本、利润、现金、资产负债等。当输入包含预测值或假设值时，输出是给定这些输入的条件计算值，仍不能当作实际值。 |
| 模型自身的参数 | 训练得到的值 | 每个模型f(x;θ)自身的θ，如需求系数β、曲线参数a/b/c/d、效率尺度θ；须标明所属模型、版本、训练来源与适用回合。 |
| 模型自身的参数 | 假设的值 | 人为预设、尚未由数据训练识别的系数或结构取值，如预设的延续权重ρ；须注明假设依据，不能与已训练参数混称。 |
| 训练所用指标与配置 | 训练配置及评价指标 | λ为正则化超参数，用于控制训练惩罚；损失函数、选参规则属于训练配置，MAE/WAPE等用于评价训练或验证效果。它们与f(x)自身的作用参数分开列示。 |

本队t回合候选决策属于可控输入，未知对手决策属于情景假设，均单独标明，不混入“已公布的初值条件”。平台公布的税率、工资等属于已知输入；未来回合未公布的对应值只能作为假设输入。ρ、分段点等按实际用途分类：参与f(x)且由训练选择的值，注明“训练选择”；人为固定的值，注明“假设”；不能仅因它们出现在配置文件中就与λ归为同一类。

模型和等式分为两类：

1. **自行假设并训练的模型**：我们设定函数形式并依据数据或约束拟合。包括比赛隐藏机制的近似模型、网页曲线拟合模型，以及额外建立的量之间的关系模型。函数形式、训练系数和适用条件都需要证据与验证；即使模型内部使用softmax、乘法等确定运算，也不会因此成为比赛中的确定规律。
2. **确定的计算等式**：会计恒等式、收入与利润分解等现实和比赛中通用的计算关系；在统一定义和口径下，等式本身不因回合、前景或训练而改变，无需拟合。变化的是输入值。税率、折旧率、计息时点、产能衰减比例等具体规则须另行核验，不能因写进财务或生产公式就宣称普遍不变。所有输入均为已实现且已核验的实际值时，结果可标为“基于实际值的计算值”；否则保持“条件计算值”标识。

### 训练数据的回合依据

**预测目标与训练样本**：用于t回合的预测模型，通过t回合所有已知条件预测t回合期末真实终值。输入包括由t−1回合实际终值形成的期初条件、t回合新增初值条件，以及有需要的历史数据真实值；目标标签是t回合结算后公布的实际终值。记为 `ŷ_t,end=f(X_t,known;θ)`，其中 `X_t,known` 是预测时已知的条件，`ŷ_t,end` 是对尚未知的真实终值 `y_t,end` 的估计。候选决策作为可控输入、未知对手决策作为假设输入另列，不能称为已知实际条件。

**当前回合不能完成实际结果监督训练**：t回合尚未结算时，真实终值标签不存在，因此不可能用t回合完整的“已知条件→真实终值”样本训练或验证该回合预测模型。使用t回合已知条件进行预测、按前景调整历史模型，不等于已经用t回合实际结果训练。只有t回合真实终值公布后，才能组成该回合训练样本；先核验事前冻结预测，再将该样本用于后续训练。

- **隐藏机制及额外关系模型**：用于预测t回合终值的模型，实际使用此前已结束回合的“该历史回合预测时已知条件→该历史回合实际期末终值”配对样本训练。历史输入必须按对应回合还原，不能把该回合结束后才知道的结果放回其事前输入。依据t回合前景核对历史模型的适用性，调整样本选择、当期已知输入或有依据的参数假设。记录实际训练回合、调整对象、依据和幅度；定性前景不足以给出精确系数时，使用明确情景，不伪造t回合标签，也不把历史参数当作当期已知规则。
- **网页曲线拟合模型**：必须使用本市场、本阶段、t回合的网页曲线数据拟合，记录图表/JSON/SVG来源、采集时间、单位及拟合范围。缺少t回合曲线时标明缺口，不能用旧曲线冒充当期拟合；历史曲线只用于对应历史回合的回算、对照或明确标记的假设情景。
- **确定的计算等式**：不训练等式本身；按目标回合匹配已知输入、模型输出和假设输入，再计算结果。确定等式只传播输入的不确定性，不会消除它。
- **逐模型记录**：分别列明模型类别、目标回合、训练数据回合与来源、当前前景依据、输入类别、训练参数、假设参数、λ等训练配置、验证指标及输出类别。训练使用的历史回合与预测目标t回合必须分列；回溯验证获得的实际值不能写成事前已知数据。

本节更新分类和执行口径，不改变下文历史版本的参数数值、训练记录或冻结边界。下文旧曲线及旧参数不因此获得t回合适用性。

本文汇集主拟合、冻结和情境模型，以及对照、消融和敏感性参数。交叉验证折、删队/删市场和重采样产生的重复拟合属于诊断，具体系数见第14项来源，不拼接为部署参数。数值显示15位有效数字，完整精度保留在对应JSON。

- **当前状态**：新版是情境内研究候选，尚无同情境跨回合独立验证；旧A/B及混合回合模型保留为历史诊断，不能据此直接推荐。
- **情境分类**：`M5_P1_FORMAL1_VISIBLE`关联市场5练习1与正式1可见前景；`M5_P2_GROWTH_MARKETING_BULK`关联市场5练习2。其他市场360条练习记录在新版中因前景未核实而隔离。情境与回合共变，未识别独立情境因果效应。
- **单位**：需求、销量、产量、产能和投资新增产能为千单位；财务金额和投入为千美元；价格/单位材料/运输为美元/单位；效率为千单位/人；人数为人；内部利率/增长率/税率为小数，产能分配`a`使用百分数。
- **参数类别**：按上文统一分类区分模型自身的训练参数、假设参数，以及λ等训练配置；税率、工资等为已知输入或条件假设，不是需求训练系数。接近零不代表实际作用为零。
- **定位变量**：`m/market_id`编号市场，`h/phase`初始/练习/正式阶段，`t/round`回合，`c/country`泰国或印尼，`i/team_id`本队，`j`竞争队，`J`同市场同回合同国竞争集合；`context_id`情境，`category`实际需求/预算/玩家预测等类别。它们控制匹配、分组和适用性，不是连续回归系数。`team_column`是源表团队列位置，用于整队留出；`sources`和采集时间定位证据，不作需求特征。
- **下标与变换**：0为期初/初始参考，prev或t−1为上一回合，t−2为上上回合；帽号表示模型预测。`ln/log1p/exp`分别为自然对数/ln(1+x)/指数。`scale`来自训练折组内中心化特征的加权均方根；`inactive_columns`是缺乏训练变化而关闭的列；`positive_fit_n`为该损失实际参与拟合条数。千单位×美元/单位=千美元，无需再乘1000。
''')
    add('''## 1. 行业总需求与增长模型

- 公式：`T̂_t=T_(t−1)²/T_(t−2)`，或显式情景`T̂_t=T_(t−1)(1+g_T)`；正式1旧冻结使用不增长或沿用本市场练习1增长两种情景。
- 输入：`T`为同编号市场、同阶段、同回合、同国家的实际公司需求之和；`g_T`为外推/假定的行业增长率；历史分母缺失或为零时比例不可算。销量、玩家预测、平台预算不能替代`T`。
- 训练参数：**无**；尚无独立行业价格、营销、宏观因素总量回归。
- 练习2官方叙述5–10%是预期范围，不能自动作为已实现需求增幅。
''')
    add('''## 2. 新版情境内竞争份额与公司需求模型

- 基本公式：`u_i=−e_c ln(P_i/P0_i)+b_G ln(1+G_i/1000)+b_H ln(1+H_i/1000)+b_R ln(f_R(R_i+ρ_R Rprev_i))`。
- 分段候选追加：`−k_c max[ln(P_i/(1.5P0_i)),0]`，泰国和印尼分别一列；超过分段点后的对数价格斜率为`−(e_c+k_c)`。
- 输出：`ŝ_i=exp(u_i)/Σ_j exp(u_j)`；`D̂_i=T̂_c ŝ_i`。竞争集合只含相同市场、阶段、回合、国家的团队，不能跨编号市场计算softmax。
- 输入：`P_i`本队当期售价，`P0_i`该队初始价；`G_i/H_i`两国合计一般/设计师营销代理；`R_i/Rprev_i`当期/上期研发；`T̂_c`给定行业规模；各竞争队也需同类策略输入。正式对手策略未知时使用明确情景。
- `e_c`为相对价格得分系数，不能直接当绝对需求弹性；`b_G/b_H/b_R`为模型内条件关联，不能解释为投入因果收益；竞争模型无国别绝对截距。
''')
    for label, pool in latest['pools'].items():
        model = pool['refit_model']
        extended = names + (['k_TH：泰国高价追加系数', 'k_ID：印尼高价追加系数'] if model['piecewise'] else [])
        add(f'### {label}\n\n- 训练记录：{len(model["training_keys"])}条；仅本情境单一练习回合。\n- 配置：ρ_R={model["rho"]}，λ={model["penalty"]}，标准化={model["standardized"]}，分段={model["piecewise"]}，损失={model["loss"]}。\n- 内部留队份额MAE：{number(pool["cv_share_mae_pp"])}个百分点；外部跨回合误差未取得。')
        beta_table(extended, {'训练后原尺度β': model['beta'], '训练尺度scale': model['scale']})
        add(f'- 非活动列（从0计数）：`{model["inactive_columns"]}`。练习2印尼高价追加列未被训练识别；其0是关闭该特征的结果，不能解释为印尼高价无作用。' if model['inactive_columns'] else '- 本模型无被关闭的特征列。')
    add('''- 标准化只用于训练惩罚：`z=x_centered/scale`，`β_original=β_scaled/scale`。上述β已经反变换，预测使用原始特征，不要再次除scale；scale不是新作用系数。
- `share`损失拟合份额，保留零需求；`log`损失拟合组内去均值对数需求，零值不进入对数训练。两者的λ不能直接比较。新版按市场/国家等权，训练内选参，1%误差以内优先参数更少者。
''')
    add('来源：' + link(V2 + '/demand.json') + '；实现：' + link('code/model_v2/core.py') + '、' + link('code/model_v2/context.py'))
    add('## 3. 旧冻结跨市场A/B竞争需求模型（历史对照）\n\n- 与第2项基本公式相同，无高价追加项，ρ_R=0.5；A只市场5，B市场1–10，练习1/2混合。行业规模仍由外部情景提供。旧B情境未核实，未用于新版同情境训练。')
    beta_table(names, {key: v['competitive']['coefficients'] for key, v in frozen['models'].items()})
    table(['模型', '训练条数', 'λ', '市场'], [[k,v['competitive']['train_n'],v['competitive']['penalty'],str(v['competitive']['train_markets'])] for k,v in frozen['models'].items()])
    add('来源：' + link(FROZEN) + '。冻结时点：' + frozen['frozen_at'] + '。旧λ用市场等权平均损失；不能与分步残差总和口径的同数值λ混为一谈。')
    add('## 4. 旧A/B自身策略绝对需求模型（对照）\n\n- 公式：`D̂_i=exp(α_c+u_i)`，u使用第3项特征，系数另行拟合。\n- 输入与第3项相同；不输入对手策略或行业总量，不保证总需求守恒。α_c为国别对数需求截距，可为负；其余系数非负。ρ_R=0.5。')
    beta_table(seven, {k:v['own_only']['coefficients'] for k,v in frozen['models'].items()})
    add('- A训练40条、B训练400条；两者λ=0.01。来源：' + link(FROZEN))
    add('## 5. 原分步竞争模型（历史）\n\n- 第2项基本公式，使用国别参考价1800/2000美元/单位、研发曲线f_R、ρ_R=0.5。\n- 冻结版仅练习1训练20条；全练习版练习1/2训练40条。两者λ=0.01，但使用残差总和损失，不能直接套用到A/B的平均损失。')
    beta_table(names, {'正式1旧冻结':step['demand']['frozen_round1_beta'], '全练习重拟合':step['demand']['all_practice_beta']})
    add('来源：' + link('分步模型拟合与验证.json'))
    add('''## 6. 原绝对对数需求模型与价格消融（历史）

- 公式：`D̂=exp[α_c−e_c ln(P/P0_c)+b_G ln(1+G/1000)+b_H ln(1+H/1000)+b_R ln(1+(R+ρ_R Rprev)/1000)]`。
- 输入与第2项对应，差别是研发直接log1p投入代理，不通过f_R；P0为泰国1800、印尼2000。全练习训练40条，前向版只练习1训练20条。
- ρ_R=0.5，λ=1，残差总和损失，截距不受惩罚。价格消融只保留截距和价格项，其余列关闭。
''')
    beta_table(seven, {'全练习拟合':hist['coefficients'], '练习1训练→练习2回溯':hist['nested_forward_holdout']['coefficients'], '前向价格消融':hist['price_only_ablation']['forward_holdout']['coefficients']})
    add('来源：' + link('需求拟合与留出核验.json') + '。此处b_R是log1p研发投入系数，与研发曲线模型的b_R不可互换。')
    add('''## 7. 可见研发与运营乘数曲线

- 研发：`x_R=max(R+ρ_R Rprev,0)`；`f_R=a_R+b_curve,R(x_R+c_R)^d_R`。输入x_R为有效研发千美元，输出为无量纲需求乘数；需正值才能取ln。
- 运营：`x_O=max(O+ρ_O Oprev,0)`；`f_O=a_O+b_curve,O x_O/(c_O+x_O)`。O/Oprev为当期/上期运营改进千美元，输出无量纲效率乘数。
- 两条曲线参数来自市场5可见图形拟合，不是由实际需求因果回归识别。ρ不由图形决定；研发可见支持约至1200千美元，超出标为外推。
''')
    beta_table(['a_R：垂直偏移', 'b_curve,R：幅度', 'c_R：横轴平移（千美元）', 'd_R：指数'], {'研发拟合':step['curves']['rd']['parameters']})
    beta_table(['a_O：零投入乘数', 'b_curve,O：增加幅度', 'c_O：饱和尺度（千美元）'], {'运营拟合':step['curves']['operations']['parameters']})
    add('来源：' + link('分步模型拟合与验证.json') + '；新版沿用该曲线，未独立补证其他市场曲线。')
    add('''## 8. 生产效率模型与延续敏感性

- 公式：`η̂=θ f_O(O+ρ_O Oprev)`；η单位为千单位/人，θ为技术尺度。
- 输入：当期/上期运营投入、运营曲线；训练标签`η_actual=q_actual/N_actual`，不是玩家手填效率或两位小数显示效率。q为实际产量，N为实际工人数。
- θ按练习1十队的`η_actual/f_O`均值估计；新版另按不同投入策略等权估计θ_balanced。ρ是分别重拟合的候选配置；不能按练习2回溯误差再选ρ。
''')
    table(['ρ_O', 'θ（队均值）', 'θ_balanced（策略等权）'], [[x['rho'],x['technology_scale'],x['strategy_balanced_scale']] for x in mechanisms['efficiency']])
    add('- 旧默认ρ_O=0.5，θ=' + number(step['efficiency']['selected']['technology_scale']) + '。训练当期运营投入600–1300千美元；400属于外推。技术趋势与投入存量未分离，不自动跨未来回合恒定。\n- 来源：' + link(V2 + '/mechanisms.json'))
    add('''## 9. 贷款风险溢价模型（两个候选）

- 权益/资产指数：`r_L=r_base+a_r exp(−b_r E/A)`；旧完整条件链按训练误差采用此候选。
- 债务/权益幂：`r_L=r_base+a_r[(L+L_short)/E]^b_r`，保留为备选。
- 输入：E期末权益、A期末资产、L期末长贷、L_short期末短贷（千美元），r_base当期基准利率（小数）。训练用实际期末状态，事前应用需预测状态联立，不能输入未来实际值。
- a_r为利率小数尺度幅度，b_r为形状系数；训练样本市场5练习1十家，练习2仅回溯。E≤0范围未识别。
''')
    table(['形式', 'a_r', 'b_r'], [[x['form'],*x['parameters']] for x in mechanisms['risk']])
    add('- 给定实际状态的拟合不等于前瞻计息机制已验证；权益比率训练范围约0.452–0.645，大额还贷外推待查。\n- 来源：' + link(V2 + '/mechanisms.json'))
    add('''## 10. 产能、产量、交付、班次工资与解聘模型

- 产能：`C=Cprev(1−d_C)+I`；I为新增机器产能，机器投资金额`K_machine=p_I I`。
- 产量：`q=min(Ca/100,Σ_c D̂_c)`；a为产能分配百分数；依照交付优先级π依次`S_c=min(D̂_c,剩余供给)`，销量受供给截断，不能作为需求标签。
- 班次：`q1=min(q,C/3)`、`q2=min(max(q−C/3,0),C/3)`、`q3=max(q−2C/3,0)`；人数`N=q/η`。
- 工资：`W=w(q1+κ2q2+κ3q3)/η`；解聘费`F=max[(1−δ)Nprev−N,0]wσ`。
- 输入：Cprev上期产能、I投资、a分配、两国需求、π交付顺序、η效率、Nprev上期工人数，以及工资、班次倍数、自然减员和补偿比例。
- 没有额外训练系数；当期参数d_C=0.15、p_I=100美元/单位、w=28千美元/人、κ2=1.65、κ3=2.56、δ=0.10、σ=0.35。人数为连续近似。
- 当前链限零期初库存、零大客户交付；非零分支不能套用。利润排序/候选决策网格不构成新的预测模型。
''')
    add('''## 11. 原材料校准、收入与经营利润模型

- 原材料：`B=q(v+Δv)`；v为当期官方单位材料成本；唯一训练校准参数Δv为练习1报表与基础材料价的单位差额均值。
- 收入：`V=Σ P_c S_c`；运输`Z=Σ k_c S_c`；营销费用`G+H+marketing_fixed`；其他经营费用`overhead_fixed+F+R+O`。
- `EBITDA=V−B−W−Z−(G+H+marketing_fixed)−(overhead_fixed+F+R+O)`；`EBIT=EBITDA−Dep_machine−Dep_building`。
- 输入：售价、可交付销量、产量、材料单价、运输费、营销、研发、运营、工资、解聘费及固定费用。除Δv外均为上游预测、决策或场景参数。
''')
    table(['经验校准参数', '值', '单位'], [['Δv',step['finance']['materials']['uplift_usd_per_unit'],'美元/单位']])
    add('- Δv是经验残差，未证明是平台隐藏成本规则。正式1v=900；练习2v=1053（当期涨17%），叙述未来约20%分别保留；不得把20%再乘到1053。\n- 来源：' + link('分步模型拟合与验证.json'))
    add('''## 12. 利息、税、利润、现金与资产负债联立模型

- 长贷：`L=L0+ΔL`；`J_L=(L0+L)r_L/2`。新版r_L输入小数；原stepwise决策long_rate输入百分数、内部除100，两版输入不可直接互传。
- 周转：`AR=V d_AR/365`、`AP=B d_AP/365`；现金税息前`Cash_pre=Cash0+EBITDA−J_L+AR0−AR+AP−AP0−K_machine−K_building+ΔL`。
- 折旧：`Dep_machine=d_machine(Book_machine,0+K_machine)`；`Dep_building=d_building Book_building,0`。
- 现金利息`J_C=max((Cash0+Cash)/2,0)r_C`；税前利润`PBT=EBIT+J_C−J_L`；`Tax=max(PBT−Loss0,0)τ`；`Profit=PBT−Tax`；`Cash=Cash_pre+J_C−Tax`。Cash/J_C/Tax迭代联立。
- 期末权益`E=E0+Profit`；期末机器/厂房账面价值=期初+投资−折旧；`A=Book_machine+Book_building+AR+Cash`，零库存/零短贷范围自检`A=L+AP+E`。
- 税亏结转`Loss_end=max(Loss0−max(PBT,0),0)+max(−PBT,0)`；最低现金缺口`L_short,needed=max(Cash_min−Cash,0)`，不包含尚未识别的短贷利息。
- 本项无新增回归系数；采用第9项风险候选时额外联立r_L/E/A。新版归档基准压力链直接输入r_L，并未完成风险联立或完整候选搜索。
''')
    add('### 12.1 全部期初状态输入\n\n以下值仅是旧正式1归档期初（初始0）示例，不是当前实时账户；正式1不能继承练习2财务状态。')
    descriptions = {'capacity':('上期机器/生产产能','千单位'),'workers':('上期生产工人数','人'),'inventory':('期初库存；当前链必须为0','千单位'),'cash':('期初现金及等价物','千美元'),'ar':('期初应收账款','千美元'),'ap':('期初应付账款','千美元'),'machine_book':('期初机器账面价值','千美元'),'building_book':('期初厂房账面价值','千美元'),'long_debt':('期初长期贷款','千美元'),'short_debt':('期初短期贷款；当前链必须为0','千美元'),'equity':('期初股东权益','千美元'),'tax_loss':('期初可抵税亏损；正式1设0','千美元')}
    table(['state键', '意义', '单位', '归档期初值'], [[k,*descriptions[k],v] for k,v in step['decisions']['current_inputs']['state'].items()])
    add('''### 12.2 全部决策及外部预测输入

- `prices=[P_TH,P_ID]`：两国单价，美元/单位。
- `general=[G_TH,G_ID]`、`designer=[H_TH,H_ID]`：两国营销支出，千美元；财务按实际国别输入计算费用，旧需求训练只有合计代理，不能据此识别国别分配收益。
- `rd=R`、`operations=O`：研发和运营投入，千美元；需求/效率还需相应上期投入。
- `allocation=a`：产能分配百分数，0–100。
- `machine_investment=I`：新增产能，千单位，不是机器台数或投资金额。
- `priority=π`：两国交付次序；0=泰国、1=印尼，`[0,1]`优先泰国。
- `long_change=ΔL`：长期贷款增减，千美元；负数为还贷，不能超过期初长贷。
- `long_rate=r_L`：当期贷款利率，新版输入小数；旧版字段输入百分数。
- `demand=[D̂_TH,D̂_ID]`：两国公司需求，千单位，可来自需求模型或显式预算输入，来源必须标明。
- `efficiency=η`：千单位/人，可来自效率模型或玩家预测，不能混为实际标签。
''')
    add('### 12.3 当期场景参数与条件假设\n\n以下是新版正式1条件链所用值；各回合须关联当期前景。固定厂房投资800、厂房折旧7%、周转30天及税亏/时序等仍须独立机制验证。')
    constants = [('wage',28,'千美元/人','基础工资'),('second_shift',1.65,'乘数','第二班工资倍数'),('third_shift',2.56,'乘数','第三班工资倍数'),('attrition',.1,'小数','自然减员'),('severance',.35,'小数','解聘补偿比例'),('material_cost',900,'美元/单位','正式1基础原料；练习2=1053'),('transport',[30,120],'美元/单位','泰国/印尼运输单价'),('marketing_fixed',50,'千美元','市场调研固定费'),('overhead_fixed',4000,'千美元','管理基础成本'),('machine_unit_capex',100,'美元/单位','新增机器产能单价'),('building_capex',800,'千美元','条件链厂房投资'),('machine_depreciation',.15,'小数','机器折旧；代码亦用于产能衰减'),('building_depreciation',.07,'小数','厂房折旧'),('ar_days',30,'天','应收周转'),('ap_days',30,'天','应付周转'),('cash_rate',.01,'小数','现金利率'),('tax_rate',.29,'小数','所得税率'),('minimum_cash',2000,'千美元','最低现金'),('r_base',.03,'小数','正式1基准；练习2=.025')]
    table(['参数', '值', '单位', '解释'], constants)
    add('来源：' + link('code/model_v2/finance.py') + '；旧条件状态：' + link('分步模型拟合与验证.json'))
    add('''## 13. 下回合公司需求增长、基线与未建模项目

- 公司增长：`g_D=Σ_c D̂_(t+1,c)/Σ_c D̂_(t,c)−1`，下回合需求需重新输入行业规模、对手策略、自身价格/投入、研发延续和情境；无独立增长回归参数，分母0时未定义。
- 等份额基线：`ŝ=1/n_J`、`D̂=T̂/n_J`；n_J为同竞争集合团队数，无训练参数。
- 实际总量诊断：`D̂_oracle=T_actual ŝ`；T_actual为验证期已知总需求，使用它是事后份额诊断，不能当作可实现事前成绩。
- 历史均值/价格消融仅作对照，具体训练切分见源文件，不与主模型混用。
- 候选搜索和固定种子2000组压力抽样是决策比较/稳健性工具，没有训练得到的“最优决策系数”。抽样分位数不是置信区间或真实发生概率。
- 大客户中标概率、国别营销因果分配、非零库存计价/释放、短贷计息、完整投入存量、未来宏观总量以及至正式6完整动态最优仍无已验证预测模型，不能补造参数。
''')
    add('## 14. 情境补充之前的新版A/B与其他诊断（历史记录）\n\n以下运行194918在情境分类之前，前向练习1→练习2与全练习重拟合均保留；当前只能作跨情境/情境未核实诊断。')
    for label, pool in old_v2['pools'].items():
        add('### 旧新版 ' + label)
        model = pool['forward_model']
        expanded = names + (['k_TH', 'k_ID'] if model['piecewise'] else [])
        beta_table(expanded, {'练习1训练β':model['beta'], '练习1/2重拟合β':pool['refit_model']['beta']})
        table(['配置', '练习1训练', '全练习重拟合'], [[k,model[k],pool['refit_model'][k]] for k in ['rho','penalty','standardized','piecewise','loss','positive_fit_n']])
        beta_table(expanded, {'前向训练scale':model['scale'], '重拟合scale':pool['refit_model']['scale']})
    add('来源：' + link(OLD_V2 + '/demand.json'))
    add('### 历史绝对需求模型的ρ/λ敏感性\n\n系数次序与第6项一致，不按验证误差选为当前部署参数。')
    table(['ρ_R', 'λ', *seven], [[x['rd_persistence'],x['penalty'],*x['coefficients']] for x in hist['sensitivity']])
    add('''### 诊断参数的完整来源

- 当前情境每个242项候选的CV路径、逐折scale、所选模型训练键：情境文件与demand.json。
- 旧新版删队/删市场beta、200次整簇重采样beta及分位数：旧新版demand.json的influence/resampling。
- 两种风险模型逐队留出a_r/b_r：mechanisms.json的risk[].leave_team_out。
- 原绝对需求的整队/跨回合/嵌套留出coefficients，价格消融及9项敏感性：需求拟合与留出核验.json。
- 跨市场留市场/前向比较的单独训练模型：cross_market/validation.json；不能用全量冻结系数替代前向训练系数。
- 跨市场更早时间戳档案为采集/运行阶段的历史冻结版本，主表固定引用081705正式冻结；其他档案的数值在下方另列。
''')
    for path in sorted((ROOT / 'output/cross_market').glob('parameters_20*.json')):
        if path.relative_to(ROOT).as_posix() == FROZEN:
            continue
        obj = read(path.relative_to(ROOT).as_posix())
        add('### 历史档案 ' + path.name)
        for mode, cols in [('competitive',names),('own_only',seven)]:
            beta_table(cols, {k: v[mode]['coefficients'] for k,v in obj['models'].items()})
        add('完整训练范围及λ：' + link(path.relative_to(ROOT).as_posix()))
    add('## 15. 来源、适用性与核验\n\n- 本文参数全部读取保存结果，未把官方参数称为训练结果；未把旧冻结、跨情境与情境内系数拼接。\n- 练习2中印尼高价追加系数0属于非活动列，近零研发系数也不能作因果解释。\n- 未完成正式实际、其他市场同情境、低投入效率、短贷/库存/大客户等独立验证；这些限制影响模型可用范围。\n- 后续模型更新应同时更新运行编号、输入哈希、情境、训练键和参数；本文是本次读取时点的摘要。')
    table(['参数源文件', 'SHA256'], [[link(k),v] for k,v in sources.items()])
    text = '\n'.join(lines)
    assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in sources.items())
    assert all(number(v) in text for p in latest['pools'].values() for v in p['refit_model']['beta'])
    assert text.count('## ') >= 15 and '1053' in text and '0.03' in text
    OUTPUT.write_text(text, encoding='utf-8')
    print(f'PASS: {OUTPUT}; {len(sources)} parameter sources; {len(text)} characters')


if __name__ == '__main__':
    main()
