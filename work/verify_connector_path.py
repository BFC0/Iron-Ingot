"""Exercise and archive connector fixed-plan path without retraining demand."""
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0,str(ROOT/'code/model_v2'))
import t3v1 as model
from connector_free_production import project

nd = model.nd
old = ROOT/'output/t3v1/20261013T193815695205+0800'
manifest = nd.read(old/'manifest.json')
assert all(nd.sha(old/p)==h for p,h in manifest['output_hashes'].items())
request = nd.read(old/'example_request.json')
request['connector_plan'] = dict(allocation_pct=80.,opening_inventory_kunits=5.,
    holding_cost_per_unit=.6,country_priority=['泰国','印尼'])
request['assumptions'] += '；连接件固定80%自由生产、期初库存5千单位；持有费按期末数量计为情景假设。'
registry = nd.read(old/'models.json')
prediction = model.predict_joint(request,registry)
c = prediction['allocation']['products']['连接件']
assert c['production_kunits']==64.
assert abs(c['closing_inventory_kunits']-(5+64-sum(c['sales_kunits'].values())))<1e-8
assert c['closing_inventory_kunits']>0
assert prediction['allocation']['total_workers']<=100+1e-8
checks = model.self_check()
p = dict(request['production']['连接件'], demand={'泰国':10.,'印尼':5.})
next_plan = dict(request['connector_plan'], allocation_pct=0.,**c['next_state'])
next_prediction = project(p,next_plan,30.,[1.,1.65,2.56])
assert next_prediction['production_kunits']==0
assert abs(next_prediction['closing_inventory_kunits']-(c['closing_inventory_kunits']-15))<1e-8
out = ROOT/'output/connector_free_production'/datetime.now(nd.TZ).strftime('%Y%m%dT%H%M%S%f%z')
out.mkdir(parents=True,exist_ok=False)
nd.save(out/'request.json',request)
nd.save(out/'prediction.json',dict(category='SYNTHETIC_FIXED_PLAN_NOT_CURRENT_RECOMMENDATION',**prediction))
nd.save(out/'next_round_inventory_demo.json',dict(category='SYNTHETIC_QUANTITY_CARRYOVER_NOT_FORMAL4_DEMAND_PREDICTION',
    product=p,plan=next_plan,prediction=next_prediction))
nd.save(out/'checks.json',dict(self_check=checks,old_t3v1_outputs_unchanged=True,
    fixed_production_not_demand_capped=True,inventory_conservation=True,
    shared_workers=True,next_round_quantity_carryover=True,demand_retrained=False))
snapshot = out/'code_snapshot'
snapshot.mkdir()
for name in ('t3v1.py','joint_allocation.py','connector_free_production.py'):
    (snapshot/name).write_bytes((ROOT/'code/model_v2'/name).read_bytes())
report = f'''# 连接件独立自由生产路径验收

复用t3v1需求参数，未重训。演示是假设输入，不是当前本人推荐。

连接件产能80千单位，计划80%，产量固定64千单位；期初库存5千单位，交付{sum(c['sales_kunits'].values()):.6f}千单位，期末库存{c['closing_inventory_kunits']:.6f}千单位。需求只限制交付，未截断生产。

下期数量演示：零生产、需求15千单位，期初使用上述期末库存，结余{next_prediction['closing_inventory_kunits']:.6f}千单位。这仅验证状态结转，不是正式4需求预测。

自检覆盖超产库存、两期结转、生产计材料/工资、国别优先级、零产能、无效输入、固定计划占用共享用工及用工不足拒绝。

原t3v1产物哈希不变。库存计价、期初库存成本转出、大客户订单、税/利息/现金及跨期最优尚未接入；不把当期资源差额当净利润。
'''
(out/'report.md').write_text(report,encoding='utf-8')
inputs = {str(old/name):nd.sha(old/name) for name in ('manifest.json','models.json','example_request.json')}
nd.save(out/'manifest.json',dict(path_version='CONNECTOR_FREE_PRODUCTION_V1',demand_version='t3v1',
    input_hashes=inputs,output_hashes={p.relative_to(out).as_posix():nd.sha(p) for p in out.rglob('*') if p.is_file()}))
saved = nd.read(out/'manifest.json')
assert all(nd.sha(out/p)==h for p,h in saved['output_hashes'].items())
assert all(nd.sha(Path(p))==h for p,h in saved['input_hashes'].items())
print('PASS',out)
