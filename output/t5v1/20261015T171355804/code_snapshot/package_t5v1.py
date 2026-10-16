"""Freeze t5v1 as an independent runtime and report while checking t5v0b remains intact."""
import ast
import copy
import csv
import json
import os
import re
import shutil
import sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work'),str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'code')]
import numpy as np
import solve_marketing_formal4_to5 as update

OUT=ROOT/(ROOT/'work/t5v1_active_run.txt').read_text(encoding='utf-8-sig').strip()
SOURCE=update.OUT
read=update.read;sha=update.base.sha


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def encode(v):
    if isinstance(v,np.ndarray):return {'__ndarray__':v.tolist()}
    if isinstance(v,dict):return {k:encode(x) for k,x in v.items()}
    if isinstance(v,list):return [encode(x) for x in v]
    if isinstance(v,np.generic):return v.item()
    return v


def runtime_source():
    base_tree=ast.parse((ROOT/'work/solve_formal5_full.py').read_text(encoding='utf-8'))
    base_class=next(n for n in base_tree.body if isinstance(n,ast.ClassDef) and n.name=='ScenarioModel')
    application=ast.parse((ROOT/'work/solve_marketing_formal4_to5.py').read_text(encoding='utf-8'))
    application_class=next(n for n in application.body if isinstance(n,ast.ClassDef) and n.name=='MarketingModel')
    raw=ast.ClassDef(name='_BaseScenario',bases=[],keywords=[],decorator_list=[],
        body=[copy.deepcopy(n) for n in base_class.body if isinstance(n,ast.FunctionDef) and n.name in ['demand','evaluate']])
    adapted=ast.ClassDef(name='ApplicationModel',bases=[ast.Name(id='_BaseScenario',ctx=ast.Load())],keywords=[],decorator_list=[],
        body=[copy.deepcopy(n) for n in application_class.body if isinstance(n,ast.FunctionDef) and n.name=='demand'])
    tree=ast.fix_missing_locations(ast.Module(body=[raw,adapted],type_ignores=[]))
    header='''"""t5v1 frozen inference: formal4 marketing training with formal5 importance; no training or platform writes."""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'work/python_packages'))
import numpy as np

def curve(x,item):
    p=item['parameters']
    return p[0]+p[1]*(x+p[2])**p[3] if item['form']=='power' else p[0]+p[1]*x/(p[2]+x)

'''
    footer='''

def decode(value):
    if isinstance(value,dict):
        if set(value)=={'__ndarray__'}:return np.array(value['__ndarray__'],float)
        return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list):return [decode(v) for v in value]
    return value


def apply_request(registry,request):
    if (registry.get('version'),registry.get('base_version'),registry.get('application_round'))!=('t5v1','t5v0b',5):
        raise ValueError('需要t5v1注册表，基线t5v0b，应用正式5')
    if (request.get('version'),request.get('market_id'),request.get('phase'),request.get('round'))!=('t5v1',5,'formal',5):
        raise ValueError('需要t5v1／市场5／formal／正式5请求')
    if set(request)-{'version','market_id','phase','round','plan','scenario','decision_vector'}:
        raise ValueError('未知请求字段')
    scenario_name=request.get('scenario','中性SHARE')
    scenarios=[s for s in registry['scenario_configs'] if s['name']==scenario_name]
    if len(scenarios)!=1:raise ValueError('未知情景')
    if 'decision_vector' in request:values=request['decision_vector']
    else:
        plans=[p for p in registry['saved_plans'] if p['name']==request.get('plan','稳健利润候选')]
        if len(plans)!=1:raise ValueError('未知方案')
        values=plans[0]['x']
    if not isinstance(values,list) or len(values)!=20 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
        raise ValueError('decision_vector须为20个有限数；机器连接件为20千单位档，贷款为100千美元档')
    bounds=registry['application_state']['bounds']
    if any(not lo<=v<=hi for v,(lo,hi) in zip(values,bounds)) or any(v<=0 for v in values[:4]):
        raise ValueError('决策超出保存的分析范围')
    if any(values[i]!=round(values[i]) for i in [15,16,19]) or sum(values[4:8])>2700+1e-8 or sum(values[8:12])>3840+1e-8:
        raise ValueError('投资/融资档位或营销预算范围不合法')
    model=ApplicationModel()
    model.__dict__.update(decode(registry['application_state']))
    model.r={'risk':registry['risk']}
    model.current={int(k):v for k,v in model.current.items()}
    result=model.evaluate(np.array(values,float),scenarios[0],details=True)
    result.update(version='t5v1',base_version='t5v0b',marketing_training_round=4,importance_round=5,
        inference_training_performed=False,country_product_marketing_allocation_identified=False,
        independent_forward_validation=False,full_global_optimum=False,
        scope='正式5—6条件税后利润；营销合计费用代理；正式6同价同投入及同曲线为情景；非实际成绩或已核平台候选预算')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--request',type=Path)
    args=parser.parse_args()
    registry=json.loads((args.bundle/'models_full.json').read_text(encoding='utf-8'))
    request=json.loads((args.request or args.bundle/'example_request.json').read_text(encoding='utf-8'))
    print(json.dumps(apply_request(registry,request),ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
'''
    return header+ast.unparse(tree)+'\n'+footer


