# t6v1n1 菲律宾迁移泰国及份额优化

继承t6v1n市场总量×竞争份额框架，菲律宾改用冻结t6v0的泰国国别beta及泰国对手非价格代理，价格响应采用泰国beta[0]。按team_id对齐，不继承泰国份额；十队以菲律宾指导价1600/23美元为基准。菲律宾总量5/105千单位、运费170/2.2美元/单位保持原归档。两旧市场需求计算保持原路径。

用户指定的泰国相似性是一项迁移假设，不是新增菲律宾真实标签训练，也不证明预测精度提升。公司合计营销代理保留，同合计的细分分配不改变需求；分配金额仅作展示。投标、分包和期初财务缺口继续标为未求解。

正式6终局联合搜索价格、营销合计、研发、运营、投资、产能分配、物流和融资。比较中性、稳健及两产品分别10%/20%/30%的中性交付份额目标；份额候选菲律宾优先供货，约束销量而非仅需求。全56项按决策页输出，预估项一致重算。稳健使用中性、四个响应扰动、联合不利、对手降价、缩量及二者叠加共九种核心情景；全部候选用相同13情景复算。目标档位为分析选择，不是市场份额保证。

先在新的 `output/t6v1n1/<北京时间戳>/work_log.md` 记录用户授权，再运行：

```powershell
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work/optimize_t6v1n1.py --out output/t6v1n1/<运行目录> --iterations 1200
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work/optimize_t6v1n1.py --out output/t6v1n1/<运行目录> --verify
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' code/model_v2/t6v1n1.py --bundle output/t6v1n1/<运行目录> --request output/t6v1n1/<运行目录>/example_request.json
```

请求严格使用 `version: t6v1n1`、整数 `round: 6`、28维 `decision_vector` 和保存的 `scenario` 名称。示例请求为稳健候选；份额候选的固定物流顺序见结果文件，Python接口调用时须传入 `priorities`。命令行示例按原接口自动选择物流，不作为份额候选固定物流回放入口。

新情景 `ph_rival_price` 为其他九队菲律宾报价相对指导价的倍数；必须为正有限数，默认1。其他外生总量与响应情景继承t6v1n。分析边界、收敛状态、现金时点限制及推荐理由随运行包保留。

旧模型与结果保留；新运行先备份当前说明文件并保存改前/改后哈希和链接检查。[项目状态](../../README.md)。
