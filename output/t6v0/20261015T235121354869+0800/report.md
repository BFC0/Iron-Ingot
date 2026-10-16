# t6v0 正式5全模型处理报告

北京时间运行：20261015T235121354869+0800。状态：部分训练完成，明确保留资料缺口。
全部29类逐项处理；不宣称29个独立模型全部训练通过。权威注册表：[models_full.json](models_full.json)。
决策只使用已采集正式5小组最终列：29项决策，13项玩家预估排除。4条本组产品/国家输入与真实需求配对。
其他99队逐产品/国别小组最终决策缺失。需求SHARE/COUNTRY使用真实价格、真实需求及公司合计费用代理重训；ABS暂停，费用代理不冒充细分小组决策。
正式4期末状态配正式5终值100队；前者是结转基准，未披露的期初现金时点、税亏及投入存量保持未知。
最终方案与冻结候选不完全相同，整套方案直接事前评分0项。风险/材料/工资为给定实际期末状态或产量的条件回溯，不是完整经营预测。

## 需求训练假设与筛选

真实售价及结果页需求量是训练输入和标签；销量仅作供给证据，玩家预估和预算不作标签。每队公司合计一般营销、设计师营销、研发费用用于各产品/国家的解释变量，不拆分、不等同于真实细分决策；其系数是条件关联，不能解释为细分投入的因果收益。
模型为非负系数softmax竞争份额：泰国/印尼各一项价格系数、两项营销系数及一项研发系数。价格采用对数线性，正则固定0.001、rho固定0.5，研发有效投入使用公司研发合计加0.5×上期合计，仅为研究代理；未搜索高价分段和rho，不能称最优规格。市场5曲线跨市场共享是分析假设。
各训练折内按产品/国家对log1p价格及费用使用Q1−3IQR至Q3＋3IQR围栏；IQR为零时不按该项剔除。零价、零需求不适合对数拟合，另存原记录。
先用未超围栏的训练样本拟合初步模型，计算实际/预测份额的对数残差。低于训练中位数−max(log(2),4×1.4826MAD)，且存在实际需求大于销量（超过显示精度），或机器利用率≥98%且零售销量覆盖当期产量时，标为疑似供给引起的需求偏离并排除。计划产量约束不一定伴随机器满产。
上述供给归因是模型反推假设：需求与销量差异本身不证明需求标签失真，库存及订单也可能影响售罄判断。所有原数据及排除理由保留，可回放；不凭残差单独删除。
外层按10个整市场留出；阈值与初步模型只看该折训练市场，测试市场不参加筛选或参数拟合。主误差覆盖所有正价正需求测试样本，包括极端/疑似受限样本；另列同规格完全未筛选模型作消融比较。使用已实现对手输入和实际总量的份额验证，不能视为事前跨回合预测精度。

| 产品/模型 | 有效→保留 | 极端输入 | 疑似供给偏离 | 全量留出MAE，百分点 | 未筛选同规格MAE |
|---|---:|---:|---:|---:|---:|
| 复合梁/SHARE | 200→193 | 7 | 0 | 0.831231 | 1.294103 |
| 复合梁/COUNTRY/泰国 | 100→97 | 3 | 0 | 0.747405 | 1.106400 |
| 复合梁/COUNTRY/印尼 | 100→96 | 4 | 0 | 0.875374 | 1.503142 |
| 连接件/SHARE | 180→170 | 9 | 1 | 1.745256 | 2.182375 |
| 连接件/COUNTRY/泰国 | 90→83 | 7 | 0 | 1.788297 | 2.468030 |
| 连接件/COUNTRY/印尼 | 90→87 | 2 | 1 | 1.721209 | 1.879132 |

SHARE和COUNTRY是替代规格，不累加样本数；排除类别可能重叠。[全部原样本](demand_actual_rows.json) · [逐项筛选及反推量](demand_screening.json) · [不适合对数的样本](demand_invalid_rows.json)。

