# t5v0a：正式5非重训应用调整

2026-10-15（北京时间）。按用户“基于建议调整模型、不是重训、缺少数据先跳过、保存t5v0a”执行。不要输出真名，姓名统一用首字母替代。

已保存独立[注册表](models_full.json)，保留t5v0所有训练系数、正式4训练曲线及29类历史状态。应用回合为正式5，新增应用曲线完整复用已保存的t5v0回合5曲线。本次未调用拟合、训练、选型或平台操作，无新增经营预测精度成绩。

## 建议落实结果

| 模块 | 本次已调整 | 假设、限制与跳过项 |
| --- | --- | --- |
| TOTAL／BASELINE／GROWTH | 基准改为正式4市场5两产品两国实际总量，记录泰国+7%、印尼−5%建筑前景；支持显式两产品两国增速情景 | 建筑到产品需求映射未知，默认不计算需求总量；不假定两产品同增速；没有自设不利幅度 |
| MATERIAL／MATERIAL_PROP | 材料基价690／9.30美元；保留公布价、加法及比例三种情景，生产量给定后同步计算材料费 | 不重新选型；修正跨价迁移未验证，三情景是机制比较而非置信区间 |
| LABOR／EFF／OPS | 工资43.50千美元/人、班次1.65/2.56、离职10%与解聘35%进入固定产量情景；运营曲线换为正式5已有曲线 | 效率必须显式给定，运营乘数不直接变成绝对效率；rho、存量和自动投入映射跳过 |
| OPERATING／FINANCE | 行政基础费10000千美元，较正式4税前增量−4000千美元；42项公布参数完整保存 | 不把前景增加400万与基础费重复叠加；现金影响、税后利润、付款时点未知，不补零 |
| SHARE／COUNTRY／ABS | 保留历史模型、暂停状态及主次用途，不新调系数 | 缺99队正式4最终决策与当前竞争行为，需求响应调整跳过；不以旧份额响应冒充回合5预测 |
| RD | 正式5两产品曲线支持有效坐标求值，核验上期实际900/1300千美元 | 仅市场5 PYT情境、限定横轴范围；不自动叠加历史研发，不推断延期收益 |
| CONNECTOR | 期初库存202.40千单位接入订单前生产及两国优先配送；使用当期材料、工资、运费和持有费 | 须显式给定需求/价格/效率/生产；无新招标设为False。历史合同、库存账面价值、收付款未齐，V2及联合完整优化跳过 |
| CAPACITY | 机器价格78／1.10美元及归档的零投资产能投影保存为条件证据 | 投影不是无条件期初资产；不推断投资生效时点或扩产收益 |
| RISK／INTEREST | 基准5%、冻结风险溢价及短贷3.50个百分点分开；仅对范围内显式财务状态求值 | 杠杆幂函数仍禁止应用；不推定未来计息状态、融资量或最低现金，现金压力结果跳过 |
| HORIZON | 评价窗口改为正式5—6，两回合 | 正式6前景、税亏和完整现金链未知，剩余利润保持null，不输出排名 |

## 材料迁移数值

单位：美元/单位。费用（千美元）=产量（千单位）×单位成本。公布价为无经验修正基准；后两列直接保留t5v0冻结系数。

| 产品 | 公布价 | 固定加价保持 | 比例修正保持 |
| --- | ---: | ---: | ---: |
| 复合梁 | 690.000000000 | 691.453410659 | 690.952377355 |
| 连接件 | 9.300000000 | 9.319726472 | 9.312919450 |

## 调用和输入

[运行说明](../../../code/model_v2/t5v0a_README.md)；[最小请求](example_request.json)与[结果](example_result.json)将未知项保留为空。这是模型应用交付，不是当前个人方案或全参数优化候选，无平台推荐值。

请求头：version=t5v0a、market_id=5、phase=formal、round=5。全部可选输入如下；不提供时跳过相应计算，不默认继承旧草稿。

| 字段 | 内容及单位 |
| --- | --- |
| production | 产品→capacity_kunits、production_kunits、previous_workers、efficiency_kunits_per_person；efficiency_basis=EXPLICIT_SCENARIO。数量千单位、人数人、效率千单位/人 |
| curve_coordinates | 曲线键rd/复合梁、rd/连接件或operations/泰国→effective_x_kusd与context；context须包含market_id=5、area=PYT、phase=formal、round=5、previous_input=900/1300/750、unit=千美元、coordinate_kind=effective_investment_scenario |
| financial_state | equity、assets、long_debt、short_debt，均为同一显式状态下的千美元数值；不代表已核验计息状态 |
| product_growth | 两产品→两国→小数增速；基于正式4实际总量的显式假设，不自动应用建筑前景 |
| connector | product包含capacity（千单位）、efficiency（千单位/人）、demand（两国千单位）、prices（两国美元/单位）；另给allocation_pct、country_priority、material_form（published/additive/proportional）与scope=BEFORE_UNVERIFIED_ORDERS |

