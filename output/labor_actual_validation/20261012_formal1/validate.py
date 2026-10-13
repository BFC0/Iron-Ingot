"""Frozen budget-derived labor parameters against 100 formal-1 actual accounts."""
import hashlib
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from itertools import product
from pathlib import Path
from statistics import mean

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT/'code'))
from archive_and_report import table_rows, number
from formal_update_state import parse_state
from build_model_inputs import production_and_delivery

MODEL_PATH = ROOT/'output/labor_budget/20261012_web_trials/validation.json'
model = json.loads(MODEL_PATH.read_text(encoding='utf-8'))
assert model['all_checks_passed'] and model['restoration_checked']
frozen = model['fitted']
published = model['published']
hashes = {}

def read(path):
    hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    doc = json.loads(path.read_text(encoding='utf-8'))
    return doc, table_rows(doc['snapshot'])

def headers(rows):
    return next(r['cells'] for r in rows if len(r['cells'])==10)

def field(rows, label, column, path):
    found = [r for r in rows if len(r['cells'])==11 and r['cells'][0]==label]
    assert len(found)==1, (path, label)
    return dict(value=number(found[0]['cells'][column]), file=str(path.relative_to(ROOT)),
                line=found[0]['line'], column=column, label=label)

def calculate(cap, q, n, prev, pars):
    assert q>0 and n>0 and cap>0 and q<=cap+1e-9
    return production_and_delivery(cap, q/cap*100, q/n, [q,0], [0,1],
        pars['wage'], pars['second_shift'], pars['third_shift'], prev,
        pars['attrition'], pars['severance'])

# Small self-checks for one-shift wages and the zero-firing floor.
check = calculate(30, 3, 20, 10, published)
assert abs(check['payroll']-560)<1e-9 and check['firing']==0
records = []
for market in range(1,11):
    actual_path = ROOT/f'output/formal_update/20261011T223000+0800_sources/market_{market}_formal1.json'
    verified = parse_state(actual_path)  # validates actual identity, selected round and team order
    actual_doc, actual_rows = read(actual_path)
    read(ROOT/actual_doc['selection_file'])
    initial_path = ROOT/('raw/initial0_printable.json' if market==5 else
                        f'raw/cross_market/market_{market:02d}_initial_0.json')
    initial_doc, initial_rows = read(initial_path)
    if market!=5:
        assert initial_doc['market_id']==market and initial_doc['phase']=='initial'
        assert initial_doc['round']==0 and initial_doc['kind']=='actual_result'
        assert initial_doc['selection_verified'] and initial_doc['selected_round']=='初始回合0'
    initial_teams = headers(initial_rows)
    assert len(set(initial_teams))==10
    for team in verified:
        col = team['team_column']
        assert team['team'] in initial_teams
        prev_col = initial_teams.index(team['team'])+1
        refs = {key:field(actual_rows,label,col,actual_path) for key,label in [
            ('capacity','生产能力, 千单位'),('q','生产规模, 千单位'),('n','生产线人工数量'),
            ('printed_eta','生产效率, 千单位/人'),('payroll','生产人员成本'),('firing','解雇成本')]}
        refs['prev_n'] = field(initial_rows,'生产线人工数量',prev_col,initial_path)
        v = {key:r['value'] for key,r in refs.items()}
        assert all(math.isfinite(x) for x in v.values())
        row = dict(market=market,team_id=f'M{market}:T{col}',phase='formal',round=1,
                   actual=v, sources=refs, evaluation='conditional_actual_reconstruction')
        for name,pars in [('frozen_budget_fit',frozen),('published_rules',published)]:
            p = calculate(v['capacity'],v['q'],v['n'],v['prev_n'],pars)
            results = {}
            for metric in ['payroll','firing']:
                if metric=='payroll':
                    corners = []
                    for dc,dq,dn in product([-.005,.005],repeat=3):
                        c,q,n=v['capacity']+dc,v['q']+dq,v['n']+dn
                        q=min(q,c)
                        corners.append(calculate(c,q,n,v['prev_n'],pars)[metric])
                else:
                    corners = [max(prev*(1-pars['attrition'])-n,0)*pars['wage']*pars['severance']
                        for prev,n in product([v['prev_n']-.005,v['prev_n']+.005],
                                              [v['n']-.005,v['n']+.005])]
                lo,hi=min(corners),max(corners)
                error = p[metric]-v[metric]
                results[metric] = dict(predicted=p[metric],observed=v[metric],error=error,
                    relative_error_percent=100*error/v[metric] if v[metric]>0 else None,
                    input_rounding_interval=[lo,hi],
                    display_compatible=lo<=v[metric]+.5+1e-9 and hi>=max(v[metric]-.5,0)-1e-9)
            row[name] = results
        # Diagnostic only: cost calculated using the two-decimal printed efficiency.
        if v['printed_eta']>0:
            row['printed_efficiency_payroll'] = production_and_delivery(v['capacity'],v['q']/v['capacity']*100,
                v['printed_eta'],[v['q'],0],[0,1],published['wage'],published['second_shift'],
                published['third_shift'],v['prev_n'],published['attrition'],published['severance'])['payroll']
        records.append(row)
assert len(records)==100 and len({r['team_id'] for r in records})==100

