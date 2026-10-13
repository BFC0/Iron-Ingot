# OPS · 运营效率乘数曲线

核对日期：2026-10-12（北京时间）。每类模型独立说明；其保存版本在本页分列，不混合参数。

参数说明：[输入类别、参数含义与训练口径](预测模型与训练参数汇总.md)；[逐回合给定参数与期限](参数细化与六回合期限要求.md)。

版本关联：[全部保存版本及来源](训练拟合模型与版本清单.md)；[全部模型文档索引](模型说明/README.md)。

## 公式

`x_O=max(O_t+ρ_O O_t−1,0)`

`f_O(x_O)=a_O+b_O,curve x_O/(c_O+x_O)`

## 输入变量（字母与文字描述）

| 字母符号 | 文字描述 | 单位 | 输入类别/来源 |
| --- | --- | --- | --- |
| O_t | 当期运营投入 | 千美元 | 可控决策；对手对应值为情景假设 |
| O_t−1 | 上期实际运营投入 | 千美元 | 历史实际输入 |
| x_O | 直接调用曲线时的有效运营横轴 | 千美元 | 有效投入代理 |

## 输出变量（字母与文字描述）

| 字母符号 | 文字描述 | 单位 | 输出类别 |
| --- | --- | --- | --- |
| f_O | 运营效率乘数 | 无量纲 | 曲线拟合输出，尚未乘技术尺度 |

## 参数定义与取值

| 参数字母/字段 | 文字描述 | 值或取值位置 | 类别 |
| --- | --- | --- | --- |
| a_O | 零投入乘数 | parameters[0] | 训练参数 |
| b_O,curve | 饱和增量幅度 | parameters[1] | 训练参数 |
| c_O | 饱和投入尺度 | parameters[2]，千美元 | 训练参数 |
| ρ_O | 运营延续权重 | 调用效率版本给定，见EFF | 不是曲线自身参数 |



## 适用版本与限制

运营图纵轴是效率乘数；它不能直接当作千单位/人的生产效率。

下标：i/j为队伍，c为国家（TH泰国、ID印尼），m为编号市场，h为阶段，t为回合；0为期初，t−1为上一回合；帽号表示预测，不能当作已实现实际值。

## 实现与原始参数来源

- [code/fit_chart_json.py](code/fit_chart_json.py)
- [code/stepwise_model.py](code/stepwise_model.py)

## 已保存主版本的完整精度参数

下表保留原参数字段及数组顺序；本页上方给出字母映射。配置与训练参数分别列示；本页不自动选定部署版本。

| 版本名称与JSON定位 | 参数值（完整精度） | 配置/假设 | 参数原档 |
| --- | --- | --- | --- |
| 20261011T225637591747+0800_training/models::/operations/rho | {"curve_parameters":[0.44999999999999984,0.7499999999999997,400.1058201058195]} | {} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/operations/rho | {"curve_parameters":[0.44999999999999984,0.7499999999999997,400.1058201058195]} | {} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/operations/rho | {"curve_parameters":[0.44999999999999984,0.7499999999999997,400.1058201058195]} | {} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| OPERATIONS_RHO_V1/20261011T213127200793+0800/model::/ | {"curve_parameters":[0.44999999999999984,0.7499999999999997,400.1058201058195]} | {"version":"OPERATIONS_RHO_V1"} | [原档](output/operations_rho/20261011T213127200793+0800/model.json) |
| unified-market/20261012T114145124558+0800/models::/mechanisms/operations_efficiency | {"curve_parameters":[0.44999999999999984,0.7499999999999997,400.1058201058195]} | {"model_id":"unified-market","phase":"formal","round":1} | [原档](output/unified-market/20261012T114145124558+0800/models.json) |
| unified-market/20261012T114145124558+0800/models::/curve_registry/formal/1/curves/operations | {"parameters":[0.44999999999999984,0.7499999999999997,400.1058201058195]} | {"model_id":"unified-market","phase":"formal","round":1,"form":"saturation"} | [原档](output/unified-market/20261012T114145124558+0800/models.json) |
| unified-market/20261012T114145124558+0800/models::/curve_registry/formal/2/curves/operations | {"parameters":[0.45024954480871243,0.7497585383708855,400.18915053467106],"train_parameters":[0.4504014392662713,0.7495579832868283,400.1563123466628]} | {"model_id":"unified-market","phase":"formal","round":2,"form":"saturation"} | [原档](output/unified-market/20261012T114145124558+0800/models.json) |
| 20261012_archive_review/coefficients::/curves/operations | {"parameters":[0.44999999999999984,0.7499999999999997,400.1058201058195]} | {"form":"saturation"} | [原档](output/visible_coefficients/20261012_archive_review/coefficients.json) |
| 20261012_round2_joint/verification::/curves/operations | {"parameters":[0.45024954480871243,0.7497585383708855,400.18915053467106],"train_parameters":[0.4504014392662713,0.7495579832868283,400.1563123466628]} | {"round":2} | [原档](output/visible_coefficients/20261012_round2_joint/verification.json) |
| 20261012_round2_json/coefficients::/curves/operations | {"parameters":[0.45024954480871243,0.7497585383708855,400.18915053467106],"train_parameters":[0.4504014392662713,0.7495579832868283,400.1563123466628]} | {"round":2,"form":"saturation"} | [原档](output/visible_coefficients/20261012_round2_json/coefficients.json) |
| STEPWISE_20261011T045441Z/分步模型拟合与验证::/curves/operations | {"parameters":[0.44999999999999984,0.7499999999999997,400.1058201058195]} | {"form":"saturation"} | [原档](分步模型拟合与验证.json) |

诊断子拟合、保存副本及候选评分关联：[全部参数位置与完整精度配置](output/model_catalog/20261012T122718963696+0800/model_versions.json)；[逐项定位清单](output/model_catalog/20261012T122718963696+0800/全部参数位置.md)。诊断系数不拼成部署参数。

## unified-market逐回合曲线值

| 阶段/回合 | 参数数组（按上方顺序） | 来源 |
| --- | --- | --- |
| formal/1 | [0.44999999999999984, 0.7499999999999997, 400.1058201058195] | [曲线登记原档](output/unified-market/20261012T114145124558+0800/models.json) |
| formal/2 | [0.45024954480871243, 0.7497585383708855, 400.18915053467106] | [曲线登记原档](output/unified-market/20261012T114145124558+0800/models.json) |
