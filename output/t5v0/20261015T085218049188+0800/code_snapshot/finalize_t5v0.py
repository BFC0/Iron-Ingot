"""Append final t5v0 evidence, plots and backed-up documentation updates."""
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'code')]
sys.dont_write_bytecode=True
import t5v0 as t
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics import renderSVG
from reportlab.lib.colors import HexColor


def main(out):
    nd=t.nd; model=nd.read(out/'models_full.json');check=nd.read(out/'checks.json')
    assert nd.read(out/'verification.json')['status']=='PASS_WITH_EXPLICIT_TRAINING_GAPS'
    assert not (out/'manifest_final.json').exists()
    added_inputs={}
    initial=t.CURVES.parents[1]/'verification/20261014T002441'
    refs=nd.read(initial/'sources.json')
    for ref in refs:
        source=t.prior.CLOSE/ref['path']
        assert nd.sha(source)==ref['sha256']
        added_inputs[source.relative_to(ROOT).as_posix()]=ref['sha256']
    for path in [initial/'known_conditions.json',initial/'carryover_comparison.json',initial/'acceptance.json',
        t.CURVES.parents[1]/'carryover_classification/20261014T005023/carryover_classified.json',
        t.DEC/'actual_crosschecks.json']:
        added_inputs[path.relative_to(ROOT).as_posix()]=nd.sha(path)
        shutil.copy2(path,out/('initial_'+path.name if 'initial' in str(path) else path.name))
    cross=nd.read(t.DEC/'actual_crosschecks.json')
    assert len(cross)==21 and all(r['passed'] for r in cross)
    plot_dir=out/'figures';plot_dir.mkdir()
    for i,(key,c) in enumerate(model['curves'].items(),1):
        d=Drawing(760,300);d.add(String(65,278,'Formal4 '+key+' - visible effective-input curve',fontSize=13))
        p=LinePlot();p.x=65;p.y=50;p.width=620;p.height=200
        pts=c['points'];pred=[(x,float(t.prior.curve_value(x,c['parameters'],c['form']))) for x,y in pts]
        p.data=[pts,pred];p.lines[0].strokeColor=HexColor('#167786');p.lines[1].strokeColor=HexColor('#ce623a')
        p.lines[0].strokeWidth=2;p.lines[1].strokeWidth=1;p.lines[1].strokeDashArray=[4,3]
        p.xValueAxis.valueMin=0;p.xValueAxis.valueMax=c['x_range'][1]
        p.yValueAxis.valueMin=0;p.yValueAxis.valueMax=max(y for x,y in pts)*1.08
        d.add(p);d.add(String(280,15,'Effective input (k USD), rounded labels',fontSize=10))
        d.add(String(65,263,'Teal: original JSON; orange dashed: fitted multiplier. 200 points; not business validation.',fontSize=9))
        renderSVG.drawToFile(d,str(plot_dir/f'formal4_curve_{i}.svg'))
    issues=[
        ('1','需求系数与正则','暂停','竞争队最终输入缺失，不能选参','补99队最终输入后做训练内选参与嵌套留出'),
        ('2','损失尺度统一','沿用未新验证','需求未重训，不新增尺度等价结论','补输入后核验加权尺度'),
        ('3','极端价格影响','未新验证','本组售价不足以识别价格函数','补同竞争集合售价及投入'),
        ('4','共变及内生性','未解决','费用/投入关联不是因果收益','补独立变化及完整决策'),
        ('5','国别产品投入','部分','本组29项最终决策有效，99隊缺失','补采核验其他队国别产品最终决策'),
        ('6','零需求与损失形式','暂停','未用零销量替代需求，需求拟合暂停','补决策后保留真实零需求检验'),
        ('7','行业总量机制','部分','40组实际总量及增长已核，非预测训练','补独立行业机制及时间外标签'),
        ('8','条件回溯与事前验证','部分','候选未采用，事前评分0；新误差仅条件回溯','需匹配生效方案的结算前冻结预测'),
        ('9','投入延续及完整存量','不可识别','本组效率每个rho有对应theta','补历史最终投入及有效横轴映射'),
        ('10','曲线及市场适用','部分','市场5正式4三曲线600点已重拟合','补其他市场同回合曲线或共享规则'),
        ('11','研发有效横轴外推','部分','曲线保存范围，自动支出映射未知','补有效投入原横坐标及机制'),
        ('12','效率与低投入范围','不可识别','仅本组最终投入可用于效率校准','补多个独立最终投入及效率样本'),
        ('13','风险利率及稳定性','部分','92状态重拟合，保存10市场折参数范围','补事前计息状态与独立后续结果'),
        ('14','当期给定常数','部分','正式4公布参数归档、5%基准单独匹配','补实际生效时点及跨市场同值依据'),
        ('15','材料差额及舍入','部分','100/89样本及嵌套市场留出保存','残差不宣称机制已识别；补采购精度'),
        ('16','完整财务预测','未解决','1900财务等式是源结果验收','需期初/决策到财务独立前向复算'),
        ('17','库存订单投资时序','未解决','规则自检、容量上界不等于生命周期训练','补合同交付预收/余款及真实投资时点'),
        ('18','剩余回合收益','暂停','完整正式5/6状态链缺失','补链后再比较5至6新增收益'),
        ('19','压力与保证','未验证','本任务未优化收益，不报告盈利保证','完整预测链后核边界组合压力'),
        ('20','版本与输入混用','本次检查通过','正式4专属数据、哈希及决策来源验证','后续保留独立来源、回合和截止点')]
    records=[dict(id=i,topic=a,status=b,impact=c,next_evidence=e,evidence='checks.json; verification.json; models_full.json; data_gaps.json') for i,a,b,c,e in issues]
    nd.save(out/'problem_status_20.json',records)
    nd.csv_write(out/'problem_status_20.csv',records)
    text=(out/'report.md').read_text(encoding='utf-8').replace('环境恒等式1000项','生产环境600项及物流恒等式400项')
    text += '\n## 初值边界与追加核验\n\n正式4已知参数、九子页初值证据及结转分类另存 initial_*.json。只有直接披露的期初量标为期初；上年参考不改称期初现金或完整存量。本组21项实际交叉核验通过。\n\n'
    text += '材料模型嵌套整市场留出重新在各训练折选型，明细位于注册表 materials.*.nested_market_validation；风险留出参数范围记录为敏感性，不是置信区间。\n\n'
    text += '| 产品 | 材料嵌套留出MAE，千美元 | 工资整市场MAE，千美元 |\n|---|---:|---:|\n'
    for product,m in model['materials'].items():
        values=[f['evaluation']['mae_kusd'] for f in m['nested_market_validation']]
        wage=[f['mae_kusd'] for f in model['labor'][product]['holdouts']]
        text+=f'| {product} | {sum(values)/len(values):.6g} | {sum(wage)/len(wage):.6g} |\n'
    text+='\n## 独立曲线图\n\n'
    for i,key in enumerate(model['curves'],1):
        text+=f'![正式4 {key} 原点与拟合](figures/formal4_curve_{i}.svg)\n\n'
    text+='## 20项问题的本次状态\n\n| 编号 | 问题 | 状态 | 影响与证据 | 下一项所需证据/处理 |\n|---|---|---|---|---|\n'
    text+='\n'.join(f'| {i} | {a} | {b} | {c} | {e} |' for i,a,b,c,e in issues)+'\n'
    (out/'report_final.md').write_text(text,encoding='utf-8')
    rel=out.relative_to(ROOT).as_posix()
    report=f'[{"t5v0正式4训练与缺口"}]({rel}/report_final.md)'
    params=f'[t5v0注册表]({rel}/models_full.json)'
    inventory=f'[29类状态]({rel}/model_inventory_final.json)'
    summary='正式4：100队初终值；3曲线600点；材料/工资100与89条、风险92条重拟合。竞争队最终决策缺失，需求暂停；效率rho不可识别，未部署。'
    changes={}
    root=ROOT/'README.md';s=root.read_text(encoding='utf-8')
    s=s.replace('更新：2026-10-14（北京时间）。正式4已结算','更新：2026-10-15（北京时间）。正式4已结算',1)
    s=s.replace('| 最新实际训练 | **t4v1**：',f'| 最新实际训练（有缺口） | **t5v0**：{report}、{params}、{inventory} | {summary} |\n| 正式3需求训练基线 | **t4v1**：',1)
    s=s.replace('当前仍使用正式3训练版本，未因采集正式4结果而自动重训','t5v0已完成可估计项重训及29类状态核验；需求缺竞争队最终决策仍暂停，正式3需求基线保留',1)
    changes[root]=s
    for name in ['训练拟合模型与版本清单.md','训练拟合模型与版本清单_文字说明版.md']:
        path=ROOT/name;s=path.read_text(encoding='utf-8')
        s=s.replace('| 实际训练 |',f'| 正式4最新实际训练（有缺口） | {report}、{params}、{inventory} | {summary} |\n| 正式3实际训练 |',1)
        changes[path]=s
    path=ROOT/'模型版本重新统计.md';s=path.read_text(encoding='utf-8')
    s=s.replace('| 最新实际训练 |',f'| 最新实际训练（有缺口） | {report} | {summary} |\n| 正式3需求训练基线 |',1)
    changes[path]=s
    path=ROOT/'预测模型与训练参数汇总.md';s=path.read_text(encoding='utf-8')
    s=s.replace('## 相关版本归档',f'## 正式4 t5v0 参数及训练边界\n\n{report}；{params}；{inventory}。{summary} 利率参数由interest.parameters_source引用risk，避免重复登记；工资是条件回溯参数，不替代官方班次参数。旧版本参数保持各自范围。\n\n## 相关版本归档',1)
    changes[path]=s
    path=ROOT/'模型说明/README.md';s=path.read_text(encoding='utf-8')
    s=s.replace('## 当前模型和应用入口\n','## 当前模型和应用入口\n\n[t5v0正式4训练与缺口](T5V0_正式4训练与缺口.md)维护最新可估计模型及29类状态；需求缺99队最终决策而暂停，旧需求基线独立保留。\n',1)
    s=s.replace('当前参数查阅使用[去重29类注册表]','正式3参数查阅使用[去重29类注册表]',1)
    changes[path]=s
    path=ROOT/'code/model_v2/README.md';s=path.read_text(encoding='utf-8')
    s=s.replace('## 入口与输出','## 正式4 t5v0\n\n[t5v0运行说明](t5v0_README.md)；正式4可估计项训练，缺竞争队最终决策的需求项暂停，未部署。\n\n## 入口与输出',1)
    changes[path]=s
    path=ROOT/'code/model_v2/t5v0_README.md'
    changes[path]=f'# t5v0 正式4训练\n\n'+summary+f'\n\n[报告](../../{rel}/report_final.md)；[注册表](../../{rel}/models_full.json)；[验收](../../{rel}/verification.json)。\n\n运行：`python code/model_v2/t5v0.py`；来源自检：加`--self-check`。每次独立输出，保留旧版本。使用项目已安装的NumPy/SciPy运行环境。\n\n验证：`python code/model_v2/verify_t5v0.py <运行目录>`。训练入口产物report.md为阶段报告；`python work/finalize_t5v0.py <运行目录>`补初值证据、图表和入口，权威报告为report_final.md。\n\n决策仅接受正式4实际采集的小组最终列；个人草稿、玩家预估、预算及实际费用代理不得作为决策输入。市场5曲线跨市场共享未证实，条件费用误差不等于事前经营误差。\n'
    path=ROOT/'模型说明/T5V0_正式4训练与缺口.md'
    changes[path]=f'# t5v0 正式4训练与缺口\n\n'+summary+f'\n\n[报告](../{rel}/report_final.md)、[参数](../{rel}/models_full.json)、[全部状态](../{rel}/model_inventory_final.json)、[验收](../{rel}/verification.json)。\n\n本组29项最终决策已核，13项玩家预估排除；其他99队最终投入缺失。需求ABS/SHARE/COUNTRY、A/D及HORIZON暂停；EFF仅单公司多rho校准，不选择rho。确定规则逐项核验，不称全部监督训练通过。\n\n先核冻结方案：实际方案未采用候选，模型事前评分0。正式3期末作为结转参考，未披露期初现金/税亏保持未知。风险与材料/工资使用真实期末状态/产量，仅条件模型。旧t4v1需求及历史结果保留，不能混入t5v0注册表。\n'
    backups=out/'entry_backups';doc_hashes=[]
    for path,new in changes.items():
        relative=path.relative_to(ROOT);before=None
        if path.exists():
            before=nd.sha(path);backup=backups/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
        path.write_text(new,encoding='utf-8')
        assert path.read_text(encoding='utf-8')==new
        doc_hashes.append(dict(path=relative.as_posix(),before=before,after=nd.sha(path)))
    # Check all new version links; preserve unrelated historical links as-is.
    link_checks=[]
    for path,text in changes.items():
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if 't5v0' not in target and 'T5V0' not in target:
                continue
            dest=path.parent/target.split('#')[0];assert dest.is_file(),dest
            link_checks.append(dict(document=path.relative_to(ROOT).as_posix(),target=target,exists=True))
    nd.save(out/'documentation_changes.json',dict(files=doc_hashes,new_version_links=link_checks))
    for script in [Path(__file__),ROOT/'code/model_v2/verify_t5v0.py']:
        shutil.copy2(script,out/'code_snapshot'/script.name)
        added_inputs[script.relative_to(ROOT).as_posix()]=nd.sha(script)
    with (out/'work_log.md').open('a',encoding='utf-8') as f:
        f.write('\n'+datetime.now(nd.TZ).isoformat()+f' 最终交付：补期初核验原件引用、21项实际交叉核验、三张SVG、20项问题状态；备份并更新{len(changes)}个文档，保存改前改后哈希，新版本链接全部通过。调度任务已处于PAUSED。\n')
    manifest=nd.read(out/'manifest.json');protected=dict(manifest['input_hashes'],**added_inputs)
    assert all(nd.sha(ROOT/p)==h for p,h in protected.items())
    nd.save(out/'manifest_final.json',dict(version='t5v0',training_round=4,status='PARTIAL_TRAINING_WITH_EXPLICIT_DATA_GAPS',
        input_hashes=protected,output_hashes={p.relative_to(out).as_posix():nd.sha(p) for p in out.rglob('*') if p.is_file()},
        complete_all_models_trained=False,canonical_report='report_final.md',canonical_models='models_full.json'))
    print(json.dumps(dict(out=str(out),documents=len(changes),new_links=len(link_checks),route_checks=check['route_checks'],plots=3),ensure_ascii=False))


if __name__=='__main__':
    main(Path(sys.argv[1]))
