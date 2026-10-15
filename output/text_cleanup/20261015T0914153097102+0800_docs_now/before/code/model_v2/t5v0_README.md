# t5v0 正式4训练

正式4：100队初终值；3曲线600点；材料/工资100与89条、风险92条重拟合。竞争队最终决策缺失，需求暂停；效率rho不可识别，未部署。

[报告](../../output/t5v0/20261015T085218049188+0800/report_final.md)；[注册表](../../output/t5v0/20261015T085218049188+0800/models_full.json)；[验收](../../output/t5v0/20261015T085218049188+0800/verification.json)。

运行：`python code/model_v2/t5v0.py`；来源自检：加`--self-check`。每次独立输出，保留旧版本。使用项目已安装的NumPy/SciPy运行环境。

验证：`python code/model_v2/verify_t5v0.py <运行目录>`。训练入口产物report.md为阶段报告；`python work/finalize_t5v0.py <运行目录>`补初值证据、图表和入口，权威报告为report_final.md。

决策仅接受正式4实际采集的小组最终列；个人草稿、玩家预估、预算及实际费用代理不得作为决策输入。市场5曲线跨市场共享未证实，条件费用误差不等于事前经营误差。

## t5v0 · 回合5曲线（独立产物）

回合5三曲线600点独立拟合，标注“回合5曲线”；上期投入900/1300/750千美元。保留正式4训练注册表；图形近似不代表经营预测精度。

[报告](../../output/t5v0/20261015T090943259882+0800_formal5_curves/report.md) · [参数](../../output/t5v0/20261015T090943259882+0800_formal5_curves/formal5_curves.json) · [验收](../../output/t5v0/20261015T090943259882+0800_formal5_curves/acceptance.json)。

复现：`python code/model_v2/fit_formal5_curves.py`；每次独立输出。