| 模型 | 状态 |
|---|---|
| ABS | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| SHARE | RETRAINED_ACTUAL_DEMAND_COMPANY_EXPENSE_PROXY_SCREENED |
| COUNTRY | RETRAINED_ACTUAL_DEMAND_COMPANY_EXPENSE_PROXY_SCREENED |
| EFF | OWN_FINAL_DECISION_CALIBRATION_RHO_UNIDENTIFIABLE |
| RISK_POWER | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| RISK_EXP | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| MATERIAL | RETRAINED_SEPARATE_PRODUCTS |
| MATERIAL_PROP | RETRAINED_SEPARATE_PRODUCTS |
| INTEREST | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| RD | RETRAINED_FORMAL5_CURVES |
| OPS | RETRAINED_FORMAL5_CURVES |
| TOTAL | ACTUAL_TOTALS_AND_GROWTH_DIAGNOSTICS_NOT_SUPERVISED_FIT |
| BASELINE | ACTUAL_TOTALS_AND_GROWTH_DIAGNOSTICS_NOT_SUPERVISED_FIT |
| GROWTH | ACTUAL_TOTALS_AND_GROWTH_DIAGNOSTICS_NOT_SUPERVISED_FIT |
| CAPACITY | OWN_ACTUAL_CAPACITY_BOUND_CHECKED_TIMING_UNRESOLVED |
| LABOR | CONDITIONAL_WAGE_FIT_IDENTIFIABILITY_RECORDED |
| OPERATING | SOURCE_EXPENSE_ACCOUNTING_ONLY_NOT_FORWARD_PROFIT_MODEL |
| FINANCE | 1900_SOURCE_EQUATIONS_ACCEPTED_NO_COMPLETE_FORWARD_FORECAST |
| HORIZON | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| METRICS | SOURCE_HASH_AND_DECISION_GUARDS_CHECKED |
| A | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| B | PUBLISHED_RULE_CHECKED_WITH_DISPLAY_INTERVALS |
| C | CONDITIONAL_WAGE_FIT_IDENTIFIABILITY_RECORDED |
| D | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| E | ACTUAL_INTENSITY_FORMULA_CHECKED |
| F | ROUTE_FORMULA_CHECKED_WITH_MISSING_ROWS_RECORDED |
| CONNECTOR | RULE_SELF_CHECK_ONLY_NO_ACTUAL_LIFECYCLE_TRAINING |
| CONNECTOR_V2 | RULE_SELF_CHECK_ONLY_NO_ACTUAL_LIFECYCLE_TRAINING |
| JOINT_ALLOCATION | RULE_SELF_CHECK_ONLY_NO_ACTUAL_LIFECYCLE_TRAINING |

## 曲线与条件验证

| 曲线 | 交错留点MAE | 最大误差 |
|---|---:|---:|
| rd/复合梁 | 0.000120341328 | 0.0033776323 |
| rd/连接件 | 0.000114567155 | 0.00331868709 |
| operations/泰国 | 9.23307085e-05 | 0.000726225628 |

三条曲线各200点，正式5市场5上期研发900/1300、运营750千美元；其他市场曲线共享未独立证实。横轴为取整有效投入，图形误差不是经营精度。

| 风险形式 | 有效样本 | 整市场留出MAE，基点 |
|---|---:|---:|
| solvency_exponential | 91 | 1.03582 |
| leverage_power | 91 | 1.31217 |

材料复合梁：100条，选型additive，选型留出MAE 1.73948千美元；选型误差不是嵌套独立检验。

材料连接件：90条，选型proportional，选型留出MAE 0.252467千美元；选型误差不是嵌套独立检验。

解雇规则100项、环境恒等式1000项：失败0/0；容差传播原显示精度。

## 当前全部问题与不足

- 需求营销及研发采用公司合计费用代理，不能解释为细分投入或因果效应；EFF/A/D完整运营机制及历史投入仍不可识别。
- 工资回溯使用实际产量/人数/产能，不解决生产预测、投资生效及跨期效应。
- 风险、材料同期模型及曲线跨市场共享缺独立前向验证；新旧比较仅条件误差，不表明事前收益改善。

## 因缺乏数据而无法验证的问题

- 99队正式5产品/国别最终决策；完整运营/研发存量、自动有效投入横轴。
- 真实确认订单、交付、预收与余款、税亏及正式6经营状态链。
- 本版本不部署、不输出完整利润排名；旧模型及原始证据保留。

[数据缺口](data_gaps.json)；[新旧比较](old_new_comparison.json)；[逐项验收](checks.json)。
