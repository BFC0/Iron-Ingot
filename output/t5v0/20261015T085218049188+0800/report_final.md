# t5v0 正式4全模型处理报告

北京时间运行：20261015T085218049188+0800。状态：部分训练完成，明确保留资料缺口。
全部29类逐项处理；不宣称29个独立模型全部训练通过。权威注册表：[models_full.json](models_full.json)。
决策只使用已采集正式4小组最终列：29项决策，13项玩家预估排除。4条本组产品/国家输入与真实需求配对。
其他99队逐产品/国别小组最终决策缺失，需求ABS/SHARE/COUNTRY暂停；不把结果费用或个人草稿当小组决策。
正式3期末状态配正式4终值100队；前者是结转基准，未披露的期初现金时点、税亏及投入存量保持未知。
原冻结候选未被采用，直接事前评分0项。风险/材料/工资为给定实际期末状态或产量的条件回溯，不是完整经营预测。

| 模型 | 状态 |
|---|---|
| ABS | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| SHARE | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| COUNTRY | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| EFF | OWN_FINAL_DECISION_CALIBRATION_RHO_UNIDENTIFIABLE |
| RISK_POWER | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| RISK_EXP | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| MATERIAL | RETRAINED_SEPARATE_PRODUCTS |
| MATERIAL_PROP | RETRAINED_SEPARATE_PRODUCTS |
| INTEREST | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| RD | RETRAINED_FORMAL4_CURVES |
| OPS | RETRAINED_FORMAL4_CURVES |
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
| rd/复合梁 | 0.000157199424 | 0.00435660712 |
| rd/连接件 | 0.000131109867 | 0.00372317392 |
| operations/泰国 | 0.000137093795 | 0.00111272163 |

三条曲线各200点，正式4市场5上期研发1000/400、运营600千美元；其他市场曲线共享未独立证实。横轴为取整有效投入，图形误差不是经营精度。

| 风险形式 | 有效样本 | 整市场留出MAE，基点 |
|---|---:|---:|
| solvency_exponential | 92 | 1.36977 |
| leverage_power | 92 | 1.24538 |

材料复合梁：100条，选型additive，选型留出MAE 2.55784千美元；选型误差不是嵌套独立检验。

材料连接件：89条，选型additive，选型留出MAE 0.265988千美元；选型误差不是嵌套独立检验。

解雇规则100项、生产环境600项及物流恒等式400项：失败0/0；容差传播原显示精度。

## 当前全部问题与不足

- 决策依赖模型缺竞争队最终输入；EFF/A/D完整运营机制及历史投入仍不可识别。
- 工资回溯使用实际产量/人数/产能，不解决生产预测、投资生效及跨期效应。
- 风险、材料同期模型及曲线跨市场共享缺独立前向验证；新旧比较仅条件误差，不表明事前收益改善。

## 因缺乏数据而无法验证的问题

- 99队正式4产品/国别最终决策；完整运营/研发存量、自动有效投入横轴。
- 真实确认订单、交付、预收与余款、税亏及正式5–6经营状态链。
- 本版本不部署、不输出完整利润排名；旧模型及原始证据保留。

[数据缺口](data_gaps.json)；[新旧比较](old_new_comparison.json)；[逐项验收](checks.json)。

## 初值边界与追加核验

正式4已知参数、九子页初值证据及结转分类另存 initial_*.json。只有直接披露的期初量标为期初；上年参考不改称期初现金或完整存量。本组21项实际交叉核验通过。

材料模型嵌套整市场留出重新在各训练折选型，明细位于注册表 materials.*.nested_market_validation；风险留出参数范围记录为敏感性，不是置信区间。

| 产品 | 材料嵌套留出MAE，千美元 | 工资整市场MAE，千美元 |
|---|---:|---:|
| 复合梁 | 2.55784 | 0.263871 |
| 连接件 | 0.266364 | 0.11593 |

## 独立曲线图

![正式4 rd/复合梁 原点与拟合](figures/formal4_curve_1.svg)

![正式4 rd/连接件 原点与拟合](figures/formal4_curve_2.svg)

![正式4 operations/泰国 原点与拟合](figures/formal4_curve_3.svg)

## 20项问题的本次状态

| 编号 | 问题 | 状态 | 影响与证据 | 下一项所需证据/处理 |
|---|---|---|---|---|
| 1 | 需求系数与正则 | 暂停 | 竞争队最终输入缺失，不能选参 | 补99队最终输入后做训练内选参与嵌套留出 |
| 2 | 损失尺度统一 | 沿用未新验证 | 需求未重训，不新增尺度等价结论 | 补输入后核验加权尺度 |
| 3 | 极端价格影响 | 未新验证 | 本组售价不足以识别价格函数 | 补同竞争集合售价及投入 |
| 4 | 共变及内生性 | 未解决 | 费用/投入关联不是因果收益 | 补独立变化及完整决策 |
| 5 | 国别产品投入 | 部分 | 本组29项最终决策有效，99队缺失 | 补采核验其他队国别产品最终决策 |
| 6 | 零需求与损失形式 | 暂停 | 未用零销量替代需求，需求拟合暂停 | 补决策后保留真实零需求检验 |
| 7 | 行业总量机制 | 部分 | 40组实际总量及增长已核，非预测训练 | 补独立行业机制及时间外标签 |
| 8 | 条件回溯与事前验证 | 部分 | 候选未采用，事前评分0；新误差仅条件回溯 | 需匹配生效方案的结算前冻结预测 |
| 9 | 投入延续及完整存量 | 不可识别 | 本组效率每个rho有对应theta | 补历史最终投入及有效横轴映射 |
| 10 | 曲线及市场适用 | 部分 | 市场5正式4三曲线600点已重拟合 | 补其他市场同回合曲线或共享规则 |
| 11 | 研发有效横轴外推 | 部分 | 曲线保存范围，自动支出映射未知 | 补有效投入原横坐标及机制 |
| 12 | 效率与低投入范围 | 不可识别 | 仅本组最终投入可用于效率校准 | 补多个独立最终投入及效率样本 |
| 13 | 风险利率及稳定性 | 部分 | 92状态重拟合，保存10市场折参数范围 | 补事前计息状态与独立后续结果 |
| 14 | 当期给定常数 | 部分 | 正式4公布参数归档、5%基准单独匹配 | 补实际生效时点及跨市场同值依据 |
| 15 | 材料差额及舍入 | 部分 | 100/89样本及嵌套市场留出保存 | 残差不宣称机制已识别；补采购精度 |
| 16 | 完整财务预测 | 未解决 | 1900财务等式是源结果验收 | 需期初/决策到财务独立前向复算 |
| 17 | 库存订单投资时序 | 未解决 | 规则自检、容量上界不等于生命周期训练 | 补合同交付预收/余款及真实投资时点 |
| 18 | 剩余回合收益 | 暂停 | 完整正式5/6状态链缺失 | 补链后再比较5至6新增收益 |
| 19 | 压力与保证 | 未验证 | 本任务未优化收益，不报告盈利保证 | 完整预测链后核边界组合压力 |
| 20 | 版本与输入混用 | 本次检查通过 | 正式4专属数据、哈希及决策来源验证 | 后续保留独立来源、回合和截止点 |
