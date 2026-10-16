# t5v1独立冻结应用

正式4初终值营销费用代理训练＋正式5已知重要性；其余组件继承t5v0b，原版不变。

[完整建议与敏感性](../../output/t5v1/20261015T171355804/report.md) · [注册表](../../output/t5v1/20261015T171355804/models_full.json) · [验证](../../output/t5v1/20261015T171355804/validation.json)。

运行：

```powershell
python code/model_v2/t5v1.py --bundle output/t5v1/20261015T171355804
```

依赖项目NumPy（与原运行环境一致），可用`--request`传入示例同结构JSON。入口不训练、不改平台；三方案15情景已回放。营销细分真实响应未知，只识别两类合计；正式5—6利润是条件情景，非全参数最优或独立前向预测。
