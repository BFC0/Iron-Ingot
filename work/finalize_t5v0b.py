"""Finalize the offline t5v0b application and preserve current documentation backups."""
import platform
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code/model_v2'))
import t5v0b as t
from verify_t5v0b import verify


def main():
    app = t.app
    out = Path((ROOT/'work/t5v0b_active_run.txt').read_text(encoding='utf-8').strip())
    assert not (out/'report.md').exists(),'Refuse to overwrite a completed report'
    old_manifest = app.read(t.BASE/'version_manifest.json')
    for p,digest in old_manifest['outputs'].items(): assert app.sha(t.BASE/p) == digest,p
    with app.no_training():
        acceptance = verify(out)
        model = app.read(out/'models_full.json')
        request = app.read(out/'example_request.json')
        held_request = dict(request,demand_basis='FORMAL4_OWN_SHARE_HELD')
        held = t.apply_request(model,held_request)
        unit_request = dict(request,investments_kunits=dict.fromkeys(t.PRODUCTS,1.))
        unit = t.apply_request(model,unit_request)
    for name,value in [('acceptance.json',acceptance),('own_share_held_request.json',held_request),
                       ('own_share_held_result.json',held),('unit_investment_request.json',unit_request),
                       ('unit_investment_result.json',unit)]: app.save(out/name,value)
    result = app.read(out/'example_result.json')
    rows = []
    for p in t.PRODUCTS:
        for c in t.COUNTRIES:
            previous = model['formal4_market_totals_kunits'][p][c]
            total = result['market_totals']['totals_kunits'][p][c]
            baseline = result['equal_share_baseline_kunits'][p][c]
            own = model['formal4_own_demand_kunits'][p][c]
            held_demand = held['demand']['demand_kunits'][p][c]
            rows.append(f'| {p} | {c} | {previous:.6f} | {t.GROWTH[c]:+.0%} | {total:.6f} | {baseline:.6f} | {own:.6f} | {held_demand:.6f} |')
    actions = '\n'.join(f"| {name} | {item['t5v0b_impact']} | {item['action']} |" for name,item in model['application_actions'].items())
    rel = out.relative_to(ROOT).as_posix()
    doc = ROOT/'code/model_v2/t5v0b_README.md'
    assert not doc.exists(),'Refuse to overwrite an existing version document'
    doc.write_text(f'''# t5v0b：国别需求映射与机器稳定价

2026-10-15（北京时间）。基于t5v0a，保留t5v0全部训练系数及已有回合5曲线，不重训或选型。

[报告](../../{rel}/report.md) · [注册表](../../{rel}/models_full.json) · [验收](../../{rel}/acceptance.json) · [29类影响](../../{rel}/model_adjustments.json)。

用户假设：泰国+7%、印尼−5%作为两产品需求变化比例，默认进入正式4实际总量到正式5总量的计算。机器趋稳按正式5公布78／1.10美元/单位处理，不改回上期价；正式6价格和投资生效时点仍未知。

```powershell
$py = '<LOCAL_USER_DIR>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $py code/model_v2/t5v0b.py --bundle {rel}
& $py code/model_v2/verify_t5v0b.py {rel}
```

请求头为version=t5v0b、market_id=5、phase=formal、round=5。沿用[t5v0a输入](t5v0a_README.md)，但product_growth固定为两产品泰国0.07、印尼−0.05，不能另行覆盖。

新增investments_kunits（两产品投资量，千单位，零投资显式0），仅计算采购金额，不擅自计算付款现金或生效产能；可选demand_basis=FORMAL4_OWN_SHARE_HELD须额外假设本组份额保持，连接件缺省需求会取该情景，冲突需求拒绝。默认只给市场总量及等份额基线，公司竞争需求仍待数据。

29类均记录影响，成本、效率、曲线、风险参数不因这两个外生假设重新拟合；新总量不再乘到ABS独立数量输出，也不重复施加正式6。此交付是全模型影响检查和条件应用调整，不是全部可控决策的优化方案。已知数据缺口按授权跳过，完整收益仍不可排名。

运行依赖项目归档及现有Python3.12/NumPy/SciPy；artifact引用原t5v0档案，不能单独搬走包运行。代码快照供追溯，正常入口在项目code目录。
''',encoding='utf-8')
    changes = app.read(out/'document_hashes.json')
    for path,hashes in changes.items():
        file = ROOT/path
        assert app.sha(file) == hashes['before'],'Document changed during run: '+path
        text = file.read_text(encoding='utf-8')
        if path == 'README.md':
            marker = '| 最新独立应用情景 | **t5v0a**'
            assert text.count(marker) == 1
            row = (f'| 最新独立应用情景 | **t5v0b**：[报告]({rel}/report.md)、[注册表]({rel}/models_full.json)、'
                   f'[验收]({rel}/acceptance.json)、[运行说明](code/model_v2/t5v0b_README.md) | '
                   '两产品国别需求默认按泰国+7%／印尼−5%重算；机器按正式5固定公布价78／1.10计采购金额。29类逐项记录影响，系数不重训，缺数据继续跳过，不是完整决策优化。 |\n')
            text = text.replace(marker,row+'| 正式5前一应用版本 | **t5v0a**')
        elif path == 'code/model_v2/README.md':
            marker = '- [t5v0a应用]'
            assert text.count(marker) == 1
            text = text.replace(marker,'- [t5v0b应用](t5v0b_README.md)：国别市场变化映射为需求变化、机器稳定公布价，逐项检查29类影响，不重训。\n'+marker)
        else:
            marker = '[t5v0a正式5非重训应用]'
            assert text.count(marker) == 1
            text = text.replace(marker,'[t5v0b国别需求与机器稳定价](../code/model_v2/t5v0b_README.md)接入用户指定需求比例假设并保留全部训练系数，维护29类影响与数据缺口。\n\n'+marker)
        file.write_text(text,encoding='utf-8')
        hashes['after'] = app.sha(file)
    app.save(out/'document_hashes.json',changes)
    (out/'report.md').write_text(f'''# t5v0b：国别需求变化与机器价格趋稳

2026-10-15（北京时间）。按用户两项新要求调整全部模型的应用条件，独立保存t5v0b。不要输出真名，姓名统一用首字母替代。

已完成29类模型影响检查及可用计算路径调整，不重训、不重新选型。原t5v0与t5v0a保留。这里的“全模型”是逐项检查并统一应用这两项外生假设；缺数据模块保持暂停，不宣称全参数最优或完整利润预测。

## 两点的处理

| 项目 | t5v0a | t5v0b | 性质与边界 |
| --- | --- | --- | --- |
| 国别市场变化→产品需求 | 默认不映射，需另给产品国别增长 | 两产品泰国+7%、印尼−5%默认生效 | 用户明确指定的分析假设，未改称平台机制或实证验证 |
| 市场总量及BASELINE | 缺映射时跳过 | 正式4实际总量分别乘1.07／0.95，并重算10队等份额基线 | 行业总量已可算，竞争份额仍另求；本组份额不能自动等于1/10 |
| 机器价格趋稳 | 已保存正式5公布价78／1.10，但没有独立投资金额接口 | 按正式5固定公布价接通投资数量→采购金额 | 上期58／1.00不替代当期价；旧代码也未额外预测涨价，本次未虚构或删除不存在的涨价系数 |
| 跨期 | 仅正式5—6期限、未来未知 | 同一边界：正式5增速不自动重复至正式6，正式6机器价仍未知 | 当期“趋稳”不能单独证明未来回合精确同价，投资支付及生效时点仍缺证据 |

## 已重算需求

全部数量单位为千单位。前五列采用用户明确假设；末列另需“本组各产品国别份额保持”假设，只是对照情景，不是竞争模型预测或当前决策建议。

| 产品 | 国家 | 正式4市场实际需求 | 变化比例 | 正式5市场情景需求 | 10队等份额基线 | 正式4本组实际需求 | 本组份额保持情景 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

公式：`市场需求5=市场实际需求4×(1+国别增速)`；`等份额基线=市场需求5÷10`。显式本组份额保持情景等价于`本组实际需求4×(1+国别增速)`。价格、营销、研发及竞争行为变化时不能继续把该份额假设当成已预测结果。销量仍须经过供给、库存和订单约束。

## 稳定机器价如何进入模型

| 产品 | 正式4参考价 | 正式5固定公布价，美元/单位 | 每投资1千单位的采购金额，千美元 |
| --- | ---: | ---: | ---: |
| 复合梁 | 58 | 78 | 78 |
| 连接件 | 1.00 | 1.10 | 1.10 |

`采购金额（千美元）=投资量（千单位）×公布价（美元/单位）`。上述1千单位仅单位自检，不是推荐投资规模。机器“趋稳”不等于免费投资、已增加生产能力或确定期末现金。现金支付、生效产能、折旧增量、正式6回收收益仍保持未知，FINANCE/HORIZON不能凭采购金额补齐。

## 29类逐项影响

各类历史训练状态不改写。“沿用/跳过/条件调整”列沿用t5v0a处理边界，新增影响列准确记录本次两点如何传导。

| 类别 | 本次影响或跳过原因 | 沿用处理边界 |
| --- | --- | --- |
{actions}

生产、班次、工资、材料、运输及持有费仍根据显式方案输入重算；不能仅因市场增长便强制提高生产量。显式本组份额保持情景可统一填充连接件需求，供给及202.40千单位期初库存使用同一需求链；冲突输入被拒绝。研发及运营曲线、风险参数不会因市场增速或机器趋势而自动改变。

## 复现与验收

[运行说明](../../../code/model_v2/t5v0b_README.md) · [注册表](models_full.json) · [29类调整](model_adjustments.json) · [验收](acceptance.json)。

[默认请求](example_request.json)及[结果](example_result.json)给市场总量和等份额基线，公司竞争需求仍明确跳过；[本组份额保持请求](own_share_held_request.json)与[结果](own_share_held_result.json)单列额外假设；[单位投资请求](unit_investment_request.json)及[结果](unit_investment_result.json)用于金额校验。

验收通过：全部冻结模型参数和回合5已有曲线不变；25份来源哈希一致；四组国别需求比例及10队基线守恒；机器采购金额、零投资、非法输入拒绝、同输入下工资/材料/利率/曲线与t5v0a一致；连接件需求/库存传导一致；禁止训练调用的保护覆盖构建和复核。t5v0a完整原验收再次通过，本次增加12项非法输入拒绝。

缺99队最终决策、当前竞争输入、投入完整存量、历史合同、库存计价、投资支付/生效、税亏与完整现金链、正式6前景的问题继续跳过。没有生成决策候选、运行决策最优搜索或修改平台；本次不新增预测精度或收益改善结论。

来源：[t5v0a](../../t5v0a/20261015T131507850861+0800/report.md)、[正式5前景](../../round_close/20261014_formal4_close/formal5_initial/report.md)、[t5v0训练](../../t5v0/20261015T085218049188+0800/report_final.md)。原始前景、参数和需求来源哈希在注册表；用户假设单独记录，不覆盖原始参数。

[文档前后哈希](document_hashes.json) · [工作日志](work_log.md) · [版本与文件清单](version_manifest.json)。3处索引先备份当前内容，已有未提交修改保留。代码快照用于追溯，当前运行依赖本项目归档。
''',encoding='utf-8')
    files = set()
    for module in list(sys.modules.values()):
        filename = getattr(module,'__file__',None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(ROOT/'code'): files.add(path)
    files.add(Path(__file__).resolve())
    for file in files:
        dest = out/'code_snapshot'/file.relative_to(ROOT)
        dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(file,dest)
    app.save(out/'version_manifest.json',dict(status='FINALIZING'))
    links = []
    for file in [out/'report.md',doc]+[ROOT/p for p in changes]:
        for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',file.read_text(encoding='utf-8')):
            target = target.strip('<>').split('#')[0]
            if not target or '://' in target: continue
            dest = Path(target) if Path(target).is_absolute() else file.parent/target
            assert dest.exists(),(file,target)
            links.append(dict(document=file.relative_to(ROOT).as_posix(),target=target))
    app.save(out/'link_checks.json',dict(status='PASS',checked=len(links),links=links))
    with (out/'work_log.md').open('a',encoding='utf-8') as log:
        log.write('\n完成：'+app.datetime.now(app.TZ).isoformat()+'。29类影响已记录，25份来源哈希、原t5v0a验收及新增12项拒绝边界通过；'
            '未重训，未改变冻结系数。市场总量默认映射、单位机器投资金额可算，公司历史份额保持仅显式对照。缺数据问题继续跳过，未运行决策方案搜索或操作平台。'
            f'3处文档当前内容已备份，前后哈希保存，{len(links)}条链接核验通过。状态：完成。\n')
    app.save(out/'version_manifest.json',dict(version='t5v0b',training_performed=False,
        python=sys.executable,python_version=platform.python_version(),numpy=app.np.__version__,scipy=app.scipy.__version__,
        source_code={p.relative_to(ROOT).as_posix():app.sha(p) for p in sorted(files)},
        documents={p:app.sha(ROOT/p) for p in [*changes,'code/model_v2/t5v0b_README.md']},
        outputs={p.relative_to(out).as_posix():app.sha(p) for p in sorted(out.rglob('*'))
                 if p.is_file() and not p.is_relative_to(out/'before') and p.name != 'version_manifest.json'},
        prior_manifest_sha256=app.sha(t.BASE/'version_manifest.json')))
    print(app.json.dumps(dict(status='PASS',output=str(out),links=len(links),source_files=len(files)),ensure_ascii=False))


if __name__ == '__main__':
    main()
