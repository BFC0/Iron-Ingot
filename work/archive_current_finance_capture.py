import json
import shutil
import hashlib
from pathlib import Path

root=Path(__file__).resolve().parents[1]
old=root/'output/model_v2/20261011T195500_live'
new=root/'output/model_v2/20261011T211500_live_finance'
names=['finance_before','checklist_before','production_before','checklist_operations400',
       'production400_before','baseline400_income','baseline400_balance','baseline400_cashflow',
       'machine20_input','machine20_checklist','machine20_reentry','machine20_plan','machine20_income',
       'machine20_balance','machine20_cashflow','machine20_before_restore','machine10_restored_input',
       'machine10_restored_checklist']
for name in names:
    target=new/(name+'.json')
    assert not target.exists()
    shutil.copy2(old/(name+'.json'),target)
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
previous=json.loads((root/'output/model_v2/20261011T204411978414+0800/live_trials.json').read_text(encoding='utf-8'))
altered=[dict(file=s,expected_sha256=h,current_sha256=digest(root/s))
         for s,h in previous['source_hashes'].items() if digest(root/s)!=h]
assert {Path(r['file']).name for r in altered}=={'checklist_before.json','production_before.json'}
incident=dict(status='DISCLOSED_RAW_BASELINE_OVERWRITE',cause='旧capture函数闭包仍指向原目录；两次复用基准文件名覆盖旧原件',
              affected=altered,raw_originals_recovered=False,
              remediation='本次文件复制到新独立目录；后续写入显式路径并使用wx；旧派生报告及其他原件保留，旧基准缺口不伪装复原',
              frozen_derived_record='output/model_v2/20261011T204411978414+0800/live_trials.json')
(new/'source_integrity_incident.json').write_text(json.dumps(incident,ensure_ascii=False,indent=2),encoding='utf-8')
print('18 captures preserved separately; two legacy raw gaps documented')
