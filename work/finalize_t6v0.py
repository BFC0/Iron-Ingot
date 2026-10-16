"""Back up documentation before adding the verified t6v0 research version."""
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
out=Path((ROOT/'work/t6v0_active_run.txt').read_text(encoding='utf-8').strip())
rel=out.relative_to(ROOT).as_posix()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
assert read(out/'verification.json')['status']=='PASS_WITH_EXPLICIT_ASSUMPTIONS_AND_GAPS'
log=out/'delivery_work_log.md'
with log.open('x',encoding='utf-8') as f:
    f.write('# t6v0 交付与文档维护\n\n'+datetime.now(timezone(timedelta(hours=8))).isoformat()+' 开始。\n不要输出真名，姓名统一用大写首字母替代。用户授权回合5数据曲线训练、明确费用代理假设及排除极端/疑似供给偏离；离线复用归档。\n')
paths=['README.md','code/model_v2/README.md']
before={}
for name in paths:
    p=ROOT/name; dest=out/'documentation_before'/name
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    before[name]=sha(p);assert sha(dest)==before[name]
p=ROOT/'README.md';s=p.read_text(encoding='utf-8')
marker='| 最新需求竞争情景 |'
assert s.count(marker)==1
row=f'| 最新实际训练研究版本 | **t6v0**：[回合5训练与假设]({rel}/report.md)、[注册表]({rel}/models_full.json)、[复核]({rel}/verification.json)、[运行说明](code/model_v2/t6v0_README.md) | 正式5的100队实际及600点曲线；需求采用真实价格/需求与公司合计费用代理。SHARE保留复合梁193/200、连接件170/180条，极端及疑似供给偏离按训练折筛选，测试全量评分；未验证正式6迁移，未部署。 |\n'
s=s.replace(marker,row+marker)
old='正式5结果与本组最终方案已归档；先按最终决策对应关系评估冻结版本，再决定是否重训。'
assert old in s
s=s.replace(old,'正式5结果与本组最终方案已归档；t6v0已完成可估计项训练及需求费用代理研究，最终方案与冻结候选不完全匹配，未补造事前成绩。')
p.write_text(s,encoding='utf-8')
p=ROOT/'code/model_v2/README.md';s=p.read_text(encoding='utf-8')
marker='## 当前工作入口\n'
assert s.count(marker)==1
s=s.replace(marker,marker+'\n- [t6v0正式5实际训练](t6v0_README.md)：真实需求/价格与公司费用代理，极端及疑似供给偏离筛选；市场留出全量评分，600点曲线及成本/风险重训，未部署。\n')
p.write_text(s,encoding='utf-8')
p=ROOT/'code/model_v2/t6v0_README.md'
with p.open('x',encoding='utf-8') as f:
    f.write(f'''# t6v0：回合5实际数据与曲线训练

[报告](../../{rel}/report.md) · [注册表](../../{rel}/models_full.json) · [复核](../../{rel}/verification.json) · [筛选清单](../../{rel}/demand_screening.json)。

正式5的10市场100队实际结果、三曲线600点，正式4期末状态作结转参照。训练所得可用于正式6迁移研究；尚未接入正式6新增菲律宾、印尼投资及终局经营链，不输出完整决策方案。

需求的价格和需求量直接采用实际值；一般营销、设计师营销和研发采用公司合计实际费用代理，不伪造产品/国家分摊，不能解释为细分投入因果收益。rho固定0.5、正则0.001、价格对数线性，曲线跨市场共享是分析假设，详情见报告。ABS为单独的绝对需求研究，训练内选正则、外层整市场留出。

极端输入采用训练折内log1p的3IQR围栏；疑似供给偏离要求低残差与实际缺货或产能/销售证据同时成立。归因仍是假设，原记录不删除，零价/零需求单独保存。测试市场不筛除，报告全部有效测试样本误差及未筛选同规格对照。SHARE及COUNTRY是替代规格，样本不可相加。

运行：使用项目已配NumPy/SciPy的Python执行 `code/model_v2/t6v0.py`；`--self-check`执行来源守卫与筛选自检。当前可用解释器为 `<LOCAL_USER_DIR>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。系统Python与work/python_packages的SciPy二进制不匹配，不用于本版运行。

独立复核：同一解释器执行 `code/model_v2/verify_t6v0.py {rel}`。检查来源/输出哈希、实际单元格、曲线回放、每折筛选与参数、全量测试市场评分、材料/工资/风险回算及29类状态。每次训练建立新目录，旧版及历史训练结果保留。

限制：公司费用代理、需求异常的供给归因、完整研发运营历史及曲线迁移尚未独立证实；同期条件回溯不代表事前经营预测精度。模型不自动部署，不修改平台。
''')
changes=[dict(path=name,before_sha256=before[name],after_sha256=sha(ROOT/name),backup=(out/'documentation_before'/name).relative_to(ROOT).as_posix()) for name in paths]
changes.append(dict(path='code/model_v2/t6v0_README.md',before_sha256=None,after_sha256=sha(p),backup=None))
links=[]
for name in paths+['code/model_v2/t6v0_README.md']:
    doc=ROOT/name
    for target in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        target=target.split('#')[0]
        resolved=doc.parent/target
        exists=resolved.exists();links.append(dict(document=name,target=target,exists=exists))
assert all(x['exists'] for x in links),[x for x in links if not x['exists']]
(out/'documentation_changes.json').write_text(json.dumps(dict(changes=changes,links=links),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
failures={
    '20261015T234750573527+0800':'原归档无selected_period字段，来源读取适配后新目录重跑。',
    '20261015T234829103336+0800':'前景页不含回合选择器，改以已核版本清单及源哈希核验归属。',
    '20261015T234857934586+0800':'旧曲线日志哈希已变化；未改原件，收窄为实际使用的曲线参数及其源哈希，数值产物匹配。',
    '20261015T234913839857+0800':'中间成功运行，后续完善供给筛选及报告，以最终目录为准。',
    '20261015T235121354869+0800':'中间成功运行，后续补齐ABS绝对需求，以最终目录为准。'}
for folder,reason in failures.items():
    previous=ROOT/'output/t6v0'/folder
    with (previous/'run_status.md').open('x',encoding='utf-8') as f:f.write('# 本次运行状态\n\n历史尝试，非最终交付。'+reason+'\n最终版本：../'+out.name+'/report.md\n')
with log.open('a',encoding='utf-8') as f:
    f.write('\n完成：说明改前备份、前后SHA256及全部本地链接核验通过。训练与独立复核通过。系统Python二进制不匹配后改用现成项目解释器；修复单国空样本自检，来源结构适配失败的三个目录及两个中间成功目录保留并标记。未覆盖历史资料、未操作平台。\n')
(out/'delivery_hashes.json').write_text(json.dumps({str(p.relative_to(out)).replace('\\','/'):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='delivery_hashes.json'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(output=rel,document_changes=len(changes),links_checked=len(links),status='PASS'),ensure_ascii=False))
