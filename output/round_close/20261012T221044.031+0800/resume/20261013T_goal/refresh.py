"""Refresh this continuation from the latest complete local audit; never edit raw files."""
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from check_html import check as check_html

RUN = Path(__file__).resolve().parent
BASE = RUN.parents[1]
ROOT = BASE.parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    audit = BASE / sys.argv[1] if len(sys.argv) > 1 else max(
        p for p in (BASE / 'audit').glob('20*')
        if all((p / name).is_file() for name in ('validation.json', 'coverage.json', 'sources.json')))
    validation = read(audit / 'validation.json')
    coverage = read(audit / 'coverage.json')
    sources = read(audit / 'sources.json')
    baseline_resume = read(BASE / 'resume/20261013T103249/sources.json')
    baseline_all = read(BASE / 'audit/20261013T103201.321516+0800/sources.json')
    assert all(sha(BASE / item['source']) == item['sha256'] for item in baseline_resume + baseline_all), 'Baseline source changed'
    assert all(sha(BASE / item['source']) == item['sha256'] for item in sources), 'Audit source changed'
    assert all(validation['selfchecks'].values()), 'Audit selfcheck failed'
    assert not validation['source_hash_changes_during_run']
    assert not validation['source_hash_changes_since_first_audit']
    counts = dict(Counter(item['status'] for item in coverage))
    assert counts == validation['coverage_counts'] and len(coverage) == 750
    pending = [item for item in coverage if item['status'] != 'verified']
    verified = counts.get('verified', 0)
    next_item = {key: pending[0][key] for key in ('market', 'phase', 'round', 'panel')} if pending else None
    phase_labels = {'initial': '初始', 'practice': '练习', 'formal': '正式'}
    next_label = f"市场{next_item['market']}{phase_labels[next_item['phase']]}{next_item['round']}" if next_item else '历史结果逐栏采集已齐'
    stamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
    baseline_names = {item['source'] for item in baseline_all}
    added = [item for item in sources if item['source'] not in baseline_names and item['identity_status'] == 'verified']
    html_check = check_html()
    html_complete = html_check['complete_html_pages']
    capture_complete = not pending and html_complete == 750
    next_html = next((item for item in html_check['items'] if item['status'] != 'resolved'), None)
    if not pending and next_html:
        next_label = f"补齐市场{next_html['market']}{phase_labels[next_html['phase']]}{next_html['round']}/{next_html['panel']}完整HTML"
    status = {
        'recorded_at': stamp, 'status': 'HISTORY_CAPTURE_COMPLETE' if capture_complete else 'IN_PROGRESS',
        'user_resumed': True, 'previous_pause_is_historical': True,
        'coverage': {'verified': verified, 'pending': len(pending)}, 'added_pages': len(added),
        'baseline_resume_hashes_unchanged': True, 'baseline_all_212_hashes_unchanged': True,
        'audit': audit.relative_to(BASE).as_posix(), 'audit_data_status': validation['data_status'],
        'next': next_item, 'financial_counts': validation['financial_counts'],
        'structure_counts': validation['structure_counts'], 'audit_failures': validation['failures'],
        'decision_modified': False, 'model_trained': False,
        'html_integrity': {key: value for key, value in html_check.items() if key != 'items'},
        'next_html': next_html,
    }
    report = f'''# 历史结果网页续采

更新：{stamp}。已逐页核验{verified}/750页，剩余{len(pending)}页。下一位置：{next_label}。

完整HTML另计：{html_complete}/750页；已有原件HTML缺口{html_check['incomplete_original_pages']}页，其中补件已核验{html_check['resolved_count']}页、仍待补{html_check['pending_count']}页。具体身份、长度、原件哈希及补件路径见[HTML完整性核验](html_recapture_pending.json)。只有覆盖与完整HTML均达到750页才标记采集完成。完整HTML计数扫描当前原件，可能暂领先于上述已归档核验的覆盖计数。

覆盖按[本次核验](../../{status['audit']}/report.md)的真实选中市场、阶段、回合、HTML选项及URL栏目计入；可打印报告不替代独立逐栏证据。未采集不补零。全部待补项见[pending.json](pending.json)，来源及SHA256见[sources.json](sources.json)。核验产生后新采的页面须刷新核验才计入本报告。

截至本次核验，相对10:32基线新增{len(added)}页；resume/20261013T103249的15份来源及当时核验的全部212份来源哈希均不变。旧history_paused.json仅是历史暂停记录，本次用户已恢复续采；执行状态以[status.json](status.json)为准。

先通过下拉框选择市场及回合，再并行读取同回合各栏，每页独立核验。仅改URL不能切换回合。HTML、表格、SVG及内联图表脚本随原件保存。

财务核验：{validation['financial_counts']}；结构核验：{validation['structure_counts']}。完整待核及拒绝项保留于上述核验报告；历史结果采齐不代表当前正式3预算与草稿缺口、财务配对及建模任务已完成。只读采集，未修改平台决策，未训练模型。

刷新：先运行既有audit/verify_archive.py，再运行本目录refresh.py；默认选择最新完整核验目录，也可传入audit/<目录名>。
'''
    for name, value in [('sources.json', sources), ('pending.json', pending), ('status.json', status)]:
        (RUN / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    (RUN / 'report.md').write_text(report, encoding='utf-8')
    readme_path = ROOT / 'README.md'
    readme = readme_path.read_text(encoding='utf-8-sig')
    link = (RUN / 'report.md').relative_to(ROOT).as_posix()
    notice = f'网页补采最新进度：**覆盖{verified}/750页，完整HTML {html_complete}/750页**；[续采记录]({link})。逐栏待采{len(pending)}页，已有HTML缺口待补{html_check["pending_count"]}页；下一位置：{next_label}。'
    if re.search(r'^网页补采最新进度：.*$', readme, re.M):
        readme = re.sub(r'^网页补采最新进度：.*$', notice, readme, count=1, flags=re.M)
    else:
        readme = readme.replace('# Cesim 项目总览\n', '# Cesim 项目总览\n\n' + notice + '\n', 1)
    row = f'| 历史结果逐栏补采 | **{"采集已齐" if capture_complete else "部分完成"}：覆盖{verified}/750页，完整HTML {html_complete}/750页。** [最新续采报告]({link}) | 逐栏待采{len(pending)}页，已有HTML缺口待补{html_check["pending_count"]}页。下一位置：{next_label}。先切换并核验平台选中回合，再读各栏；仅改URL不能切换回合。此进度优先于旧报告及历史暂停标记。财务与正式3草稿待核项另见续采报告。 |'
    assert len(re.findall(r'^\| 历史结果逐栏补采 \|.*$', readme, re.M)) == 1
    readme = re.sub(r'^\| 历史结果逐栏补采 \|.*$', row, readme, count=1, flags=re.M)
    readme_path.write_text(readme, encoding='utf-8')
    assert read(RUN / 'status.json')['coverage']['pending'] == len(read(RUN / 'pending.json'))
    assert read(RUN / 'sources.json') == sources
    print(json.dumps(status, ensure_ascii=False))


if __name__ == '__main__':
    main()
