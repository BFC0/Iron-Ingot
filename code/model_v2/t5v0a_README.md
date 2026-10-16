# t5v0a 正式5非重训应用

2026-10-15（北京时间）。基于t5v0正式4训练参数与已完成的回合5曲线，按用户授权调整当期应用；不重新拟合、选型或训练。

[报告](../../output/t5v0a/20261015T131507850861+0800/report.md) · [注册表](../../output/t5v0a/20261015T131507850861+0800/models_full.json) · [验收](../../output/t5v0a/20261015T131507850861+0800/acceptance.json) · [全部29类调整状态](../../output/t5v0a/20261015T131507850861+0800/model_adjustments.json)。

材料同时保留公布价、固定加价及比例修正；工资/班次/解聘、利率分解、显式曲线坐标、订单前库存数量场景可调用。42项公布参数全部保存。完整需求预测、有效投入映射、订单现金及投资时序仍缺数据；正式5—6完整收益不排名。

在项目根目录使用已安装的Python 3.12及现有NumPy/SciPy，不能用默认Python 3.13加载本项目3.12扩展：

```powershell
$py = '<LOCAL_USER_DIR>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $py code/model_v2/t5v0a.py --bundle output/t5v0a/20261015T131507850861+0800
& $py code/model_v2/verify_t5v0a.py output/t5v0a/20261015T131507850861+0800
```

另加`--request <JSON路径>`计算显式条件场景。请求头固定version=t5v0a、market_id=5、phase=formal、round=5；可选字段见报告及[t5v0a.py](t5v0a.py)。缺少输入返回跳过，未知字段拒绝。最小示例不伪造缺失数据。

模型保留正式4原曲线于curves，正式5应用曲线独立位于application_curves；historical model_inventory状态与application_actions分开。历史artifact相对路径指向原t5v0档案，当前包依赖本项目归档，不能单独移动目录后运行。代码快照用于追溯，运行入口为项目code目录。
