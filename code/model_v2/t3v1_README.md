# t3v1 运行说明

更新：2026-10-14（北京时间）。本文按所列版本维护专题内容；项目当前状态与最新证据统一见[项目总览](../../README.md)。历史公式、参数和误差保留各自版本范围；具体进展在所属主题维护。

## 版本内容与运行边界

该版本连接件扩展：[V2库存、确认订单及影响路径](../../模型说明/CONNECTOR_V2_库存订单及影响路径.md)。通过`connector_plan.lifecycle`启用；通过`connector_rd_mode: "observed_sensitivity"`显式比较独立研发图线。[最新注册表与验收](../../output/connector_model_update/README.md)，复现脚本为`work/verify_connector_model_v2.py`。旧注册表仍可回放默认同曲线路径，独立图线需要新版注册表。V2不是完整利润模型。

2026-10-13扩展：[连接件独立自由生产路径](../../模型说明/CONNECTOR_连接件独立自由生产路径.md)。请求增加`connector_plan`，明确`allocation_pct`、`opening_inventory_kunits`、`holding_cost_per_unit`和`country_priority`；按计划生产，超需求结转库存，先预留用工再优化复合梁。不提供时保留原零库存当期优化行为。[新完整输入](../../output/connector_free_production/20261013T194825493581+0800/request.json)。独立验收：`python work/verify_connector_path.py`。

训练：`python code/model_v2/t3v1.py`。自检：`python code/model_v2/t3v1.py --self-check`。保存结果核验：`python work/verify_t3v1.py <训练运行目录>`。

情景预测：`python code/model_v2/t3v1.py --registry <t3v1运行目录>/models.json --predict <request.json>`。每次独立写入`output/t3v1/<北京时间运行编号>/`，不覆盖输入或旧结果。依赖沿用项目已有NumPy/SciPy；本机Python为`<LOCAL_USER_DIR>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。

完整输入可从[合成示例](../../output/t3v1/20261013T193815695205+0800/example_request.json)复制。必须提供：

- `competitors`：两个产品、两个国家的完整10队竞争输入；每行有市场/团队/阶段/回合/产品/国家、售价、产品基准价、一般营销、设计师营销、研发和上期研发。仅支持正式2回放或正式3假设迁移，两产品分组计算。
- `market_totals_kunits`：以字符串市场编号→产品→国家组织的外部行业总量，单位千单位。
- `market_id`、`team_id`：要分配的目标市场及团队，必须在竞争输入中。
- `production`：产品→`capacity`、`efficiency`、`material_cost`、两国`prices`及`transport_costs`。需求由模型注入，售价必须与竞争输入一致。
- `worker_limit`、`wage_kusd`、`shift_multipliers`：共享用工上限（null表示无上限）、基础工资和三个班次乘数。

返回需求预测与联合分配：各产品数量、独立产能填写比例、数量占比、用工占比、交付及当期贡献。无需两项产能比例合计100%。

t3v1历史训练：[报告](../../output/t3v1/20261013T193815695205+0800/report.md)、[参数](../../output/t3v1/20261013T193815695205+0800/models.json)。[假设、公式与范围](../../模型说明/T3V1_同曲线假设与联合分配.md)。连接件没有真实训练标签，联合分配是训练后需求驱动的条件优化；示例不是当前本人推荐。
