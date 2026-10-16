# 模型说明分类索引

更新：2026-10-15（北京时间）。本文按所列版本维护专题内容；项目当前状态与最新证据统一见[项目总览](../README.md)。历史公式、参数和误差保留各自版本范围；具体进展在所属主题维护。

## 当前模型和应用入口

[t5v0a正式5非重训应用](../code/model_v2/t5v0a_README.md)维护当期参数、条件计算及未解决项，保留t5v0全部训练系数。

[t5v0正式4训练与缺口](T5V0_正式4训练与缺口.md)维护最新可估计模型及29类状态；需求缺99队最终决策而暂停，旧需求基线独立保留。

[t4v1完整训练](T4V1_正式3完整数据训练.md)维护训练范围与复现；[t4v1a应用情景](T4V1A_正式4非重训应用情景.md)说明冻结参数应用与缺口。正式3参数查阅使用[去重29类注册表](../output/t4v1_deduplicated/20261014T162452595723+0800/models_full.json)，原训练和应用参数分别冻结保存。

历史UNIFIED/T2V0页面仍解释各自组合；从当前清单删除重复入口不删除历史功能。目录中的公式、参数与留出误差均按来源版本使用。

## 按业务主题查阅

### 需求与行业规模

| 类型 | 说明文档 |
| --- | --- |
| ABS | [ABS_绝对对数需求模型](ABS_绝对对数需求模型.md) |
| SHARE | [SHARE_双国竞争份额模型](SHARE_双国竞争份额模型.md) |
| COUNTRY | [COUNTRY_国别独立竞争份额模型](COUNTRY_国别独立竞争份额模型.md) |
| TOTAL | [TOTAL_行业总需求与增长情景](TOTAL_行业总需求与增长情景.md) |
| BASELINE | [BASELINE_等份额基线与实际总量诊断](BASELINE_等份额基线与实际总量诊断.md) |
| GROWTH | [GROWTH_下回合公司需求增长模型](GROWTH_下回合公司需求增长模型.md) |

### 投入响应与生产成本

| 类型 | 说明文档 |
| --- | --- |
| RD | [RD_研发需求乘数曲线](RD_研发需求乘数曲线.md) |
| OPS | [OPS_运营效率乘数曲线](OPS_运营效率乘数曲线.md) |
| EFF | [EFF_生产效率与运营延续模型](EFF_生产效率与运营延续模型.md) |
| CAPACITY | [CAPACITY_产能产量与交付模型](CAPACITY_产能产量与交付模型.md) |
| LABOR | [LABOR_用工班次工资与解聘模型](LABOR_用工班次工资与解聘模型.md) |
| MATERIAL | [MATERIAL_PROP_原材料单位费用比例模型](MATERIAL_PROP_原材料单位费用比例模型.md) |
| MATERIAL_PROP | [MATERIAL_PROP_原材料单位费用比例模型](MATERIAL_PROP_原材料单位费用比例模型.md) |

### 经营财务与期限评价

| 类型 | 说明文档 |
| --- | --- |
| OPERATING | [OPERATING_收入成本与经营利润模型](OPERATING_收入成本与经营利润模型.md) |
| FINANCE | [FINANCE_利息税利润现金与资产负债联立模型](FINANCE_利息税利润现金与资产负债联立模型.md) |
| INTEREST | [INTEREST_实际贷款利率独立模型](INTEREST_实际贷款利率独立模型.md) |
| RISK_POWER | [RISK_POWER_杠杆幂函数风险溢价模型](RISK_POWER_杠杆幂函数风险溢价模型.md) |
| RISK_EXP | [RISK_EXP_权益比指数风险溢价模型](RISK_EXP_权益比指数风险溢价模型.md) |
| HORIZON | [HORIZON_六回合剩余利润与候选比较](HORIZON_六回合剩余利润与候选比较.md) |
| METRICS | [METRICS_模型误差评价计算](METRICS_模型误差评价计算.md) |

### 连接件与联合分配

| 类型 | 说明文档 |
| --- | --- |
| CONNECTOR | [CONNECTOR_V2_库存订单及影响路径](CONNECTOR_V2_库存订单及影响路径.md) |
| CONNECTOR_V2 | [CONNECTOR_V2_库存订单及影响路径](CONNECTOR_V2_库存订单及影响路径.md) |
| T3V1 | [T3V1_同曲线假设与联合分配](T3V1_同曲线假设与联合分配.md) |

### 训练版本与历史组合

| 类型 | 说明文档 |
| --- | --- |
| T5V0 | [T5V0_正式4训练与缺口](T5V0_正式4训练与缺口.md)；含正式5独立曲线入口 |
| T4V1 | [T4V1_正式3完整数据训练](T4V1_正式3完整数据训练.md) |
| T4V0 | [T4V0_正式3实际训练](T4V0_正式3实际训练.md) |
| T3V0 | [T3V0_正式2重训及正式3附加曲线](T3V0_正式2重训及正式3附加曲线.md) |
| UNIFIED | [UNIFIED_unified-market正式1模型组合](UNIFIED_unified-market正式1模型组合.md) |
| T2V0 | [T2V0_t2v0-um练习2组件及正式2迁移组合](T2V0_t2v0-um练习2组件及正式2迁移组合.md) |

## 参数和流程的职责

[计算流程图](完整计算流程图.md)区分当前冻结应用和历史条件链；[变量说明](../预测模型与变量说明.md)维护符号与通用公式；[参数汇总](../预测模型与训练参数汇总.md)维护输入、参数、训练配置和误差分类；[版本统计](../模型版本重新统计.md)解释数量口径；[完整历史清单](../训练拟合模型与版本清单.md)保留参数ID及副本关系。

## 研究诊断与应用限制

- [正式4材料误差与舍入诊断](../output/t5_material_diagnosis/20261015T091215236523+0800/report.md)。
- [连接件价格和运营历史候选](../output/t4v1_connector_optimization/20261014T162353579815+0800/report.md)。
- [ABS与SHARE嵌套对照](../output/t4v1_abs_nested/20261014T170607791200+0800/report.md)。
- [本组效率情景](../output/own_efficiency_scenarios/20261014T170508965934+0800/report.md)。
- [其他9市场ρ细化参考](../output/efficiency_rho_local_reference/20261014T171500629011+0800/report.md)。

研究候选未部署，99队真实产品/国别投入、前向曲线横轴映射、订单实际状态及完整财务/剩余收益链仍缺。确定规则自检、曲线近似与同期留出不能代替独立后续回合成绩。
