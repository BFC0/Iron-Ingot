# t6v1n2 印尼梁定价链修复

基于t6v1n1，保留菲律宾迁移泰国、正式6终局、生产财务及五类候选。研发需求特征统一公司合计口径，沿用训练曲线作为研究代理尺度；不再将单产品投入映射直接作用于公司合计系数。价格参数不重训、不人为压价。

新增旧市场价格敏感度+20%/+50%、营销与研发新增收益失效及联合失效情景，共18情景。稳健核心为包内`robust_scenario_names`列出的九项。失效保留比例`marketing_gain`、`rd_gain`须为0至1，零值只取消相对历史特征的正增量，负增量仍保留。旧市场对手价格倍数`old_rival_price`须为正有限数；其余情景继承原版。

营销和研发细分仍不可识别，合计参数参与搜索，细分只是展示约定；投标、分包与完整期初财务仍未求解。无新增真实标签，不宣称因果精度或全参数最优。

```powershell
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work/optimize_t6v1n2.py --out output/t6v1n2/新运行目录 --iterations 600
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work/optimize_t6v1n2.py --out output/t6v1n2/新运行目录 --verify
& '<LOCAL_USER_DIR>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' code/model_v2/t6v1n2.py --bundle output/t6v1n2/新运行目录 --request output/t6v1n2/新运行目录/example_request.json
```

请求严格使用`version=t6v1n2`、整数`round=6`、28维决策及保存的情景名称。示例为稳健候选，Python接口回放份额候选须传入其固定物流顺序。每次输出目录必须新建，原版及历史结果保留。[项目入口](../../README.md)。
