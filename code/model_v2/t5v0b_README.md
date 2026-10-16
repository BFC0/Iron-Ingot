# t5v0b：国别需求映射与机器稳定价

2026-10-15（北京时间）。基于t5v0a，保留t5v0全部训练系数及已有回合5曲线，不重训或选型。

[报告](../../output/t5v0b/20261015T153107587428+0800/report.md) · [注册表](../../output/t5v0b/20261015T153107587428+0800/models_full.json) · [验收](../../output/t5v0b/20261015T153107587428+0800/acceptance.json) · [29类影响](../../output/t5v0b/20261015T153107587428+0800/model_adjustments.json)。

用户假设：泰国+7%、印尼−5%作为两产品需求变化比例，默认进入正式4实际总量到正式5总量的计算。机器趋稳按正式5公布78／1.10美元/单位处理，不改回上期价；正式6价格和投资生效时点仍未知。

```powershell
$py = '<LOCAL_USER_DIR>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $py code/model_v2/t5v0b.py --bundle output/t5v0b/20261015T153107587428+0800
& $py code/model_v2/verify_t5v0b.py output/t5v0b/20261015T153107587428+0800
```

请求头为version=t5v0b、market_id=5、phase=formal、round=5。沿用[t5v0a输入](t5v0a_README.md)，但product_growth固定为两产品泰国0.07、印尼−0.05，不能另行覆盖。

新增investments_kunits（两产品投资量，千单位，零投资显式0），仅计算采购金额，不擅自计算付款现金或生效产能；可选demand_basis=FORMAL4_OWN_SHARE_HELD须额外假设本组份额保持，连接件缺省需求会取该情景，冲突需求拒绝。默认只给市场总量及等份额基线，公司竞争需求仍待数据。

29类均记录影响，成本、效率、曲线、风险参数不因这两个外生假设重新拟合；新总量不再乘到ABS独立数量输出，也不重复施加正式6。此交付是全模型影响检查和条件应用调整，不是全部可控决策的优化方案。已知数据缺口按授权跳过，完整收益仍不可排名。

运行依赖项目归档及现有Python3.12/NumPy/SciPy；artifact引用原t5v0档案，不能单独搬走包运行。代码快照供追溯，正常入口在项目code目录。
