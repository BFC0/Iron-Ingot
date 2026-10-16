# t5v3 统一对手默认价格需求情景

以t5v2为基线，假设市场5其他九队统一使用本组正式5回合初默认价格：复合梁泰国1860／印尼2180，连接件泰国36／印尼32美元。逐队按其正式4价格与需求份额重估价格吸引力，再归一化十队份额。对手非价格吸引力冻结；原t5v2不改。

[预测对照与假设](../../output/t5v3/20261015_common_default_prices/report.md) · [逐队输入](../../output/t5v3/20261015_common_default_prices/competition_inputs.json)

```powershell
python code/model_v2/t5v3.py --bundle output/t5v3/20261015_common_default_prices
python code/model_v2/verify_t5v3.py output/t5v3/20261015_common_default_prices
```

可用`--request`指定与example_request.json同结构的请求；`decision_vector`延用t5v2的20项顺序及单位。默认预测归档本人基准，只输出正式5份额和需求；支持中性SHARE、国别COUNTRY和联合不利情景。逐队份额维度为对手×产品×国家，本组为产品×国家，份额单位0—1。

`ApplicationModel.demand(x,cfg,t)`兼容原计算链。正式6默认拒绝外推，只有显式设置`rival_prices_formal6='freeze_formal5_common_defaults'`才允许冻结价格情景。历史优化脚本继续使用t5v2；新版没有重新优化方案，不能把旧推荐及利润视为新版结果。

依赖NumPy及同目录冻结t5v2，不访问平台、不训练。未验证实际预测精度提升，未来对手非价格行为及供给再分配仍未知。
