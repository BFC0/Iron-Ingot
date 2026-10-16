# 代码入口与运行边界

当前竞争价格假设：其他九组分别沿用各自上回合实际价格；正式6沿用各组正式5价格，新增菲律宾价格未知。[输入及估计重算](../output/rival_previous_prices/20261015T233356004667+0800/report.md)。历史统一同价情景保留。

更新：2026-10-16（北京时间）。本文按所列版本维护专题内容；项目当前状态与最新证据统一见[项目总览](../README.md)。历史公式、参数和误差保留各自版本范围；具体进展在所属主题维护。

## 当前训练、应用与诊断

| 工作 | 维护入口 | 输出与限制 |
| --- | --- | --- |
| 正式5实际训练及正式6应用 | [t6v0](model_v2/t6v0_README.md)、[t6v1](model_v2/t6v1_README.md)、[t6v1n](model_v2/t6v1n_README.md)、[t6v1n1](model_v2/t6v1n1_README.md)、[t6v1n2](model_v2/t6v1n2_README.md) | 独立训练与条件应用；业务解释见[模型说明](../模型说明/README.md)，部分优化、未部署 |
| 正式6独立曲线 | [fit_formal6_curves.py](model_v2/fit_formal6_curves.py) | 600点图形近似，非经营精度 |
| 正式5统一对手价格情景 | [t5v3](model_v2/t5v3_README.md) | 逐队重算需求份额，冻结t5v2系数；无新版优化，正式6默认拒绝外推 |
| 正式5有效投资映射 | [t5v2](model_v2/t5v2_README.md) | 独立条件应用及验收；正式6迁移仍为显式假设 |
| 正式4营销代理重估与正式5应用 | [t5v1](model_v2/t5v1_README.md) | 两类营销合计响应，细分未识别；不是完整全参数最优 |
| 正式4可估计项及状态核验 | [t5v0](model_v2/t5v0_README.md) | 独立训练目录，29类状态包含暂停和不可识别项，不代表完整预测通过 |
| 正式5曲线 | [fit_formal5_curves.py](model_v2/fit_formal5_curves.py) | 三曲线600点，独立于正式4注册表保存 |
| 材料误差诊断 | [diagnose_t5_materials.py](../work/diagnose_t5_materials.py) | 复现既有材料留出及舍入兼容性，独立诊断，不替换模型 |
| 正式3完整训练 | [t4v1](model_v2/t4v1_README.md) | `output/t4v1/`新目录；当前查阅[去重参数](../output/t4v1_deduplicated/20261014T162452595723+0800/models_full.json)，重跑训练会产生原31类登记，去重交付另列 |
| 正式4冻结应用情景 | [t4v1a](model_v2/t4v1a_README.md) | 不训练或选参；缺状态返回缺口，禁止完整利润/期限排名 |
| 连接件历史/价格研究 | [optimize_t4v1_connector.py](model_v2/optimize_t4v1_connector.py) | 新目录保存；`--self-check`最小合成检查，`work/accept_connector_optimization.py`对应验收 |
| 本组效率诊断 | [diagnose_own_efficiency.py](model_v2/diagnose_own_efficiency.py) | 单公司ρ不可识别；独立保存情景及其他9市场留出结果 |
| ρ局部参考 | [refine_efficiency_rho_reference.py](../work/refine_efficiency_rho_reference.py) | 仅其他9市场训练，不改主注册表 |
| ABS嵌套数量对照 | [validate_t4v1_abs_nested.py](../work/validate_t4v1_abs_nested.py) | 复用冻结代码、保存同集合外折；SHARE数量基线使用实际总量 |

## 历史版本与专项脚本

[t4v0](model_v2/t4v0_README.md)仅正式3的6市场子集；[t3v1](model_v2/t3v1_README.md)为连接件同曲线假设及联合分配；[t3v0](model_v2/t3v0_README.md)为正式2统一训练。这些运行和报告保持原版本范围，不作为正式4完整预测入口。

历史脚本可能仍生成HTML报告；新任务应使用Markdown交付，不为本次文档整理运行历史生成器或改写旧报告。`code/要求说明_模板.md`只供早期归档生成器使用，不能覆盖当前任务要求。

## 按工作选择入口

正式2专用独立入口：[t2v0-um说明](t2v0_um/README.md)。`python code/t2v0_um/run.py --train-practice2-components`只用练习2训练新利率和材料模型，并登记受影响参数；两国需求/效率仍需练习2绑定曲线，正式2整体预测仍需全部一致性门槛。当前有两项组件训练参数，33项前景/给定值一致、15项待配对；不替代正式1 unified-market。新财务调用 `calibrated.conditional_accounts`显式传入未识别参数、迭代风险利率；不叠加旧材料差额，不处理未知短贷/库存/订单分支。

