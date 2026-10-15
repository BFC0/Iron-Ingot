# 本地逐栏核验

状态：PAUSED_BY_USER。602份来源、12648表格行、994条全精度JSON图表初始化记录；覆盖585/750独立页面。

范围为市场1–10、初始0、练习1/2、正式1/2。URL panel与真实selected市场、历史回合及选项值同时匹配才计入覆盖。可打印报告不计独立逐栏完成。重复标签按表格/行号保留，单位和产品上下文不删除，连接件与复合梁保留原维度。

本次新增独立子栏证据包括市场明细、生产明细/环境/人力、物流明细/排放、财务三表及社会影响；逐页图表保存原始JSON浮点数和NaN字符串，没有执行网页脚本。是否属于打印版没有的具体字段仍须逐项对照，不能仅凭子栏名认定。

已配对37个市场/历史回合的旧打印原件及独立选择证据；694行同名标签未出现于配对打印原件，详见printable_supplement.json。标签别名和单位写法仍需审查，这些差异不能全部算作新字段；本次保存的逐页全精度图表JSON不能由旧打印快照的舍入表格替代。

财务检查：{'pass': 5530, 'pending': 180, 'not_applicable_initial_base': 8}。残差与各单元格显示精度合计容差保留在financial_checks.json。

详情：coverage.csv为覆盖矩阵，rows.json保留逐表行、队列、类别、单位和来源SHA256，charts.json为JSON图表索引。缺失、拒绝、重复键和完成标记见validation.json。未采集不补零；完成标记只表示采集任务结束，缺口仍按原件核验结果保留。

采集标记 history_paused.json：PAUSED_BY_USER；缺口：
采集标记 round3_complete.json：PARTIAL_BUDGET_SUBPAGE_NAVIGATION_FAILED；缺口：预算资产负债表：两次Playwright与一次原生点击均返回财务页且面板关闭，文件名budget_balance不代表取得资产负债表；预算现金流量表：子栏切换后无可定位链接；未取得；预算金融指标：未取得，不能用当前财务决策页代替；采集期间PYT个人方案变化：早期销售原件与后期预算不能合并为同一方案；正式2最终决策与实际由另一对话处理，本次当前草稿不能代替历史生效方案

姓名：已按项目既有哈希映射处理四名已知人员，未知人员仍需映射审查；原件未改。没有评分或重训模型，没有改变latest、README、工作清单或任何平台决策。

身份未通过的来源及原因：

- raw/round3_productionplanning.json：['current_market_footer_missing_or_mismatched']

打印快照同名字段缺口（逐行来源见printable_supplement.json，别名仍待审查）：

- balancesheet：已收预付款
        
            ?；已收预付款 ?；总流动资产；资产 总计；额外实收资本
        
            ?；额外实收资本 ?
- cashflow：已收预付款变化(增 + / 减 -)
        
            ?；股息支付；股票发行收益+ / 股票回购成本 -
- incomestatement：直接税
        
            ?；直接税 ?
- marketdetails：下一回合 复合梁；市场份额 总计；市场份额 总计 - 复合梁；本回合 复合梁；销售额总计；销售额总计 - 复合梁；需求 总计 - 复合梁
- productiondetails：机器产能, 复合梁, 千单位
- productionhr：招聘 + / 裁员 -；每人平均工资, 千 美元；生产人员数量, 上回合；生产人员数量, 本回合；裁员, %；辞职；运营改进, 千 美元
- summary：泰国, 复合梁；累计收益；销货成本
