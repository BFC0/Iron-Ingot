# 代码入口与运行边界

更新：2026-10-12。维护源代码在本目录，历史运行副本在 `output/`；固定路径保持不变。项目数据及报告导航见[项目结构](../项目结构.md)。

## 按工作选择入口

| 工作 | 脚本 | 读取或输出边界 |
| --- | --- | --- |
| 同期市场共享假设训练 | [unified_market.py](unified_market.py) | 使用正式1实际训练，正式2曲线单列；写入新的 `output/unified-market/<时间戳>/` |
| 正式回合训练 | [formal_update_train.py](formal_update_train.py) | `--source` 指定来源；默认来源与若干基准模型固定在历史路径，不能直接当新回合通用入口 |
| 正式期初状态 | [formal_update_state.py](formal_update_state.py) | 需要 `--sources`、`--out`；将已归档期末资料整理为期初状态 |
| 正式报告 | [formal_update_report.py](formal_update_report.py) | 需要 `--sources`、`--training`、`--scenario`、`--out`，输入版本必须相互对应 |
| 情境重审 | [model_v2/run.py](model_v2/run.py)、[使用说明](model_v2/README.md) | `--stage` 选择阶段；写入独立历史目录，未通过门槛的优化仍不运行 |
| 国别需求 | [model_v2/country_demand.py](model_v2/country_demand.py) | 独立国别模型，输出到 `output/country_demand/` |
| 运营与参数研究 | [operations_rho.py](operations_rho.py)、[parameter_priority.py](parameter_priority.py)、[price_diagnostics.py](price_diagnostics.py) | 各自产物目录，适用范围见各次报告 |
| 图表拟合与核验 | [fit_chart_json.py](fit_chart_json.py)、[verify_joint_chart_data.py](verify_joint_chart_data.py)、[verify_visible_coefficients.py](verify_visible_coefficients.py) | 固定回合来源与输出路径，重跑前先检查覆盖行为 |
| 截图与情境归档 | [archive_practice2_screenshots.py](archive_practice2_screenshots.py)、[archive_practice2_background.py](archive_practice2_background.py) | 面向练习2资料；部分归档脚本更新根目录索引，不作为新回合通用采集命令 |
| 旧模型链与跨市场核验 | [build_model_inputs.py](build_model_inputs.py)、[fit_demand.py](fit_demand.py)、[stepwise_model.py](stepwise_model.py)、[cross_market_validation.py](cross_market_validation.py)、[joint_scenarios.py](joint_scenarios.py) | 保留历史输入、拟合及核验链；部分输出为根目录固定文件 |
| 增量与预算试验核验 | [audit_incremental.py](audit_incremental.py)、[audit_model_trials.py](audit_model_trials.py) | 依赖历史捕获；部分更新固定索引或核验文件 |
| 说明文档生成 | [summarize_model_parameters.py](summarize_model_parameters.py)、[export_model_docx.py](export_model_docx.py) | 读取已保存版本，写根目录汇总或Word文件；重跑会更新交付文档 |
| 网页采集辅助 | [browser_capture.js](browser_capture.js) | 浏览器采集辅助代码；执行前核验当前页面、身份及回合授权 |

专项交付核验在 `work/verify_*.py`，例如 [共享假设模型核验](../work/verify_unified_market.py)和[20项问题核验](../work/verify_twenty_issues.py)。它们验证对应归档版本，不能自动代表当前所有模型通过。

## 依赖与复现注意

- 数值脚本使用 NumPy、SciPy；文档导出等依赖按具体脚本查看。部分运行采用 `work/python_packages/` 中的本地依赖，不能假定系统 Python 已安装全部库。
- 多个脚本使用同目录导入，`model_v2/core.py` 根据文件位置定位根目录。搬迁脚本必须同步处理导入与数据路径。
- `archive_and_report.py` 被多处导入为历史解析工具，但其直接运行入口仍含旧绝对路径，`ROOT` 指向脚本所在目录；不能将其主程序当成当前项目的一键入口。本次只标明现状，未修复业务代码。
- 部分历史脚本导入时就可能执行读写。结构检查仅静态读取，不通过批量导入或重跑训练来验证导航。
- 代码快照与来源哈希说明当时运行的版本，后续维护变更不覆盖历史记录。再次运行前核验输入回合、输出位置和是否会覆盖文件。
