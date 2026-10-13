# t2v0-um 独立版本

状态：PRACTICE2_COMPONENTS_TRAINED_MIGRATION_BLOCKED。练习2实际200条，10市场100队；正式2期初状态来自正式1实际。

一致性门槛未通过；正式2整体迁移关闭。

新增组件仅用练习2的100家公司实际训练，不混入练习1或正式1标签。

实际贷款利率：solvency_exponential，参数[0.12281068318353833, 8.180868311208613]（内部利率为小数），嵌套整市场留出MAE 2.832508基点。

材料单位费用：1053 × (1 + 0.00138457394359) = 1054.457956美元/单位；整市场留出总费MAE 2.323743千美元。

两项误差均为给定实际期末状态/产量的条件误差，不能作为正式2事前成绩。单一基础价不能识别跨回合比例与固定差额，比例结构按用户新增模型保留。

28项给定参数及5段前景已与正式2归档逐项核对一致；余项见对照表。参数更新、依赖与未能重训项见parameter_changes.json，独立财务调用见calibrated.py。新材料费用取代旧差额项，不能重复相加；风险利率用于联立重算。

逐项结果见comparison.csv/JSON；代码自检与旧资料保护见checks.json及manifest.json。

尚未通过：15项。

- curve/rd
- curve/operations
- sales/泰国/price
- sales/泰国/general
- sales/泰国/designer
- sales/泰国/rd
- sales/印尼/price
- sales/印尼/general
- sales/印尼/designer
- sales/印尼/rd
- given/production
- given/investments
- given/logistics
- given/orders
- given/finance

正式2完整财务、税亏、订单条款及存量未识别处保留缺口；第3回合及以后不适用。没有平台改动。
