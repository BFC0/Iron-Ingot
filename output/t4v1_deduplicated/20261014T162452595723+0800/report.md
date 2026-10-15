# t4v1 完全重复功能清理

本次不重新训练。原训练归档保留，当前去重参数为 [models_full.json](models_full.json)，清单为 [model_inventory_final.json](model_inventory_final.json)。

- 删除 UNIFIED、T2V0 两个无独立参数的重复登记项，清单由31类降为29类。
- 删除 interest.parameters 的风险模型副本，使用 interest.parameters_source = "risk"，按 interest.selected 选择 risk 中的函数。
- 训练代码中，每个产品每种材料形式只调用一次 fit，评估复用该结果。
- 原训练参数、候选形式、验证结果和独立功能保持原值；辅助证据文件通过相对路径引用原归档。
- 材料加法与比例模型在当前固定基价下等价，但跨基价含义不同，保留。TOTAL、BASELINE、GROWTH 的业务含义不同，保留；未使用功能不在本次删除范围。

验证：完整参数逐字段比较、6组需求预测精确复算、2个风险函数利率复算、两个产品的材料训练语句执行检查通过，原归档所有文件哈希保持不变。未重跑全量训练或六回合经营模拟。

兼容性：读取旧 interest.parameters 的外部调用方需改为 registry[registry['interest']['parameters_source']][registry['interest']['selected']]；清单不再提供 UNIFIED、T2V0 名称。
