"""Seal this read-only continuation against the previous pause manifest."""
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUN = Path(__file__).resolve().parent
BASE = RUN.parents[1]
ROOT = BASE.parents[2]
AUDIT = BASE / 'audit/20261013T083651.255146+0800'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (RUN / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


old = read(BASE / 'history_paused.json')['raw_files']
assert len(old) == 135
assert all(sha(BASE / 'raw' / item['file']) == item['sha256'] for item in old)
old_names = {item['file'] for item in old}
added = sorted(p for p in (BASE / 'raw').glob('market*.json') if p.name not in old_names)
assert len(added) == 45
assert {p.name.rsplit('_', 1)[0] for p in added} == {
    'market02_initial0', 'market02_practice1', 'market03_initial0'}
sources = {item['source']: item for item in read(AUDIT / 'sources.json')}
manifest = []
for path in added:
    source = sources['raw/' + path.name]
    assert source['identity_status'] == 'verified', source
    assert source['sha256'] == sha(path)
    manifest.append(source)
validation = read(AUDIT / 'validation.json')
assert validation['coverage_counts'] == {'verified': 180, 'pending': 570}
assert all(validation['selfchecks'].values())
assert not validation['source_hash_changes_since_first_audit']
with (AUDIT / 'coverage.csv').open(encoding='utf-8-sig', newline='') as stream:
    coverage = list(csv.DictReader(stream))
pending = [row for row in coverage if row['status'] != 'verified']
assert len(pending) == 570
stamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
status = {
    'recorded_at': stamp,
    'status': 'PARTIAL_BROWSER_READ_TIMEOUT',
    'user_resumed': True,
    'previous_pause_is_historical': True,
    'added_pages': len(added),
    'coverage': validation['coverage_counts'],
    'prior_135_hashes_unchanged': True,
    'next': {'market': 3, 'phase': 'practice', 'round': 1},
    'blocker': '市场3练习1的整批页面读取连续60秒超时，没有保存未经身份核验的页面。',
    'audit': str(AUDIT.relative_to(BASE)),
    'audit_status_note': '旧核验脚本仍因保留的history_paused.json显示PAUSED_BY_USER；本次执行状态以此记录为准，数据覆盖取独立核验结果。',
    'decision_modified': False,
    'model_trained': False,
}
save('sources.json', manifest)
save('pending.json', pending)
save('status.json', status)
report = f'''# 2026-10-13 续采归档

已新增45页：市场2初始0、市场2练习1、市场3初始0，各15栏。市场1与市场2五个历史回合均已逐栏覆盖；市场3仅初始0、市场5仅正式2完成。总覆盖180/750，剩余570页，详见[pending.json](pending.json)。

新增页面的市场、阶段、回合、选项值、HTML选中项和URL栏目均通过既有核验。表格、HTML、SVG及内联图表JSON随原件保存；新增来源与SHA256见[sources.json](sources.json)。此前暂停清单的135份原件哈希全部保持一致。

状态为PARTIAL_BROWSER_READ_TIMEOUT：市场3练习1整批读取连续超时，没有取得可保存原件。明确市场/回合的地址已在市场3初始0验证成功，下一次从市场3练习1恢复；不得根据文件名或地址宣称完成。

本地核验见[报告](../../audit/{AUDIT.name}/report.md)与[完整覆盖](../../audit/{AUDIT.name}/coverage.csv)。7项解析器自检通过；全包财务检查1820项通过、43项待核、3项初始基准不适用。旧的正式3生产计划页身份拒绝继续保留，新增45页没有身份拒绝。旧核验脚本因历史暂停标记仍显示PAUSED_BY_USER，本次状态以[status.json](status.json)为准，旧暂停记录不覆盖本次恢复授权。

只读采集；未修改平台决策、未训练模型。未采集数据不补零，待核财务项不记为通过。
'''
with (RUN / 'report.md').open('x', encoding='utf-8') as stream:
    stream.write(report)
with (BASE / 'history_work_log.md').open('a', encoding='utf-8') as stream:
    stream.write(f'\n{stamp}：用户恢复归档；新增45页，覆盖180/750；旧135份哈希不变。市场3练习1连续读取超时，余570页待采。本次状态见resume/20261013/status.json；旧暂停标记仅为历史。未修改决策或训练模型。\n')
print(json.dumps(status, ensure_ascii=False))
