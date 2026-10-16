"""Write t5v0a documentation and hash manifest after offline acceptance."""
import hashlib
import json
import platform
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'code/model_v2'))
import t5v0a as t
from verify_t5v0a import verify


def main():
    app = t.app
    out = Path((ROOT/'work/t5v0a_active_run.txt').read_text(encoding='utf-8').strip())
    assert not (out/'report.md').exists(), 'Refuse to finalize an existing report'
    with app.no_training():
        accepted = verify(out)
    app.save(out/'acceptance.json', accepted)
    m = app.read(out/'models_full.json')
    rel = out.relative_to(ROOT).as_posix()
    doc = ROOT/'code/model_v2/t5v0a_README.md'
    doc.write_text(f'''# t5v0a 正式5非重训应用

2026-10-15（北京时间）。基于t5v0正式4训练参数与已完成的回合5曲线，按用户授权调整当期应用；不重新拟合、选型或训练。

[报告](../../{rel}/report.md) · [注册表](../../{rel}/models_full.json) · [验收](../../{rel}/acceptance.json) · [全部29类调整状态](../../{rel}/model_adjustments.json)。

材料同时保留公布价、固定加价及比例修正；工资/班次/解聘、利率分解、显式曲线坐标、订单前库存数量场景可调用。42项公布参数全部保存。完整需求预测、有效投入映射、订单现金及投资时序仍缺数据；正式5—6完整收益不排名。

在项目根目录使用已安装的Python 3.12及现有NumPy/SciPy，不能用默认Python 3.13加载本项目3.12扩展：

```powershell
$py = '<LOCAL_USER_DIR>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $py code/model_v2/t5v0a.py --bundle output/t5v0a/{out.name}
& $py code/model_v2/verify_t5v0a.py output/t5v0a/{out.name}
```

另加`--request <JSON路径>`计算显式条件场景。请求头固定version=t5v0a、market_id=5、phase=formal、round=5；可选字段见报告及[t5v0a.py](t5v0a.py)。缺少输入返回跳过，未知字段拒绝。最小示例不伪造缺失数据。

模型保留正式4原曲线于curves，正式5应用曲线独立位于application_curves；historical model_inventory状态与application_actions分开。历史artifact相对路径指向原t5v0档案，当前包依赖本项目归档，不能单独移动目录后运行。代码快照用于追溯，运行入口为项目code目录。
''', encoding='utf-8')
    changes = {}
    for path in ('README.md', 'code/model_v2/README.md', '模型说明/README.md'):
        file = ROOT/path
        backup = out/'before'/path
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists(): shutil.copy2(file, backup)
        changes[path] = dict(before=app.sha(backup), after=None)
        text = file.read_text(encoding='utf-8')
        if path == 'README.md':
            marker = '| 正式5曲线（t5v0独立保存）'
            row = (f'| 最新独立应用情景 | **t5v0a**：[报告]({rel}/report.md)、[注册表]({rel}/models_full.json)、'
                   f'[验收]({rel}/acceptance.json)、[运行说明](code/model_v2/t5v0a_README.md) | '
                   '冻结t5v0参数，接入正式5公布条件和已有曲线；材料三情景、工资/利率/库存数量条件路径已检查。未重训，缺数据部分跳过，不输出完整利润或最优决策。 |\n')
            assert text.count(marker) == 1
            if '| 最新独立应用情景 | **t5v0a**' not in text:
                text = text.replace(marker, row+marker)
            text = text.replace('| 最新独立应用情景 | **t4v1a**', '| 正式4历史应用情景 | **t4v1a**')
        elif path == 'code/model_v2/README.md':
            marker = '- [t5v0训练与核验]'
            assert text.count(marker) == 1
            if '- [t5v0a应用]' not in text:
                text = text.replace(marker, '- [t5v0a应用](t5v0a_README.md)：冻结t5v0参数的正式5非重训应用，缺数据问题跳过。\n'+marker)
        else:
            marker = '[t5v0正式4训练与缺口]'
            assert text.count(marker) == 1
            if '[t5v0a正式5非重训应用]' not in text:
                text = text.replace(marker, '[t5v0a正式5非重训应用](../code/model_v2/t5v0a_README.md)维护当期参数、条件计算及未解决项，保留t5v0全部训练系数。\n\n'+marker)
        file.write_text(text, encoding='utf-8')
        changes[path]['after'] = app.sha(file)
    app.save(out/'document_hashes.json', changes)
    costs = {p:t.material_scenarios(m,p,1.) for p in t.PRODUCTS}
    rows = '\n'.join(f'| {p} | '+ ' | '.join(f"{costs[p][form]['unit_cost_usd']:.9f}" for form in ('published','additive','proportional'))+' |' for p in t.PRODUCTS)
    actions = '\n'.join(f"| {name} | {v['action']} | {v['historical_status']} |" for name,v in m['application_actions'].items())
    params = '\n'.join(f"| {r['row']} | {r['label']} | {r['previous']} | {r['current']} |" for r in m['published_parameters'])
    (out/'report.md').write_text(f'''# t5v0a：正式5非重训应用调整

2026-10-15（北京时间）。按用户“基于建议调整模型、不是重训、缺少数据先跳过、保存t5v0a”执行。不要输出真名，姓名统一用首字母替代。

已保存独立[注册表](models_full.json)，保留t5v0所有训练系数、正式4训练曲线及29类历史状态。应用回合为正式5，新增应用曲线完整复用已保存的t5v0回合5曲线。本次未调用拟合、训练、选型或平台操作，无新增经营预测精度成绩。

## 建议落实结果

| 模块 | 本次已调整 | 假设、限制与跳过项 |
| --- | --- | --- |
| TOTAL／BASELINE／GROWTH | 基准改为正式4市场5两产品两国实际总量，记录泰国+7%、印尼−5%建筑前景；支持显式两产品两国增速情景 | 建筑到产品需求映射未知，默认不计算需求总量；不假定两产品同增速；没有自设不利幅度 |
| MATERIAL／MATERIAL_PROP | 材料基价690／9.30美元；保留公布价、加法及比例三种情景，生产量给定后同步计算材料费 | 不重新选型；修正跨价迁移未验证，三情景是机制比较而非置信区间 |
| LABOR／EFF／OPS | 工资43.50千美元/人、班次1.65/2.56、离职10%与解聘35%进入固定产量情景；运营曲线换为正式5已有曲线 | 效率必须显式给定，运营乘数不直接变成绝对效率；rho、存量和自动投入映射跳过 |
| OPERATING／FINANCE | 行政基础费10000千美元，较正式4税前增量−4000千美元；42项公布参数完整保存 | 不把前景增加400万与基础费重复叠加；现金影响、税后利润、付款时点未知，不补零 |
| SHARE／COUNTRY／ABS | 保留历史模型、暂停状态及主次用途，不新调系数 | 缺99队正式4最终决策与当前竞争行为，需求响应调整跳过；不以旧份额响应冒充回合5预测 |
| RD | 正式5两产品曲线支持有效坐标求值，核验上期实际900/1300千美元 | 仅市场5 PYT情境、限定横轴范围；不自动叠加历史研发，不推断延期收益 |
| CONNECTOR | 期初库存202.40千单位接入订单前生产及两国优先配送；使用当期材料、工资、运费和持有费 | 须显式给定需求/价格/效率/生产；无新招标设为False。历史合同、库存账面价值、收付款未齐，V2及联合完整优化跳过 |
| CAPACITY | 机器价格78／1.10美元及归档的零投资产能投影保存为条件证据 | 投影不是无条件期初资产；不推断投资生效时点或扩产收益 |
| RISK／INTEREST | 基准5%、冻结风险溢价及短贷3.50个百分点分开；仅对范围内显式财务状态求值 | 杠杆幂函数仍禁止应用；不推定未来计息状态、融资量或最低现金，现金压力结果跳过 |
| HORIZON | 评价窗口改为正式5—6，两回合 | 正式6前景、税亏和完整现金链未知，剩余利润保持null，不输出排名 |

## 材料迁移数值

单位：美元/单位。费用（千美元）=产量（千单位）×单位成本。公布价为无经验修正基准；后两列直接保留t5v0冻结系数。

| 产品 | 公布价 | 固定加价保持 | 比例修正保持 |
| --- | ---: | ---: | ---: |
{rows}

## 调用和输入

[运行说明](../../../code/model_v2/t5v0a_README.md)；[最小请求](example_request.json)与[结果](example_result.json)将未知项保留为空。这是模型应用交付，不是当前个人方案或全参数优化候选，无平台推荐值。

请求头：version=t5v0a、market_id=5、phase=formal、round=5。全部可选输入如下；不提供时跳过相应计算，不默认继承旧草稿。

| 字段 | 内容及单位 |
| --- | --- |
| production | 产品→capacity_kunits、production_kunits、previous_workers、efficiency_kunits_per_person；efficiency_basis=EXPLICIT_SCENARIO。数量千单位、人数人、效率千单位/人 |
| curve_coordinates | 曲线键rd/复合梁、rd/连接件或operations/泰国→effective_x_kusd与context；context须包含market_id=5、area=PYT、phase=formal、round=5、previous_input=900/1300/750、unit=千美元、coordinate_kind=effective_investment_scenario |
| financial_state | equity、assets、long_debt、short_debt，均为同一显式状态下的千美元数值；不代表已核验计息状态 |
| product_growth | 两产品→两国→小数增速；基于正式4实际总量的显式假设，不自动应用建筑前景 |
| connector | product包含capacity（千单位）、efficiency（千单位/人）、demand（两国千单位）、prices（两国美元/单位）；另给allocation_pct、country_priority、material_form（published/additive/proportional）与scope=BEFORE_UNVERIFIED_ORDERS |

连接件贡献是收入减当期材料、工资、运费及假设持有费；未扣期初库存账面成本，不是利润或现金流，不能据此排名。库存数量测试使用合成需求/售价，不是实际销售预测。

## 逐类状态（29类）

“条件应用调整”只表示已接入相应公布输入、显式计算或期限约束，不表示该模块完整可预测或优化成功；历史训练状态不改写为本次训练。

| 类别 | 本次动作 | 历史状态（保持） |
| --- | --- | --- |
{actions}

## 公布参数（原页面行顺序，42项）

单位保留在原标签及[完整参数来源](models_full.json)的原始分区中；同行重复标签按源行/分区区分。此表为外生条件，不是可控决策建议。

| 源表行号（从0起） | 参数 | 正式4参考值 | 正式5公布值 |
| --- | --- | ---: | ---: |
{params}

## 验收及证据

[验收](acceptance.json)：23份来源哈希一致，全部冻结系数和29类历史状态一致，正式5已有曲线逐项一致；材料三情景、工资/班次/解聘缩放、利率分解、零产量消化库存、国别情景及未知收益不补零通过，34项非法输入被拒绝。运行期禁止训练调用的保护通过。本次无重新训练或实时平台核验。

来源：[t5v0正式4训练](../../t5v0/20261015T085218049188+0800/report_final.md)、[正式5已知条件](../../round_close/20261014_formal4_close/formal5_initial/report.md)、[已保存的正式5曲线](../../t5v0/20261015T090943259882+0800_formal5_curves/report.md)、[材料诊断](../../t5_material_diagnosis/20261015T091215236523+0800/report.md)。引用聊天建议来源ID记录于[工作日志](work_log.md)。

文档先备份当前磁盘内容再更新，已有未提交修改未回退；[改前/改后哈希](document_hashes.json)。[代码与输出清单](version_manifest.json)保存运行环境和哈希；包内历史artifact仍依赖本项目归档。
''', encoding='utf-8')
    code_files = set()
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT/'code') and path.suffix == '.py': code_files.add(path)
    code_files.add(Path(__file__).resolve())
    for path in code_files:
        dest = out/'code_snapshot'/path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    app.save(out/'version_manifest.json', dict(status='FINALIZING'))
    links = []
    for file in [out/'report.md', doc] + [ROOT/p for p in changes]:
        for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
            target = target.strip('<>').split('#')[0]
            if not target or '://' in target: continue
            dest = Path(target) if Path(target).is_absolute() else file.parent/target
            assert dest.exists(), (file,target)
            links.append(dict(document=file.relative_to(ROOT).as_posix(),target=target))
    app.save(out/'link_checks.json', dict(status='PASS',checked=len(links),links=links))
    with (out/'work_log.md').open('a',encoding='utf-8') as log:
        log.write('\n验收完成：'+app.datetime.now(app.TZ).isoformat()+'。来源聊天01a13aed-cabd-76f3-94dc-5e185fddd10f建议已读取。\n'
            '仅调整条件应用，训练系数未变、无重训；23份来源哈希及34项拒绝边界通过。更新3处索引，均有改前备份、前后哈希和链接核验。\n'
            '执行更正：默认Python3.13不兼容项目3.12的SciPy扩展，首次导入失败后改用现有捆绑Python3.12，未安装依赖；初始未完成注册表备份于before/build_initial_models.json后修正动作标签。\n'
            '需求竞争、研发运营存量、真实订单、投资时点及完整现金/税亏/正式6缺口跳过；没有重采教程、生成HTML或操作平台。状态：完成（部分条件应用，不是全参数最优）。\n')
    app.save(out/'version_manifest.json', dict(version='t5v0a', training_performed=False,
        base_registry_sha256=app.sha(t.BASE/'models_full.json'),
        python=sys.executable, python_version=platform.python_version(), numpy=app.np.__version__, scipy=app.scipy.__version__,
        source_code={p.relative_to(ROOT).as_posix():app.sha(p) for p in sorted(code_files)},
        outputs={p.relative_to(out).as_posix():app.sha(p) for p in sorted(out.rglob('*'))
            if p.is_file() and not p.is_relative_to(out/'before') and p.name != 'version_manifest.json'}))
    print(json.dumps(dict(status='PASS', output=str(out), links=len(links), code_files=len(code_files)), ensure_ascii=False))


if __name__ == '__main__':
    main()
