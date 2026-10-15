# t3v0 运行说明

`python code/model_v2/t3v0.py`：正式2曲线及实际训练；正式1期末初值与正式2终值配对；正式3曲线额外保存。每次独立输出到 `output/t3v0/<北京时间运行编号>/`。归档截止点固定在入口常量中，不自动选择新网页。旧数据与结果不覆盖。

自检：`python code/model_v2/t3v0.py --self-check`。保存结果核验：`python work/verify_t3v0.py <运行目录>`；HTML静态脚本核验：`node work/verify_t3v0_html.cjs <运行目录>/report.html`。

本机Python：`<LOCAL_USER_DIR>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。复用项目已有NumPy/SciPy及ReportLab；SciPy位于`work/python_packages`。

模型、正式2训练曲线、正式3额外曲线分别在 `models.json`、`formal2_curves.json`、`formal3_curves.json`。28项训练/规则核验/门槛状态见 `model_inventory.json`。连接件没有正式2需求标签，不生成其需求系数。

仅缓存同次运行的原始特征；每折尺度和参数独立估计。`core.fit` 可选预计算特征，旧调用保持行为。`predict_version(rows, registry, curve, model_name)` 返回正式2条件份额，拒绝错回合/产品/国家、重复键及不完整竞争组；不能输入正式3曲线。

未通过增量门槛的候选不部署；确定规则不新加参数。完整累计状态、订单和六回合收益链仍未验证，不自动填值或提交平台。HTML静态检查不代替浏览器布局与打印实测。
