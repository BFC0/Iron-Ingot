"""Inventory every retained raw capture and audit report privacy/local links."""
import json,re
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
import validate_market as v

BASE=Path(__file__).parent.parent

def main():
    accepted=v.read(BASE/'final_validation/acceptance_index.json')
    accepted_paths={x['source'] for x in accepted['sources']}
    for source in accepted['sources']:
        assert v.rules.sha(v.ROOT/source['source'])==source['sha256'],source
    entries=[]
    for path in sorted((BASE/'raw').glob('*')):
        if not path.is_file():continue
        ref=v.reference(path)
        doc=v.read(path) if path.suffix=='.json' else {}
        complete=isinstance(doc,dict) and v.formal.full_html(doc.get('html',''),doc.get('html_length'))
        if '_error' in path.stem:
            status='rejected_platform_error';reason='Platform error capture retained; successful retry is a separate raw source.'
        elif 'print_html_parts' in path.stem:
            status='recovery_helper';reason='Extra recovery parts retained; not an additional independent page.'
        elif not complete:
            status='rejected_truncated_or_incomplete';reason='Incomplete HTML retained; not used as accepted evidence.'
        elif ref['source'] in accepted_paths:
            status='accepted_formal4_result';reason='Current accepted print/web source referenced by final validation.'
        elif path.stem.startswith('own_formal4'):
            status='complete_formal4_decision_history';reason='Historical final group/individual/budget source; evidence in decision_history report.'
        elif path.stem.startswith('own_formal5'):
            status='complete_formal5_initial_snapshot';reason='Next open round read-only snapshot; validation in formal5_initial report. Draft values are not final decisions.'
        else:
            status='complete_superseded_capture';reason='Retained complete capture not counted again.'
        entries.append(dict(**ref,bytes=path.stat().st_size,captured_at=doc.get('captured_at') if isinstance(doc,dict) else None,
                            html_complete=bool(complete),status=status,reason=reason,
                            url=doc.get('url') if isinstance(doc,dict) else None,share_allowed=False,
                            privacy='Original pages may contain full names; preserve locally and exclude from sharing.'))
    manifest=dict(generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),raw_count=len(entries),
        status_counts=dict(Counter(x['status'] for x in entries)),sources=entries,all_raw_preserved=True,
        raw_directory_share_allowed=False,accepted_formal4_results=140,originals_do_not_add_independent_samples=True)
    times=[datetime.fromisoformat(x['captured_at'].replace('Z','+00:00')) for x in entries
           if x['captured_at'] and x['status'].startswith(('accepted_','complete_formal'))]
    first,last=min(times),max(times)
    manifest['capture_wall_clock_window']=dict(start_beijing=first.astimezone(timezone(timedelta(hours=8))).isoformat(),
        end_beijing=last.astimezone(timezone(timedelta(hours=8))).isoformat(),elapsed_seconds=(last-first).total_seconds(),
        meaning='Valid raw captured_at window, including navigation, timeout recovery and offline waits; not measured browser active time.')
    (BASE/'source_manifest.json').write_text(v.rules.redact_names(json.dumps(manifest,ensure_ascii=False,indent=2)),encoding='utf-8')
    decision=sorted((BASE/'decision_history').glob('*/report.md'))[-1]
    initial=sorted((BASE/'formal5_initial').rglob('report.md'))
    initial_details=''
    if initial:
        verdict=v.read(initial[-1].parent/'acceptance.json')
        assert verdict['status']=='PASS_WITH_EXPLICIT_UNKNOWN_OPENING_STATES'
        for name,expected in verdict['output_hashes'].items():assert v.rules.sha(initial[-1].parent/name)==expected,name
        assert verdict['sources']==12 and verdict['current_drafts']==210 and verdict['unresolved_opening_fields']==15
        initial_details='12 原件、210 当前草稿（每列42字段，列表回读值及样式稳定）、五部分前景、42 参数、3 曲线600点配对；上期研发900/1300及运营750千美元与正式4实际匹配。20结转项中5项直接或条件相容，15项期初状态仍未知，未把预算投影当期初余额。'
    initial_link=f'[前景、参数、曲线与期初核验]({initial[-1].relative_to(BASE).as_posix()})' if initial else '验收正在生成；原件已保留，尚不标为全部状态结转完成'
    report='# 正式4结束后数据采集总览\n\n本次完成数据采集与离线核验，结果归档已验收；完整经营复盘、模型重训及正式5候选比较未执行。\n\n'
    report+='- [实际结果验收](final_validation/report.md)：10 打印 + 130 网页（概要10、定向补采120），2000 字段行、280 原始 JSON 图与 SVG 配对、1900 财务等式、100 累计衔接全部通过。打印和网页重复表示不增加独立样本。\n'
    report+='- [计算值](calculated/20261014T223424833674+0800/report.md)：700 项，保留公式、输入、原件哈希及显示精度区间；5700 输入、600 直接值交叉核验通过。\n'
    report+=f'- [正式4最终小组方案与冻结候选](decision_history/{decision.parent.name}/report.md)：42 字段（29 决策、13 玩家预估），两套冻结候选均未采用；84 项配对、21 项实际交叉核验保留。模型事前评分 0 项，不能把玩家预估或预算误差称为模型成绩。\n'
    report+='- 正式5初始资料：'+initial_link+'。'+initial_details+'个人/小组当前草稿保持基准快照属性，不作正式5最终决策。\n'
    report+='- [全部原始来源清单](source_manifest.json)：完整有效件、截断旧件、平台错误页与恢复辅助片分别登记，保留来源时间和 SHA256。原件可能含真名，保留本地且排除分享；交付报告使用首字母。\n\n'
    report+=f'有效原件 captured_at 的墙钟窗口：北京时间 {first.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")} 至 {last.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")}，约 {(last-first).total_seconds()/60:.1f} 分钟。该窗口包含导航、超时恢复及离线等待，不是纯浏览器活动耗时；没有同范围对照，未声称速度百分比。\n\n'
    report+='每个市场的 12 标签可并行只读采集，市场选择仍独占。重载曾返回旧状态，错配在保存前拒绝；规范栏目重新导航后再次确认。分块 HTML 恢复、市场2生产明细错误恢复、市场1/4额外列的原件与审查证据均保留。\n\n'
    report+='既有正式4前景和 600 条曲线按[冻结来源索引](frozen_review/source_index.json)及[冻结核验](frozen_review/report.md)复用，不重复采集已核有效的正式4已知条件；快速教程复用既有归档。\n\n'
    report+='流程依据为[每回合结束后工作清单](../../../每回合结束后工作清单.md)。本次没有完成偏差归因、20项问题全面复核、模型参数更新或重训，不能把数据采集验收表述为完整回合复盘完成。\n'
    (BASE/'overall_report.md').write_text(v.rules.redact_names(report),encoding='utf-8')
    checks=[]
    for path in sorted(BASE.rglob('*.md'))+[v.ROOT/'README.md']:
        if 'raw' in path.parts or 'document_maintenance' in path.parts:continue
        text=path.read_text(encoding='utf-8-sig')
        links=[]
        for target in re.findall(r'\]\(([^)]+)\)',text):
            target=target.strip('<>').split('#')[0]
            if not target or target.startswith(('http://','https://','app://','codex://')):continue
            resolved=Path(target) if Path(target).is_absolute() else path.parent/target
            links.append(dict(target=target,exists=resolved.exists()))
        checks.append(dict(**v.reference(path),names_are_initials=v.rules.redact_names(text)==text,
                           local_links=links,links_valid=all(x['exists'] for x in links)))
    assert all(x['names_are_initials'] and x['links_valid'] for x in checks),[x for x in checks if not x['names_are_initials'] or not x['links_valid']]
    (BASE/'report_delivery_checks.json').write_text(json.dumps(dict(status='pass',reports=len(checks),checks=checks),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(raw=len(entries),statuses=manifest['status_counts'],reports_checked=len(checks),formal5_report_ready=bool(initial)),ensure_ascii=False))

if __name__=='__main__':main()
