"""Read-only replay of existing checks; append a dated twenty-issue review."""
import ast
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT/'output/issues_review'/stamp
OUT.mkdir(parents=True, exist_ok=False)
log = OUT/'work_log.md'
log.write_text(f'# 20项问题核验日志\n\n北京时间：{stamp}\n\n进行中：用户授权继续研究并核验20项。只读旧来源、模型及结果；新增独立核验，不填写网页、不替换模型。不要输出真名，姓名统一用首字母替代。\n', encoding='utf-8')
shutil.copy2(__file__, OUT/Path(__file__).name)

def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

checks = {}
def check(name, fn):
    try:
        checks[name] = dict(status='PASS', result=fn())
    except Exception as exc:
        checks[name] = dict(status='FAIL', error_type=type(exc).__name__)

import core
import audit
import formal_update_train as formal
import formal_update_state as states
import horizon
import operations_rho as ops
import verify_joint_chart_data as joint
import numpy as np

def archived():
    rows, cells, sources = core.old.load_dataset()
    result = audit.audit(rows, cells, sources)
    return {k:result[k] for k in ['checks','n_rows','n_fit','frozen_coefficients','frozen_predictions','loss_equivalence']}

def actual():
    rows, cells, sources, links = formal.dataset(formal.SOURCE)
    return dict(rows=len(rows), markets=len({r['market_id'] for r in rows}),
                verified_context_rows=sum(r['context_verified'] for r in rows), unique_keys=len({tuple(core.key(r)) for r in rows}))

def source_hashes():
    base = ROOT/'output/formal_update/20261011T230905+0800_report'
    records = read(base/'source_manifest.json')
    mismatches = []
    for r in records:
        for kind,p in [('original',Path(r['original'])),('copy',base/r['copy'])]:
            if not p.exists() or digest(p) != r['sha256']:
                mismatches.append(dict(kind=kind, file=p.relative_to(ROOT).as_posix()))
    assert not mismatches, 'Source/copy mismatch'
    return dict(records=len(records), files_checked=2*len(records))

def recovered():
    result = read('output/model_v2/20261012T095938104706+0800_git_recovery/recovery.json')
    for r in result['files']:
        p=ROOT/r['file']
        assert digest(p)==r['restored_sha256']
        json.loads(p.read_text(encoding='utf-8'))
    return dict(status=result['status'], files=len(result['files']))

def curves():
    doc=read(joint.SOURCE)
    model=read('output/visible_coefficients/20261012_round2_json/coefficients.json')
    assert digest(joint.SOURCE)==model['source_sha256'] and doc['round']==model['round']==2
    results={}
    for name,axis in [('rd','需求乘数'),('operations','效率乘数')]:
        m=model['curves'][name]
        chart=next(c['data'] for c in doc['charts'] if c['id']==m['chart_id'])
        svg=[s for s in doc['graphs'] if axis in s]
        assert len(svg)==1
        sy,_=joint.svg_values(svg[0])
        y=np.array([float(p['value']) for p in chart['dataset'][0]['data']])
        x=np.array([float(p['label']) for p in chart['categories'][0]['category']])
        assert len(y)==200 and np.max(abs(sy-y))<1e-10
        fit=joint.fit_points(x,y,m['form'])
        assert not set(fit['train_indices']) & set(fit['held_indices'])
        assert np.allclose(fit['parameters'],m['parameters'],rtol=1e-9,atol=1e-9)
        results[name]=dict(unique_points=200, y_max_difference=float(np.max(abs(sy-y))), held_mae=fit['held_mae'])
    return results

def syntax():
    paths=list((ROOT/'code').rglob('*.py'))+[Path(__file__)]
    for p in paths:
        ast.parse(p.read_text(encoding='utf-8-sig'),str(p))
    return dict(files=len(paths))

check('archive_frozen_and_loss_equivalence',archived)
check('formal1_actual_data',actual)
check('formal2_initial_states',lambda:states.self_check(formal.SOURCE))
check('formal_report_source_hashes',source_hashes)
check('git_original_recovery',recovered)
check('round2_json_svg_pair_and_fit',curves)
check('finite_horizon',horizon.self_check)
check('operations_synthetic_and_holdout',ops.self_test)
check('python_syntax',syntax)