def metrics(rows, version, metric):
    items = [r[version][metric] for r in rows]
    errors = [r['error'] for r in items]
    positive = [r for r in items if r['observed']>0]
    return dict(n=len(rows),mae_kusd=mean(abs(e) for e in errors),
        rmse_kusd=math.sqrt(mean(e*e for e in errors)),bias_kusd=mean(errors),
        max_abs_error_kusd=max(abs(e) for e in errors),
        wape_percent=100*sum(abs(e) for e in errors)/sum(r['observed'] for r in items),
        mape_positive_percent=mean(abs(r['relative_error_percent']) for r in positive) if positive else None,
        positive_actual_n=len(positive),display_compatible_n=sum(r['display_compatible'] for r in items),
        worst_team=rows[max(range(len(rows)),key=lambda i:abs(errors[i]))]['team_id'])

summary = {version:{metric:metrics(records,version,metric) for metric in ['payroll','firing']}
           for version in ['frozen_budget_fit','published_rules']}
positive_firing = [r for r in records if r['actual']['firing']>0]
summary['positive_firing'] = {version:metrics(positive_firing,version,'firing') for version in summary.copy()}
summary['printed_efficiency_payroll_mae_kusd'] = mean(abs(r['printed_efficiency_payroll']-r['actual']['payroll']) for r in records)
own = next(r for r in records if r['team_id']=='M5:T6')
result = dict(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
    model_source=str(MODEL_PATH.relative_to(ROOT)),model_sha256=hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
    no_actual_data_retraining=True,frozen_parameters=frozen,published_parameters=published,
    implementation_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        ['code/build_model_inputs.py','code/archive_and_report.py','code/formal_update_state.py']},
    summary=summary,own_team=own,records=records,source_sha256=hashes,
    limits=['Historical validation: formal-2 budget-fitted model applied retrospectively to formal-1 actuals.',
            'Actual q/N is used; this does not validate demand, production or efficiency forecasts.',
            'Same labor constants across markets assumed; scope checked by actual error rather than asserted.',
            'Input and output display rounding included; compatible does not prove unique hidden formula.'])
(OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
lines = ['# 人力成本模型：正式1实际结果偏差', '',
    '样本为正式1十市场100队真实报表，网页预算样本不参与评分。固定正式2网页训练参数，对较早的正式1实际回溯验证；没有用实际数据重新拟合。', '',
    '实际产量q、人数N和产能C代入工资；效率η=q/N，避免使用只有两位小数的显示效率。裁员费使用对应市场初始0人数，按队名匹配，不继承练习期状态。', '',
    '| 参数版本 | 项目 | 样本数 | MAE千美元 | RMSE千美元 | 平均有符号偏差千美元 | 最大绝对偏差千美元 | WAPE | 舍入兼容 |',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|']
for version in ['frozen_budget_fit','published_rules']:
    for metric in ['payroll','firing']:
        s=summary[version][metric]
        lines.append(f"| {version} | {metric} | {s['n']} | {s['mae_kusd']:.6f} | {s['rmse_kusd']:.6f} | {s['bias_kusd']:.6f} | {s['max_abs_error_kusd']:.6f} | {s['wape_percent']:.4f}% | {s['display_compatible_n']}/{s['n']} |")
lines += ['', 'MAE是平均绝对误差；有符号偏差=模型−实际，正值代表高估。WAPE=总绝对误差/实际总金额。裁员费包含零值，另列非零子样本，避免零值掩盖偏差：', '']
for version,s in summary['positive_firing'].items():
    lines.append(f"- {version}：非零裁员费{s['n']}队，MAE {s['mae_kusd']:.6f}千美元，MAPE {s['mape_positive_percent']:.4f}%，最大偏差{s['max_abs_error_kusd']:.6f}千美元。")
lines += ['', '市场5本队（M5:T6）：', '']
for metric in ['payroll','firing']:
    r=own['frozen_budget_fit'][metric]
    lines.append(f"- {metric}：实际{r['observed']:.0f}千美元，模型{r['predicted']:.6f}千美元，偏差{r['error']:+.6f}千美元。")
lines += ['', f"若直接使用两位小数的显示效率，工资MAE为{summary['printed_efficiency_payroll_mae_kusd']:.6f}千美元。这是输入精度诊断，不是模型参数误差。", '',
    '判断：工资结构在本批实际结果上表现稳定，100/100与显示舍入兼容。网页拟合裁员比例仅92/100兼容；公布10%离职率和35%补偿比例为100/100兼容，且MAE更低。三个整数预算样本不宜替代已公布的精确比例；建议继续使用公布比例，网页拟合作为机制核验证据。此处仅建议，未改正式模型。', '',
    '舍入兼容按产量/人数/产能显示±0.005及金额±0.5计算，不将误差强行归零。工资区间检查三个输入的端点；裁员费检查当期及期初人数端点。', '',
    '边界：只验证给定实际产量与人数后的成本公式；真实效率预测、完整利润/现金、多回合动态与正式2实际尚未在本报告验证。逐队偏差、原件定位、哈希和最大误差队伍见validation.json。']
(OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(summary=summary,own_team={k:own[k] for k in ['team_id','actual','frozen_budget_fit']}),ensure_ascii=False))
