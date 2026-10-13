# 正式2独立报告包

打开report.html查看报告与市场/国家/模型筛选；导出按钮使用当前市场/国家筛选后的同一组实际行。
actuals.csv为完整200行正式1国家实际。数量单位千单位，金额千美元，价格美元/单位。

formal2_initial_states.json是新正式起点入口：按states[].market_id和team定位formal2_initial_state。
formal2_current_personal_inputs.json单独保存本人当前正式2输入与预算；预算和预估不作实际训练标签。
report_data.json保存HTML使用的数据；training/保存冻结核验及重训练参数；scenario/保存情境时间变化。
sources/与supporting/保存本次原件及训练支持原件，source_manifest.json记录原路径、复制路径及哈希。

在原工作区使用本次入口复现至新的独立输出目录：

```powershell
python code/formal_update_report.py --sources <本次原件目录> --training <训练目录> --scenario <情境目录> --out <新的报告目录>
python code/formal_update_state.py --sources <本次原件目录> --out <新的独立路径>/formal2_initial_states.json
```

输出目录与文件排他创建；保留旧报告。来源引用保留原工作区路径，跨目录搬移时按manifest恢复路径。
只累计正式2..6五期利润；未知不补零，不加终值，不自动清债或变现。
市场5前景已核验，其他市场机制拟合隔离；税损余额与累积技术存量仍未知。
冻结误差、样本内误差及内部留出分别展示，不能称为正式2未来验证。
本次没有修改平台决策。
