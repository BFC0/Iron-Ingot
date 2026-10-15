"""Apply the user's budget correction; retain sources and pre-edit copies."""
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output/budget_semantics' / stamp
OUT.mkdir(parents=True, exist_ok=False)
log = OUT / '工作日志.md'
log.write_text('# 预算与完整决策口径更正\n\n'
               '2026-10-13用户说明为依据；姓名统一用首字母。\n\n'
               '进行中：修正活动文档、生成器及派生标签；正式3两份预算保留为手改前后两个方案。'
               '不读取或修改平台，不重训，不改原件或冻结模型。\n', encoding='utf-8')
assumption = '按当时决策填写的需求预估测算，并默认按预估数量售出（用户2026-10-13更正）；须同时检查保存有效性'
old_assumptions = ['基准方案；不得套用后续全部售出假设',
                   '假设全部售出（用户说明）；须同时检查保存有效性',
                   '依赖当时决策及手填预测；具体销量假设未确认']
rules = '''## 预算与决策读取更正（2026-10-13用户确认）

- 正式3先前两份财务预算属于两个决策版本：第二份与第一份不同，是用户手动修改了部分决策数字。保留两份原件，分别绑定采集时刻、本人方案与需求预估；不能混合成同一方案，也不能仅因差异判为采集错误。缺少配对决策时标明“未配对”，不把后读值回填给前一份预算。
- 完整决策优先从“决策 → 决策列表”读取，按本人姓名所在列定位（展示用PYT），结合表头、分区、国家、产品和单位逐项保存。绿色格子是未改动的默认值，蓝色格子是改动过的值；两种颜色的值都要读取。颜色标记改动状态，不代表数据真假或来源类别；旧快照未保存颜色时标记未知，不凭数值差异推断颜色。
- 输出推荐或最优候选时，按该回合决策列表的完整输入清单及顺序逐项输出，涵盖决策项与预估项。列出国家/产品、参数名、单位、当前值、建议值、是否调整、依据与约束；保留默认值、未调整值、零值和选择项，不能只列优化变量。未建模项明确“保留当前值／未优化”，缺失项明确未知，不能补零。预算结果另列，不作为可编辑决策；按唯一字段键核验输出无遗漏、重复或多余项。未完成完整优化时保持候选方案标识。
- 预算中的需求采用决策所填的需求预估，默认按预估数量售出产品；撤回此前“全部产量或货物全部售出”的解释。预算销量、收入和利润仍是条件测算，不能作为实际需求、销量或利润训练标签。对供给、物流及订单的具体约束另按平台规则核验，不因本次更正改写已有公式或假定所有库存售罄。

'''
replacements = {
    'README.md': [('全部售出假设及保存有效性另列', '按决策需求预估售出的预算假设及保存有效性另列'),
                  ('# Cesim 项目总览\n', '# Cesim 项目总览\n\n预算与完整决策口径（2026-10-13）：[用户更正与执行规则](Cesim_任务要求与当前情况说明.md#预算与决策读取更正2026-10-13用户确认)。正式3两份预算分别对应手改前后方案；完整读取本人决策列表，绿色为默认值、蓝色为改动值；推荐覆盖全部输入与预估项。预算按填写的需求预估测算售出数量。\n')],
    'Cesim_任务要求与当前情况说明.md': [('## 执行要求\n', rules + '## 执行要求\n')],
    '参数细化与六回合期限要求.md': [('并包含全部售出等理想条件，具体适用范围待核验', '其中需求按决策所填需求预估计算，默认按预估数量售出产品（2026-10-13用户更正），具体供给与物流约束另行核验'),
        ('## 待细化参数与机制\n', '## 完整决策交付（2026-10-13）\n\n推荐须以当回合“决策 → 决策列表”的本人列为字段清单，包含全部决策项和预估项，绿色默认值与蓝色改动值均保留。未优化项输出当前值并明确标识，不能遗漏或默认补零；预算结果另列。逐字段输出及版本配对按[任务说明](Cesim_任务要求与当前情况说明.md#预算与决策读取更正2026-10-13用户确认)核验。\n\n## 待细化参数与机制\n')],
    '原生键盘标准操作.md': [('2. 进入“决策列表”，确认新值在自己的个人列。', '2. 进入“决策 → 决策列表”，确认新值在自己的个人列。读取该列全部输入与预估项：绿色为未改动默认值，蓝色为改动值（用户2026-10-13确认）；旧快照缺少颜色时记录未知。')],
    '预测模型与训练参数汇总.md': [('按货物全部售出等理想条件计算；这属于预算机制的工作理解，具体字段、假设和公式仍须逐项核验', '需求按决策所填需求预估计算，并默认按预估数量售出产品（用户2026-10-13更正）；具体字段、供给与物流约束和公式仍须逐项核验')],
    'code/summarize_model_parameters.py': [('按货物全部售出等理想条件计算；这属于预算机制的工作理解，具体字段、假设和公式仍须逐项核验', '需求按决策所填需求预估计算，并默认按预估数量售出产品（用户2026-10-13更正）；具体字段、供给与物流约束和公式仍须逐项核验')],
    '预测模型与变量说明.md': [('按货物全部售出等理想条件计算的数值不等于实际终值', '按决策所填需求预估计算需求，并默认按预估数量售出的预算数值不等于实际终值（用户2026-10-13更正）')],
    'code/label_data.py': [(old, assumption) for old in old_assumptions] + [
        ("assert probe[0]['assumption'].startswith('假设全部售出')", "assert '按当时决策填写的需求预估测算' in probe[0]['assumption']")],
    'output/data_labels/说明.md': [('用户随后确认：手填试验后从网页读出的预算也归入“预算测算值”，不用第六种主类别。“手填试验后网页预算”“假设全部售出”保存在 `budget_subtype`、`assumption` 字段。未成功保存的试验保留 `save_status=invalid`；预算始终 `usable_as_actual=false`。不能把全部售出的假设推广到常规预算或试验前基准预算；这些记录保留各自的假设说明。',
        '用户2026-10-13更正：所有网页预算仍归入“预算测算值”；需求采用决策所填需求预估，默认按预估数量售出产品，撤回旧“假设全部售出”口径。`budget_subtype` 保留基准、手填试验与常规预算区别，`assumption` 同步新口径。未成功保存的试验保留 `save_status=invalid`；预算始终 `usable_as_actual=false`。不同决策版本的预算分别配对，不混用。')],
}
for relative in ['数据分组索引.json', '分组表格行索引.csv', 'output/data_labels/cell_labels.json', 'output/data_labels/数据标签.csv']:
    replacements[relative] = [(old, assumption) for old in old_assumptions]