连接件贡献是收入减当期材料、工资、运费及假设持有费；未扣期初库存账面成本，不是利润或现金流，不能据此排名。库存数量测试使用合成需求/售价，不是实际销售预测。

## 逐类状态（29类）

“条件应用调整”只表示已接入相应公布输入、显式计算或期限约束，不表示该模块完整可预测或优化成功；历史训练状态不改写为本次训练。

| 类别 | 本次动作 | 历史状态（保持） |
| --- | --- | --- |
| ABS | 缺数据跳过 | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| SHARE | 缺数据跳过 | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| COUNTRY | 缺数据跳过 | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| EFF | 缺数据跳过 | OWN_FINAL_DECISION_CALIBRATION_RHO_UNIDENTIFIABLE |
| RISK_POWER | 沿用历史证据 | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| RISK_EXP | 条件应用调整 | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| MATERIAL | 条件应用调整 | RETRAINED_SEPARATE_PRODUCTS |
| MATERIAL_PROP | 条件应用调整 | RETRAINED_SEPARATE_PRODUCTS |
| INTEREST | 条件应用调整 | RETRAINED_CONDITIONAL_ACTUAL_STATE |
| RD | 条件应用调整 | RETRAINED_FORMAL4_CURVES |
| OPS | 条件应用调整 | RETRAINED_FORMAL4_CURVES |
| TOTAL | 条件应用调整 | ACTUAL_TOTALS_AND_GROWTH_DIAGNOSTICS_NOT_SUPERVISED_FIT |
| BASELINE | 条件应用调整 | ACTUAL_TOTALS_AND_GROWTH_DIAGNOSTICS_NOT_SUPERVISED_FIT |
| GROWTH | 条件应用调整 | ACTUAL_TOTALS_AND_GROWTH_DIAGNOSTICS_NOT_SUPERVISED_FIT |
| CAPACITY | 条件应用调整 | OWN_ACTUAL_CAPACITY_BOUND_CHECKED_TIMING_UNRESOLVED |
| LABOR | 条件应用调整 | CONDITIONAL_WAGE_FIT_IDENTIFIABILITY_RECORDED |
| OPERATING | 条件应用调整 | SOURCE_EXPENSE_ACCOUNTING_ONLY_NOT_FORWARD_PROFIT_MODEL |
| FINANCE | 条件应用调整 | 1900_SOURCE_EQUATIONS_ACCEPTED_NO_COMPLETE_FORWARD_FORECAST |
| HORIZON | 条件应用调整 | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| METRICS | 沿用历史证据 | SOURCE_HASH_AND_DECISION_GUARDS_CHECKED |
| A | 缺数据跳过 | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| B | 沿用历史证据 | PUBLISHED_RULE_CHECKED_WITH_DISPLAY_INTERVALS |
| C | 沿用历史证据 | CONDITIONAL_WAGE_FIT_IDENTIFIABILITY_RECORDED |
| D | 缺数据跳过 | BLOCKED_MISSING_CAPTURED_COMPETITOR_FINAL_DECISIONS_OR_HISTORY |
| E | 沿用历史证据 | ACTUAL_INTENSITY_FORMULA_CHECKED |
| F | 沿用历史证据 | ROUTE_FORMULA_CHECKED_WITH_MISSING_ROWS_RECORDED |
| CONNECTOR | 条件应用调整 | RULE_SELF_CHECK_ONLY_NO_ACTUAL_LIFECYCLE_TRAINING |
| CONNECTOR_V2 | 缺数据跳过 | RULE_SELF_CHECK_ONLY_NO_ACTUAL_LIFECYCLE_TRAINING |
| JOINT_ALLOCATION | 缺数据跳过 | RULE_SELF_CHECK_ONLY_NO_ACTUAL_LIFECYCLE_TRAINING |

## 公布参数（原页面行顺序，42项）

单位保留在原标签及[完整参数来源](models_full.json)的原始分区中；同行重复标签按源行/分区区分。此表为外生条件，不是可控决策建议。

