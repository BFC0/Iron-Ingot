"""Audit tracked files and prepare a separate privacy-filtered GitHub snapshot."""
import ast
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output/share_upload' / datetime.now().strftime('%Y%m%dT%H%M%S_privacy')
OUT.mkdir(parents=True, exist_ok=False)
REPO = OUT / 'repository'
REPO.mkdir()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

tree = ast.parse((ROOT / 'code/archive_and_report.py').read_text(encoding='utf-8'))
identities = next(ast.literal_eval(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'identities' for t in n.targets))
names = {}
for path in ROOT.glob('raw/*checklist*.json'):
    text = path.read_text(encoding='utf-8-sig')
    for length in (4, 3, 2):
        for match in re.finditer(r'(?=([一-鿿](?:[ \t]*[一-鿿]){' + str(length - 1) + r'}))', text):
            candidate = re.sub(r'[ \t]', '', match.group(1))
            key = hashlib.sha256(candidate.encode()).hexdigest()
            if key in identities:
                names[candidate] = identities[key]
assert len(names) == len(identities), 'Known roster not fully recovered'
name_patterns = [(re.compile(r'[ \t]*'.join(map(re.escape, name))), initials) for name, initials in names.items()]
secret_patterns = {
    'credential_token': re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|\bAKIA[A-Z0-9]{16}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}'),
    'private_key': re.compile(r'-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----'),
    'assigned_secret': re.compile(r'''(?:password|passwd|access_token|refresh_token|api_key|client_secret|authorization|cookie)\s*["']?\s*[:=]\s*["']([^"'\r\n]{8,})''', re.I),
    'bearer_token': re.compile(r'\bBearer\s+[A-Za-z0-9._~-]{20,}', re.I),
    'url_credential': re.compile(r'https?://[^\s/:]+:[^\s/@]+@'),
    'url_session': re.compile(r'[?&](?:access_token|auth_token|sessionid|session_id|token|jwt)=[A-Za-z0-9._~-]{12,}', re.I),
}

def findings(text):
    result = []
    for kind, pattern in secret_patterns.items():
        for match in pattern.finditer(text):
            # Code references and regex definitions are not credential values.
            if kind == 'assigned_secret' and (match.group(1).startswith(('fields[', 'os.environ', '<', '${')) or '\\' in match.group(1)):
                continue
            result.append(kind)
    return sorted(set(result))

def redact(text):
    for pattern, initials in name_patterns:
        text = pattern.sub(initials, text)
    for name, initials in names.items():
        text = text.replace(name.encode('unicode_escape').decode(), initials)
    for root in (str(ROOT).replace('\\', '\\\\'), str(ROOT), ROOT.as_posix()):
        text = text.replace(root + ('\\\\' if '\\\\' in root else '\\' if '\\' in root else '/'), '')
        text = text.replace(root, '.')
    text = re.sub(r'[A-Za-z]:(?:/|\\\\|\\)Users(?:/|\\\\|\\)[^/\\\s"\'<>]+', '<LOCAL_USER_DIR>', text, flags=re.I)
    text = re.sub(r'wxid_[A-Za-z0-9_]+', '<REDACTED_WECHAT_ID>', text)
    text = text.replace('LOCAL_PROJECT_OWNER', 'LOCAL_PROJECT_OWNER')
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:com|net|org|edu|gov|cn|uk|io|de|fr|jp)\b', '<REDACTED_EMAIL>', text, flags=re.I)
    text = re.sub(r'((?:手机|电话|mobile|phone)\s*["\']?\s*[:：=]\s*["\']?)1[3-9]\d{9}(?!\d)', r'\1<REDACTED_PHONE>', text, flags=re.I)
    return text

assert not findings('api_key = "<REDACTED>"')
assert findings('api_key = "' + 'a' * 30 + '"') == ['assigned_secret']
assert findings('ghp_' + 'a' * 30) == ['credential_token']
assert redact('<REDACTED_EMAIL> 电话:<REDACTED_PHONE> <LOCAL_USER_DIR>/project') == '<REDACTED_EMAIL> 电话:<REDACTED_PHONE> <LOCAL_USER_DIR>/project'
assert all(redact(name) == initials for name, initials in names.items())

