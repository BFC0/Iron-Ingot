# t6v1n 自上而下需求应用

在t6v1上明确拆分两步：先预估各产品、国家市场需求总量，再按十队竞争效用估计份额，二者相乘得到本公司需求。继承t6v1的生产、物流及正式6终局财务链，旧版保留。

泰国、印尼：正式5市场5十队真实需求合计×(1＋前景增长率)，默认分别4%、5%。菲律宾：前景5000／105000单位换算为5／105千单位，没有历史基数。总量来源及近似性质随包保存；不使用玩家预估或预算作实际标签。

份额沿用冻结t6v0参数及t6v1十队归一化，随价格、公司营销合计、研发方案重新计算；菲律宾仍迁移印尼参数。六个产品/国家市场已分别建模，无需额外分配产品占比。总量为外生情景，不包含由本公司价格导致的市场扩张机制。

运行已保存包：

```powershell
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' code/model_v2/t6v1n.py --bundle output/t6v1n/<运行目录> --request output/t6v1n/<运行目录>/example_request.json
```

请求严格包含`version: "t6v1n"`、`round: 6`、28维`decision_vector`及包内`scenario`名称。Python接口`ApplicationModel.evaluate`也支持情景字典中的`market_growth`（2×2，产品顺序复合梁/连接件，国家顺序泰国/印尼，增长率以小数表示）、`new_market_totals`（两个菲律宾产品总量，千单位）及非负`market_scale`。这些是外生预估假设，不是新增经营控制变量。增长率最低−1；非法形状、负总量及非有限数值拒绝。

详细输出新增`market_totals`、`own_shares`和需求方法。需求进入原有生产、物流和财务计算，实际可售量仍受供给约束。

构建及复核：先创建新的`output/t6v1n/<运行目录>/work_log.md`记录授权，再执行：

```powershell
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work/build_t6v1n.py --out output/t6v1n/<运行目录>
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work/build_t6v1n.py --out output/t6v1n/<运行目录> --verify
```

基准及旧两候选仅用于27次默认情景回归，不生成新版推荐。默认输入与t6v1一致，故预测应一致；版本拆分不代表精度提高。未重训、未重跑优化、未操作平台；独立前向精度、细分营销、投标、分包和期初财务机制缺口保留。[项目状态](../../README.md)。
