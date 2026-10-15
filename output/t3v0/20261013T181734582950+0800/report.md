# t3v0 全模型更新报告

独立运行：20261013T181734582950+0800（北京时间）。
训练：正式2实际结果，10市场、100队、200条国别需求；初值绑定正式1期末，终值绑定正式2实际。正式2研发与运营曲线绑定原始哈希。
正式3曲线额外保存：研发图包含复合梁和连接件两条产品序列，运营图包含泰国序列；这些参数没有进入正式2训练。
同回合同国家跨市场共享系数仍属授权研究假设；未证明跨回合参数不变。连接件没有正式2实际训练标签，不生成其需求系数。

| 需求模型 | 嵌套整市场MAE，百分点 | 样本内MAE，百分点 | 研发延续ρ |
|---|---:|---:|---:|
| SHARE | 0.490747 | 0.447047 | 0.25 |
| COUNTRY/泰国 | 0.461361 | 0.428307 | 0.25 |
| COUNTRY/印尼 | 0.508711 | 0.466470 | 0.5 |

5个外层折各留2个整个市场；只在剩余市场内选参数，逐折计算尺度；两国等权。以上为同回合、给定已实现对手策略的条件验证，不是正式3事前预测成绩。
比较原始/标准化惩罚、线性/分段价格、5档研发延续、11档正则；share损失在训练内选出的log延续处比较，沿用现有分阶段选参。误差≤1%优先较少参数。ABS单列正需求研究，零需求不伪造小数。

| 正式3额外曲线 | 留点MAE | 留点最大误差 |
|---|---:|---:|
| rd/复合梁 | 0.000179103914 | 0.00540939642 |
| rd/连接件 | 0.000134074275 | 0.00146794956 |
| operations/泰国 | 9.23307085e-05 | 0.000726225628 |

每序列200点：偶数索引拟合、奇数索引核验，再全点拟合。横轴标签有取整误差；曲线成绩不是经营预测成绩。

计算流程：18168次需求拟合复用10份特征矩阵；逐折的标准化及优化仍独立。耗时19.397秒；没有据此声称相对旧流程的加速倍数。

| 模型 | 状态 |
|---|---|
| ABS | RETRAINED |
| SHARE | RETRAINED |
| COUNTRY | RETRAINED |
| EFF | RETRAINED |
| RISK_POWER | RETRAINED |
| RISK_EXP | RETRAINED |
| MATERIAL | RETRAINED |
| MATERIAL_PROP | RETRAINED |
| INTEREST | RETRAINED |
| RD | FORMAL2_BOUND_PLUS_SEPARATE_FORMAL3_FIT |
| OPS | FORMAL2_BOUND_PLUS_SEPARATE_FORMAL3_FIT |
| TOTAL | ACTUAL_DIAGNOSTICS_AND_EXPLICIT_SCENARIO |
| BASELINE | ACTUAL_DIAGNOSTICS_AND_EXPLICIT_SCENARIO |
| GROWTH | ACTUAL_DIAGNOSTICS_AND_EXPLICIT_SCENARIO |
| CAPACITY | RULE_REPLAY_WITH_EXPLICIT_GAPS |
| LABOR | RULE_REPLAY_WITH_EXPLICIT_GAPS |
| OPERATING | RULE_REPLAY_WITH_EXPLICIT_GAPS |
| FINANCE | RULE_REPLAY_WITH_EXPLICIT_GAPS |
| HORIZON | GUARDED_REMAINING_3_TO_6 |
| METRICS | SHARED_CALCULATION_CHECKED |
| UNIFIED | HISTORICAL_COMPOSITION_REPLACED_BY_T3V0_REGISTRY |
| T2V0 | HISTORICAL_COMPOSITION_REPLACED_BY_T3V0_REGISTRY |
| A | FORMAL2_GATED_REFIT_EVALUATED |
| B | PUBLISHED_SEVERANCE_RULE_REPLAYED |
| C | CONDITIONAL_WAGE_CANDIDATE_REFITTED |
| D | LAGGED_RESEARCH_REFIT_NOT_DEPLOYED |
| E | KNOWN_INTENSITY_FORMULA_CHECKED |
| F | KNOWN_INTENSITY_FORMULA_CHECKED |

研发/运营当期曲线、费用和历史投入明确绑定。效率保留有效投入代理，不冒充完整累计状态；风险与利率依赖实际期末状态，仅作条件关联。
工资候选已重新拟合；解聘费和环境/运输关系保留公布系数，避免把派生指标再训练成新证据。A类校准逐项按增量门槛决定是否保存研究参数，未通过项保留结果。
财务附加列不截取；缺失期初/期末字段保留null。实际损益恒等式通过并不证明完整财务预测、订单中标/预付款或六回合最优。
未操作平台、未自动部署、未覆盖冻结参数和旧运行；生产策略/库存、自动短贷仍按现有简化范围。

[完整参数](models.json) · [模型清单](model_inventory.json) · [初终值与原行列](dataset.json) · [来源哈希](input_manifest.json) · [验证](checks.json) · [计算流程](calculation_flow.json)

复现：`python code/model_v2/t3v0.py`；每次创建独立目录。自检：`python code/model_v2/t3v0.py --self-check`。