def main():
    assert not (OUT/'models_full.json').exists()
    audit=read(SOURCE/'t5v0b_preservation_audit.json');assert audit['all_match']
    for path in SOURCE.iterdir():
        if path.is_file():shutil.copy2(path,OUT/path.name)
    for name in ['latest','code_before']:
        shutil.copytree(SOURCE/name,OUT/name)
    # Preserve the original task log independently; the t5v1 log records version creation below.
    shutil.copy2(SOURCE/'work_log.md',OUT/'training_work_log.md')
    m=update.MarketingModel();result=read(SOURCE/'full_result.json')
    prior=read(update.base.BUNDLE/'models_full.json');registry=copy.deepcopy(prior)
    registry.update(version='t5v1',base_version='t5v0b',application_round=5,training_performed=True,
        status='FORMAL4_MARKETING_PROXY_TRAINING_FORMAL5_IMPORTANCE_APPLICATION',
        training_scope=dict(marketing_round=4,known_price_rd_response_round=3,other_trained_parameters='inherited t5v0b',importance_round=5),
        marketing_models=read(SOURCE/'marketing_models_formal4.json'),sales_importance=read(SOURCE/'sales_importance_4_5.json'),
        applied_marketing_coefficients=read(SOURCE/'applied_marketing_coefficients.json'),
        country_product_marketing_allocation_identified=False,
        scenario_configs=result['configs'],saved_plans=[dict(name=p['name'],x=p['x']) for p in result['comparisons']],
        application_source_directory=str(SOURCE.relative_to(ROOT)),
        demand=dict(status='FORMAL4_COMPANY_MARKETING_EXPENSE_PROXY_FIT_WITH_KNOWN_PRICE_RD_OFFSETS',
            training_rows=264,eligible_beam=144,eligible_connector=120,
            mapping='beta5=beta4/importance4*importance5; relative-position y is not a multiplicative demand factor',
            full_competitor_allocations_available=False))
    attrs=['beta','tail','baseprices','gb','db','effbase','share','totals','capbase','invbase','invbook','freight','rdbase',
        'local_general','local_designer','costs','state','prevworkers','opcurve','rdcurves','opsbase','other_assets',
        'general_total','designer_total','bounds','current','baseline']
    registry['application_state']=encode({k:getattr(m,k) for k in attrs})
    for name,item in registry['model_inventory'].items():
        original=(update.base.BUNDLE/item['artifact']).resolve()
        assert original.exists()
        item['artifact']=Path(os.path.relpath(original,OUT)).as_posix()
        registry['application_actions'][name]['t5v1_impact']='沿用原版；营销及完整条件链的新增假设见t5v1独立应用记录'
    for name in ['SHARE','COUNTRY','ABS']:
        if name in registry['application_actions']:
            registry['application_actions'][name]['t5v1_impact']='营销初终值重估与正式5重要性接入；完整国别真实分配仍未识别，ABS不伪造新拟合'
    for key in ['curves','application_curves','risk','materials','labor','efficiency','interest','application_parameters']:
        assert registry[key]==prior[key],key
    save(OUT/'models_full.json',registry)
    codepath=ROOT/'code/model_v2/t5v1.py';assert not codepath.exists()
    codepath.write_text(runtime_source(),encoding='utf-8')
    (OUT/'code_snapshot').mkdir()
    shutil.copy2(codepath,OUT/'code_snapshot/t5v1.py')
    for source in [Path(__file__),ROOT/'work/solve_formal5_full.py',ROOT/'work/train_formal4_marketing.py',ROOT/'work/solve_marketing_formal4_to5.py']:
        shutil.copy2(source,OUT/'code_snapshot'/source.name)
    request=dict(version='t5v1',market_id=5,phase='formal',round=5,plan='稳健利润候选',scenario='中性SHARE')
    save(OUT/'example_request.json',request)
    sys.path.insert(0,str(ROOT/'code/model_v2'));import t5v1
    rejected=0
    for plan in result['comparisons']:
        for cfg,expected in zip(result['configs'],plan['evaluations']):
            actual=t5v1.apply_request(registry,dict(request,plan=plan['name'],scenario=cfg['name']))
            assert abs(actual['profit_5_to_6']-expected['profit_5_to_6'])<1e-8
            assert actual['balance_error_max']<1e-7 and actual['quantity_error_max']<1e-8
    for mode in ['SHARE','COUNTRY']:
        cfg=dict(result['configs'][0],response=mode)
        base=m.demand(m.baseline[:,None],cfg,0)
        for j in range(2):
            for k in range(2):
                changed=m.baseline.copy();changed[2*j+k]*=1.05
                assert m.demand(changed[:,None],cfg,0)[j,k,0]<base[j,k,0],(mode,j,k)
    for bad in [dict(request,version='t5v0b'),dict(request,round=4),dict(request,scenario='UNKNOWN'),
        dict(request,decision_vector=[True]*20),dict(request,decision_vector=[float('nan')]*20),dict(request,extra=1)]:
        try:t5v1.apply_request(registry,bad)
        except ValueError:rejected+=1
        else:raise AssertionError('Invalid request accepted')
    example=t5v1.apply_request(registry,request);save(OUT/'example_result.json',example)
    # Repeat the full original-version manifest check after freezing the new runtime.
    original=read(update.base.BUNDLE/'version_manifest.json');preserved=[]
    for category,root in [('source_code',ROOT),('outputs',update.base.BUNDLE)]:
        for relative,digest in original[category].items():
            actual=sha(root/relative);assert actual==digest,(category,relative)
            preserved.append(dict(category=category,path=str((root/relative).relative_to(ROOT)),sha256=actual))
    dedicated='code/model_v2/t5v0b_README.md'
    assert sha(ROOT/dedicated)==original['documents'][dedicated]
    preserved.append(dict(category='version_document',path=dedicated,sha256=sha(ROOT/dedicated)))
    save(OUT/'t5v0b_preservation_audit.json',dict(version='t5v0b',scope='entire conversation baseline versus original manifest',
        checked=len(preserved),all_match=True,restored_files=[],original_version_modified=False,checks=preserved))
    validation=read(SOURCE/'validation.json');validation.update(version='t5v1',frozen_runtime_all_scenarios_replay=True,
        country_price_columns_checked=8,invalid_requests_rejected=rejected,t5v0b_preserved=True)
    save(OUT/'validation.json',validation)
    print('T5V1_BUNDLE',OUT)
    print(json.dumps(validation,ensure_ascii=False))


if __name__=='__main__':main()
