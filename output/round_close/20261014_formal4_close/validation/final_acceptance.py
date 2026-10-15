"""Unified, source-hashed acceptance; never changes raw captures or model state."""
import json
import os
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
import validate_market as v

BASE=Path(__file__).parent
ROOT=v.ROOT

def main():
    out=BASE.parent/'final_validation'
    out.mkdir(parents=True,exist_ok=False)
    artifacts=[];sources={};fields=[];charts=[];counts=Counter();extra=[]
    def add_source(ref):
        path=ROOT/ref['source'];assert v.rules.sha(path)==ref['sha256'],ref
        sources[ref['source']]=ref
    def artifact(path):
        ref=v.reference(path);artifacts.append(ref);return ref
    markets=[]
    for m in range(1,11):
        run=sorted((BASE/f'market{m}').glob('*/validation.json'))[-1].parent
        doc=v.read(run/'validation.json')
        assert doc['all_field_coverage_verified'] and doc['sequence_status_counts']=={'web_original_json':28}
        assert doc['financial_numerical_counts']=={'pass':190} and doc['cumulative_numerical_counts']=={'pass':10}
        assert not doc['chart_parse_errors']
        for ref in doc['sources']:add_source(ref)
        supplements=v.read(run/'supplemental_sources.json')
        assert len(supplements)==12 and all(x['valid'] for x in supplements)
        for ref in supplements:
            add_source({k:ref[k] for k in ('source','sha256')})
            extra.extend(dict(market=m,source=ref['source'],**x) for x in ref.get('reviewed_extra_columns',[]))
        coverage=v.read(run/'field_gaps.json');assert len(coverage)==200
        assert all(len(x['formal4_values'])==10 for x in coverage)
        fields.extend(coverage)
        sequences=v.read(run/'sequence_coverage.json')
        svgpath=sorted((BASE/f'market{m}').glob('*_svg/json_svg_pairing.json'))[-1]
        svg=v.read(svgpath);assert len(svg)==28 and all(x['status']=='pass' for x in svg)
        assert {x['chart_id'] for x in svg}=={x['chart_id'] for x in sequences}
        for chart in sequences:
            pair=next(x for x in svg if x['chart_id']==chart['chart_id'])
            assert pair['source']==chart['source'];add_source(pair['source'])
            chart['svg_pairing_status']='pass';chart['svg_pairing_reference']=v.reference(svgpath)
            charts.append(chart)
        counts.update(financial=190,cumulative=10,print_web=doc['print_web_comparison_counts'].get('pass',0),svg_point_checks=sum(len(x['point_checks']) for x in svg))
        assert not doc['print_web_comparison_counts'].get('fail')
        for item in v.read(run/'cumulative_checks.json'):
            add_source({k:item['prior'][k] for k in ('source','sha256')})
        for name in ('validation','financial_checks','cumulative_checks','field_gaps','sequence_coverage','print_web_comparisons','supplemental_sources','html_table_checks'):
            artifact(run/f'{name}.json')
        artifact(svgpath)
        markets.append(dict(market=m,validation=v.reference(run/'validation.json'),svg=v.reference(svgpath)))
    merged=sorted((BASE/'merged').glob('*/validation.json'))[-1].parent
    calc=v.read(merged/'validation.json')
    assert calc['calculated_count']==700 and calc['input_checks']=={'pass':5700} and calc['direct_calculated_checks']=={'pass':600}
    merged_fields=v.read(merged/'field_coverage.json');assert len(merged_fields)==2000
    assert all(x['formal4_status'] in ('print_direct_verified','web_supplement_direct_verified') for x in merged_fields)
    for ref in (calc['calculated_index_source'],calc['calculated_value_source']):add_source(ref)
    for name in ('validation','field_coverage','direct_calculated_checks','input_checks'):artifact(merged/f'{name}.json')
    # Every accepted current page must carry complete HTML and matching market/round selector evidence.
    raw_pages=[x for x in sources.values() if '/raw/' in x['source'] and 'formal4' in x['source']]
    assert len(raw_pages)==140
    for ref in raw_pages:
        doc=v.read(ROOT/ref['source']);assert v.formal.full_html(doc['html'],doc.get('html_length'))
    rejected=[]
    for path in sorted((BASE.parent/'raw').glob('*.json')):
        if path.relative_to(ROOT).as_posix() in sources:continue
        doc=v.read(path)
        rejected.append(dict(**v.reference(path),retained_reason='recovery_helper_or_superseded_capture',html_complete=v.formal.full_html(doc.get('html',''),doc.get('html_length')) if isinstance(doc,dict) else False))
    result=dict(status='FORMAL4_ARCHIVE_ACCEPTED',round=4,markets=markets,field_rows=2000,team_field_values=20000,
        original_json_charts=280,json_svg_pairings=280,checks=dict(counts),calculated_values=700,calculated_input_checks=5700,
        direct_calculated_checks=600,accepted_current_pages=140,print_pages=10,web_pages=130,
        fixed_15_panel_coverage_claimed=False,duplicate_representations_are_independent_samples=False,
        complete_round_archive=True,sources=list(sources.values()),artifacts=artifacts,retained_other_raw=rejected,
        reviewed_extra_columns=extra,model_retrained=False,readme_modified=False,
        limitations=['SVG validates rendered positions with chart-specific pixel tolerances; JSON remains the original precision source.',
                     'Print/table values are displayed precision; calculated values retain propagated display intervals.',
                     'No scoring, parameter update, or retraining performed.'])
    def write(name,obj):
        text=json.dumps(obj,ensure_ascii=False,indent=2);text=v.rules.redact_names(text)
        (out/name).write_text(text,encoding='utf-8')
    write('acceptance_index.json',result);write('field_coverage.json',merged_fields);write('sequence_coverage.json',charts)
    def link(path,label):return f'[{label}]({Path(os.path.relpath(path,out)).as_posix()})'
    report='# 正式4归档验收\n\n市场 1–10 正式回合 4 全部通过。实际采集 10 份打印、130 份网页（每市场概要和 12 个补采页），共 140 份有效原件。未将打印虚算为固定 15 栏页面。\n\n'
    report+='200 个字段 × 10 市场（20,000 个团队值）、28 图 × 10 市场的原精度 JSON 及同点 SVG 渲染配对全部覆盖。打印与网页交叉一致；1,900 个财务等式和 100 个正式3→4累计衔接通过。\n\n'
    report+='合并 700 个计算值及索引；5,700 条原件输入和 600 条直接显示值对照通过。计算来源、公式、显示误差区间与直接值同时保留，人员净变化不替代招聘或裁员。\n\n'
    report+='市场 1、4 排放表各一个总计行附有两个无队名的 0.0 列，原件及全部 13 单元格保留；仅映射 10 个具名团队列，并逐队核对运输分项和总计。打印 DOM 426 行中 173 行为空，实质字段布局为既有 253 行。截断旧件和恢复辅助片保留，不计有效页。\n\n'
    report+='SVG 折线点容差 1e-4 像素，饼图份额容差 1e-8 百分点，柱形容差 1.5 像素并核对符号和团队槽位；JSON 为原精度数值主来源。显式零与 NaN 区分，重复表示不增加独立样本。\n\n'
    report+='所有引用源 SHA256 已重验，输出姓名使用首字母。未评分、更新参数或重训。\n\n'
    report+=link(out/'acceptance_index.json','完整验收索引与源哈希')+'；'+link(out/'field_coverage.json','2000 字段及计算值合并')+'；'+link(out/'sequence_coverage.json','280 图及配对引用')+'。\n\n'
    report+='逐市场核验：\n\n'+''.join(f'- 市场 {r["market"]}：'+link(ROOT/r['validation']['source'],'字段与财务')+'；'+link(ROOT/r['svg']['source'],'JSON/SVG 点对点')+'。\n' for r in markets)
    report=v.rules.redact_names(report);(out/'report.md').write_text(report,encoding='utf-8')
    import re
    for target in re.findall(r'\]\(([^)]+)\)',report):assert (out/target).resolve().is_file(),target
    assert v.rules.redact_names(report)==report
    print(json.dumps(dict(output=str(out),status=result['status'],checks=dict(counts),pages=140,fields=2000,charts=280),ensure_ascii=False))

if __name__=='__main__':main()
