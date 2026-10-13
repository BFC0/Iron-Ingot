"""python code/model_v2/run.py --stage all (all output is append-only)."""
import argparse
import csv
import shutil
import subprocess
import traceback
from datetime import datetime, timezone, timedelta
from core import *
from audit import audit, budget


def protected(snapshot):
    hashes=read(snapshot)
    changed=[s for s,h in hashes.items() if not (ROOT/s).is_file() or digest(ROOT/s)!=h]
    if changed: raise RuntimeError(f'Protected files changed: {changed}')
    return dict(count=len(hashes),changed=changed)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['all','audit','fit','budget','stress','search','report'],default='all')
    args=parser.parse_args()
    snapshot='output/model_v2/20261011T193318735151+0800/snapshot/protected_hashes.json'
    before=protected(snapshot)
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
    out=ROOT/'output/model_v2'/stamp
    out.mkdir(parents=True,exist_ok=False)
    code=out/'code_snapshot';code.mkdir()
    for p in Path(__file__).parent.iterdir():
        if p.is_file(): shutil.copy2(p,code/p.name)
    manifest=dict(run_id=stamp,stage=args.stage,git_branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_status=subprocess.check_output(['git','status','--porcelain=v1','-uall'],text=True),
        code_hashes={p.name:digest(p) for p in code.iterdir()},protected_before=before,
        input_hashes=read(snapshot),data_cutoff='练习2历史实际；正式结果未取得',units=UNITS,
        status='RUNNING',live_access='主页已打开但两次AX读取超时；身份/回合/个人与小组状态尚未确认',
        mutations=0,old_latest_updated=False)
    write(out/'manifest.json',manifest)
    print('OUTPUT',out,flush=True)
    results={}
    try:
        rows,cells,sources=old.load_dataset()
        results['audit']=audit(rows,cells,sources);write(out/'audit.json',results['audit'])
        results['budget']=budget();write(out/'budget.json',results['budget'])
        print('STAGE1 PASS: frozen/normalization/archive replay',flush=True)
        if args.stage in ['all','fit']:
            from demand import run
            results['demand']=run(rows,out);write(out/'demand.json',results['demand'])
        if args.stage in ['all','fit','budget','stress']:
            from finance import efficiency_and_risk
            results['mechanisms']=efficiency_and_risk();write(out/'mechanisms.json',results['mechanisms'])
        if args.stage in ['all','stress']:
            from finance import stress
            results['stress']=stress();write(out/'stress.json',results['stress'])
        if args.stage in ['all','search']:
            results['search']=dict(status='GATED_NOT_RUN',stage2_passed=False,stage3_passed=False,candidates=[],
                reason='独立需求/效率支持与预算机制门槛未通过；继续离线诊断，不输出完整利润或累计收益排名',
                required_evidence=['当前身份/回合/基准','成功保存且恢复的单变量预算及独立验证点','合法决策范围',
                                   '低运营投入效率','跨回合状态及未来前景'],
                future_rounds=[dict(round=i,status='MISSING_CURRENT_OUTLOOK_AND_VALIDATED_STATE_CHAIN',profit=None) for i in range(2,7)])
            write(out/'search.json',results['search'])
        from report import build
        build(out,results)
        manifest['status']='COMPLETE_OFFLINE_AUDIT_WITH_EXPLICIT_GAPS'
    except Exception as exc:
        manifest['status']='FAILED';manifest['error']=str(exc)
        (out/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
    finally:
        manifest['protected_after']=protected(snapshot)
        manifest['result_hashes']={p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}
        write(out/'manifest.json',manifest)
    print('DONE',out,flush=True)


if __name__=='__main__':
    main()
