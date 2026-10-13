"""Local, source-backed report; every view and CSV uses one filtered collection."""
import csv
import html
from core import *


ISSUES = [
    (1,'部分处理','尺度影响系数解释','需求留出路径及逐折尺度','比较原始/标准化惩罚；系数不是因果回报','独立正式需求与投入试验'),
    (2,'离线一致性通过','旧lambda不能直接混用','audit.json loss_equivalence','统一市场/国家等权；相应乘n的惩罚参数等价','无；新数据仍须复核训练口径'),
    (3,'已诊断，未唯一识别','极端价主导价格信息','demand.json 高价信息与删簇诊断','保留真实记录并比较固定1.5倍初始价分段','普通区间独立价格变化'),
    (4,'未识别','投入关联不能作因果回报','demand.json correlations','保留合计代理，披露共变和内生性','独立营销/研发变化与真实需求'),
    (5,'国别独立系数已纳入；国别支出仍缺','合计代理不能估计国别重分配','country_review.json；audit.json sources','并列四个国家/情境独立模型，不优化国别分配','各队国别营销原始记录及正式外部验证'),
    (6,'部分处理','对数排零与机制假设影响拟合','audit.json zero_demand；demand.json share候选','不加伪小数，另用保留零的份额损失','零值真实精度与舍入方式'),
    (7,'未识别','固定总量遗漏行业策略作用','预测行 oracle_total=true','仅给定行业总量评价份额，保留规模情景','行业总量与独立全行业策略变化'),
    (8,'已区分，外部验证缺失','回溯成绩不能当正式成绩','需求训练/测试键及原冻结1600条复现','练习1内选参，练习2仅回溯；正式先评分冻结','正式实际需求/对手决策'),
    (9,'已重拟合情景，存量未识别','延续系数与技术趋势混杂','需求rho网格；mechanisms.json效率rho','分别重拟合0/.25/.5/.75/1，不沿用系数','完整研发/运营投入历史'),
    (10,'缺独立曲线','同图留点仅证明近似','mechanisms.json curve_scope','图形误差与经营验证分开','其他编号市场可见曲线及独立结果'),
    (11,'已标记，外推未验证','研发曲线1200以外不受图形支持','预测 effective_rd 与 rd_curve_extrapolation','范围内外分组评价，不隐藏外推','高投入区间曲线和真实需求'),
    (12,'区间与重复策略诊断完成，低投入未验证','运营400超出600–1300训练范围','mechanisms.json efficiency','产量/人数舍入区间、按策略均衡尺度及五种延续','运营400成功保存恢复预算或实际效率'),
    (13,'两函数及删队诊断完成，外推未验证','风险系数来自十家实际期末状态','mechanisms.json risk','两函数保留，不据样本内好拟合确定还贷','大额还贷、计息时点及溢价试验'),
    (14,'部分关联来源，未来未验证','硬编码参数不适合跨回合照搬','budget.json parameters；stress.json parameters','当前源与经验项分开，未来值留空','各正式回合前景及精确参数'),
    (15,'单位更正通过；固定差额跨情境不兼容','单一加性差额在假定舍入下不能覆盖20条','materials_review.json 原单元格共同区间','保留900/1053当期来源、经验差额及舍入区间','高精度产量/材料、显示规则、无并发预算试验'),
    (16,'三表参考扩充，独立完整预测未完成','已知中间量回算不是前瞻证明','budget.json；financial_review.json 34项比较/8项显示恒等式','报告区别恒等式与期初决策预测，保留整数显示区间差异','完整保留预算验证点及期初/决策精度来源'),
    (17,'范围外分支保留','短贷/库存/税亏/大客户/厂房时序未唯一识别','budget.json unidentified','不补零拼利润；低现金标短贷未识别','相应非零或跨期样本'),
    (18,'被验收门槛阻止','未完成条件滚动和多区间细化','search.json GATED_NOT_RUN','前三阶段独立验证后再粗筛/细化/合并等价方案','合法范围、未来前景与完整状态结转'),
    (19,'归档基准压力扩充，完整候选覆盖未完成','现金达标不证明盈利；压力不是概率','stress.json coverage/sampling','单因子/组合/2000分层样本；未覆盖类别明确false','可验收候选及所有经营融资分支'),
    (20,'版本隔离、复现及情境分层通过；并发修改停止扰动','旧跨情境拟合不可用于确定推荐','snapshot；manifest；context；live_trials','逻辑隔离360条未核情境记录；机器试验已恢复','其他编号市场各回合前景与稳定个人/小组基准')
]


