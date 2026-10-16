# t5v2独立冻结应用

以t5v1为基线，新增网页区间验证的投入→有效投资映射，连接原需求、效率、生产及财务链。原版只读保留。

[完整报告](../../output/t5v2/20261015_effective_investment/report.md) · [映射参数](../../output/t5v2/20261015_effective_investment/effective_investment_models.json)。

```powershell
python code/model_v2/t5v2.py --bundle output/t5v2/20261015_effective_investment
```

可用`--request`传入与example_request.json同结构的请求。仅依赖NumPy，不访问平台、不训练。正式6及历史有效存量归一化仍为显式情景，营销细分、招标、分包未完全求解。