| 源表行号（从0起） | 参数 | 正式4参考值 | 正式5公布值 |
| --- | --- | ---: | ---: |
| 3 | 1 美元 = | 1 美元 | 1 美元 |
| 5 | 企业所得税率, % | 29.00 | 29.00 |
| 6 | 最低现金, 千 美元 | 2 000 | 2 000 |
| 8 | 基准利率 | 5.00 | 5.00 |
| 9 | 高于基准的短期利率溢价 | 3.00 | 3.50 |
| 10 | 现金及现金等价物 | 1.00 | 1.00 |
| 12 | 机器 | 15.00 | 15.00 |
| 14 | 市场调研 | 50 | 50 |
| 15 | 固定库存持有成本 | 0.00 | 0.00 |
| 17 | 基础成本 | 6 000 | 10 000 |
| 18 | 复合梁, 泰国 | 0 | 0 |
| 19 | 复合梁, 印尼 | 0 | 0 |
| 20 | 连接件, 泰国 | 0 | 0 |
| 21 | 连接件, 印尼 | 0 | 0 |
| 23 | 库存持有成本 | 0.60 | 0.60 |
| 25 | 复合梁 | 1 053.00 | 690.00 |
| 26 | 连接件 | 14.20 | 9.30 |
| 28 | 泰国 -> 泰国 | 30.00 | 30.00 |
| 29 | 泰国 -> 印尼 | 120.00 | 120.00 |
| 31 | 泰国 -> 泰国 | 0.50 | 0.50 |
| 32 | 泰国 -> 印尼 | 2.00 | 2.00 |
| 35 | 泰国 | 33.00 | 43.50 |
| 37 | 两班倒 | 1.65 | 1.65 |
| 38 | 三班倒 | 2.56 | 2.56 |
| 40 | 年人员离职率（without costs），% | 10.00 | 10.00 |
| 41 | 裁员成本，占薪资% | 35.00 | 35.00 |
| 44 | 机器, 复合梁 | 58.00 | 78.00 |
| 45 | 机器, 连接件 | 1.00 | 1.10 |
| 47 | 机器 | 15.00 | 15.00 |
| 50 | 每单位碳排放, kg, 泰国 | 1 355.32 | 1 355.32 |
| 51 | 每单位能源消耗, kWh, 泰国 | 4 778.38 | 4 778.38 |
| 52 | 每单位用水量, l, 泰国 | 10 307.14 | 10 307.14 |
| 54 | 每单位碳排放, kg, 泰国 | 2.30 | 2.30 |
| 55 | 每单位碳排放, kg, 分包制造 | 0.00 | 0.00 |
| 56 | 每单位能源消耗, kWh, 泰国 | 7.89 | 7.89 |
| 57 | 每单位能源消耗, kWh, 分包制造 | 0.00 | 0.00 |
| 58 | 每单位用水量, l, 泰国 | 18.56 | 18.56 |
| 59 | 每单位用水量, l, 分包制造 | 0.00 | 0.00 |
| 62 | 泰国 -> 泰国 | 3 920.5 | 3 920.5 |
| 63 | 泰国 -> 印尼 | 47 084.4 | 47 084.4 |
| 65 | 泰国 -> 泰国 | 6.2 | 6.2 |
| 66 | 泰国 -> 印尼 | 74.5 | 74.5 |

## 验收及证据

[验收](acceptance.json)：23份来源哈希一致，全部冻结系数和29类历史状态一致，正式5已有曲线逐项一致；材料三情景、工资/班次/解聘缩放、利率分解、零产量消化库存、国别情景及未知收益不补零通过，34项非法输入被拒绝。运行期禁止训练调用的保护通过。本次无重新训练或实时平台核验。

来源：[t5v0正式4训练](../../t5v0/20261015T085218049188+0800/report_final.md)、[正式5已知条件](../../round_close/20261014_formal4_close/formal5_initial/report.md)、[已保存的正式5曲线](../../t5v0/20261015T090943259882+0800_formal5_curves/report.md)、[材料诊断](../../t5_material_diagnosis/20261015T091215236523+0800/report.md)。引用聊天建议来源ID记录于[工作日志](work_log.md)。

文档先备份当前磁盘内容再更新，已有未提交修改未回退；[改前/改后哈希](document_hashes.json)。[代码与输出清单](version_manifest.json)保存运行环境和哈希；包内历史artifact仍依赖本项目归档。