def build(out, results):
    records=[]
    for r in results['audit']['data']:
        if r['category'] not in ['actual_demand','actual_sales']: continue
        records.append(dict(model='实际',market_id=r['market_id'],country=r['country'],phase=r['phase'],round=r['round'],
            team_id=r['team_id'],competition='已实现对手策略',decision='历史决策',category=r['category'],
            value=r['value'],actual=r['value'],predicted=None,unit=r['unit'],source=r['source'],
            context_id=r.get('context_id','LEGACY_CONTEXT_UNSPECIFIED'),context_verified=r.get('context_verified',False)))
    demand=results.get('demand',{})
    records+=demand.get('predictions',[])
    country=results.get('country',{})
    records+=country.get('predictions',[])
    for name,model in country.get('models',{}).items():
        for row in model['cv_path']:
            records.append(dict(model='COUNTRY_DEMAND_V1/'+name+'-path',market_id=5,country=model['country'],
                context_id=model['context_id'],phase='practice',round=model['training_keys'][0][2],
                competition='训练内留队',decision=row['config']['loss']+'/标准化/单段/rho=0.5',
                category='training_validation',penalty=row['config']['penalty'],value=row['cv_share_mae_pp'],unit='份额MAE百分点'))
    for r in results.get('financial_review',{}).get('records',[]):
        records.append(dict(r,model='三表预算参考',market_id=5,country='公司',phase='formal',round=1,
            competition='固定手填需求，非真实标签',decision='机器'+('0' if r['case']=='baseline' else '1')+'，历史已恢复',
            context_id='M5_P1_FORMAL1_VISIBLE',category='budget_statement_reference',value=r['predicted'],calibratable=False))
    for name,pool in demand.get('pools',{}).items():
        for row in pool['cv_path']:
            records.append(dict(model=name+'-v2-path',market_id=pool.get('market_id',5 if name=='A' else '1–10'),country='两国',phase='practice',round=pool['refit_model']['training_keys'][0][2],
                competition='训练内留队',decision=f"{row['loss']}/{'标准化' if row['standardized'] else '原始'}/{'分段' if row['piecewise'] else '单段'}/rho={row['rho']}",
                category='training_validation',penalty=row['penalty'],value=row['cv_share_mae_pp'],unit='份额MAE百分点',
                rho=row['rho'],loss=row['loss'],piecewise=row['piecewise'],standardized=row['standardized'],context_id=pool.get('context_id','MIXED_UNVERIFIED')))
        for i,beta in enumerate(pool.get('resampling',{}).get('beta',[])):
            records.append(dict(model=name+'-v2-resampling',market_id=pool.get('market_id',5 if name=='A' else '1–10'),country='印尼',phase='practice',round=pool['refit_model']['training_keys'][0][2],context_id=pool.get('context_id','MIXED_UNVERIFIED'),
                competition='描述性簇重采样',decision='固定选参后重拟合',category='descriptive_resampling',sample=i,
                value=beta[1],unit='印尼价格系数',beta=beta))
    for r in results['budget']['checks']:
        records.append(dict(model='旧预算回算',market_id=5,country='公司',phase='formal',round=1,competition='玩家手填需求',decision='归档个人基准',
            category='budget',context_id='M5_P1_FORMAL1_VISIBLE',metric=r['metric'],actual=r['observed'],predicted=r['predicted'],residual=r['error'],value=r['predicted'],unit='千美元',source=r['source']))
    if results.get('live'):
        for r in results['live']['single_point_checks']:
            records.append(dict(model='个人预算试验参考',market_id=5,country='公司',phase='formal',round=1,
                competition='固定手填需求，非真实标签',decision='机器0→1→0，已恢复',category='budget_trial_reference',
                metric=r['metric'],actual=r['observed'],predicted=r['predicted'],residual=r['error'],value=r['observed'],unit='千美元',
                context_id='M5_P1_FORMAL1_VISIBLE',calibratable=False))
    a=results['budget']['output'];state=read('分步模型拟合与验证.json')['decisions']['current_inputs']['state']
    waterfalls={
        '利润':[('收入',a['revenue']),('材料',-a['materials']),('工资',-a['production']['payroll']),('运输',-a['transport']),('营销',-a['marketing']),('其他费用',-a['overhead']),('机器折旧',-a['machine_depreciation']),('厂房折旧',-a['building_depreciation']),('现金利息',a['cash_interest']),('贷款利息',-a['long_interest']),('税',-a['tax'])],
        '现金':[('期初现金',state['cash']),('EBITDA',a['ebitda']),('贷款利息',-a['long_interest']),('应收变动',state['ar']-a['ar']),('应付变动',a['ap']-state['ap']),('机器投资',-a['machine_capex']),('厂房投资',-a['building_capex']),('贷款变化',a['long_debt']-state['long_debt']),('现金利息',a['cash_interest']),('税',-a['tax'])]}
    for metric,steps in waterfalls.items():
        cumulative=0
        for i,(label,amount) in enumerate(steps):
            before=cumulative;cumulative+=amount
            records.append(dict(model='条件财务瀑布',market_id=5,country='公司',phase='formal',round=1,
                competition='固定手填需求',decision='归档个人基准',context_id='M5_P1_FORMAL1_VISIBLE',category='conditional_waterfall',
                metric=metric,step=i,label=label,value=amount,waterfall_start=before,waterfall_end=cumulative,unit='千美元'))
        assert abs(cumulative-a['profit' if metric=='利润' else 'cash'])<1e-6
    stress=results.get('stress',{})
    for group in ['deterministic','samples','boundaries']:
        for i,r in enumerate(stress.get(group,[])):
            a=r['output']
            records.append(dict(model='条件财务',market_id=5,country='公司',phase='formal',round=1,
                competition='假定压力',decision='归档个人基准',category='assumed_stress_'+group,
                scenario=r.get('name',f'数学边界{i}'),sample=i,context_id='M5_P1_FORMAL1_VISIBLE',profit=a['profit'],cash=a['cash'],value=a['profit'],
                short_debt_needed=a['short_debt_needed_before_unidentified_short_interest'],equity=a['equity'],
                delivered=sum(a['sales']),in_scope=a['fully_computed_in_scope'],unit='千美元',
                factors={k:v for k,v in r.items() if k!='output'}))
    columns=sorted({k for r in records for k in r})
    with (out/'records.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in records)
    write(out/'report_data.json',records)
    issues=[dict(number=n,status=s,impact=i,evidence=e,solution=a,next_evidence=q) for n,s,i,e,a,q in ISSUES]
    write(out/'issues.json',dict(current_all_issues=issues,data_unverifiable=[r for r in issues if r['number']!=2]))
    lines=['# Cesim model-v2 重审（离线阶段交付）','',
        '已隔离新版并复现冻结结果；尚未通过独立需求/效率/预算机制验收，因此不输出当前推荐或六回合累计收益排名。',
        '',f"实际记录{results['audit']['n_rows']}条，练习训练可用{results['audit']['n_fit']}条；冻结预测{results['audit']['frozen_predictions']['n']}条完全复现。",
        '市场及国家等权损失统一；每一训练折独立计算尺度并保存逆变换。A平均损失λ=0.01对应40条记录残差总和λ=0.4；B对应n倍加权损失λ=4。',
        '旧预算11项回算完整复现；材料舍入单位更正为约4.5–5.265千美元，而非约5美元。所有预算结果仅验证归档条件，不能证明真实需求。','']
    for name,pool in demand.get('pools',{}).items():
        if pool.get('forward_share_mae_pp') is not None:
            lines += [f"{name}新版训练内所选：{pool['selected']}；跨情境练习1→2份额MAE={pool['forward_share_mae_pp']:.4f}个百分点；仅回溯。"]
        else:
            lines += [f"{name}情境内所选：{pool['selected']}；内部留队份额MAE={pool['cv_share_mae_pp']:.4f}个百分点。没有同情境跨回合外部验证。五种研发延续已重新拟合；份额损失仅在对数网格选出的延续下作补充比较，未联合枚举全部份额损失延续组合。"]
    if results.get('context'):
        lines += ['', '已接收用户补充的练习2背景并按情境重审。练习1/正式1可见情境与练习2不同；其他市场360条可拟合记录因缺各自前景而逻辑隔离。保留旧数据和先前运行，不宣称全部旧数据错误。',
                  '练习2原材料表1053、+17%；叙述未来约涨20%和机器可能降价40%与当期单价100并列。情境和回合共变，目前无法唯一分离。详见context.json。']
    if country:
        lines += ['', '已只读接入COUNTRY_DEMAND_V1的四个国家/情境独立模型；40条原保存份额预测精确复现。价格、营销与研发系数分国家，但营销输入仍是两国合计代理，研发延续固定0.5；未优化国别支出分配，未自动切换利润搜索模型。详见country_review.json。']
    if results.get('financial_review'):
        f=results['financial_review'];s=f['summary']
        lines += ['', f"补充资产负债/现金流参考{s['comparison_n']}项，其中{s['target_display_interval_matches']}项名义预测落在目标整数显示±0.5千美元区间；其余保留差额，未传播全部输入与经验参数精度，不能仅凭此拒绝或验收机制。{s['accounting_identities_n']}项显示会计恒等式满足按项数传播的舍入范围。",
                  '补齐固定手填利率下的贷款最低现金数学边界及非法财务输入拒绝检查；边界1e-6内的数值误差不触发短贷。网页贷款合法步长、风险联动及独立套件仍缺，未恢复网页扰动。详见financial_review.json。']
    if results.get('materials'):
        lines += ['', '独立材料核验：练习1共同加性差额区间[1.0935,1.3248]美元/单位；练习2[1.3303,1.4962]，不相交。固定差额不覆盖全部记录；不能据此证明隐藏加价，详见materials_review.json。']
    live_note='初始页面读取多次超时；未进行预算扰动。'
    if results.get('live'):
        live_note='实时正式1/身份/市场5/个人基准已核验。个人机器0→1→0保存并重入恢复；完整预算/生产/物流已捕获。恢复时其他成员列变化，已停止后续扰动，样本不拟合；尚无完整独立保留验证套件。'
    lines += ['', live_note,
        '归档个人基准完成单因素、关键组合、班次/解聘数学边界与固定种子2000组分层范围抽样；完整候选、对手策略、风险联立及跨回合覆盖尚未完成，详见stress.json coverage。',
        '报告筛选、摘要、图表与CSV共用report_data.json对应的集合；未计算的图明确显示缺口。实时UI筛选/导出/打印/宽窄屏验收尚未完成。','',
        '## 当前全部问题与不足','', '| 编号 | 状态 | 影响 | 证据 | 解决方案 | 下一项证据 |','| --- | --- | --- | --- | --- | --- |']
    lines += [f'| {n} | {s} | {i} | {e} | {a} | {q} |' for n,s,i,e,a,q in ISSUES]
    lines += ['', '## 因缺乏数据而无法验证的问题','', '| 编号 | 状态 | 影响 | 证据 | 解决方案 | 所需证据 |','| --- | --- | --- | --- | --- | --- |']
    lines += [f'| {n} | {s} | {i} | {e} | {a} | {q} |' for n,s,i,e,a,q in ISSUES if n!=2]
    lines += ['', '预算试验、国别营销、完整历史、正式实际、低投入及非零库存/短贷/大客户/亏后转盈/未来前景缺口未解决。分层分位数不称置信区间或真实概率，测试最小值不称所有可能情形的最坏值。']
    (out/'conclusions.md').write_text('\n'.join(lines),encoding='utf-8')
    table='<table><thead><tr>'+''.join('<th>'+c+'</th>' for c in ['编号','状态','影响','证据','解决方案','所需证据'])+'</tr></thead><tbody>'
    for row in ISSUES:
        table+='<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>'
    table+='</tbody></table>'
    issue_gap='<table><thead><tr>'+''.join('<th>'+c+'</th>' for c in ['编号','状态','影响','证据','解决方案','所需证据'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in ISSUES if row[0]!=2)+'</tbody></table>'
    page=HTML.replace('__DATA__',json.dumps(records,ensure_ascii=False,allow_nan=False).replace('<','\\u003c'))
    page=page.replace('__ISSUES__',table).replace('__GAPS__',issue_gap)
    (out/'report.html').write_text(page,encoding='utf-8')
    script=page.split('<script id="data" type="application/json">')[1].split('</script>')[0]
    assert json.loads(script)==records
    assert len(issues)==20 and len(set(r['number'] for r in issues))==20
    write(out/'report_checks.json',dict(embedded_json_equals_saved_json=True,records_n=len(records),all_twenty_issues=True,
        cdn_dependencies=False,html_numeric_values_generated_from_json=True,browser_interaction_tested=False,
        pending_ui_checks=['筛选','导出','打印','宽屏','窄屏','标签截断','颜色辨识','并排比较'],
        reason='生成时只完成静态检查；实际浏览器验收另存追加QA目录，不回写此冻结运行'))


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cesim model-v2 重审</title><style>
:root{color-scheme:light;--ink:#162d43;--accent:#146b84}*{box-sizing:border-box}body{font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif;margin:0;background:#f1f4f5;color:var(--ink)}main{max-width:1500px;margin:auto;padding:28px}h1{font-size:30px;margin:0}h2{font-size:21px;margin-top:34px}.notice{border-left:5px solid #b86818;background:#fff5e5;padding:16px;margin:18px 0}.filters{display:flex;flex-wrap:wrap;gap:12px;padding:16px;background:white;border:1px solid #cbd4db}label{display:flex;flex-direction:column;max-width:220px}select,input,button{font:inherit;padding:6px;border:1px solid #8093a1;background:white;color:var(--ink);border-radius:3px}select[multiple]{height:110px}button{cursor:pointer}button:focus-visible,select:focus-visible{outline:3px solid #cf7824}.charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.chart{padding:14px;background:white;border:1px solid #cbd4db;overflow:hidden}.chart h3{margin:0 0 8px;font-size:16px}.chart svg{width:100%;height:auto;display:block}.empty{min-height:140px;display:flex;align-items:center;color:#657580}.scroll{overflow:auto;background:white}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #dae1e5;text-align:left;padding:8px;vertical-align:top;min-width:75px}th{background:#e6edf1}td{overflow-wrap:anywhere}#summary{font-weight:600;margin:16px 0}details{margin:20px 0}a{color:#126c88}@media(max-width:750px){main{padding:14px}.charts{grid-template-columns:1fr}h1{font-size:24px}}@media print{body{background:white}main{max-width:none;padding:0}.filters,button,#paging{display:none}.chart{break-inside:avoid}.scroll{overflow:visible}details{display:block}table{font-size:10px}}
</style><main><h1>Cesim model-v2 建模重审</h1><p>版本隔离 · 损失口径统一 · 冻结复现 · 识别缺口保留</p>
<div class="notice"><b>阶段门槛尚未通过，当前没有确定推荐。</b>冻结1,600条需求预测和旧预算回算已复现。新版仅为回溯研究；实际、预算、模型与假定压力分别标记。正式1个人基准已核，机器0→1→0试验已恢复；其他成员列变化后停止后续扰动。未知数值显示“未知”。</div>
<p><a href="conclusions.md">Markdown结论</a> · <a href="manifest.json">版本及源哈希</a> · <a href="audit.json">一致性检查</a> · <a href="budget.json">预算与材料差额</a> · <a href="report_data.json">完整报告数据</a> · <a href="records.csv">全部CSV</a></p>
<section class="filters" id="filters" aria-label="统一筛选"></section>
<p><button id="reset">重置筛选</button> <button id="export">导出当前筛选CSV</button> <button id="print">打印当前筛选</button></p>
<div id="summary" aria-live="polite"></div><section class="charts" id="charts"></section>
<h2>筛选明细（排序、分页与导出使用相同集合）</h2><label>按字段排序<select id="sort"></select></label>
<div id="paging"><button id="prev">上一页</button> <span id="page"></span> <button id="next">下一页</button></div><div class="scroll"><table id="rows"></table></div>
<details open><summary><b>当前全部问题与不足（20项）</b></summary><div class="scroll">__ISSUES__</div></details>
<details><summary><b>因缺乏数据而无法验证的问题（按原编号）</b></summary><div class="scroll">__GAPS__</div></details>
<p>抽样仅描述指定测试集合，不是盈利概率或置信区间；现金达标不保证盈利。图形留点只检验近似。联合搜索与跨回合排名被验收门槛阻止，未把缺失未来状态补为零。</p>
<p>图表标明单位和样本数；原始信息与完整因素见JSON。图中同情境拟合为样本内描述；情境与回合共变，不能作独立正式验证。</p></main>
<script id="data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent), fields={context_id:'情境（未知单列）',model:'模型版本（可多选）',market_id:'编号市场',country:'国家',phase:'阶段',round:'回合',competition:'竞争情景',decision:'决策/拟合条件',category:'数据类别'};
const controls={},filterBox=document.getElementById('filters');let view=[],page=0;
const text=v=>v===null||v===undefined?'未知':typeof v==='object'?JSON.stringify(v):String(v);
const unique=k=>[...new Set(data.map(r=>text(r[k])))].sort();const display=(k,v)=>{if(k==='context_id'){if(v==='M5_P1_FORMAL1_VISIBLE')return '情境1：练习1/正式1';if(v==='M5_P2_GROWTH_MARKETING_BULK')return '情境2：练习2';if(v.startsWith('UNVERIFIED_'))return '未核 '+v.slice(11);}if(k==='model'){if(v==='A-old-frozen')return '旧冻结A（跨情境）';if(v==='B-old-frozen')return '旧冻结B（情境未核）';if(v.startsWith('COUNTRY_DEMAND_V1/')){return (v.includes('_P1_')?'情境1':'情境2')+'·国别'+(v.includes('/泰国')?'泰国':'印尼')+(v.endsWith('-path')?'·正则':'');}if(v.startsWith('A/M5_P')){const c=v.includes('_P1_')?'情境1':'情境2';return c+(v.endsWith('-v2-path')?'·正则路径':v.endsWith('-v2-resampling')?'·重采样':'·新版A');}}return v;};

for(const [k,label]of Object.entries(fields)){const l=document.createElement('label');l.append(label);const s=document.createElement('select');s.setAttribute('aria-label',label);if(k==='model')s.multiple=true;else s.add(new Option('全部',''));for(const v of unique(k)){const o=new Option(display(k,v),v);o.title=v;s.add(o);}s.onchange=()=>{s.title=[...s.selectedOptions].map(o=>o.value).join('；');page=0;render()};l.append(s);filterBox.append(l);controls[k]=s;}
const columns=['context_id','model','market_id','country','phase','round','competition','decision','category','scenario','metric','label','step','team_id','price','actual','predicted','residual','penalty','value','profit','cash','in_scope','rd_curve_extrapolation','unit'];
const columnLabels={context_id:'情境',model:'模型',market_id:'市场',country:'国家',phase:'阶段',round:'回合',competition:'竞争情景',decision:'决策',category:'类别',scenario:'压力情景',metric:'指标',label:'分解项',step:'步骤',team_id:'团队',price:'单价（美元）',actual:'观测',predicted:'预测',residual:'残差',penalty:'λ',value:'数值',profit:'利润（千美元）',cash:'现金（千美元）',in_scope:'计算范围内',rd_curve_extrapolation:'研发曲线外推',unit:'单位'};const sort=document.getElementById('sort');for(const k of columns)sort.add(new Option(columnLabels[k]||k,k));sort.onchange=()=>{page=0;render()};let printing=false;
function selection(){return data.filter(r=>Object.entries(controls).every(([k,s])=>{const values=[...s.selectedOptions].map(o=>o.value).filter(Boolean);return !values.length||values.includes(text(r[k]));})).sort((a,b)=>typeof a[sort.value]==='number'&&typeof b[sort.value]==='number'?a[sort.value]-b[sort.value]:text(a[sort.value]).localeCompare(text(b[sort.value])));}
const ns='http://www.w3.org/2000/svg';function el(tag,attrs={},value=''){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);e.textContent=value;return e;}
function chart(title,rows,x,y,xlabel,ylabel,bar=false){const c=document.createElement('div');c.className='chart';const h=document.createElement('h3');h.textContent=title;c.append(h);document.getElementById('charts').append(c);const good=rows.filter(r=>Number.isFinite(x(r))&&Number.isFinite(y(r)));const models=[...new Set(good.map(r=>r.model))];const palette=['#126b87','#9b4520','#6d498c','#3f7051'];const legend=document.createElement('p');legend.style.fontSize='12px';for(const [i,m]of models.entries()){const label=document.createElement('span');label.textContent=display('model',m)+' ';label.style.color=palette[i%palette.length];legend.append(label);}c.append(legend);if(!good.length){const p=document.createElement('p');p.className='empty';p.textContent='当前筛选无可计算数据；未知不补零。';c.append(p);return;}const svg=el('svg',{viewBox:'0 0 620 300',role:'img','aria-label':`${title}，样本数${good.length}，横轴${xlabel}，纵轴${ylabel}`});c.append(svg);const xs=good.map(x),ys=good.map(y);let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(0,...ys),ymax=Math.max(...ys);if(xmax===xmin)xmax=xmin+1;if(ymax===ymin)ymax=ymin+1;const X=v=>70+(v-xmin)/(xmax-xmin)*515,Y=v=>245-(v-ymin)/(ymax-ymin)*210;svg.append(el('path',{d:'M70 30V245H585',stroke:'#677b87',fill:'none'}));for(let i=0;i<5;i++){const xx=xmin+(xmax-xmin)*i/4,yy=ymin+(ymax-ymin)*i/4;svg.append(el('text',{x:X(xx),y:263,'text-anchor':'middle','font-size':11},xx.toFixed(2)));svg.append(el('text',{x:62,y:Y(yy)+4,'text-anchor':'end','font-size':11},yy.toFixed(2)));}svg.append(el('text',{x:330,y:289,'text-anchor':'middle','font-size':12},xlabel));svg.append(el('text',{x:9,y:17,'font-size':12},ylabel));svg.append(el('text',{x:580,y:18,'text-anchor':'end','font-size':12},`n=${good.length}`));for(const r of good){const shape=r.rd_curve_extrapolation?'rect':'circle';const dot=el(shape,shape==='circle'?{cx:X(x(r)),cy:Y(y(r)),r:2.8,fill:palette[models.indexOf(r.model)%palette.length],opacity:.55}:{x:X(x(r))-3,y:Y(y(r))-3,width:6,height:6,fill:palette[models.indexOf(r.model)%palette.length],stroke:'#ab481c',opacity:.7});dot.append(el('title',{},`${text(r.model)} ${text(r.country)} ${text(r.scenario||r.team_id||r.decision)}: ${x(r)}, ${y(r)}`));svg.append(dot);}}
function waterfall(metric,collection){const rows=collection.filter(r=>r.category==='conditional_waterfall'&&r.metric===metric).sort((a,b)=>a.step-b.step);const c=document.createElement('div');c.className='chart';const h=document.createElement('h3');h.textContent=metric+'瀑布（归档个人基准条件计算，千美元）';c.append(h);document.getElementById('charts').append(c);if(!rows.length){const p=document.createElement('p');p.className='empty';p.textContent='当前筛选没有完整分解数据；未知不补零。';c.append(p);return;}const svg=el('svg',{viewBox:'0 0 620 360',role:'img','aria-label':metric+'瀑布，千美元，条件计算'});c.append(svg);const vals=rows.flatMap(r=>[r.waterfall_start,r.waterfall_end]);const lo=Math.min(0,...vals),hi=Math.max(0,...vals),span=hi-lo||1,Y=v=>260-(v-lo)/span*220;svg.append(el('path',{d:'M58 35V260H600',stroke:'#677b87',fill:'none'}));rows.forEach((r,i)=>{const x=62+i*530/rows.length,w=530/rows.length-5;const rect=el('rect',{x,y:Y(Math.max(r.waterfall_start,r.waterfall_end)),width:w,height:Math.max(1,Math.abs(Y(r.waterfall_start)-Y(r.waterfall_end))),fill:r.value>=0?'#146b84':'#b6531c'});rect.append(el('title',{},r.label+': '+r.value.toFixed(6)+'；累计'+r.waterfall_end.toFixed(6)));svg.append(rect);svg.append(el('text',{transform:'translate('+(x+w/2)+',280) rotate(45)','font-size':11},r.label));});svg.append(el('text',{x:60,y:20,'font-size':12},'终值 '+rows.at(-1).waterfall_end.toFixed(3)+' 千美元；n='+rows.length));}
function missing(title,reason){const c=document.createElement('div');c.className='chart';const h=document.createElement('h3');h.textContent=title;const p=document.createElement('p');p.className='empty';p.textContent=reason;c.append(h,p);document.getElementById('charts').append(c);}
function render(){view=selection();document.getElementById('summary').textContent=`当前集合 ${view.length} 条；模型 ${new Set(view.map(r=>r.model)).size} 种；实际 ${view.filter(r=>r.category.startsWith('actual')).length}；预算 ${view.filter(r=>r.category==='budget').length}；假定压力 ${view.filter(r=>r.category.startsWith('assumed_stress')).length}。未标范围通过的利润不参与排名。`;
document.getElementById('charts').replaceChildren();chart('正则路径（条件见悬浮明细）',view.filter(r=>r.category==='training_validation'),r=>Math.log10(r.penalty),r=>r.value,'log10 λ','留出份额MAE，百分点');chart('价格与实际需求散点',view.filter(r=>['retrospective_model','in_sample_context_model','historical_frozen_baseline','in_sample_independent_country_model'].includes(r.category)),r=>r.price,r=>r.actual,'价格，美元/单位','实际需求，千单位');chart('预测与实际（给定真实行业总量）',view.filter(r=>['retrospective_model','in_sample_context_model','historical_frozen_baseline','in_sample_independent_country_model'].includes(r.category)),r=>r.actual,r=>r.predicted,'实际需求，千单位','模型需求，千单位');chart('残差与价格（方形标研发曲线外推）',view.filter(r=>['retrospective_model','in_sample_context_model','historical_frozen_baseline','in_sample_independent_country_model'].includes(r.category)),r=>r.price,r=>r.residual,'价格，美元/单位','预测−实际，千单位');chart('簇重采样系数分布（描述性）',view.filter(r=>r.category==='descriptive_resampling'),r=>r.value,r=>r.sample,'印尼价格系数','抽取编号');chart('利润与现金权衡（归档基准假定压力）',view.filter(r=>r.category.startsWith('assumed_stress')),r=>r.profit,r=>r.cash,'条件利润，千美元','现金，千美元');waterfall('利润',view);waterfall('现金',view);missing('价格热力图','联合决策搜索未通过前三阶段门槛；当前没有经过完整经营验证的价格网格。');missing('跨回合状态图','未来当期前景及非零状态结转尚未验证，正式2–6状态未知，未计算累计收益排名。');
const table=document.getElementById('rows');table.replaceChildren();const head=document.createElement('thead'),tr=document.createElement('tr');for(const k of columns){const th=document.createElement('th');th.textContent=columnLabels[k]||k;tr.append(th)}head.append(tr);table.append(head);const body=document.createElement('tbody');for(const r of (printing?view:view.slice(page*100,(page+1)*100))){const tr=document.createElement('tr');for(const k of columns){const td=document.createElement('td');td.textContent=typeof r[k]==='number'?String(Number(r[k].toFixed(6))):text(r[k]);tr.append(td)}body.append(tr)}table.append(body);document.getElementById('page').textContent=`第${page+1}/${Math.max(1,Math.ceil(view.length/100))}页，每页100条，导出含全部${view.length}条`;document.getElementById('prev').disabled=page===0;document.getElementById('next').disabled=(page+1)*100>=view.length;}
document.getElementById('reset').onclick=()=>{for(const[k,s]of Object.entries(controls)){if(s.multiple)for(const o of s.options)o.selected=false;else s.value='';}page=0;render()};document.getElementById('prev').onclick=()=>{page--;render()};document.getElementById('next').onclick=()=>{page++;render()};window.addEventListener('beforeprint',()=>{printing=true;render()});window.addEventListener('afterprint',()=>{printing=false;render()});document.getElementById('print').onclick=()=>window.print();
document.getElementById('export').onclick=()=>{const keys=[...new Set(view.flatMap(r=>Object.keys(r)))].sort();const quote=v=>'"'+text(v).replaceAll('"','""')+'"';const csv='\ufeff'+[keys.map(quote).join(','),...view.map(r=>keys.map(k=>quote(r[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='cesim_model_v2_filtered.csv';a.click();URL.revokeObjectURL(url);};render();
</script></html>'''
