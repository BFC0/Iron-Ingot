# 财务标签配对验收

时间：2026-10-13T17:04:15.559484+08:00（北京时间）。不要输出真名，姓名统一用首字母替代；交付表仅使用市场/团队列编号。

财务审计9340项通过、0项数值失败、6项待核、10项初始基准不适用。旧235个pending记录中229个已配对，6个保留；记录数随按团队展开增加，不能将235与新增通过条数直接相减。历史页覆盖仍为750/750。26项结构review未关闭。

根因：换行帮助符号不能用rstrip精确去除；市场份额分区未重置导致需求重复；7个累计待核记录需要完整HTML补件；部分HTML本身有额外列。规范化仅去空白与末尾帮助问号，不改数字、单位或标签含义。重复标签和多列继续拒绝。所有等式均核对队列；供需只配市场明细需求/销售与物流明细未满足需求，保持国家、产品、千单位及供给截断含义。缺失/NaN不补零。

累计收益：指南第6页说明练习结束后回到初始状态。50个时期的概要表与同页CumulEarnings/Profitability图表逐队配对；初始0显示收益约1293千美元，不是零。正式1与练习1各自回到初始0基准，正式2接正式1，练习2接练习1，不能继承练习2到正式1。累计表与初始利润加同阶段各期利润的全精度和交叉核验结果为{'pass': 1000}（共1000项利润/累计检查）；图表与表格同源，不是独立样本。CumulRevenue图是收入序列，不能当累计收益；CumulEarnings时间序列本身已舍入，保留其NaN及显示精度。

发现新证据冲突：市场2练习1完整HTML补件选择器虽为练习1，利润/累计图第1年却为NaN且表仍为初始值。补件被拒绝；原件所保存的练习1数表与原件脚本、练习2历史图一致，因此继续使用原件，不用旧值或补零替代。旧“完整HTML750页”是结构验收，本次内容配对只有46/47补件获接纳；该页完整且同期的HTML仍待补证。旧round3_productionplanning身份拒绝亦保留。两个拒绝项使完整档案审计仍标INCOMPLETE，不能称全部证据通过。

正式3新版本16份来源哈希已核；三次个人列稳定及四类预算绑定沿用同期验收。新productionplanning独立存在且通过当前身份核验，未替换旧拒绝原件。旧两份预算各留版本，缺同期决策的旧预算未配对；预算不作为实际标签。

## 剩余待核

|市场/阶段/回合|检查|原因|
|---|---|---|
|1/formal/1|aftertax_profit|原件有11或12个值，而已核团队队列为10；不能截列或猜测附加列归属。|
|2/practice/1|assets_equal_liabilities_equity|原件有11或12个值，而已核团队队列为10；不能截列或猜测附加列归属。|
|3/formal/1|working_capital_movements|原件有11或12个值，而已核团队队列为10；不能截列或猜测附加列归属。|
|4/formal/1|gross_profit|原件有11或12个值，而已核团队队列为10；不能截列或猜测附加列归属。|
|4/formal/2|fixed_assets_components|原件有11或12个值，而已核团队队列为10；不能截列或猜测附加列归属。|
|7/formal/2|current_assets_components|原件有11或12个值，而已核团队队列为10；不能截列或猜测附加列归属。|

逐项来源、原列数和数值见[剩余证据](remaining.json)；26项见[结构审查](structure_review.json)。不能截去Name11或第12值，也不凭会计平衡猜测团队归属。

交付：[标签映射](label_mapping.json)、[逐项核验](financial_checks.json)、[旧待核迁移](old_pending_transition.json)、[同源图表交叉检查](chart_crosschecks.json)、[来源哈希](source_hashes.json)、[验收JSON](acceptance.json)。映射保存源行列、规范化前后标签、分区、单位、国家/产品、数值及显示半步容差。原始证据和旧结论未覆盖。

复现：在项目根目录先运行 `"<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" output/round_close/20261012T221044.031+0800/audit/verify_archive.py`，再运行 `"<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" work/verify_financial_pairing.py --audit <新审计目录>`。第二条默认排他创建新报告目录；不要重用--output覆盖旧交付。新审计包含完整代码快照；本目录另附验收脚本快照。离线复现不访问平台。

未训练模型、未改平台决策、未提交小组方案、未评价六回合最优。额外列和同期HTML冲突尚未解决；原件及审计中未知队名未全面认证，只分享本目录脱敏交付文件，勿打包raw或旧审计目录。
