# MATERIAL · 原材料单位差额校准

更新：2026-10-14（北京时间）。本文按所列版本维护专题内容；项目当前状态与最新证据统一见[项目总览](../README.md)。历史公式、参数和误差保留各自版本范围；具体进展在所属主题维护。

历史参数核对日期：2026-10-12（北京时间）。每类模型独立说明；其保存版本在本页分列，不混合参数。

参数说明：[输入类别、参数含义与训练口径](预测模型与训练参数汇总.md)；[逐回合给定参数与期限](参数细化与六回合期限要求.md)。

版本关联：[全部保存版本及来源](训练拟合模型与版本清单.md)；[全部模型文档索引](模型说明/README.md)。

## 适用版本与限制

旧加法校准；正式1unified-market的差额为1.2422839506172636。新版比例模型单列，不将两个差额叠加。

下标：i/j为队伍，c为国家（TH泰国、ID印尼），m为编号市场，h为阶段，t为回合；0为期初，t−1为上一回合；帽号表示预测，不能当作已实现实际值。

## 公式

`v_eff=v+Δv`

`B=q v_eff`

## 输入变量（字母与文字描述）

| 字母符号 | 文字描述 | 单位 | 输入类别/来源 |
| --- | --- | --- | --- |
| v | 当期公布原材料基准单价 | 美元/单位 | 当期给定输入 |
| q | 生产量 | 千单位 | 实际量或条件预测量 |

## 输出变量（字母与文字描述）

| 字母符号 | 文字描述 | 单位 | 输出类别 |
| --- | --- | --- | --- |
| v_eff | 校准后的原材料单位费用 | 美元/单位 | 经验模型输出 |
| B | 原材料购买总费 | 千美元 | 给定产量的条件输出 |

## 参数定义与取值

| 参数字母/字段 | 文字描述 | 值或取值位置 | 类别 |
| --- | --- | --- | --- |
| Δv | 相对公布价的单位残差 | uplift_usd_per_unit等字段；见版本表 | 训练校准，非官方加价 |

## 实现与原始参数来源

- [code/unified_market.py](code/unified_market.py)
- [code/stepwise_model.py](code/stepwise_model.py)

## 已保存主版本的完整精度参数

下表保留原参数字段及数组顺序；本页上方给出字母映射。配置与训练参数分别列示；本页不自动选定部署版本。

| 版本名称与JSON定位 | 参数值（完整精度） | 配置/假设 | 参数原档 |
| --- | --- | --- | --- |
| 20261011T225637591747+0800_training/models::/finance/material_uplift | {"uplift_usd_per_unit":1.2353006067291972} | {} | [原档](output/formal_update/20261011T225637591747+0800_training/models.json) |
| 20261011T225959533924+0800_training/models::/finance/material_uplift | {"uplift_usd_per_unit":1.2353006067291972} | {} | [原档](output/formal_update/20261011T225959533924+0800_training/models.json) |
| 20261011T230135216100+0800_training/models::/finance/material_uplift | {"uplift_usd_per_unit":1.2353006067291972} | {} | [原档](output/formal_update/20261011T230135216100+0800_training/models.json) |
| 20261011T203248461563+0800/materials_review::/independent_review | {"empirical_uplift_usd_per_unit":1.176470588235361} | {} | [原档](output/model_v2/20261011T203248461563+0800/materials_review.json) |
| 20261011T200759885512+0800/review::/ | {"empirical_uplift_usd_per_unit":1.176470588235361} | {} | [原档](output/model_v2/materials_review/20261011T200759885512+0800/review.json) |
| unified-market/20261012T114145124558+0800/models::/mechanisms/materials | {"uplift_usd_per_unit":1.2422839506172636} | {"model_id":"unified-market","phase":"formal","round":1} | [原档](output/unified-market/20261012T114145124558+0800/models.json) |
| STEPWISE_20261011T045441Z/分步模型拟合与验证::/finance/materials | {"uplift_usd_per_unit":1.176470588235361} | {} | [原档](分步模型拟合与验证.json) |

诊断子拟合、保存副本及候选评分关联：[全部参数位置与完整精度配置](output/model_catalog/20261012T122718963696+0800/model_versions.json)；[逐项定位清单](output/model_catalog/20261012T122718963696+0800/全部参数位置.md)。诊断系数不拼成部署参数。
