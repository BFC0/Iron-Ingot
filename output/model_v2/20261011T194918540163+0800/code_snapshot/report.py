"""Local, source-backed report; every view and CSV uses one filtered collection."""
import csv
import html
from core import *


ISSUES = [
    (1,'部分处理','尺度影响系数解释','需求留出路径及逐折尺度','比较原始/标准化惩罚；系数不是因果回报','独立正式需求与投入试验'),
    (2,'离线一致性通过','旧lambda不能直接混用','audit.json loss_equivalence','统一市场/国家等权；相应乘n的惩罚参数等价','无；新数据仍须复核训练口径'),
    (3,'已诊断，未唯一识别','极端价主导价格信息','demand.json 高价信息与删簇诊断','保留真实记录并比较固定1.5倍初始价分段','普通区间独立价格变化'),
    (4,'未识别','投入关联不能作因果回报','demand.json correlations','保留合计代理，披露共变和内生性','独立营销/研发变化与真实需求'),
    (5,'缺资料','合计代理可能把国别差异转移到价格','audit.json sources','不优化国别分配，不把代理当国别营销','各队国别营销原始记录'),
    (6,'部分处理','对数排零与机制假设影响拟合','audit.json zero_demand；demand.json share候选','不加伪小数，另用保留零的份额损失','零值真实精度与舍入方式'),
    (7,'未识别','固定总量遗漏行业策略作用','预测行 oracle_total=true','仅给定行业总量评价份额，保留规模情景','行业总量与独立全行业策略变化'),
    (8,'已区分，外部验证缺失','回溯成绩不能当正式成绩','需求训练/测试键及原冻结1600条复现','练习1内选参，练习2仅回溯；正式先评分冻结','正式实际需求/对手决策'),
    (9,'已重拟合情景，存量未识别','延续系数与技术趋势混杂','需求rho网格；mechanisms.json效率rho','分别重拟合0/.25/.5/.75/1，不沿用系数','完整研发/运营投入历史'),
    (10,'缺独立曲线','同图留点仅证明近似','mechanisms.json curve_scope','图形误差与经营验证分开','其他编号市场可见曲线及独立结果'),
    (11,'已标记，外推未验证','研发曲线1200以外不受图形支持','预测 effective_rd 与 rd_curve_extrapolation','范围内外分组评价，不隐藏外推','高投入区间曲线和真实需求'),
    (12,'区间与重复策略诊断完成，低投入未验证','运营400超出600–1300训练范围','mechanisms.json efficiency','产量/人数舍入区间、按策略均衡尺度及五种延续','运营400成功保存恢复预算或实际效率'),
    (13,'两函数及删队诊断完成，外推未验证','风险系数来自十家实际期末状态','mechanisms.json risk','两函数保留，不据样本内好拟合确定还贷','大额还贷、计息时点及溢价试验'),
    (14,'部分关联来源，未来未验证','硬编码参数不适合跨回合照搬','budget.json parameters；stress.json parameters','当前源与经验项分开，未来值留空','各正式回合前景及精确参数'),
    (15,'单位更正；机制差额保留','原料差额仍不能归因于隐藏成本','budget.json materials/correction','分别列基础成本、经验差额、舍入包络','完整材料/产量高精度独立试验'),
    (16,'旧回算已复现，独立完整预测未完成','已知中间量回算不是前瞻证明','budget.json 11项回算及原372/240项检查','报告区别恒等式与期初决策预测','完整保留预算验证点及期初/决策来源'),
    (17,'范围外分支保留','短贷/库存/税亏/大客户/厂房时序未唯一识别','budget.json unidentified','不补零拼利润；低现金标短贷未识别','相应非零或跨期样本'),
    (18,'被验收门槛阻止','未完成条件滚动和多区间细化','search.json GATED_NOT_RUN','前三阶段独立验证后再粗筛/细化/合并等价方案','合法范围、未来前景与完整状态结转'),
    (19,'归档基准压力扩充，完整候选覆盖未完成','现金达标不证明盈利；压力不是概率','stress.json coverage/sampling','单因子/组合/2000分层样本；未覆盖类别明确false','可验收候选及所有经营融资分支'),
    (20,'版本隔离及复现通过，实时基准缺失','新旧训练/研发存量不可混用','snapshot；manifest.json；冻结复现','独立分支与目录，旧资料哈希保护，旧latest不更新','实时身份/开放回合/个人与小组最新值')
]


