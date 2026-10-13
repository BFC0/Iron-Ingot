import ast
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'code/model_v2'))
sys.path.insert(0,str(root/'code'))
import operations_rho
from horizon import self_check
from live_review import review as legacy_review

digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
trial=root/'output/model_v2/20261011T215311031194+0800_current_trial'
manifest=json.loads((trial/'manifest.json').read_text(encoding='utf-8'))
for s,h in manifest['input_hashes'].items(): assert digest(root/s)==h,s
for s,h in manifest['result_hashes'].items(): assert digest(trial/s)==h,s
for s,h in manifest['code_hashes'].items(): assert digest(trial/'code_snapshot'/s)==h,s
for p in (root/'code/model_v2').glob('*.py'): ast.parse(p.read_text(encoding='utf-8'),str(p))
operations=root/'output/operations_rho/20261011T213209904415+0800'
op_manifest=json.loads((operations/'manifest.json').read_text(encoding='utf-8'))
for s,h in op_manifest['sources'].items(): assert digest(root/s)==h,s
for s,h in op_manifest['outputs'].items(): assert digest(operations/s)==h,s
op=json.loads((operations/'model.json').read_text(encoding='utf-8'))
fit=operations_rho.select([r for r in op['rows'] if r['round']==1],op['curve_parameters'])
assert fit==op['chosen']
assert operations_rho.self_test()==op['checks']
legacy=legacy_review()
assert len(legacy['altered_original_sources'])==2 and not legacy['tests']['calibratable']
htmls=[]
for p in (root/'output/model_v2').glob('*/report.html'):
    m=json.loads((p.parent/'manifest.json').read_text(encoding='utf-8'))
    assert digest(p)==m['result_hashes']['report.html']
    htmls.append(p.relative_to(root).as_posix())
protected=json.loads((root/'output/model_v2/20261011T193318735151+0800/snapshot/protected_hashes.json').read_text(encoding='utf-8'))
authorized={'README.md','练习与正式_已知数据差异.md','预测模型与变量说明.md','Cesim_任务要求与当前情况说明.md','原生键盘标准操作.md'}
for s,h in protected.items():
    if s not in authorized: assert digest(root/s)==h,s
stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
out=root/'output/model_v2'/(stamp+'_remaining_checks');out.mkdir()
result=dict(current_trial=str(trial.relative_to(root)),source_and_result_hashes_verified=True,
    old_protected_files_unchanged=len(protected)-len(authorized),authorized_shared_document_updates=sorted(authorized),
    htmls_unchanged=htmls,python_syntax='PASS',horizon=self_check(),
    operations_review=dict(source=str(operations.relative_to(root)),selected=fit,exact_replay=True,
        deployment='未切换利润模型或玩家效率输入',operations400='仍超训练投入范围'),
    legacy_raw_integrity=dict(status=legacy['source_integrity_status'],affected=legacy['altered_original_sources'],recovered=False))
(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
print('PASS: trial provenance, finite horizon, operations replay, protected originals and unchanged HTML; legacy raw gap disclosed')