| 工作 | 脚本 | 读取或输出边界 |
| --- | --- | --- |
| 原材料单位费用 | [material_unit_cost_model.py](material_unit_cost_model.py) | `train`比较公布价、固定单位差额、比例差额，练习选型/正式1历史检验后全数据重拟合；`predict`接收当期公布单价与产量，独立写入`output/material_unit_cost/<时间戳>/`，不替换旧财务模型 |
| 实际贷款利率预测 | [interest_rate_model.py](interest_rate_model.py) | `train`按正式1整市场嵌套留出选型；`predict`接收预测期末财务状态及当期利率参数；独立写入`output/interest_rate/<时间戳>/`，条件误差不代表事前跨回合精度 |
| 同期市场共享假设训练 | [unified_market.py](unified_market.py) | 使用正式1实际训练，正式2曲线单列；写入新的 `output/unified-market/<时间戳>/` |
| 正式回合训练 | [formal_update_train.py](formal_update_train.py) | `--source` 指定来源；默认来源与若干基准模型固定在历史路径，不能直接当新回合通用入口 |
| 正式期初状态 | [formal_update_state.py](formal_update_state.py) | 需要 `--sources`、`--out`；将已归档期末资料整理为期初状态 |
| 正式报告 | [formal_update_report.py](formal_update_report.py) | 需要 `--sources`、`--training`、`--scenario`、`--out`，输入版本必须相互对应 |
| 情境重审 | [model_v2/run.py](model_v2/run.py)、[使用说明](model_v2/README.md) | `--stage` 选择阶段；写入独立历史目录，未通过门槛的优化仍不运行 |
| 国别需求 | [model_v2/country_demand.py](model_v2/country_demand.py) | 独立国别模型，输出到 `output/country_demand/` |
| 新增数据的信息价值 | [model_v2/new_data_value.py](model_v2/new_data_value.py)、[使用说明](model_v2/新增数据价值验证.md) | `audit` → `ablation` → `train`；显式冻结归档目录，同集合验证，仅保存通过门槛的研究参数 |
| 运营与参数研究 | [operations_rho.py](operations_rho.py)、[parameter_priority.py](parameter_priority.py)、[price_diagnostics.py](price_diagnostics.py) | 各自产物目录，适用范围见各次报告 |
| 图表拟合与核验 | [fit_chart_json.py](fit_chart_json.py)、[verify_joint_chart_data.py](verify_joint_chart_data.py)、[verify_visible_coefficients.py](verify_visible_coefficients.py) | 固定回合来源与输出路径，重跑前先检查覆盖行为 |
| 截图与情境归档 | [archive_practice2_screenshots.py](archive_practice2_screenshots.py)、[archive_practice2_background.py](archive_practice2_background.py) | 面向练习2资料；部分归档脚本更新根目录索引，不作为新回合通用采集命令 |
| 旧模型链与跨市场核验 | [build_model_inputs.py](build_model_inputs.py)、[fit_demand.py](fit_demand.py)、[stepwise_model.py](stepwise_model.py)、[cross_market_validation.py](cross_market_validation.py)、[joint_scenarios.py](joint_scenarios.py) | 保留历史输入、拟合及核验链；部分输出为根目录固定文件 |
| 增量与预算试验核验 | [audit_incremental.py](audit_incremental.py)、[audit_model_trials.py](audit_model_trials.py) | 依赖历史捕获；部分更新固定索引或核验文件 |
| 说明文档生成 | [summarize_model_parameters.py](summarize_model_parameters.py)、[export_model_docx.py](export_model_docx.py) | 读取已保存版本，写根目录汇总或Word文件；重跑会更新交付文档 |
| 网页采集辅助 | [browser_capture.js](browser_capture.js) | 浏览器采集辅助代码；执行前核验当前页面、身份及回合授权 |

专项交付核验在 `work/verify_*.py`，例如 [共享假设模型核验](../work/verify_unified_market.py)和[20项问题核验](../work/verify_twenty_issues.py)。它们验证对应归档版本，不能自动代表当前所有模型通过。

## 运行前检查：依赖、路径与写入

- 数值脚本使用 NumPy、SciPy；文档导出等依赖按具体脚本查看。部分运行采用 `work/python_packages/` 中的本地依赖，不能假定系统 Python 已安装全部库。
- 多个脚本使用同目录导入，`model_v2/core.py` 根据文件位置定位根目录。搬迁脚本必须同步处理导入与数据路径。
- `archive_and_report.py` 被多处导入为历史解析工具，但其直接运行入口仍含旧绝对路径，`ROOT` 指向脚本所在目录；不能将其主程序当成当前项目的一键入口。本次只标明现状，未修复业务代码。
- 部分历史脚本导入时就可能执行读写。结构检查仅静态读取，不通过批量导入或重跑训练来验证导航。
- 代码快照与来源哈希说明当时运行的版本，后续维护变更不覆盖历史记录。再次运行前核验输入回合、输出位置和是否会覆盖文件。
