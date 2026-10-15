"""Publish supplementary results and comparisons without replacing training artifacts."""
import copy
import html
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'code')]
sys.dont_write_bytecode=True
import numpy as np
import t4v0 as t


def main(out):
    nd=t.nd;model=nd.read(out/'models.json');data=nd.read(out/'dataset.json')
    supplementary=nd.read(out/'supplementary_verification.json')
    inventory=nd.read(out/'model_inventory.json')
    items=inventory['models']
    items['A']=dict(status='EVALUATED_NO_INCREMENT_GATE_PASS_NO_REFIT',artifact='supplementary_A.json')
    items['B']=dict(status='PUBLISHED_SEVERANCE_RULE_60_CHECKS_PASS',artifact='severance_checks.csv')
    items['C']=dict(status='RETRAINED_SEPARATE_PRODUCT_CONDITIONAL_WAGE',artifact='supplementary_verification.json')
    items['D']=dict(status='RETRAINED_FORMAL2_TO_FORMAL3_RESEARCH_NOT_DEPLOYED',artifact='lagged_efficiency.json')
    for name in ('E','F'):
        items[name]=dict(status='KNOWN_INTENSITY_FORMULAS_ALL_CHECKS_PASS',artifact='physics_checks.csv')
    for name in ('RISK_POWER','RISK_EXP','INTEREST'):
        items[name]=dict(status='RETRAINED_STABILITY_GATE_FAILED_EXTREME_HELD_MARKET',artifact='models_full.json',
                         reason='近零权益队产生极端杠杆；外层留出显著外推，不能作确定推荐')
    for name in ('UNIFIED','T2V0'):
        items[name]=dict(status='COMPOSITION_MAPPED_TO_T4V0_SEPARATE_PRODUCT_REGISTRY',artifact='models_full.json',
                         reason='组合入口，无额外独立参数；旧版本不覆盖')
    for name in ('CONNECTOR','CONNECTOR_V2','JOINT_ALLOCATION'):
        items[name]=dict(status='EXISTING_RULE_SELF_CHECK_PASS_ACTUAL_TRAINING_SCOPE_LIMITED',artifact='connector_checks.json',
                         reason='连接件需求/效率/材料/工资已有真实训练；库存/订单跨期仅现有规则自检，完整利润未验证')
    model['labor']=supplementary['wages']
    model['supplementary_A']=supplementary['A']
    model['lagged_efficiency']=supplementary['D']
    model['connector_rule_checks']=supplementary['connector']
    model['joint_allocation_rule_checks']=supplementary['joint_allocation']
    model['model_inventory']=items
    model['stability_gate']=dict(risk=False,interest=False,automatic_deployment=False)
    for r in model['risk'].values():
        r['deployment']=False;r['stability_status']='FAILED_EXTREME_MARKET_HOLDOUT'
        r['ranges']={k:[min(x[k] for x in data['risk']),max(x[k] for x in data['risk'])] for k in ('equity_ratio','leverage')}
    nd.save(out/'models_full.json',model)
    nd.save(out/'model_inventory_final.json',inventory)
    nd.csv_write(out/'model_inventory_final.csv',[dict(model=k,**v) for k,v in items.items()])
    old_dir=ROOT/'output/t3v0/20261013T182432038858+0800'
    old=nd.read(old_dir/'models.json');old_curve=nd.read(old_dir/'formal2_curves.json')
    comparisons=[]
    for product,rows in data['competitive_rows_by_product'].items():
        for name,m in model['demand'][product].items():
            if name=='ABS':continue
            pool=[r for r in rows if name=='SHARE' or r['country']==name.split('/')[1]]
            baseline=old['demand'][name]
            # Missing initial connector prices prohibit use of the old piecewise branch.
            if product=='连接件' and baseline['piecewise']:
                comparisons.append(dict(product=product,model=name,status='OLD_PIECEWISE_CONNECTOR_REFERENCE_UNAVAILABLE'));continue
            p=t.base.core.predict(pool,t.base.core.features(pool,old_curve['curves']['rd']['parameters'],baseline['rho'],baseline['piecewise']),baseline['beta'])
            comparisons.append(dict(product=product,model=name,n=len(pool),old_fixed_parameter_mae_pp=100*t.base.core.score(pool,p),
                new_full_training_mae_pp=m['training_mae_pp'],new_nested_market_holdout_mae_pp=m['nested_validation']['mae_pp'],
                scope='旧参数与新参数对同一实际输入的条件回放；新全样本误差乐观；外层误差独立列出，非事前成绩',
                connector_old_scope='原正式2复合梁参数假设迁移' if product=='连接件' else None))
    nd.save(out/'old_new_comparison.json',comparisons)
    nd.csv_write(out/'old_new_comparison.csv',comparisons)
    validation=nd.read(out/'demand_validation.json')
    predictions=[dict(model=r['model'],product=r['product'],market=r['key'][0],team_id=r['key'][3],country=r['key'][4],round=3,
                      actual_share_pp=r['actual_share']*100,predicted_share_pp=r['predicted_share']*100,
                      residual_pp=(r['predicted_share']-r['actual_share'])*100) for r in validation]
    nd.save(out/'report_data.json',predictions)
    nd.csv_write(out/'report_predictions.csv',predictions)
    counts={p:len(rows) for p,rows in data['competitive_rows_by_product'].items()}
    limits=['实际归档6市场、60队、90/150页；市场3/6/7/8尚未纳入。',
        '复合梁120条、连接件110条需求训练记录；10条零售价且零实际需求/销量记录保留为范围外，不加伪小数。',
        '营销与研发是公司合计代理，未拆成国别/产品因果投入；本组最终决策4条产品国别配对和7项交叉核验通过。',
        '风险/利率已拟合56个正权益有效状态；其余4项保留范围外。极端杠杆导致留出严重外推，稳定性门槛未通过。',
        '基准利率叙述5%与参数表4%冲突仍待补证；本次使用参数表4%。',
        'A类校准已完整比较，但未过增量门槛，没有保存新自由参数；D类正式2→3残差已拟合60条，仍为条件研究。',
        '期初/期末未知税亏、完整研发/运营存量、订单与跨期财务不补零。正式4曲线没有进入训练。',
        '冻结果与实际小组方案不匹配，事前评分0项；新误差不冒充事前成绩。']
    lines=['# t4v0 正式3全部模型更新验收','',f'北京时间运行：{out.name}。',
        '已执行用户追加授权“先全部以实际值训练”。全部31类逐项交付：可估计项训练；确定规则核验；未识别或未过门槛项明确保留状态。',
        '本组决策来自已采集的正式3小组最终决策，其他队使用正式3实际结果。正式2期末配正式3期初，真实正式3终值作为标签。',
        '权威参数注册表为 models_full.json；原训练阶段 models.json 和 manifest.json 保留。',
        '', '## 验收结果','',
        '双产品需求保存参数复算、整市场训练/测试隔离、份额守恒通过；三条曲线600点的JSON/SVG与交错留点验收通过。',
        '300项财务等式、600项生产环境/物流公式、60项解聘费核验通过。分产品工资重训：复合梁60样本、连接件54样本。',
        'A类环境校准与D类跨期残差均已执行；连接件固定生产、库存/订单情景及联合分配自检通过。完整六回合利润和订单状态不在通过结论内。',
        '', '| 产品 | SHARE嵌套MAE pp | 泰国独立MAE pp | 印尼独立MAE pp |','|---|---:|---:|---:|']
    for product,models in model['demand'].items():
        values=[models[k]['nested_validation']['mae_pp'] for k in ('SHARE','COUNTRY/泰国','COUNTRY/印尼')]
        lines.append(f'| {product} | '+ ' | '.join(f'{v:.6f}' for v in values)+' |')
    lines+=['','上述为同期已实现竞争输入和行业总量的条件验证；投入合计代理不可用来声称国别/产品投入优化。',
        '', '## 全部模型状态','', '| 模型 | 状态 |','|---|---|']
    lines += [f"| {name} | {item['status']} |" for name,item in items.items()]
    lines += ['', '## 当前全部问题与不足',''] + ['- '+s for s in limits]
    lines += ['', '## 因缺乏数据而无法验证的问题','',
        '- 未归档四市场正式3全部实际、其他队分产品/国别最终营销研发、连接件初始价格与早期技术状态。',
        '- 完整税亏、累计投入、确认订单及预收、未来回合前景与完整状态结转。',
        '', '新旧条件比较见 old_new_comparison.json/CSV。缺失项、范围外行、舍入与来源详见 dataset.json。',
        '原件、旧模型和冻结结果保留；未填写决策、未提交平台、未部署。']
    report='\n'.join(lines)+'\n';(out/'report_final.md').write_text(report,encoding='utf-8')
    header='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>t4v0 正式3模型验收</title><style>body{font:16px/1.6 system-ui;margin:32px;max-width:1500px;color:#20313b}h1{font-size:28px}label,button{margin-right:18px}select,button{font:inherit;padding:5px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;text-align:right;padding:5px}td:first-child,th:first-child{text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}svg{max-width:100%;height:auto}details{margin:15px 0}@media print{button,select{display:none}body{margin:10px}}</style>'
    content='<h1>t4v0 正式3模型验收</h1><p>6市场 · 60队 · 230条有效需求 · 31类模型。同期条件研究，未部署。</p><p><strong>风险/利率稳定性未通过；公司合计投入代理不能解释为分产品因果作用。</strong></p>'
    content+='<label>产品<select id="product"></select></label><label>模型<select id="model"></select></label><label>市场<select id="market"><option value="">全部</option></select></label><label>国家<select id="country"><option value="">全部</option><option>泰国</option><option>印尼</option></select></label><button id="export">导出筛选CSV</button><button onclick="print()">打印</button><p id="summary"></p><svg id="plot" viewBox="0 0 900 350" role="img" aria-label="实际与预测需求份额"></svg><details><summary>筛选后的逐队数据</summary><table><thead><tr><th>团队编号</th><th>市场</th><th>国家</th><th>实际份额pp</th><th>预测份额pp</th><th>残差pp</th></tr></thead><tbody id="records"></tbody></table></details><h2>验收与限制</h2><pre>'+html.escape(report)+'</pre>'
    script=r'''const data=PAYLOAD;const byId=id=>document.getElementById(id);let selected=[];
for(const k of ['product','model'])[...new Set(data.map(r=>r[k]))].forEach(v=>byId(k).add(new Option(v,v)));
[...new Set(data.map(r=>r.market))].sort((a,b)=>a-b).forEach(v=>byId('market').add(new Option(v,v)));
function render(){selected=data.filter(r=>r.product===byId('product').value&&r.model===byId('model').value&&(!byId('market').value||r.market===Number(byId('market').value))&&(!byId('country').value||r.country===byId('country').value));
const mae=selected.reduce((s,r)=>s+Math.abs(r.residual_pp),0)/Math.max(1,selected.length);byId('summary').textContent=`正式3；${selected.length}条；当前筛选逐行MAE ${mae.toFixed(6)}个百分点。市场/国家等权主指标见验收表；蓝点为实际与预测需求份额。`;
byId('records').replaceChildren(...selected.map(r=>{const tr=document.createElement('tr');[r.team_id,r.market,r.country,r.actual_share_pp.toFixed(6),r.predicted_share_pp.toFixed(6),r.residual_pp.toFixed(6)].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td)});return tr}));
const max=Math.max(1,...selected.flatMap(r=>[r.actual_share_pp,r.predicted_share_pp]));byId('plot').innerHTML='<path d="M60 20V310H860 M60 310L860 20" stroke="#bcc" fill="none"/><text x="300" y="345">实际需求份额（百分点）</text><text x="8" y="18">预测需求份额</text>'+selected.map(r=>`<circle cx="${60+r.actual_share_pp/max*800}" cy="${310-r.predicted_share_pp/max*290}" r="3" fill="#21618c"><title>${r.team_id} ${r.residual_pp.toFixed(6)}pp</title></circle>`).join('');}
['product','model','market','country'].forEach(k=>byId(k).addEventListener('change',render));
byId('export').onclick=()=>{const keys=['model','product','market','team_id','country','round','actual_share_pp','predicted_share_pp','residual_pp'];const csv='\ufeff'+[keys.join(','),...selected.map(r=>keys.map(k=>JSON.stringify(String(r[k]))).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='t4v0_filtered.csv';a.click();URL.revokeObjectURL(url)};render();'''
    script=script.replace('PAYLOAD',json.dumps(predictions,ensure_ascii=False).replace('</','<\\/'))
    (out/'report_final.html').write_text(header+content+'<script>'+script+'</script></html>',encoding='utf-8')
    (out/'report_final_script.js').write_text(script,encoding='utf-8')
    for name in ['verify_t4v0.py','finalize_t4v0.py']:
        shutil.copy2(ROOT/'work'/name,out/'code_snapshot'/name)
    print(json.dumps(dict(out=str(out),models=len(items),demand_counts=counts,report_rows=len(predictions)),ensure_ascii=False))


if __name__=='__main__':main(Path(sys.argv[1]))
