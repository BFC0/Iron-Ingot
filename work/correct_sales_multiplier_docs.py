"""Correct current prose only; preserve pre-edit copies and historical evidence."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output/curve_semantics' / (stamp + '_given_values')
OUT.mkdir(parents=True, exist_ok=False)
statement = ('销售页价格、一般营销、设计师营销、研发四项需求乘数暂按平台给定数值记录；'
             '现有证据不足以认定它们随当前个人决策输入变化，不再据此分别拟合函数。'
             '“给定”不代表跨回合或情境不变，须按市场、国家、产品、阶段、回合及情境保存；'
             '确切含义、适用范围及其进入需求模型的方式仍待核验。')
replacements = {
    'README.md': [('销售四项需求乘数是当前对应决策值的函数显示点，应分国家、分类别拟合，不能当固定需求系数。', statement)],
    '参数细化与六回合期限要求.md': [('销售四项乘数是当前价格、一般营销、设计师营销、研发决策对应的函数值，按国家和类别分别收集多组输入—乘数配对拟合，不能当固定系数。', statement)],
    '预测模型与训练参数汇总.md': [('销售四项需求乘数分别是当前对应决策输入的函数值，须分国家、分类别拟合。', statement)],
    'code/summarize_model_parameters.py': [('销售四项需求乘数分别是当前对应决策输入的函数值，须分国家、分类别拟合。', statement)],
    '网页图表原始数据读取.md': [
        ('销售图中的价格、一般营销、设计师营销、研发四个需求乘数，分别是当前决策相应输入的函数值。按国家与类别分别保存 `当前输入→显示乘数` 配对并拟合；图中横向位置/权重不能当作当前决策输入，显示乘数不能当作固定系数，也不能当作实际需求标签。单次截图提供四个不同函数各一个显示点；每个函数需要收集该类别的多个输入取值，或读取其完整响应数据。', statement + ' 图中横向位置/权重和纵向相对竞争位置分别保存，不当作实际需求标签，也不未经核验直接替代需求模型系数。'),
        ('采样时记录当前完整决策、上一期实际研发/运营投入、国家、情境、区域、时间和显示精度；固定其他条件分别拟合四个函数。研发销售点与生产页研发曲线须先核验关系，不能重复乘入需求。生产曲线跨团队或练习/正式迁移须匹配上期投入，或已有经验证的历史映射；不能直接要求不同历史状态下的原始点相等。', '销售页给定数值与生产页投入响应曲线分别处理。正式2手动试验中，个人价格2200保存并重入确认后，四个销售图表点与基准相同；这支持暂按给定数值处理，但不能证明所有投入、回合或情境下均不变化。回合结束后用户要求停止拟合，未生成四函数参数，恢复状态未完成核验，见[试验记录](output/sales_response/20261012_manual_formal2/工作日志.md)。研发销售项与生产页研发曲线的关系仍须核验，避免重复计入需求。生产曲线跨团队或练习/正式迁移仍须匹配上期投入，或已有经验证的历史映射。')],
    'code/t2v0_um/README.md': [
        ('销售四项乘数分别是当前相应输入的函数值，不能当固定系数。', statement),
        ('- 销售项是各类别自己的输入—乘数配对，必须保持国别和类别对应。value采用 `{"kind":"curve","factor":"price/general/designer/rd之一","x":[该类别当前决策输入],"y":[对应显示乘数],"input_unit":"原始输入单位","conditions":{"其他输入":"固定值及历史状态"}}`。同屏四个类别各提供一个函数显示点，不是同一函数的四个样本。分别积累同条件下多个取值后拟合；不接受 published_coefficient，也不使用图中横向权重替代当前输入。', '- ' + statement + ' 归档应保留四类原始显示值、图轴定义、国别/产品/时期身份和来源，不要求手动变值拟合。现有 pipeline.py 销售证据校验仍要求 curve 并拒绝 published_coefficient，是此前口径的实现，尚未适配给定值记录；不要为了通过旧校验伪造响应曲线。本次只修正文档，未更改或启用该迁移流程。')],
}
old_help = '销售四类显示点应分别绑定当前决策及本市场竞争条件，不能把四点当同一曲线的四条样本，也不能把显示乘数直接当固定系数。'
for name in ('report.md', 'report_base.md'):
    replacements[f'output/help_review/20261012/{name}'] = [(old_help, statement + ' 显示值与模型训练系数分开记录，不把四个类别当成同一响应曲线的四条样本。')]

historical = ('output/curve_semantics/20261012_correction/工作日志.md',
              'output/sales_response/20261012_manual_formal2/工作日志.md')
log = OUT / '工作日志.md'
log.write_text('# 销售乘数文档口径更正\n\n用户授权修正文档。不要输出真名，姓名统一用首字母替代。\n\n'
               '进行中：同步当前说明与生成模板；旧日志加后续更正提示，历史原件、快照及模型保留。\n', encoding='utf-8')
changes = []
for relative in list(replacements) + list(historical):
    path = ROOT / relative
    before = path.read_text(encoding='utf-8')
    after = before
    for old, new in replacements.get(relative, []):
        assert after.count(old) == 1, (relative, 'Expected exactly one outdated passage')
        after = after.replace(old, new, 1)
    if relative in historical:
        heading, body = after.split('\n', 1)
        after = heading + '\n\n> 后续更正（2026-10-12）：' + statement + ' 下文为当时判断和操作经过，关于四项函数拟合的旧口径已撤回，不作为现行要求。\n' + body
    assert after != before, relative
    backup = OUT / 'before' / relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(path.read_bytes())
    path.write_text(after, encoding='utf-8')
    changes.append(dict(file=relative, before_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),
                        after_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

for relative, pairs in replacements.items():
    text = (ROOT / relative).read_text(encoding='utf-8')
    assert all(old not in text and new in text for old, new in pairs), relative
assert '研发需求乘数记作' in (ROOT / '网页图表原始数据读取.md').read_text(encoding='utf-8')
assert statement in (ROOT / 'code/summarize_model_parameters.py').read_text(encoding='utf-8')
(OUT / 'verification.json').write_text(json.dumps(dict(changes=changes, checks_passed=True,
    current_wrong_passages_removed=True, generator_synced=True, historical_logs_superseded=True,
    production_history_rule_retained=True, models_retrained=False, browser_modified=False,
    pipeline_given_value_support='NOT_IMPLEMENTED_DOCUMENTED_LIMITATION'), ensure_ascii=False, indent=2), encoding='utf-8')
with log.open('a', encoding='utf-8') as stream:
    stream.write(f'\n完成：更新{len(changes)}个文件。逐条断言确认旧表述已替换、生成器同步、生产曲线历史条件保留。编辑前副本及文件哈希见 before/ 与 verification.json。未重训模型、未修改网页或原始证据。代码校验尚未适配给定值口径，已在正式2说明中注明。\n')
print(json.dumps(dict(output=str(OUT), files=[r['file'] for r in changes], checks_passed=True), ensure_ascii=False))
