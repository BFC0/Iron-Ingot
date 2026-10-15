# EFF · 生产效率与运营延续模型

更新：2026-10-14（北京时间）。本文按所列版本维护专题内容；项目当前状态与最新证据统一见[项目总览](../README.md)。历史公式、参数和误差保留各自版本范围；具体进展在所属主题维护。

历史参数核对日期：2026-10-12（北京时间）。每类模型独立说明；其保存版本在本页分列，不混合参数。

参数说明：[输入类别、参数含义与训练口径](预测模型与训练参数汇总.md)；[逐回合给定参数与期限](参数细化与六回合期限要求.md)。

版本关联：[全部保存版本及来源](训练拟合模型与版本清单.md)；[全部模型文档索引](模型说明/README.md)。

**主题导航：** [当前证据与使用边界](#当前证据与使用边界) · [适用版本与限制](#适用版本与限制) · [公式](#公式) · [输入变量（字母与文字描述）](#输入变量字母与文字描述) · [输出变量（字母与文字描述）](#输出变量字母与文字描述) · [参数定义与取值](#参数定义与取值) · [实现与原始参数来源](#实现与原始参数来源) · [已保存主版本的完整精度参数](#已保存主版本的完整精度参数)

## 当前证据与使用边界

t4v1基线为O3+ρO2。独立历史候选使用O3+ρO2+ρ²O1，连接件留出逐队MAPE从0.953284%降至0.194342%，复合梁从0.863225%降至0.191008%；见[连接件候选报告](../output/t4v1_connector_optimization/20261014T162353579815+0800/report.md)。本组10情景已单独恢复，见[本组效率情景](../output/own_efficiency_scenarios/20261014T170508965934+0800/report.md)；单观测不能识别ρ。[ρ局部参考](../output/efficiency_rho_local_reference/20261014T171500629011+0800/report.md)仅其他9市场数值细化，不更新注册表。正式4成本比较保持正式3效率响应，不等于前向效率预测。

## 适用版本与限制

实际标签q/N。均值、策略等权均值、加权最小二乘各有保存版本；t2v0-um练习2效率尚未实际重训。

下标：i/j为队伍，c为国家（TH泰国、ID印尼），m为编号市场，h为阶段，t为回合；0为期初，t−1为上一回合；帽号表示预测，不能当作已实现实际值。

## 公式

`η̂=θ f_O(O_t+ρ_O O_t−1)`

`训练实际效率：η_obs=q_actual/N_actual`

## 输入变量（字母与文字描述）

| 字母符号 | 文字描述 | 单位 | 输入类别/来源 |
| --- | --- | --- | --- |
| O_t | 当期运营投入 | 千美元 | 可控决策；对手对应值为情景假设 |
| O_t−1 | 上期实际运营投入 | 千美元 | 历史实际输入 |
| f_O | 绑定回合的运营乘数函数 | 函数 | 已拟合曲线依赖 |

## 输出变量（字母与文字描述）

| 字母符号 | 文字描述 | 单位 | 输出类别 |
| --- | --- | --- | --- |
| η̂ | 预测生产效率，即人均产量 | 千单位/人 | 不确定模型输出 |

## 参数定义与取值

| 参数字母/字段 | 文字描述 | 值或取值位置 | 类别 |
| --- | --- | --- | --- |
| θ | 技术生产尺度 | theta / technology_scale / strategy_balanced_scale | 训练参数，不同估计器不得合并 |
| ρ_O | 运营历史延续权重 | 按rho字段；unified-market正式1为0.562 | 假设或网格训练选择值 |

## 实现与原始参数来源

- [code/operations_rho.py](code/operations_rho.py)
- [code/model_v2/finance.py](code/model_v2/finance.py)

## 已保存主版本的完整精度参数

下表保留原参数字段及数组顺序；本页上方给出字母映射。配置与训练参数分别列示；本页不自动选定部署版本。

| 版本名称与JSON定位 | 参数值（完整精度） | 配置/假设 | 参数原档 |
| --- | --- | --- | --- |
| 20261011T225637591747+0800_training/models::/operations/rho/chosen | {"theta":0.1700719928621304} | {"rho":0.558} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225637591747+0800_training/models::/operations/rho/parameter_change | {"theta":5.957661841332618e-06} | {"rho":-0.0010000000000000009} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225637591747+0800_training/models::/operations/rho/strategy_cv/0/fitted | {"theta":0.17007123084303244} | {"rho":0.558} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225637591747+0800_training/models::/operations/rho/strategy_cv/1/fitted | {"theta":0.17006197279184468} | {"rho":0.559} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225637591747+0800_training/models::/operations/rho/strategy_cv/2/fitted | {"theta":0.1700690591845081} | {"rho":0.558} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225637591747+0800_training/models::/operations/rho/strategy_cv/3/fitted | {"theta":0.17007134462874904} | {"rho":0.558} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225637591747+0800_training/models::/operations/rho/strategy_cv/4/fitted | {"theta":0.17007339897651733} | {"rho":0.558} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225637591747+0800_training/models::/operations/rho/strategy_cv/5/fitted | {"theta":0.17007281644984598} | {"rho":0.558} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225637591747+0800_training/models::/operations/rho/strategy_cv/6/fitted | {"theta":0.17005732401651494} | {"rho":0.559} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/chosen | {"theta":0.1700719928621304} | {"rho":0.558} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/parameter_change | {"theta":5.957661841332618e-06} | {"rho":-0.0010000000000000009} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/strategy_cv/0/fitted | {"theta":0.17007123084303244} | {"rho":0.558} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/strategy_cv/1/fitted | {"theta":0.17006197279184468} | {"rho":0.559} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/strategy_cv/2/fitted | {"theta":0.1700690591845081} | {"rho":0.558} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/strategy_cv/3/fitted | {"theta":0.17007134462874904} | {"rho":0.558} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/strategy_cv/4/fitted | {"theta":0.17007339897651733} | {"rho":0.558} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/strategy_cv/5/fitted | {"theta":0.17007281644984598} | {"rho":0.558} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho/strategy_cv/6/fitted | {"theta":0.17005732401651494} | {"rho":0.559} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/chosen | {"theta":0.1700719928621304} | {"rho":0.558} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/parameter_change | {"theta":5.957661841332618e-06} | {"rho":-0.0010000000000000009} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/strategy_cv/0/fitted | {"theta":0.17007123084303244} | {"rho":0.558} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/strategy_cv/1/fitted | {"theta":0.17006197279184468} | {"rho":0.559} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/strategy_cv/2/fitted | {"theta":0.1700690591845081} | {"rho":0.558} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/strategy_cv/3/fitted | {"theta":0.17007134462874904} | {"rho":0.558} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/strategy_cv/4/fitted | {"theta":0.17007339897651733} | {"rho":0.558} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/strategy_cv/5/fitted | {"theta":0.17007281644984598} | {"rho":0.558} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho/strategy_cv/6/fitted | {"theta":0.17005732401651494} | {"rho":0.559} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T194918540163+0800/mechanisms::/efficiency/0 | {"technology_scale":0.18232093157325216,"strategy_balanced_scale":0.1810482100950491} | {"rho":0,"train_n":10} | [原档](output/model_v2/20261011T194918540163+0800/mechanisms.json) |
| 20261011T194918540163+0800/mechanisms::/efficiency/1 | {"technology_scale":0.17569399747166478,"strategy_balanced_scale":0.17514344754770406} | {"rho":0.25,"train_n":10} | [原档](output/model_v2/20261011T194918540163+0800/mechanisms.json) |
| 20261011T194918540163+0800/mechanisms::/efficiency/2 | {"technology_scale":0.17097560695565167,"strategy_balanced_scale":0.170900229762634} | {"rho":0.5,"train_n":10} | [原档](output/model_v2/20261011T194918540163+0800/mechanisms.json) |
| 20261011T194918540163+0800/mechanisms::/efficiency/3 | {"technology_scale":0.1674409289011259,"strategy_balanced_scale":0.16769382826695609} | {"rho":0.75,"train_n":10} | [原档](output/model_v2/20261011T194918540163+0800/mechanisms.json) |
| 20261011T194918540163+0800/mechanisms::/efficiency/4 | {"technology_scale":0.16469212506098896,"strategy_balanced_scale":0.1651807882266988} | {"rho":1,"train_n":10} | [原档](output/model_v2/20261011T194918540163+0800/mechanisms.json) |
| 20261011T204411978414+0800/mechanisms::/efficiency/0 | {"technology_scale":0.18232093157325216,"strategy_balanced_scale":0.1810482100950491} | {"rho":0,"train_n":10} | [原档](output/model_v2/20261011T204411978414+0800/mechanisms.json) |
| 20261011T204411978414+0800/mechanisms::/efficiency/1 | {"technology_scale":0.17569399747166478,"strategy_balanced_scale":0.17514344754770406} | {"rho":0.25,"train_n":10} | [原档](output/model_v2/20261011T204411978414+0800/mechanisms.json) |
| 20261011T204411978414+0800/mechanisms::/efficiency/2 | {"technology_scale":0.17097560695565167,"strategy_balanced_scale":0.170900229762634} | {"rho":0.5,"train_n":10} | [原档](output/model_v2/20261011T204411978414+0800/mechanisms.json) |
| 20261011T204411978414+0800/mechanisms::/efficiency/3 | {"technology_scale":0.1674409289011259,"strategy_balanced_scale":0.16769382826695609} | {"rho":0.75,"train_n":10} | [原档](output/model_v2/20261011T204411978414+0800/mechanisms.json) |
| 20261011T204411978414+0800/mechanisms::/efficiency/4 | {"technology_scale":0.16469212506098896,"strategy_balanced_scale":0.1651807882266988} | {"rho":1,"train_n":10} | [原档](output/model_v2/20261011T204411978414+0800/mechanisms.json) |
| OPERATIONS_RHO_V1/20261011T213127200793+0800/model::/chosen | {"theta":0.17006603520028907} | {"version":"OPERATIONS_RHO_V1","rho":0.559} | [原档](output/operations_rho/20261011T213127200793+0800/model.json) |
| OPERATIONS_RHO_V1/20261011T213127200793+0800/model::/baseline | {"theta":0.17088572199586327} | {"version":"OPERATIONS_RHO_V1","rho":0.5} | [原档](output/operations_rho/20261011T213127200793+0800/model.json) |
| OPERATIONS_RHO_V1/20261011T213127200793+0800/model::/strategy_cv/0/fitted | {"theta":0.17007728724559282} | {"version":"OPERATIONS_RHO_V1","rho":0.558} | [原档](output/operations_rho/20261011T213127200793+0800/model.json) |
| OPERATIONS_RHO_V1/20261011T213127200793+0800/model::/strategy_cv/1/fitted | {"theta":0.17006023017710592} | {"version":"OPERATIONS_RHO_V1","rho":0.56} | [原档](output/operations_rho/20261011T213127200793+0800/model.json) |
| OPERATIONS_RHO_V1/20261011T213127200793+0800/model::/strategy_cv/2/fitted | {"theta":0.1700571282131579} | {"version":"OPERATIONS_RHO_V1","rho":0.559} | [原档](output/operations_rho/20261011T213127200793+0800/model.json) |
| OPERATIONS_RHO_V1/20261011T213127200793+0800/model::/strategy_cv/3/fitted | {"theta":0.17013120820867644} | {"version":"OPERATIONS_RHO_V1","rho":0.555} | [原档](output/operations_rho/20261011T213127200793+0800/model.json) |
| OPERATIONS_RHO_V1/20261011T213127200793+0800/model::/round2_separate_fit_diagnostic | {"theta":0.169605991487711} | {"version":"OPERATIONS_RHO_V1","rho":0.5660000000000001} | [原档](output/operations_rho/20261011T213127200793+0800/model.json) |
| unified-market/20261012T114145124558+0800/models::/mechanisms/operations_efficiency/chosen | {"theta":0.17001715019534525} | {"model_id":"unified-market","phase":"formal","round":1,"rho":0.562} | [原档](output/unified-market/20261012T114145124558+0800/models.json) |
| STEPWISE_20261011T045441Z/分步模型拟合与验证::/efficiency/selected | {"technology_scale":0.17097560695565167} | {"rho":0.5} | [原档](分步模型拟合与验证.json) |

诊断子拟合、保存副本及候选评分关联：[全部参数位置与完整精度配置](output/model_catalog/20261012T122718963696+0800/model_versions.json)；[逐项定位清单](output/model_catalog/20261012T122718963696+0800/全部参数位置.md)。诊断系数不拼成部署参数。
