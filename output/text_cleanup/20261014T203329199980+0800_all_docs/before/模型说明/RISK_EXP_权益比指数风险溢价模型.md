# RISK_EXP · 权益比指数风险溢价模型

核对日期：2026-10-12（北京时间）。每类模型独立说明；其保存版本在本页分列，不混合参数。

参数说明：[输入类别、参数含义与训练口径](预测模型与训练参数汇总.md)；[逐回合给定参数与期限](参数细化与六回合期限要求.md)。

版本关联：[全部保存版本及来源](训练拟合模型与版本清单.md)；[全部模型文档索引](模型说明/README.md)。

## 公式

`π_r=a_r exp(−b_r E/A)`

`r_L=r_base+π_r`

## 输入变量（字母与文字描述）

| 字母符号 | 文字描述 | 单位 | 输入类别/来源 |
| --- | --- | --- | --- |
| E | 期末权益 | 千美元 | 历史实际或预测状态 |
| A | 期末资产总额 | 千美元 | 历史实际或预测状态 |
| r_base | 对应回合基准利率 | 小数 | 当期给定或明确假设 |

## 输出变量（字母与文字描述）

| 字母符号 | 文字描述 | 单位 | 输出类别 |
| --- | --- | --- | --- |
| π_r | 预测风险溢价 | 利率小数 | 不确定模型输出 |
| r_L | 预测长期贷款利率 | 利率小数 | 不确定模型输出 |

## 参数定义与取值

| 参数字母/字段 | 文字描述 | 值或取值位置 | 类别 |
| --- | --- | --- | --- |
| a_r | 风险幅度 | parameters[0] | 训练参数 |
| b_r | 风险形状 | parameters[1] | 训练参数 |
| r_base | 基准利率 | 正式1归档0.03；练习2归档0.025 | 当期给定输入，不是训练系数 |



## 适用版本与限制

各候选单独拟合；条件验证使用实际期末财务状态，事前使用预测状态并联立。E>0，指数版另需A>0；独立利率接口还核对债务一致性及训练范围。

下标：i/j为队伍，c为国家（TH泰国、ID印尼），m为编号市场，h为阶段，t为回合；0为期初，t−1为上一回合；帽号表示预测，不能当作已实现实际值。

## 实现与原始参数来源

- [code/interest_rate_model.py](code/interest_rate_model.py)
- [code/model_v2/finance.py](code/model_v2/finance.py)

## 已保存主版本的完整精度参数

下表保留原参数字段及数组顺序；本页上方给出字母映射。配置与训练参数分别列示；本页不自动选定部署版本。

| 版本名称与JSON定位 | 参数值（完整精度） | 配置/假设 | 参数原档 |
| --- | --- | --- | --- |
| 20261011T225637591747+0800_training/models::/finance/risk/solvency_exponential | {"parameters":[0.319945300704861,10.311067733079852]} | {} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/finance/risk/solvency_exponential | {"parameters":[0.319945300704861,10.311067733079852]} | {} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/finance/risk/solvency_exponential | {"parameters":[0.319945300704861,10.311067733079852]} | {} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T194918540163+0800/mechanisms::/risk/1 | {"parameters":[0.29481208768832323,10.139849774472733]} | {"form":"solvency_exponential"} | [原档](output/model_v2/20261011T194918540163+0800/mechanisms.json) |
| 20261011T204411978414+0800/mechanisms::/risk/1 | {"parameters":[0.29481208768832323,10.139849774472733]} | {"form":"solvency_exponential"} | [原档](output/model_v2/20261011T204411978414+0800/mechanisms.json) |
| unified-market/20261012T114145124558+0800/models::/mechanisms/risk/solvency_exponential | {"parameters":[0.3370146537049656,10.41618899063242]} | {"model_id":"unified-market","phase":"formal","round":1} | [原档](output/unified-market/20261012T114145124558+0800/models.json) |
| STEPWISE_20261011T045441Z/分步模型拟合与验证::/finance/risk_candidates/1 | {"parameters":[0.29481208768832323,10.139849774472733]} | {"form":"solvency_exponential"} | [原档](分步模型拟合与验证.json) |

诊断子拟合、保存副本及候选评分关联：[全部参数位置与完整精度配置](output/model_catalog/20261012T122718963696+0800/model_versions.json)；[逐项定位清单](output/model_catalog/20261012T122718963696+0800/全部参数位置.md)。诊断系数不拼成部署参数。

## 练习2专用组件值与来源

a_r、b_r = `[0.12281068318353833, 8.180868311208613]`；来源：[components.json](output/t2v0-um/20261012T181028387320+0800/components.json)，JSON定位 `/interest_rate`。