def build(out, results):
    records=[]
    for r in results['audit']['data']:
        if r['category'] not in ['actual_demand','actual_sales']: continue
        records.append(dict(model='实际',market_id=r['market_id'],country=r['country'],phase=r['phase'],round=r['round'],
            team_id=r['team_id'],competition='已实现对手策略',decision='历史决策',category=r['category'],
            value=r['value'],actual=r['value'],predicted=None,unit=r['unit'],source=r['source']))
    demand=results.get('demand',{})
    records+=demand.get('predictions',[])
    for name,pool in demand.get('pools',{}).items():
        for row in pool['cv_path']:
            records.append(dict(model=name+'-v2-path',market_id=5 if name=='A' else '1–10',country='两国',phase='practice',round=1,
                competition='训练内留队',decision=f"{row['loss']}/{'标准化' if row['standardized'] else '原始'}/{'分段' if row['piecewise'] else '单段'}/rho={row['rho']}",
                category='training_validation',penalty=row['penalty'],value=row['cv_share_mae_pp'],unit='份额MAE百分点',
                rho=row['rho'],loss=row['loss'],piecewise=row['piecewise'],standardized=row['standardized']))
        for i,beta in enumerate(pool['resampling']['beta']):
            records.append(dict(model=name+'-v2-resampling',market_id=5 if name=='A' else '1–10',country='印尼',phase='practice',round='1+2',
                competition='描述性簇重采样',decision='固定选参后重拟合',category='descriptive_resampling',sample=i,
                value=beta[1],unit='印尼价格系数',beta=beta))
    for r in results['budget']['checks']:
        records.append(dict(model='旧预算回算',market_id=5,country='公司',phase='formal',round=1,competition='玩家手填需求',decision='归档个人基准',
            category='budget',metric=r['metric'],actual=r['observed'],predicted=r['predicted'],residual=r['error'],value=r['predicted'],unit='千美元',source=r['source']))
    stress=results.get('stress',{})
    for group in ['deterministic','samples','boundaries']:
        for i,r in enumerate(stress.get(group,[])):
            a=r['output']
            records.append(dict(model='条件财务',market_id=5,country='公司',phase='formal',round=1,
                competition='假定压力',decision='归档个人基准',category='assumed_stress_'+group,
                scenario=r.get('name',f'数学边界{i}'),sample=i,profit=a['profit'],cash=a['cash'],value=a['profit'],
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
        lines += [f"{name}新版训练内所选：{pool['selected']}；练习1→练习2给定真实总量份额MAE={pool['forward_share_mae_pp']:.4f}个百分点。该成绩仍为回溯研究。"]
    lines += ['', '实时主页打开及绑定均超时；未确认开放回合/身份/最新个人与小组基准，网页扰动次数为0，无新有效预算样本。',
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
    issue_gap=table.replace('</tbody>', '</tbody>')
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
        reason='尚未获得可读取的浏览器AX状态；只完成静态一致性检查'))


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cesim model-v2 重审</title><style>
:root{color-scheme:light;--ink:#162d43;--accent:#146b84}*{box-sizing:border-box}body{font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif;margin:0;background:#f1f4f5;color:var(--ink)}main{max-width:1500px;margin:auto;padding:28px}h1{font-size:30px;margin:0}h2{font-size:21px;margin-top:34px}.notice{border-left:5px solid #b86818;background:#fff5e5;padding:16px;margin:18px 0}.filters{display:flex;flex-wrap:wrap;gap:12px;padding:16px;background:white;border:1px solid #cbd4db}label{display:flex;flex-direction:column;max-width:220px}select,input,button{font:inherit;padding:6px;border:1px solid #8093a1;background:white;color:var(--ink);border-radius:3px}select[multiple]{height:110px}button{cursor:pointer}button:focus-visible,select:focus-visible{outline:3px solid #cf7824}.charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.chart{padding:14px;background:white;border:1px solid #cbd4db;overflow:hidden}.chart h3{margin:0 0 8px;font-size:16px}.chart svg{width:100%;height:auto;display:block}.empty{min-height:140px;display:flex;align-items:center;color:#657580}.scroll{overflow:auto;background:white}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #dae1e5;text-align:left;padding:8px;vertical-align:top;min-width:75px}th{background:#e6edf1}td{overflow-wrap:anywhere}#summary{font-weight:600;margin:16px 0}details{margin:20px 0}a{color:#126c88}@media(max-width:750px){main{padding:14px}.charts{grid-template-columns:1fr}h1{font-size:24px}}@media print{body{background:white}main{max-width:none;padding:0}.filters,button,#paging{display:none}.chart{break-inside:avoid}.scroll{overflow:visible}details{display:block}table{font-size:10px}}
</style><main><h1>Cesim model-v2 建模重审</h1><p>版本隔离 · 损失口径统一 · 冻结复现 · 识别缺口保留</p>
<div class="notice"><b>阶段门槛尚未通过，当前没有确定推荐。</b>冻结1,600条需求预测和旧预算回算已复现。新版仅为回溯研究；实际、预算、模型与假定压力分别标记。最新个人基准未确认，网页改动为0。未知数值显示“未知”。</div>
<p><a href="conclusions.md">Markdown结论</a> · <a href="manifest.json">版本及源哈希</a> · <a href="audit.json">一致性检查</a> · <a href="budget.json">预算与材料差额</a> · <a href="report_data.json">完整报告数据</a> · <a href="records.csv">全部CSV</a></p>
<section class="filters" id="filters" aria-label="统一筛选"></section>
<p><button id="reset">重置筛选</button> <button id="export">导出当前筛选CSV</button> <button id="print">打印当前筛选</button></p>
<div id="summary" aria-live="polite"></div><section class="charts" id="charts"></section>
<h2>筛选明细（排序、分页与导出使用相同集合）</h2><label>按字段排序<select id="sort"></select></label>
<div id="paging"><button id="prev">上一页</button> <span id="page"></span> <button id="next">下一页</button></div><div class="scroll"><table id="rows"></table></div>
<details open><summary><b>当前全部问题与不足（20项）</b></summary><div class="scroll">__ISSUES__</div></details>
<details><summary><b>因缺乏数据而无法验证的问题（按原编号）</b></summary><div class="scroll">__GAPS__</div></details>
<p>抽样仅描述指定测试集合，不是盈利概率或置信区间；现金达标不保证盈利。图形留点只检验近似。联合搜索与跨回合排名被验收门槛阻止，未把缺失未来状态补为零。</p>
<p>图表标明单位和样本数；原始信息与完整因素见JSON。HTML静态数据一致性已检查，浏览器交互与打印验收待补。</p></main>
<script id="data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent), fields={model:'模型版本（可多选）',market_id:'编号市场',country:'国家',phase:'阶段',round:'回合',competition:'竞争情景',decision:'决策/拟合条件',category:'数据类别'};
const controls={},filterBox=document.getElementById('filters');let view=[],page=0;
const text=v=>v===null||v===undefined?'未知':typeof v==='object'?JSON.stringify(v):String(v);
const unique=k=>[...new Set(data.map(r=>text(r[k])))].sort();
for(const [k,label]of Object.entries(fields)){const l=document.createElement('label');l.append(label);const s=document.createElement('select');s.setAttribute('aria-label',label);if(k==='model')s.multiple=true;else s.add(new Option('全部',''));for(const v of unique(k))s.add(new Option(v,v));s.onchange=()=>{page=0;render()};l.append(s);filterBox.append(l);controls[k]=s;}
const columns=['model','market_id','country','phase','round','competition','decision','category','scenario','team_id','price','actual','predicted','residual','penalty','value','profit','cash','in_scope','rd_curve_extrapolation','unit'];
const sort=document.getElementById('sort');for(const k of columns)sort.add(new Option(k,k));sort.onchange=()=>{page=0;render()};
function selection(){return data.filter(r=>Object.entries(controls).every(([k,s])=>{const values=[...s.selectedOptions].map(o=>o.value).filter(Boolean);return !values.length||values.includes(text(r[k]));})).sort((a,b)=>typeof a[sort.value]==='number'&&typeof b[sort.value]==='number'?a[sort.value]-b[sort.value]:text(a[sort.value]).localeCompare(text(b[sort.value])));}
const ns='http://www.w3.org/2000/svg';function el(tag,attrs={},value=''){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);e.textContent=value;return e;}
function chart(title,rows,x,y,xlabel,ylabel,bar=false){const c=document.createElement('div');c.className='chart';const h=document.createElement('h3');h.textContent=title;c.append(h);document.getElementById('charts').append(c);const good=rows.filter(r=>Number.isFinite(x(r))&&Number.isFinite(y(r)));if(!good.length){const p=document.createElement('p');p.className='empty';p.textContent='当前筛选无可计算数据；未知不补零。';c.append(p);return;}const svg=el('svg',{viewBox:'0 0 620 300',role:'img','aria-label':`${title}，样本数${good.length}，横轴${xlabel}，纵轴${ylabel}`});c.append(svg);const xs=good.map(x),ys=good.map(y);let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(0,...ys),ymax=Math.max(...ys);if(xmax===xmin)xmax=xmin+1;if(ymax===ymin)ymax=ymin+1;const X=v=>70+(v-xmin)/(xmax-xmin)*515,Y=v=>245-(v-ymin)/(ymax-ymin)*210;svg.append(el('path',{d:'M70 30V245H585',stroke:'#677b87',fill:'none'}));for(let i=0;i<5;i++){const xx=xmin+(xmax-xmin)*i/4,yy=ymin+(ymax-ymin)*i/4;svg.append(el('text',{x:X(xx),y:263,'text-anchor':'middle','font-size':11},xx.toFixed(2)));svg.append(el('text',{x:62,y:Y(yy)+4,'text-anchor':'end','font-size':11},yy.toFixed(2)));}svg.append(el('text',{x:330,y:289,'text-anchor':'middle','font-size':12},xlabel));svg.append(el('text',{x:9,y:17,'font-size':12},ylabel));svg.append(el('text',{x:580,y:18,'text-anchor':'end','font-size':12},`n=${good.length}`));for(const r of good){const shape=r.rd_curve_extrapolation?'rect':'circle';const dot=el(shape,shape==='circle'?{cx:X(x(r)),cy:Y(y(r)),r:2.8,fill:r.in_scope===false?'#ab481c':'#146b84',opacity:.55}:{x:X(x(r))-3,y:Y(y(r))-3,width:6,height:6,fill:'#ab481c',opacity:.7});dot.append(el('title',{},`${text(r.model)} ${text(r.country)} ${text(r.scenario||r.team_id||r.decision)}: ${x(r)}, ${y(r)}`));svg.append(dot);}}
function missing(title,reason){const c=document.createElement('div');c.className='chart';const h=document.createElement('h3');h.textContent=title;const p=document.createElement('p');p.className='empty';p.textContent=reason;c.append(h,p);document.getElementById('charts').append(c);}
function render(){view=selection();document.getElementById('summary').textContent=`当前集合 ${view.length} 条；模型 ${new Set(view.map(r=>r.model)).size} 种；实际 ${view.filter(r=>r.category.startsWith('actual')).length}；预算 ${view.filter(r=>r.category==='budget').length}；假定压力 ${view.filter(r=>r.category.startsWith('assumed_stress')).length}。未标范围通过的利润不参与排名。`;
document.getElementById('charts').replaceChildren();chart('正则路径（条件见悬浮明细）',view.filter(r=>r.category==='training_validation'),r=>Math.log10(r.penalty),r=>r.value,'log10 λ','留出份额MAE，百分点');chart('价格与实际需求散点',view.filter(r=>r.category==='retrospective_model'),r=>r.price,r=>r.actual,'价格，美元/单位','实际需求，千单位');chart('预测与实际（给定真实行业总量）',view.filter(r=>r.category==='retrospective_model'),r=>r.actual,r=>r.predicted,'实际需求，千单位','模型需求，千单位');chart('残差与价格（方形标研发曲线外推）',view.filter(r=>r.category==='retrospective_model'),r=>r.price,r=>r.residual,'价格，美元/单位','预测−实际，千单位');chart('簇重采样系数分布（描述性）',view.filter(r=>r.category==='descriptive_resampling'),r=>r.value,r=>r.sample,'印尼价格系数','抽取编号');chart('利润与现金权衡（归档基准假定压力）',view.filter(r=>r.category.startsWith('assumed_stress')),r=>r.profit,r=>r.cash,'条件利润，千美元','现金，千美元');missing('价格热力图 / 利润与现金瀑布','联合决策搜索未通过前三阶段门槛；财务完整分解交互图尚未验收，详见budget.json与stress.json。');missing('跨回合状态图','未来当期前景及非零状态结转尚未验证，正式2–6状态未知，未计算累计收益排名。');
const table=document.getElementById('rows');table.replaceChildren();const head=document.createElement('thead'),tr=document.createElement('tr');for(const k of columns){const th=document.createElement('th');th.textContent=k;tr.append(th)}head.append(tr);table.append(head);const body=document.createElement('tbody');for(const r of view.slice(page*100,(page+1)*100)){const tr=document.createElement('tr');for(const k of columns){const td=document.createElement('td');td.textContent=typeof r[k]==='number'?String(Number(r[k].toFixed(6))):text(r[k]);tr.append(td)}body.append(tr)}table.append(body);document.getElementById('page').textContent=`第${page+1}/${Math.max(1,Math.ceil(view.length/100))}页，每页100条，导出含全部${view.length}条`;document.getElementById('prev').disabled=page===0;document.getElementById('next').disabled=(page+1)*100>=view.length;}
document.getElementById('reset').onclick=()=>{for(const[k,s]of Object.entries(controls)){if(s.multiple)for(const o of s.options)o.selected=false;else s.value='';}page=0;render()};document.getElementById('prev').onclick=()=>{page--;render()};document.getElementById('next').onclick=()=>{page++;render()};document.getElementById('print').onclick=()=>window.print();
document.getElementById('export').onclick=()=>{const keys=[...new Set(view.flatMap(r=>Object.keys(r)))].sort();const quote=v=>'"'+text(v).replaceAll('"','""')+'"';const csv='\ufeff'+[keys.map(quote).join(','),...view.map(r=>keys.map(k=>quote(r[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='cesim_model_v2_filtered.csv';a.click();URL.revokeObjectURL(url);};render();
</script></html>'''
