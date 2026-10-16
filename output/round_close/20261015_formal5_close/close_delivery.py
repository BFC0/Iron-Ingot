"""Record final hashes, preserve the current README, and verify delivery links."""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,text):
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():return  # Resume preserves artifacts created before a failed README update.
    with p.open('x',encoding='utf-8') as stream:
        stream.write(text if isinstance(text,str) else json.dumps(text,ensure_ascii=False,indent=2))


def main():
    now=datetime.now(timezone(timedelta(hours=8))).isoformat()
    index=read(BASE/'final_validation/acceptance_index.json')
    initial=read(BASE/'formal6_initial/acceptance.json')
    assert index['status']=='FORMAL5_ARCHIVE_ACCEPTED'
    assert initial['curve_points']==600 and initial['draft_fields_per_column']==56
    for ref in index['sources']:
        assert sha(ROOT/ref['source'])==ref['sha256']
    sources=[]
    for p in sorted(BASE.glob('*.json')):
        d=read(p)
        if not isinstance(d,dict) or 'captured_at' not in d:continue
        h=''.join(d['html_parts']) if d.get('html_parts') else d.get('html','')
        complete=h.rstrip().endswith('</html>') and (not d.get('html_length') or len(h.encode('utf-16-le'))//2==d['html_length']) and '[Truncated]' not in h
        sources.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),captured_at=d['captured_at'],
            html_complete=complete,retained=True,share_allowed=False,
            note='原始页面可能含姓名；完整性不自动等于字段、身份和图表全部验收。'))
    write(BASE/'source_manifest.json',dict(generated_at=now,original_captures=sources,
        accepted_current_result_pages=140,accepted_result_index='final_validation/acceptance_index.json',
        normalized_copies='raw/ files preserve HTML and table values; selector label aliases only.',
        selection_incident='市场4补采返回市场5，保存前拒绝；用户确认停止其他操作后独占重采。',
        recoveries=['首次长字符串截断，另存分块完整件','市场2概要加载不完整，另存完整件','市场1单图SVG横向槽未通过，定点重读后通过'],
        no_training=True,no_platform_input_changes=True,no_group_submission=True))
    write(BASE/'calculated/report.md','# 正式5打印缺项计算\n\n700项计算值，5700个输入与原件哈希通过；其中600项与网页直接值的显示精度区间相容。直接值保留，不重复计为独立样本。\n\n'
          '| 指标（均为计算值） | 公式 | 单位与条件 |\n| --- | --- | --- |\n'
          '| 产品跨国需求 | 泰国需求＋印尼需求 | 同产品，千单位 |\n'
          '| 产品整体销量份额 | 100×本队两国销量／全部十队两国销量 | %，零售范围 |\n'
          '| 总流动资产 | 成品库存账面价值＋应收账款＋现金 | 千美元 |\n'
          '| 人均生产工资 | 泰国工资合计／两产品生产人员合计 | 千美元/人 |\n'
          '| 人员净变化 | 正式5人员－正式4人员 | 人，不代表招聘或裁员 |\n\n'
          '输入按原始显示位数保存；求和与差值传播半步误差，比值使用分子分母区间端点。半步区间依赖近似最近舍入假设，未恢复平台内部精度。销量总计和净现金已有直接值，保留并仅作核对。\n\n'
          '[计算值与全部输入](20261015T230536498982+0800/calculated_values.json) · [索引](20261015T230536498982+0800/calculated_index.json) · [验收](20261015T230536498982+0800/acceptance.json)\n')
    comparison=read(BASE/'decision_history/candidate_comparison.json')
    precise=[]
    for row in comparison['fields']:
        if row['plan']=='中性联合候选' and not row['matched']:
            field=next(r for r in read(BASE/'decision_history/group_final_42.json') if r['key']==row['key'])
            half=.5*10**(-len(field['source']['display'].replace(' ','').split('.')[1])) if '.' in field['source']['display'] else .5
            precise.append(dict(**row,compatible_with_list_display_rounding=abs(row['final']-row['frozen_suggested'])<=half))
    write(BASE/'decision_history/display_precision_addendum.json',precise)
    report='# 正式5结束后数据采集\n\n已完成10市场正式5实际结果、本组历史最终决策及正式6初始资料采集与验收。未修改决策输入或提交小组方案，未重训。姓名统一使用首字母。\n\n'
    report+='| 范围 | 完成结果 |\n| --- | --- |\n'
    report+='| 正式5实际 | 10市场100队；10打印＋130所需网页；2000字段行、20000团队值；280图JSON/SVG配对通过 |\n'
    report+='| 数值核验 | 1900财务等式、100累计衔接、10910打印/网页对照通过；700计算值含公式与舍入区间 |\n'
    report+='| 本组历史最终方案 | 42项（29决策、13玩家预估）；168项个人输入及10项预算摘要分开保存 |\n'
    report+='| 正式6初始 | 14完整原件、56字段×5列、48公布参数、五部分前景、3条曲线600点；三次草稿回读稳定 |\n'
    report+='| 状态结转 | 20项中两项库存和长期贷款参考匹配，两项机器产能条件相容；15项缺独立期初核验 |\n\n'
    report+='本组回合5实际：营业收入40305、利润−919、累计收益6183、期末现金10703、长期贷款7600千美元；复合梁期末库存0、连接件6.02千单位。数据来自本组正式5结果，预算利润4082千美元另行标记，不能代替实际。\n\n'
    report+='与t5v2中性联合候选严格匹配39/42字段，两项效率差异与列表显示舍入相容；连接件泰国设计师营销为422，候选442千美元。稳健候选匹配23/42。两套完整方案均不与最终值完全一致，不直接把其整套预测当成实际方案事前成绩；玩家需求预估误差已单列。本次未评分其他冻结版本、未做完整偏差归因或模型更新。\n\n'
    report+='正式6截止2026-10-16 22:00（北京时间），新增菲律宾市场及印尼机器投资字段。新曲线上期实际研发2600/231、运营754千美元已与回合5最终小组列配对。第6回合为本项目终局，平台第7回合提示保留原文，不创建第7回合预测。\n\n'
    report+='[实际结果验收](final_validation/report.md) · [计算公式与来源](calculated/report.md) · [历史最终决策](decision_history/report.md) · [正式6前景、曲线及状态](formal6_initial/report.md) · [原始采集清单](source_manifest.json)\n\n'
    report+='采集恢复记录：长HTML截断件排除验收；市场2未加载完整概要另存完整件；市场4跨标签共享选择错配在保存前拒绝，用户确认独占后重采；市场1单图初次横向配对失败，重读后通过。原件与旧失败记录均保留，不能整包分享原始目录。快速教程、正式5已核前景与曲线复用既有归档。\n'
    write(BASE/'overall_report.md',report)
    readme=ROOT/'README.md'
    before=readme.read_bytes()
    write(BASE/'document_backup/README_before.md',before.decode('utf-8'))
    text=before.decode('utf-8').replace('\r\n','\n')
    first=text.split('\n\n')[1]
    newfirst='更新：2026-10-15（北京时间）。正式5已结算，10市场100队结果归档通过；当前开放正式6，截止2026-10-16 22:00。已保存正式5本组最终42项字段、正式6的56项当前字段与48项公布参数、五部分前景及600点曲线，尚有15项状态缺独立期初核验。[本次采集总览](output/round_close/20261015_formal5_close/overall_report.md)。本文集中维护当前状态、版本入口、问题和下一步；操作平台前仍须重新确认实时回合与本人输入。'
    text=text.replace(first,newfirst,1)
    anchor='| 正式5已知条件与当前基准 |'
    additions='| 正式5实际及最终小组方案 | 10市场、100队，10打印＋130网页；2000字段行、280图配对、1900财务等式、100累计衔接通过 | [正式5验收](output/round_close/20261015_formal5_close/final_validation/report.md)；[最终42项及候选配对](output/round_close/20261015_formal5_close/decision_history/report.md)。本组利润−919、累计6183千美元；中性候选营销有改动，整套预测不直接计为实际方案成绩 |\n'
    additions+='| 正式6已知条件及当前草稿 | 14份原件、56字段×5列、48公布参数、五部分前景、3曲线600点配对；截止2026-10-16 22:00 | [正式6初值](output/round_close/20261015_formal5_close/formal6_initial/report.md)；新增菲律宾市场及印尼机器投资；上期研发2600/231、运营754已配对，15项期初状态仍未知，当前草稿不是最终方案 |\n'
    assert text.count(anchor)==1
    text=text.replace(anchor,additions+'| 正式5已知条件与历史基准 |',1)
    text=text.replace('正式5最新决策分析：','正式5历史决策分析：',1)
    old='| 3 | 正式5至6完整经营收益链 | 正式5前景及曲线已归档；正式6条件、完整状态结转及独立实际验证不足。接通需求→效率→生产→财务→下一期状态后再比较5至6新增收益 |'
    new='| 3 | 正式6终局完整经营收益链 | 正式5实际及正式6前景、48参数、56字段和600点曲线已归档；15项独立期初状态仍缺，正式6新增菲律宾需求及印尼投资机制尚未接入验证。本次未重训，正式6仅比较该回合新增收益并按终局规则处理 |'
    assert old in text;text=text.replace(old,new)
    oldstep='4. 正式4结果归档与最终方案配对已完成；依据新增实际做独立复盘及模型更新，正式5候选只比较5至6新增收益。t5v0已完成可估计项重训及29类状态核验；需求缺竞争队最终决策仍暂停，正式3需求基线保留；正式6走终局分支。'
    assert oldstep in text
    text=text.replace(oldstep,'4. 正式5结果与本组最终方案已归档；先按最终决策对应关系评估冻结版本，再决定是否重训。正式6新增菲律宾及印尼投资字段需适配，只比较正式6新增收益并走终局分支；竞争队最终输入及15项独立期初状态缺口仍保留。')
    assert readme.read_bytes()==before,'README changed concurrently'
    readme.write_text(text,encoding='utf-8')
    checks=[]
    for p in [readme,BASE/'overall_report.md',BASE/'calculated/report.md',BASE/'formal6_initial/report.md',BASE/'decision_history/report.md',BASE/'final_validation/report.md']:
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if re.match(r'^[a-zA-Z]+://|^#',target):continue
            path=(p.parent/unquote(target.split('#')[0])).resolve()
            checks.append(dict(document=p.relative_to(ROOT).as_posix(),target=target,exists=path.is_file()))
    assert all(r['exists'] for r in checks),[r for r in checks if not r['exists']]
    write(BASE/'document_changes.json',dict(path='README.md',before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=sha(readme),
        backup='document_backup/README_before.md',other_existing_changes_preserved=True,links=checks))
    with (BASE/'work_log.md').open('a',encoding='utf-8') as stream:
        stream.write('\n\n完成验收：'+now+'。10市场100队，140有效结果页、2000字段行、280图配对、1900财务等式、100累计衔接通过；700计算值、5700输入及600直接值核对通过。本组最终42项、正式6的56字段×5列、48参数、五部分前景和600曲线点归档。15项独立期初状态保持未知。平台只读，无填写或提交；未重训。浏览器超时、共享选择错配和图形重读恢复见总览；用户确认独占后继续。README备份当前磁盘内容，保存前后哈希并核验链接，未回退已有修改。\n')
    write(BASE/'delivery_acceptance.json',dict(status='COLLECTION_ACCEPTED_WITH_EXPLICIT_STATE_GAPS',completed_at=now,
        results=index['status'],initial=initial['status'],unknown_opening_states=15,report_sha256=sha(BASE/'overall_report.md'),
        readme_sha256=sha(readme),link_checks=len(checks),all_links_valid=True))
    print(json.dumps(dict(status='COLLECTION_ACCEPTED_WITH_EXPLICIT_STATE_GAPS',links=len(checks),report=str(BASE/'overall_report.md')),ensure_ascii=False))


if __name__=='__main__':main()
