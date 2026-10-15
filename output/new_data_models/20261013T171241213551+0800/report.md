# 新增数据的信息价值审计与实验报告

阶段：ablation；固定核验覆盖：{'verified': 750}。
本报告只读本地，未操作平台、未替换冻结模型；所有成绩为历史研究。

## 字段与独立信息

| 字段 | 数值单元格 | 市场数 | 有效变化组 |
|---|---:|---:|---:|
| average_wage | 500 | 10 | 40 |
| capacity | 500 | 10 | 40 |
| co2 | 500 | 10 | 40 |
| co2_intensity | 490 | 10 | 0 |
| current_workers | 500 | 10 | 40 |
| energy | 500 | 10 | 40 |
| energy_intensity | 490 | 10 | 0 |
| eta | 500 | 10 | 16 |
| hires_fires | 500 | 10 | 40 |
| hr_wage | 500 | 10 | 40 |
| layoff_percent | 500 | 10 | 37 |
| operations | 500 | 10 | 40 |
| previous_workers | 500 | 10 | 20 |
| previous_workers_old | 390 | 10 | 19 |
| profit | 500 | 10 | 40 |
| q | 500 | 10 | 40 |
| quits | 500 | 10 | 20 |
| route_ID | 500 | 10 | 40 |
| route_TH | 500 | 10 | 40 |
| route_co2_ID | 500 | 10 | 40 |
| route_co2_TH | 500 | 10 | 40 |
| route_intensity_ID | 500 | 10 | 26 |
| route_intensity_TH | 500 | 10 | 14 |
| severance | 500 | 10 | 37 |
| shifts | 490 | 10 | 39 |
| short_debt | 500 | 10 | 2 |
| wage | 500 | 10 | 40 |
| water | 500 | 10 | 40 |
| water_intensity | 490 | 10 | 0 |
| workers | 490 | 10 | 39 |

## 实验与门槛

| 实验 | 状态 | 基线MAE | 候选MAE | 相对改善 | 重拟合 |
|---|---|---:|---:|---:|---|
| B0 | PASS | — | — | — | False |
| A/B2|formal|1|泰国|复合梁 | RESEARCH_INCONCLUSIVE | 0.000167482 | 0.000167284 | 0.00118377 | False |
| B3|formal|1|泰国|复合梁 | RESEARCH_INCONCLUSIVE | 0.135631 | 0.160222 | -0.181306 | False |
| C|formal|1|泰国|复合梁 | DERIVED_NO_NEW_MODEL | — | — | — | False |
| E|formal|1|泰国|复合梁 | KNOWN_COEFFICIENT_FORMULA | — | — | — | False |
| F|formal|1|泰国|复合梁 | KNOWN_COEFFICIENT_FORMULA | — | — | — | False |
| A/B2|formal|2|泰国|复合梁 | RESEARCH_INCONCLUSIVE | 0.000524739 | 0.000524891 | -0.000289767 | False |
| B3|formal|2|泰国|复合梁 | RESEARCH_INCONCLUSIVE | 0.0217251 | 0.0308889 | -0.421809 | False |
| C|formal|2|泰国|复合梁 | DERIVED_NO_NEW_MODEL | — | — | — | False |
| E|formal|2|泰国|复合梁 | KNOWN_COEFFICIENT_FORMULA | — | — | — | False |
| F|formal|2|泰国|复合梁 | KNOWN_COEFFICIENT_FORMULA | — | — | — | False |
| A/B2|practice|1|泰国|复合梁 | PREDICTIVE_INCREMENT | 0.000178289 | 0.000169774 | 0.0477594 | True |
| B3|practice|1|泰国|复合梁 | RESEARCH_INCONCLUSIVE | 0.141668 | 0.1562 | -0.102579 | False |
| C|practice|1|泰国|复合梁 | DERIVED_NO_NEW_MODEL | — | — | — | False |
| E|practice|1|泰国|复合梁 | KNOWN_COEFFICIENT_FORMULA | — | — | — | False |
| F|practice|1|泰国|复合梁 | KNOWN_COEFFICIENT_FORMULA | — | — | — | False |
| A/B2|practice|2|泰国|复合梁 | PREDICTIVE_INCREMENT | 0.000700683 | 0.000621556 | 0.112928 | True |
| B3|practice|2|泰国|复合梁 | PREDICTIVE_INCREMENT | 0.103785 | 0.0776 | 0.252297 | False |
| C|practice|2|泰国|复合梁 | DERIVED_NO_NEW_MODEL | — | — | — | False |
| E|practice|2|泰国|复合梁 | KNOWN_COEFFICIENT_FORMULA | — | — | — | False |
| F|practice|2|泰国|复合梁 | KNOWN_COEFFICIENT_FORMULA | — | — | — | False |
| B4|formal1->2 | RESEARCH_INCONCLUSIVE | 0.000545891 | 0.000497202 | 0.0891921 | False |

## 当前全部问题与不足

- 旧效率特征仍是一阶投入代理；本实验不修复累计运营与历史条件曲线结构。
- 环境观测相关；精度区间依赖尚未核实的显示舍入，不是统计置信区间。
- 人员事件可验证费用关系，但同期期末事件不能用于事前输入。
- 缺基础参数的回合不计算工资；缺完整财务链不计算完整利润。
- 来源列/身份/产品冲突按字段排除，不将补采页数作为训练样本数。

## 因缺乏数据而无法验证的问题

- 正式1→2之外的独立正式转移和事前冻结预测。
- 新产品、未知技术版本和多产品工资分摊。
- 自动短贷、非零库存与订单影响下的完整利润；本阶段范围外。
- 排放影响需求、环境收费和随机离职机制未有有效证据。

详见字段证据.csv、样本资格.json、划分.json、实验.json、预测.json及manifest.json。
