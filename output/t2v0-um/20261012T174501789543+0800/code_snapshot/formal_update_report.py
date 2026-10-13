"""Standalone formal2 report; no old-report imports, decision writes or overwrite."""
import argparse
import csv
import hashlib
import html
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from formal_update_state import ROOT, build, self_check
from archive_and_report import table_rows, number


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def display(value):
    if value is None:
        return '未知'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def metric_text(score):
    return '；'.join(f'{k}={v:.5g}' for k, v in score.items()
                    if isinstance(v, (float, int)) and not isinstance(v, bool)) or '见原始模型'


def personal_inputs(path):
    doc = read(path)
    assert doc['phase'] == 'formal' and doc['round'] == 2 and doc['kind'] == 'decision_not_actual_label'
    assert '- option "回合2" [selected]' in doc['snapshot']
    rows = table_rows(doc['snapshot'])
    headers = [r for r in rows if any(c.replace(' ', '') == 'PYT' for c in r['cells'])]
    assert len(headers) == 1, 'Ambiguous personal decision column'
    header = headers[0]['cells']
    column = next(i for i, cell in enumerate(header, 1) if cell.replace(' ', '') == 'PYT')
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    refs = {}
    def field(key, label, occurrence=0):
        matches = [r for r in rows if len(r['cells']) == len(header) + 1 and r['cells'][0] == label]
        assert len(matches) > occurrence, (label, occurrence)
        row = matches[occurrence]
        value = number(row['cells'][column])
        assert math.isfinite(value), (key, value)
        if key not in ['long_debt_change', 'budget_profit']:
            assert value >= 0, (key, value)
        refs[key] = dict(value=value, file=str(path.resolve()), sha256=sha, line=row['line'],
                         column=column, label=label, occurrence=occurrence)
        return value
    values = {}
    for key, label, occurrence in [
        ('price_thailand', '泰国, 美元', 0), ('price_indonesia', '印尼, 美元', 0),
        ('general_thailand', '泰国', 0), ('general_indonesia', '印尼', 0),
        ('designer_thailand', '泰国', 1), ('designer_indonesia', '印尼', 1),
        ('machine_investment', '机器, 复合梁', 0), ('allocation_percent', '复合梁', 0),
        ('operations', '泰国', 3), ('rd', '复合梁', 1),
        ('long_debt_change', '长期贷款变化(增加 + / 减少 -), 千 美元', 0),
        ('demand_estimate_thailand', '泰国', 4), ('demand_estimate_indonesia', '印尼', 3),
        ('efficiency_estimate', '复合梁', 3), ('long_debt_rate_percent', '长期贷款利率, %', 0),
        ('budget_profit', '利润, 千 美元', 0)]:
        values[key] = field(key, label, occurrence)
    assert values['price_thailand'] > 0 and values['price_indonesia'] > 0
    assert 0 <= values['allocation_percent'] <= 100 and values['efficiency_estimate'] > 0
    initials = {'JY': 'JY', 'XXL': 'XXL', 'SRQ': 'SRQ', 'PYT': 'PYT'}
    return dict(phase='formal', round=2, person='PYT', personal_column=column,
        header=header, values=values, fields=refs, usable_as_actual_training_labels=False,
        interpretation='Current personal inputs and budget; separate from formal1 closing state. Budget profit and demand/efficiency estimates are not actual labels')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['sources', 'training', 'scenario', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    states = build(args.sources.resolve())
    states['self_check'] = self_check(args.sources.resolve())
    dataset = read(args.training / 'dataset.json')
    models = read(args.training / 'models.json')
    evaluation = read(args.training / 'frozen_evaluation.json')
    inventory = read(args.training / 'model_inventory.json')
    training_checks = read(args.training / 'checks.json')
    scenario = read(args.scenario / 'scenario_comparison.json')
    user_delta = read(args.scenario / 'user_delta_interpretation.json')
    current = personal_inputs(args.sources / 'formal2_current_checklist.json')
    for source in scenario['sources'].values():
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
    source_rows = dataset['rows']
    assert states['all_markets_complete'] and len(states['states']) == 100
    assert len(source_rows) == 200 and all(r['phase'] == 'formal' and r['round'] == 1 for r in source_rows)
    indexed = {(r['market_id'], r['team']): r for r in states['states']}
    assert all((r['market_id'], r['team']) in indexed for r in source_rows)
    table = []
    for row in source_rows:
        s = indexed[row['market_id'], row['team']]['formal2_initial_state']
        table.append(dict(market=row['market_id'], country=row['country'], team=row['team'],
            price=row['price'], demand=row['demand'], sales=row['sales'], rd=s['previous_rd'],
            operations=s['previous_operations'], cash=s['cash'], inventory=s['inventory'],
            long_debt=s['long_debt'], short_debt=s['short_debt'],
            context='市场5前景已核验' if row['context_verified'] else '前景未逐市场核验；机制拟合隔离',
            source=row['sources']['demand']))
    summaries = []
    for item in inventory:
        name = item['model']
        model = models.get(name, {})
        summaries.append(dict(model=name, status=item['status'], reason=item.get('reason'),
            frozen=metric_text(evaluation.get(name, evaluation.get(f"country/{model.get('country')}", {}) if model.get('market_id') == 5 else {})),
            training=metric_text(model.get('training_score', {})),
            parameter_change=model.get('parameter_change'),
            holdout={k: v for k, v in model.items() if 'holdout' in k and not isinstance(v, list)},
            market=model.get('market_id', 5 if name.startswith(('country/', 'parameter_priority/')) else None),
            country=model.get('country'), scope=model.get('scope', model.get('status', model.get('limit')))))
    ours = indexed[5, '营销团队']['formal2_initial_state']
    generated = datetime.now(timezone(timedelta(hours=8))).isoformat()
    payload = dict(generated_at=generated, rows=table, models=summaries, scenario=scenario,
                   user_delta=user_delta, ours=ours, states=states, current_inputs=current)
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = []
    for label, directory in [('sources', args.sources), ('training', args.training), ('scenario', args.scenario)]:
        target = args.out / label
        target.mkdir()
        for path in sorted(directory.glob('*.json')):
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            shutil.copy2(path, target / path.name)
            assert hashlib.sha256((target / path.name).read_bytes()).hexdigest() == sha
            manifest.append(dict(original=str(path.resolve()), copy=f'{label}/{path.name}', sha256=sha))
    for relative, expected_hash in training_checks['source_and_model_hashes_before_after_unchanged'].items():
        path = ROOT / relative
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert sha == expected_hash, f'Training input changed: {path}'
        target = args.out / 'supporting' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == sha
        manifest.append(dict(original=str(path), copy=target.relative_to(args.out).as_posix(), sha256=sha))
    write(args.out / 'formal2_initial_states.json', states)
    write(args.out / 'formal2_current_personal_inputs.json', current)
    write(args.out / 'report_data.json', payload)
    write(args.out / 'source_manifest.json', manifest)
    csv_fields = ['market', 'country', 'team', 'price', 'demand', 'sales', 'rd', 'operations',
                  'cash', 'inventory', 'long_debt', 'short_debt', 'context']
    with (args.out / 'actuals.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in csv_fields} for row in table)
    shutil.copy2(Path(__file__), args.out / Path(__file__).name)
    shutil.copy2(Path(__file__).with_name('formal_update_state.py'), args.out / 'formal_update_state.py')
    notes = ('正式1实际结果已更新全部10个市场、100队、200条国家需求记录。'
             '正式2起点来自正式1期末；需求标签来自实际结果，不使用预算。'
             '市场5正式1/2前景已核验，其余市场的可见前景未逐市场核验，拟合仅作为隔离研究。'
             '先评估旧冻结模型，再使用正式1数据重拟合；重拟合与内部留出误差不能代表正式2外部验证。'
             '正式2以后仅累计2至6五期利润；未来利润未知，不补零，不加终值，不强制还债或变现。'
             '税损余额、累积研发运营存量、未来订单条款未知，不能声称完整财务机制已核验或六回合最优。')
    fragment = (args.scenario / 'report_fragment.md').read_text(encoding='utf-8')
    fragment = fragment.replace('算术应为+150%，该矛盾保留', '相对算术为+150%，绝对增加0.9个百分点；显示约定尚未确认')
    fragment += '\n\n短贷溢价显示增幅另有用户解释：0.6%加0.9个百分点为1.5%；网页“+90%”的显示约定尚未确认。使用绝对费率列，不将其认定为绝对费率错误。'
    md = ['# 正式2数据与模型更新', generated, notes, '## 情境及时间变化', fragment,
          '## 营销团队正式2初始状态', '|字段|值|', '|---|---|']
    md += [f'|{k}|{display(v)}|' for k, v in ours.items()]
    md += ['## PYT正式2当前个人输入',
           f"按表头姓名实际定位第{current['personal_column']}列；与正式1期末状态分开保存。",
           '个人当前价格、营销、投资、运营、研发及贷款逐字段列在下表；需求与效率为本人预估。',
           f"预算利润{current['values']['budget_profit']:g}千美元不是实际结果，不参与真实标签训练；本次没有修改平台。", '|字段|值|', '|---|---|']
    md += [f'|{k}|{display(v)}|' for k, v in current['values'].items()]
    md += ['## 模型核验与更新', '|模型|状态|旧冻结误差|新模型样本内误差|', '|---|---|---|---|']
    md += [f"|{s['model']}|{s['status']}|{s['frozen']}|{s['training']}|" for s in summaries]
    md += ['## 全部市场正式1实际', '|市场|国家|团队|价格|需求|销量|研发|运营|现金|库存|', '|---|---|---|---|---|---|---|---|---|---|']
    md += ['|' + '|'.join(display(r[k]) for k in ['market', 'country', 'team', 'price', 'demand', 'sales', 'rd', 'operations', 'cash', 'inventory']) + '|' for r in table]
    md += ['## 来源与限度', '逐字段行号及哈希见formal2_initial_states.json；原件、训练与情境JSON独立复制至同目录子文件夹，source_manifest.json记录哈希。',
           '新正式起点入口：formal2_initial_states.json的states中按market_id与team选择formal2_initial_state；未知字段保留null，不能补零后调用旧财务模型。复现命令：python code/formal_update_state.py --sources <本次原件目录> --out <新的独立路径>/formal2_initial_states.json。',
           '旧历史证据曾有两份源文件覆盖缺口，见output/model_v2/20261011T211500_live_finance/source_integrity_incident.json；本次不以该缺口来源替代正式实际。',
           '个人决策与已执行小组结果分开：研发650、运营760为正式1已执行历史；本次没有修改或提交平台决策。']
    with (args.out / 'report.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(md).replace('\n## ', '\n\n## ') + '\n')
    readme = '''# 正式2独立报告包

打开report.html查看报告与市场/国家/模型筛选；导出按钮使用当前市场/国家筛选后的同一组实际行。
actuals.csv为完整200行正式1国家实际。数量单位千单位，金额千美元，价格美元/单位。

formal2_initial_states.json是新正式起点入口：按states[].market_id和team定位formal2_initial_state。
formal2_current_personal_inputs.json单独保存本人当前正式2输入与预算；预算和预估不作实际训练标签。
report_data.json保存HTML使用的数据；training/保存冻结核验及重训练参数；scenario/保存情境时间变化。
sources/与supporting/保存本次原件及训练支持原件，source_manifest.json记录原路径、复制路径及哈希。

在原工作区使用本次入口复现至新的独立输出目录：

```powershell
python code/formal_update_report.py --sources <本次原件目录> --training <训练目录> --scenario <情境目录> --out <新的报告目录>
python code/formal_update_state.py --sources <本次原件目录> --out <新的独立路径>/formal2_initial_states.json
```

输出目录与文件排他创建；保留旧报告。来源引用保留原工作区路径，跨目录搬移时按manifest恢复路径。
只累计正式2..6五期利润；未知不补零，不加终值，不自动清债或变现。
市场5前景已核验，其他市场机制拟合隔离；税损余额与累积技术存量仍未知。
冻结误差、样本内误差及内部留出分别展示，不能称为正式2未来验证。
本次没有修改平台决策。
'''
    with (args.out / 'README.md').open('x', encoding='utf-8') as stream:
        stream.write(readme)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>正式2数据与模型更新</title>
<style>body{margin:0;background:#f5f3ed;color:#202d35;font:15px/1.6 system-ui,sans-serif}main{max-width:1240px;margin:auto;padding:32px}h1{font-size:34px;margin:0}h2{margin-top:32px;font-size:23px}p{max-width:1000px}.tag{color:#12635c}.panel{background:white;border:1px solid #dcded5;padding:20px;margin:20px 0;border-radius:8px}.scroll{overflow:auto;max-height:560px}table{border-collapse:collapse;width:100%;white-space:nowrap;font-size:13px}th,td{text-align:left;padding:8px 11px;border-bottom:1px solid #e4e7e0}th{position:sticky;top:0;background:#e6eeea}select{font:inherit;padding:7px;border:1px solid #bdc6c1;border-radius:4px;margin:5px 18px 5px 5px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.note{border-left:4px solid #d59b38;padding-left:16px}label{display:inline-block}</style>
<main><p class="tag">CESIM · 正式回合2 · 起点与证据</p><h1>正式1结果，正式2起点</h1><p id="generated"></p><p>NOTES</p>
<section class="panel"><h2>先看情境与时间变化</h2><p>正式1的“将来”保留为历史前瞻，在正式2重新检查生效时间。需求增5–10%是今年预测；材料1053是当前表价，机器当前100。未来材料约增20%与机器可能最多降40%仍无确认生效回合。</p><p class="note">短贷增幅的网页显示约定尚未确认：用户解释为0.6%增加0.9个百分点至1.5%。本报告使用绝对费率列。</p><div class="scroll"><table id="events"></table></div><details><summary>情境原件与参数</summary><pre id="scenario"></pre></details></section>
<section class="panel"><h2>营销团队正式2起点</h2><p>市场5；正式1小组已执行研发650、运营760。个人下一回合决策不替代这两项实际历史。</p><div class="scroll"><table id="state"></table></div></section>
<section class="panel"><h2>PYT：正式2当前个人输入</h2><p id="personalColumn"></p><p class="note" id="personalBudget"></p><div class="scroll"><table id="current"></table></div><a href="formal2_current_personal_inputs.json">本人输入与逐字段来源</a></section>
<section class="panel"><h2>全部市场的正式1实际数据</h2><p>数量：千单位；金额：千美元；价格：美元/单位。点击筛选可查看市场与国家。</p><label>市场<select id="market"></select></label><label>国家<select id="country"></select></label><span id="count"></span> <button id="exportCsv" type="button">导出当前筛选 CSV</button> · <a href="actuals.csv" download>完整实际CSV</a><div class="scroll"><table id="actual"></table></div></section>
<section class="panel"><h2>旧冻结核验与模型更新</h2><p>份额误差为百分点，绝对需求误差为千单位，风险溢价误差为基点。已实现对手决策的条件份额检验，与事前需求场景评分分别保存。新模型样本内误差和内部留出不能代表正式2未来准确度。</p><label>模型<select id="model"></select></label><div class="scroll"><table id="models"></table></div><details><summary>模型参数变化与内部留出</summary><pre id="modelDetail"></pre></details></section>
<section class="panel"><h2>来源与可识别边界</h2><p>期末库存、债务、资产、应收应付、税损、研发运营状态及订单保留；无法确认的值显示“未知”。正式2至6五期利润路径尚未观察，剩余利润为空。</p><p>新正式入口为formal2_initial_states.json：在states中按market_id及team读取formal2_initial_state。未知字段为null，不能补零后调用旧财务模型。可用formal_update_state.py从本次原件重新生成至新独立路径。</p><p>所有本次原件、训练和情境数据保存在此报告目录。两份旧历史源曾覆盖，保留既有缺口说明；新结果不冒充旧来源。本次没有修改或提交平台决策。</p><a href="report.md">Markdown报告</a> · <a href="formal2_initial_states.json">100队正式2起点</a> · <a href="source_manifest.json">来源哈希</a> · <a href="training/prospective_scenarios_evaluation.json">事前冻结场景核验</a> · <a href="training/models.json">完整模型</a> · <a href="report_data.json">报告数据</a></section></main>
<script type="application/json" id="data">DATA</script><script>
const d=JSON.parse(document.getElementById('data').textContent), by=id=>document.getElementById(id);
const text=v=>v==null?'未知':typeof v==='object'?JSON.stringify(v):String(v);
function table(id,headers,rows){const el=by(id);el.replaceChildren();let tr=document.createElement('tr');headers.forEach(v=>{let th=document.createElement('th');th.textContent=v;tr.append(th)});let head=document.createElement('thead');head.append(tr);el.append(head);let body=document.createElement('tbody');rows.forEach(row=>{let r=document.createElement('tr');row.forEach(v=>{let c=document.createElement('td');c.textContent=text(v);r.append(c)});body.append(r)});el.append(body)}
function options(id,values){let all=document.createElement('option');all.value='';all.textContent='全部';by(id).append(all);values.forEach(v=>{let o=document.createElement('option');o.value=v;o.textContent=v;by(id).append(o)})}
options('market',[...new Set(d.rows.map(r=>r.market))].sort((a,b)=>a-b));options('country',[...new Set(d.rows.map(r=>r.country))]);options('model',d.models.map(r=>r.model));
const actualKeys=['market','country','team','price','demand','sales','rd','operations','cash','inventory','long_debt','short_debt','context'];
const filteredRows=()=>d.rows.filter(r=>(!by('market').value||r.market==by('market').value)&&(!by('country').value||r.country===by('country').value));
function render(){const rows=filteredRows();by('count').textContent=rows.length+' 条';table('actual',['市场','国家','团队','价格','需求','销量','研发','运营','现金','库存','长债','短债','情境'],rows.map(r=>actualKeys.map(k=>r[k])));const ms=d.models.filter(r=>!by('model').value||r.model===by('model').value);table('models',['模型','状态','旧冻结误差','新样本内误差','适用范围'],ms.map(r=>[r.model,r.status,r.frozen,r.training,r.scope||r.reason]));by('modelDetail').textContent=JSON.stringify(ms,null,2)}
by('exportCsv').addEventListener('click',()=>{const cell=v=>'"'+text(v).replace(/"/g,'""')+'"';const csv=[actualKeys,...filteredRows().map(r=>actualKeys.map(k=>r[k]))].map(r=>r.map(cell).join(',')).join('\\r\\n');const url=URL.createObjectURL(new Blob(['\\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='formal1_filtered_actuals.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
['market','country','model'].forEach(id=>by(id).addEventListener('change',render));by('generated').textContent=d.generated_at+' · 10市场 / 100队 / 200条国家需求';table('state',['字段','值'],Object.entries(d.ours));table('events',['主题','来源回合','时间锚','生效回合','状态','叙述或跟进'],d.scenario.events.map(r=>[r.topic,r.source_round,r.time_anchor,r.effective_round,r.status,r.statement||r.followup||r.conflict||r]));by('scenario').textContent=JSON.stringify(d.scenario,null,2);render();
by('personalColumn').textContent='按表头实际定位本人第'+d.current_inputs.personal_column+'列，与正式1期末起点分开。';table('current',['个人输入字段','当前值'],Object.entries(d.current_inputs.values));
const cv=d.current_inputs.values;by('personalBudget').textContent='预算利润'+cv.budget_profit+'千美元为当前预算，需求'+cv.demand_estimate_thailand+'/'+cv.demand_estimate_indonesia+'与效率'+cv.efficiency_estimate+'为本人预估。它们均不是正式实际标签。本次未修改平台决策。';
</script></html>'''.replace('NOTES', html.escape(notes)).replace('DATA', encoded)
    assert '<script type="application/json" id="data">' in page and '\\u003c' not in notes
    with (args.out / 'report.html').open('x', encoding='utf-8') as stream:
        stream.write(page)
    write(args.out / 'checks.json', dict(markets=10, teams=100, demand_rows=200,
        actual_formal1_only=True, new_state_used=True, sources_copied_with_hash_verification=True,
        remaining_rounds=[2, 3, 4, 5, 6], remaining_profit=None,
        unknown_not_zero=True, no_old_report_import=True,
        personal_column_from_header=current['personal_column'], personal_budget_not_actual_label=True))
    print('REPORT', args.out.resolve())


if __name__ == '__main__':
    main()