tracked = git('ls-files', '-z').decode().split('\0')[:-1]
text_suffixes = {'.py', '.md', '.txt', '.json', '.csv', '.tsv', '.svg', '.yaml', '.yml', '.toml', '.ini', '.ps1', '.sh', '.html', '.css', '.js', '.tex'}
excluded_parts = {'raw', 'sources', 'quarantine', 'share_upload', 'github_cli', 'python_packages', '__pycache__'}
excluded = []
manifest = []
changed = []
current_findings = []
for rel in tracked:
    source = ROOT / rel
    data = source.read_bytes()
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError:
        text = None
    detected = findings(text) if text is not None else []
    if detected:
        current_findings.append({'path': rel, 'categories': detected})
    reason = None
    if any(part in excluded_parts for part in Path(rel).parts):
        reason = 'original_evidence_or_local_tools'
    elif source.suffix.lower() not in text_suffixes and source.name != '.gitignore':
        reason = 'binary_or_unreviewed_format'
    elif text is None:
        reason = 'non_utf8'
    elif detected:
        reason = 'potential_credential_requires_review'
    elif source.suffix == '.json':
        doc = json.loads(text)
        if isinstance(doc, dict) and isinstance(doc.get('snapshot'), str):
            reason = 'original_browser_snapshot'
    elif source.suffix == '.txt' and source.with_suffix('.json').is_file():
        try:
            doc = json.loads(source.with_suffix('.json').read_text(encoding='utf-8-sig'))
            if isinstance(doc, dict) and isinstance(doc.get('snapshot'), str):
                reason = 'original_browser_snapshot_text'
        except (ValueError, UnicodeError):
            pass
    if reason:
        excluded.append({'path': rel, 'reason': reason})
        continue
    safe = redact(text)
    assert not findings(safe), rel
    assert redact(safe) == safe, rel
    try:
        if source.suffix == '.json':
            json.loads(safe)
        if source.suffix == '.py':
            ast.parse(safe)
    except (ValueError, SyntaxError):
        raise RuntimeError('Sanitization syntax check failed: ' + rel) from None
    target = REPO / rel
    assert target.resolve().is_relative_to(REPO)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = (b'\xef\xbb\xbf' if data.startswith(b'\xef\xbb\xbf') else b'') + safe.encode('utf-8')
    assert len(result) < 100 * 1024 * 1024
    target.write_bytes(result)
    if result != data:
        changed.append(rel)
    manifest.append({'path': rel, 'bytes': len(result), 'sha256': hashlib.sha256(result).hexdigest()})

# Check historical text blobs without displaying secret values or importing history.
objects = git('rev-list', '--objects', '--all').decode().splitlines()
history = []
proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
for entry in objects:
    oid, _, rel = entry.partition(' ')
    proc.stdin.write((oid + '\n').encode())
    proc.stdin.flush()
    header = proc.stdout.readline().decode().split()
    size = int(header[2])
    data = proc.stdout.read(size)
    assert proc.stdout.read(1) == b'\n'
    if header[1] != 'blob':
        continue
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError:
        continue
    categories = findings(text)
    if redact(text) != text:
        categories.append('personal_name_contact_or_local_path')
    if categories:
        history.append({'object': oid, 'path': rel, 'categories': categories})
proc.stdin.close()
assert proc.wait() == 0

notice = '# GitHub 分享范围\n\n代码、模型、文本报告及结构化导出经过隐私过滤。姓名使用首字母，个人联系方式与本机用户路径使用占位符。\n\n原始网页快照、原始附件、历史截图、未核验二进制文件、工具缓存及本地 Git 历史不上传。部分原件链接因此不可用，依赖原件的训练、采集及来源哈希验证无法仅凭分享副本完整复现。历史哈希不代表脱敏副本哈希；当前清单见 SHARE_MANIFEST.json。\n'
(REPO / 'SHARING.md').write_text(notice, encoding='utf-8')
readme = REPO / 'README.md'
readme.write_text('> GitHub 分享副本：请先阅读[分享范围](SHARING.md)。\n\n' + readme.read_text(encoding='utf-8-sig'), encoding='utf-8')
for item in manifest:
    data = (REPO / item['path']).read_bytes()
    item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
(REPO / 'SHARE_MANIFEST.json').write_text(json.dumps({'files': manifest, 'excluded_files': len(excluded)}, ensure_ascii=False, indent=2), encoding='utf-8')
report = {'repository': str(REPO), 'local_commit': git('rev-parse', 'HEAD').decode().strip(), 'included': len(manifest) + 2,
          'excluded': excluded, 'sanitized_files': changed, 'current_potential_credentials': current_findings,
          'historical_findings': history, 'exclusion_counts': dict(Counter(x['reason'] for x in excluded)),
          'checks': {'known_roster': True, 'credential_patterns': True, 'python_json_syntax': True, 'local_history_not_uploaded': True}}
(OUT / 'privacy_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'repository': str(REPO), 'included': report['included'], 'sanitized': len(changed), 'excluded': report['exclusion_counts'],
                  'credential_candidates': current_findings, 'historical_flagged_objects': len(history)}, ensure_ascii=False))