source_dir = ROOT / 'output/round_close/20261012T221044.031+0800/raw'
sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in source_dir.glob('round3_*.json')}
changes = []
for relative, pairs in replacements.items():
    path = ROOT / relative
    before = path.read_text(encoding='utf-8-sig')
    after = before
    for old, new in pairs:
        assert old in after, (relative, old)
        after = after.replace(old, new)
    backup = OUT / 'before' / relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(path.read_bytes())
    # Retain CSV BOM and existing newline style.
    original = path.read_bytes()
    encoded = after.replace('\n', '\r\n') if b'\r\n' in original else after
    path.write_bytes(encoded.encode('utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'))
    assert all(new in after and (old in new or old not in after) for old, new in pairs)
    if path.suffix == '.json':
        json.loads(after)
    if path.suffix == '.py':
        compile(after, str(path), 'exec')
    changes.append(dict(file=relative, before_sha256=hashlib.sha256(original).hexdigest(),
                        after_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

sys.path.insert(0, str(ROOT / 'code'))
from label_data import budget_source
for name, subtype in [('baseline', '试验前基准预算'), ('probe_B', '手填试验后网页预算'), ('ordinary', '常规网页预算')]:
    assert budget_source({'file': name + '.json'}) == (subtype, assumption)
assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha for p, sha in sources.items())
(OUT / '正式3更正.md').write_text('# 正式3预算版本说明\n\n' + rules.split('\n\n', 1)[1] +
    '来源：用户2026-10-13本对话说明。现有采集完成清单为 `output/round_close/20261012T221044.031+0800/round3_complete.json`，其中本人方案变化应结合本次说明解释为用户手改。该历史清单及原始采集不覆盖；缺失预算子表与颜色证据仍按原核验保留缺口。此次没有逐表确认两份预算与决策的精确配对。\n', encoding='utf-8')
(OUT / 'verification.json').write_text(json.dumps(dict(status='PASS', changes=changes,
    budget_subtypes_checked=3, round3_source_hashes=sources, raw_sources_unchanged=True,
    generators_synced=True, models_retrained=False, platform_modified=False,
    limitations=['未逐表配对两份正式3预算', '未重新采集格子颜色', '未重新导出旧Word或HTML报告']),
    ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
with log.open('a', encoding='utf-8') as stream:
    stream.write(f'\n完成：{len(changes)}个活动文件同步，三种预算来源的断言通过，JSON解析和Python语法检查通过；正式3原件哈希不变。编辑前副本、变更哈希与限制见 verification.json。旧历史报告、Word和冻结模型仍保留当时口径，现行要求以本次更正为准。\n')
print(json.dumps(dict(output=str(OUT), changed_files=len(changes), status='PASS'), ensure_ascii=False))