# Each item keeps the original README numbering; diagnostics do not close identification gaps.
items = [
 (1,'部分完成','标准化、惩罚路径和留出已实现；系数作用与跨期稳定性仍未验证','独立投入变化及后续回合留出'),
 (2,'已解决','平均损失与对应加权总和惩罚重标定后系数复现；本次重新断言','无需新增资料；新增消费者须沿用统一口径'),
 (3,'部分完成','极端价格影响和分段候选已有；高价尾部稀疏，阈值与外部性能未确证','高价及普通价格区间的独立实际需求'),
 (4,'未解决','投入共变与内生性未消除；现有回归不能证明因果回报','独立投入变化或可识别的实验设计'),
 (5,'部分完成','国别独立系数已比较；竞争队营销仍为两国合计代理','逐国家实际营销预算'),
 (6,'部分完成','零值显示精度与保留零的份额候选已处理；响应形式及真实零值未确证','未取整零值及独立响应验证'),
 (7,'未解决','行业总量仍外生；正式1实际总量不等于独立识别行业响应','多回合行业价格、营销及总需求变化'),
 (8,'部分完成','正式1实际已取得并有冻结评分；条件份额仍使用已实现对手，正式2无外部标签','正式2实际及事前冻结完整预测'),
 (9,'部分完成','运营ρ独立分析及正式1重拟合、研发ρ敏感性已有；完整存量未识别','研发运营历史存量与独立变化'),
 (10,'部分完成','正式2 JSON/SVG各200点配对去重及拟合复现通过；其他市场曲线及经营验证不足','各市场各回合独立曲线及实际结果'),
 (11,'部分完成','研发外推已标记；历史回算仍须匹配历史曲线，高投入经营效果未验证','对应历史回合高投入曲线与需求'),
 (12,'部分完成','重复策略等权与效率舍入诊断已有；低运营400仍缺验证','低运营投入有效预算或实际效率'),
 (13,'部分完成','两风险函数和正式1条件期末状态留队拟合已有；还贷风险联动未验证','独立贷款变化、利率与计息样本'),
 (14,'部分完成','正式2前景和初值已归档；五部分及逐回合曲线未完整接入，训练仍取冻结研发曲线','当期参数接入、失效参数拒绝及回合选择检查'),
 (15,'部分完成','错误单位已更正、材料舍入区间已重审；差额机制未解释，不可固定跨情境使用','独立材料成本明细与未取整预算'),
 (16,'部分完成','11项旧预算重放和正式1期末数据可核；完整财务独立前瞻未验收','期初加决策的整链财务留出'),
 (17,'未解决','财务入口要求零库存、零期初短贷；大客户、税亏与厂房跨期分支尚不完整','非零订单库存短贷与亏后转盈独立样本'),
 (18,'未解决','正式6期限自检通过，但搜索仍GATED_NOT_RUN；完整滚动链未建立','合法候选、状态结转和各期前景，完成前三阶段验收'),
 (19,'部分完成','扩充单因子、组合及2000样本压力；对手、库存、短贷、订单及跨期覆盖仍false','完整可验收候选和全部经营融资分支'),
 (20,'部分完成','版本与快照隔离可追溯，两份被覆盖原件已精确恢复；旧入口截止点和旧缺口文字仍过时','统一当前入口与截止点；旧预测保留原版本')]
assert [i[0] for i in items]==list(range(1,21))
if checks['archive_frozen_and_loss_equivalence']['status']!='PASS':
    items[1]=(2,'待核验','本次损失尺度复现失败，不能关闭','排查本次检查失败')
issues=[dict(number=n,status=s,finding=f,next_evidence=e) for n,s,f,e in items]
counts=dict(Counter(r['status'] for r in issues))
result=dict(reviewed_at=stamp,scope='归档与现有实现只读核验；未采集当前平台',counts=counts,
            all_resolved=all(r['status']=='已解决' for r in issues),checks=checks,
            issues=issues,data_unverifiable=[r for r in issues if r['number'] in [1,3,4,5,6,7,8,9,10,11,12,13,15,16,17,18,19]])
with (OUT/'verification.json').open('x',encoding='utf-8') as f:
    json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
lines=['# 20项问题重新核验','',f'北京时间：{stamp}','',
       '结论：未全部解决。'+ '；'.join(f'{k}{v}项' for k,v in counts.items())+'。',
       '“部分完成”表示已有修正或诊断，但没有完成整项验收；不将缺口披露当成问题解决。',
       '', '本次新增证据：正式1实际200条、正式2期初100队重新核验；两份旧原件恢复哈希复核。正式2曲线配对复现仅验证图形，不验证需求经营效果。',
       '', '## 当前全部问题与不足','', '| 编号 | 状态 | 核验结论 | 下一步 |','|---:|---|---|---|']
lines += [f"| {r['number']} | {r['status']} | {r['finding']} | {r['next_evidence']} |" for r in issues]
lines += ['', '## 因缺乏数据而无法验证的问题','']
lines += [f"- #{r['number']}：{r['next_evidence']}。" for r in result['data_unverifiable']]
lines += ['', '## 本次运行检查','']
lines += [f"- {k}：{v['status']}。" for k,v in checks.items()]
lines += ['', '## 证据入口','',
 '- `README.md` 原始20项；`code/model_v2/audit.py` 损失尺度与冻结重放。',
 '- `output/formal_update/20261011T230135216100+0800_training/` 正式1冻结评分、重训和内部留出。',
 '- `code/formal_update_train.py` 冻结研发曲线选择；`code/model_v2/run.py` 历史截止点及搜索门槛。',
 '- `code/model_v2/finance.py` 财务适用限制及未覆盖压力类别。',
 '- `output/model_v2/20261012T095938104706+0800_git_recovery/recovery.json` 原件恢复；旧事故说明保留为历史。',
 '- `output/visible_coefficients/20261012_round2_json/` 和 `20261012_round2_joint/` 回合2曲线。',
 '', '未检查：当前网页身份、个人预算扰动、未来实际、完整UI；未重训或替换交付模型。风险：现有模型仍不能据此宣称六回合最优。']
with (OUT/'report.md').open('x',encoding='utf-8') as f:
    f.write('\n'.join(lines)+'\n')
with log.open('a',encoding='utf-8') as f:
    f.write('\n验收完成：逐项状态、所需证据及运行检查保存于report.md和verification.json；保留旧模型、原件及事故记录。检索中两次路径匹配未成功，已按实际目录纠正。\n')
print(json.dumps(dict(output=str(OUT),counts=counts,checks={k:v['status'] for k,v in checks.items()}),ensure_ascii=False))
