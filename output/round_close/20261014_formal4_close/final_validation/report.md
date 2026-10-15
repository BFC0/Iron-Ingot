# 正式4归档验收

市场 1–10 正式回合 4 全部通过。实际采集 10 份打印、130 份网页（每市场概要和 12 个补采页），共 140 份有效原件。未将打印虚算为固定 15 栏页面。

200 个字段 × 10 市场（20,000 个团队值）、28 图 × 10 市场的原精度 JSON 及同点 SVG 渲染配对全部覆盖。打印与网页交叉一致；1,900 个财务等式和 100 个正式3→4累计衔接通过。

合并 700 个计算值及索引；5,700 条原件输入和 600 条直接显示值对照通过。计算来源、公式、显示误差区间与直接值同时保留，人员净变化不替代招聘或裁员。

市场 1、4 排放表各一个总计行附有两个无队名的 0.0 列，原件及全部 13 单元格保留；仅映射 10 个具名团队列，并逐队核对运输分项和总计。打印 DOM 426 行中 173 行为空，实质字段布局为既有 253 行。截断旧件和恢复辅助片保留，不计有效页。

SVG 折线点容差 1e-4 像素，饼图份额容差 1e-8 百分点，柱形容差 1.5 像素并核对符号和团队槽位；JSON 为原精度数值主来源。显式零与 NaN 区分，重复表示不增加独立样本。

所有引用源 SHA256 已重验，输出姓名使用首字母。未评分、更新参数或重训。

[完整验收索引与源哈希](acceptance_index.json)；[2000 字段及计算值合并](field_coverage.json)；[280 图及配对引用](sequence_coverage.json)。

逐市场核验：

- 市场 1：[字段与财务](../validation/market1/20261014T232516.222766+0800/validation.json)；[JSON/SVG 点对点](../validation/market1/20261014T232516.479316+0800_svg/json_svg_pairing.json)。
- 市场 2：[字段与财务](../validation/market2/20261014T232517.446498+0800/validation.json)；[JSON/SVG 点对点](../validation/market2/20261014T232517.721028+0800_svg/json_svg_pairing.json)。
- 市场 3：[字段与财务](../validation/market3/20261014T232518.723351+0800/validation.json)；[JSON/SVG 点对点](../validation/market3/20261014T232518.974214+0800_svg/json_svg_pairing.json)。
- 市场 4：[字段与财务](../validation/market4/20261014T232519.929173+0800/validation.json)；[JSON/SVG 点对点](../validation/market4/20261014T232520.191061+0800_svg/json_svg_pairing.json)。
- 市场 5：[字段与财务](../validation/market5/20261014T232521.141929+0800/validation.json)；[JSON/SVG 点对点](../validation/market5/20261014T232521.397216+0800_svg/json_svg_pairing.json)。
- 市场 6：[字段与财务](../validation/market6/20261014T232522.398562+0800/validation.json)；[JSON/SVG 点对点](../validation/market6/20261014T232522.651062+0800_svg/json_svg_pairing.json)。
- 市场 7：[字段与财务](../validation/market7/20261014T232523.625075+0800/validation.json)；[JSON/SVG 点对点](../validation/market7/20261014T232523.878521+0800_svg/json_svg_pairing.json)。
- 市场 8：[字段与财务](../validation/market8/20261014T232524.853680+0800/validation.json)；[JSON/SVG 点对点](../validation/market8/20261014T232525.112426+0800_svg/json_svg_pairing.json)。
- 市场 9：[字段与财务](../validation/market9/20261014T232526.089781+0800/validation.json)；[JSON/SVG 点对点](../validation/market9/20261014T232526.374896+0800_svg/json_svg_pairing.json)。
- 市场 10：[字段与财务](../validation/market10/20261014T232527.341640+0800/validation.json)；[JSON/SVG 点对点](../validation/market10/20261014T232527.592925+0800_svg/json_svg_pairing.json)。
