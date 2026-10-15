# 正式4结转分类追加修正

不要输出真名，姓名统一用首字母替代。此次只更新分类，原数值和旧验收不覆盖。真正缺少同口径期初余额/持续状态等的UNKNOWN为27 项，之前46项包含不应结转的发生额和历史上下文。

| 状态 | 项数 |
|---|---:|
| CONDITIONAL_ZERO_INVESTMENT_PROJECTION | 2 |
| NOT_APPLICABLE_FLOW_NOT_CARRIED | 13 |
| OPENING_QUANTITY_MATCHED | 2 |
| PRIOR_CONTEXT_NOT_OPENING_INPUT | 3 |
| PRIOR_CUMULATIVE_BASELINE_NOT_OPENING_INPUT | 1 |
| PRIOR_REFERENCE_MATCHED_NOT_OPENING_BALANCE | 12 |
| UNKNOWN | 27 |

13 项当期费用/投入/资本支出/还本等标NOT_APPLICABLE_FLOW_NOT_CARRIED；已发生投资不重复加入，下期真实待生效投资仍在独立UNKNOWN项。3项历史现金/人员核对上下文和1项累计收益共同基准也不算缺失期初。12项上年投入/长债参考匹配，不冒称期初；2项库存数量匹配。2项容量仅为个人零投资场景投影核验。

27个真正UNKNOWN包含14个期末余额、1个人员状态、2个下一期订单承诺及10个未披露持续状态/税亏/待生效投资/产品独立价值等。正式4已获得订单栏本期为空，不能补成确认0；招标仍单独。

60唯一键、原hash未变、数值未变、没有费用当余额检查通过。正式3历史玩家预估/预算对照及费用交叉核验仍单列为非模型，不升级模型成绩。不训练，正式4当前草稿不标final。

首版字典分组汇总未读取status，汇总表错误；本版按解析对象分组修正，逐字段状态和数值未改。保留首版记录，入口采用本版。
