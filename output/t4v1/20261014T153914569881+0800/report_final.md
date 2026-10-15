# t4v1 正式3全部模型更新验收

北京时间运行：20261014T153914569881+0800。
已执行用户追加授权“先全部以实际值训练”。全部31类逐项交付：可估计项训练；确定规则核验；未识别或未过门槛项明确保留状态。
本组决策来自已采集的正式3小组最终决策，其他队使用正式3实际结果。正式2期末配正式3期初，真实正式3终值作为标签。
权威参数注册表为 models_full.json；原训练阶段 models.json 和 manifest.json 保留。

## 验收结果

双产品需求保存参数复算、整市场训练/测试隔离、份额守恒通过；三条曲线600点的JSON/SVG与交错留点验收通过。
500项源财务等式通过；生产环境/物流公式1000项，解聘费100项，失败数分别为0/0。分产品工资样本：{'复合梁': 100, '连接件': 87}
A类环境校准与D类跨期残差均已执行；连接件固定生产、库存/订单情景及联合分配自检通过。完整六回合利润和订单状态不在通过结论内。

| 产品 | SHARE嵌套MAE pp | 泰国独立MAE pp | 印尼独立MAE pp |
|---|---:|---:|---:|
| 复合梁 | 0.793234 | 0.832297 | 0.796301 |
| 连接件 | 2.602759 | 3.023460 | 2.441329 |

上述为同期已实现竞争输入和行业总量的条件验证；投入合计代理不可用来声称国别/产品投入优化。

## 风险及利率留出误差

| 函数 | 有效样本 | 整市场MAE（基点） |
|---|---:|---:|
| solvency_exponential | 93 | 32.1094 |
| leverage_power | 93 | 8.7825e+06 |

杠杆幂函数留出出现极端外推误差。上述均依赖已实现期末资产负债；不直接用于未来利率推荐。

## 全部模型状态

| 模型 | 状态 |
|---|---|
| ABS | RETRAINED_SEPARATE_PRODUCTS_COMPANY_TOTAL_PROXIES |
| SHARE | RETRAINED_SEPARATE_PRODUCTS_COMPANY_TOTAL_PROXIES |
| COUNTRY | RETRAINED_SEPARATE_PRODUCTS_COMPANY_TOTAL_PROXIES |
| EFF | RETRAINED_SEPARATE_PRODUCT_MARKET_HOLDOUTS |
| RISK_POWER | RETRAINED_CONDITIONAL_NO_FORWARD_VALIDATION |
| RISK_EXP | RETRAINED_CONDITIONAL_NO_FORWARD_VALIDATION |
| MATERIAL | RETRAINED_SEPARATE_PRODUCTS |
| MATERIAL_PROP | RETRAINED_SEPARATE_PRODUCTS |
| INTEREST | RETRAINED_CONDITIONAL_NO_FORWARD_VALIDATION |
| RD | RETRAINED_CURVE_200_POINTS_PER_SERIES |
| OPS | RETRAINED_CURVE_200_POINTS_PER_SERIES |
| TOTAL | ACTUAL_TOTAL_DIAGNOSTICS_NOT_PREDICTIVE_TRAINING |
| BASELINE | ACTUAL_TOTAL_DIAGNOSTICS_NOT_PREDICTIVE_TRAINING |
| GROWTH | ACTUAL_TOTAL_DIAGNOSTICS_NOT_PREDICTIVE_TRAINING |
| CAPACITY | RULE_DIAGNOSTICS_WITH_EXPLICIT_GAPS |
| LABOR | RULE_DIAGNOSTICS_WITH_EXPLICIT_GAPS |
| OPERATING | RULE_DIAGNOSTICS_WITH_EXPLICIT_GAPS |
| FINANCE | RULE_DIAGNOSTICS_WITH_EXPLICIT_GAPS |
| HORIZON | BLOCKED_INCOMPLETE_ROUNDS_4_TO_6_STATE_CHAIN |
| METRICS | SOURCE_AND_SELF_CHECKS_PASS |
| UNIFIED | COMPOSITION_MAPPED_TO_T4V1_SEPARATE_PRODUCT_REGISTRY |
| T2V0 | COMPOSITION_MAPPED_TO_T4V1_SEPARATE_PRODUCT_REGISTRY |
| A | RESEARCH_REFIT_SAVED |
| B | PUBLISHED_SEVERANCE_RULE_100_CHECKS_PASS |
| C | RETRAINED_SEPARATE_PRODUCT_CONDITIONAL_WAGE |
| D | RETRAINED_FORMAL2_TO_FORMAL3_RESEARCH_NOT_DEPLOYED |
| E | KNOWN_INTENSITY_FORMULAS_ALL_CHECKS_PASS |
| F | KNOWN_INTENSITY_FORMULAS_ALL_CHECKS_PASS |
| CONNECTOR | EXISTING_RULE_SELF_CHECK_PASS_ACTUAL_TRAINING_SCOPE_LIMITED |
| CONNECTOR_V2 | EXISTING_RULE_SELF_CHECK_PASS_ACTUAL_TRAINING_SCOPE_LIMITED |
| JOINT_ALLOCATION | EXISTING_RULE_SELF_CHECK_PASS_ACTUAL_TRAINING_SCOPE_LIMITED |

## 当前全部问题与不足

- 实际归档10市场、100队、150/150页；全部纳入。
- 有效需求记录：{'复合梁': 200, '连接件': 176}；零售价/零需求记录保留为范围外，不加伪小数。
- 营销与研发是公司合计代理，未拆成国别/产品因果投入；本组最终决策4条产品国别配对和7项交叉核验通过。
- 风险/利率有效状态93项；极端杠杆外推与利率来源冲突仍限制部署。
- 基准利率叙述5%与参数表4%冲突仍待补证；本次使用参数表4%。
- A类校准状态：RESEARCH_REFIT_SAVED；D类正式2→3残差100条，仍为条件研究。
- 期初/期末未知税亏、完整研发/运营存量、订单与跨期财务不补零。正式4曲线没有进入训练。
- 冻结果与实际小组方案不匹配，事前评分0项；新误差不冒充事前成绩。

## 因缺乏数据而无法验证的问题

- 其他队分产品/国别最终营销研发、连接件初始价格与早期技术状态。
- 完整税亏、累计投入、确认订单及预收、未来回合前景与完整状态结转。

新旧条件比较见 old_new_comparison.json/CSV。缺失项、范围外行、舍入与来源详见 dataset.json。
原件、旧模型和冻结结果保留；未填写决策、未提交平台、未部署。
