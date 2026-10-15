# 新增数据的信息价值审计与实验报告

阶段：audit；固定核验覆盖：{'verified': 480, 'pending': 270}。
本报告只读本地，未操作平台、未替换冻结模型；所有成绩为历史研究。

## 字段与独立信息

| 字段 | 数值单元格 | 市场数 | 有效变化组 |
|---|---:|---:|---:|
| average_wage | 320 | 7 | 25 |
| capacity | 320 | 7 | 25 |
| co2 | 320 | 7 | 25 |
| co2_intensity | 320 | 7 | 0 |
| current_workers | 320 | 7 | 25 |
| energy | 320 | 7 | 25 |
| energy_intensity | 320 | 7 | 0 |
| eta | 320 | 7 | 11 |
| hires_fires | 320 | 7 | 25 |
| hr_wage | 320 | 7 | 25 |
| layoff_percent | 320 | 7 | 22 |
| operations | 320 | 7 | 25 |
| previous_workers | 320 | 7 | 12 |
| previous_workers_old | 250 | 7 | 12 |
| profit | 320 | 7 | 25 |
| q | 320 | 7 | 25 |
| quits | 320 | 7 | 12 |
| route_ID | 320 | 7 | 25 |
| route_TH | 320 | 7 | 25 |
| route_co2_ID | 320 | 7 | 25 |
| route_co2_TH | 320 | 7 | 25 |
| route_intensity_ID | 320 | 7 | 14 |
| route_intensity_TH | 320 | 7 | 7 |
| severance | 320 | 7 | 22 |
| shifts | 320 | 7 | 25 |
| short_debt | 320 | 7 | 1 |
| wage | 320 | 7 | 25 |
| water | 320 | 7 | 25 |
| water_intensity | 320 | 7 | 0 |
| workers | 320 | 7 | 25 |

## 实验与门槛

| 实验 | 状态 | 基线MAE | 候选MAE | 相对改善 | 重拟合 |
|---|---|---:|---:|---:|---|
| B0 | PASS | — | — | — | False |
| A | AUDIT_ONLY | — | — | — | False |
| B | AUDIT_ONLY | — | — | — | False |
| C | AUDIT_ONLY | — | — | — | False |
| D | AUDIT_ONLY | — | — | — | False |
| E | AUDIT_ONLY | — | — | — | False |
| F | AUDIT_ONLY | — | — | — | False |

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
