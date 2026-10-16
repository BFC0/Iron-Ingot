"""Verify the isolated share and remote history, then optionally push with Git."""
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output/scheduled_github/20261015T1132+0800'
CLONE = ROOT / 'output/share_upload/20261015T1132_remote/repository'
REPO = ROOT / 'output/share_upload/20261015T113508_privacy/repository'
source = (ROOT / 'work/audit_github_share.py').read_text(encoding='utf-8')
# Reuse the existing roster recovery, filters and their assertions without creating another snapshot.
exec(compile(source[source.index('tree = ast.parse'):source.index('tracked = git(')],
             'existing_privacy_filters', 'exec'))
base_findings = findings
reviewed_authorization_text = {
    '726fef060a87903c48b6928b2fd55cd2016f7202394a3d60456aa2274a4d7489',
    'b33d819ab03f0445824ce70dae1bf657bdd1df9f73d84e54e320fa985957ff91',
}

def findings(text):
    result = base_findings(text)
    matches = list(secret_patterns['assigned_secret'].finditer(text))
    if 'assigned_secret' in result and matches and all(
            hashlib.sha256(m.group(1).encode()).hexdigest() in reviewed_authorization_text
            for m in matches):
        result.remove('assigned_secret')
    return result

assert findings('api_key="' + 'a' * 30 + '"') == ['assigned_secret']
assert findings('ghp_' + 'a' * 30) == ['credential_token']
if '--restore' in sys.argv:
    audit = json.loads((REPO.parent / 'privacy_audit.json').read_text(encoding='utf-8'))
    manifest_path = REPO / 'SHARE_MANIFEST.json'
    old = manifest_path.read_bytes()
    (OUT / 'manifest_before_review.json').write_bytes(old)
    manifest = json.loads(old)
    restored = []
    for item in audit['current_potential_credentials']:
        rel = item['path']
        assert item['categories'] == ['assigned_secret']
        original = (ROOT / rel).read_bytes()
        text = original.decode('utf-8-sig')
        assert not findings(text), rel
        safe = redact(text)
        assert not findings(safe) and redact(safe) == safe
        if Path(rel).suffix == '.py':
            ast.parse(safe)
        if Path(rel).suffix == '.json':
            json.loads(safe)
        target = REPO / rel
        assert not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'') + safe.encode('utf-8')
        target.write_bytes(data)
        manifest['files'].append({'path': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        restored.append(rel)
    assert len(restored) == 17
    manifest['excluded_files'] -= len(restored)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'credential_review.json').write_text(json.dumps({
        'restored': restored, 'reason': 'Exact-hash-reviewed Chinese authorization descriptions; not credentials',
        'before_manifest_sha256': hashlib.sha256(old).hexdigest(),
        'after_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'reviewed_false_positive_files_restored': len(restored)}))
    sys.exit(0)

def git(*args, worktree=False):
    command = ['git', '--git-dir=' + str(CLONE / '.git')]
    command += ['--work-tree=' + str(REPO)] if worktree else []
    result = subprocess.run(command + list(args), cwd=CLONE, capture_output=True)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    return result.stdout

assert git('remote', 'get-url', 'origin').decode().strip() == 'https://github.com/BFC0/Iron-Ingot.git'
base = git('rev-parse', 'origin/main').decode().strip()
assert base == '3fca469b84c9800516000dd28db1eeed52d4d294'
objects = git('rev-list', '--objects', '--all').decode().splitlines()
checked = 0
proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=CLONE,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
for entry in objects:
    oid = entry.split(' ', 1)[0]
    proc.stdin.write((oid + '\n').encode())
    proc.stdin.flush()
    header = proc.stdout.readline().decode().split()
    data = proc.stdout.read(int(header[2]))
    assert proc.stdout.read(1) == b'\n'
    if header[1] != 'blob':
        continue
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError:
        raise AssertionError('Unreviewed binary in remote history') from None
    assert not findings(text), 'Credential pattern in remote object ' + oid
    assert redact(text) == text, 'Personal information in remote object ' + oid
    checked += 1
proc.stdin.close()
assert proc.wait() == 0
metadata = git('log', '--all', '--format=%an%n%ae%n%cn%n%ce%n%B').decode()
assert not findings(metadata)
assert all(not pattern.search(metadata) for pattern, _ in name_patterns)
print(json.dumps({'remote_history_blobs_checked': checked, 'base': base}), flush=True)
if '--history-only' in sys.argv:
    sys.exit(0)
manifest = json.loads((REPO / 'SHARE_MANIFEST.json').read_text(encoding='utf-8'))
expected = {item['path'] for item in manifest['files']} | {'SHARING.md', 'SHARE_MANIFEST.json'}
actual_files = {p.relative_to(REPO).as_posix() for p in REPO.rglob('*') if p.is_file()}
assert expected == actual_files
for item in manifest['files']:
    assert hashlib.sha256((REPO / item['path']).read_bytes()).hexdigest() == item['sha256']
for rel in expected:
    text = (REPO / rel).read_text(encoding='utf-8-sig')
    assert not findings(text), rel
    assert redact(text) == text, rel
git('config', 'user.name', 'BFC0')
git('config', 'user.email', '<REDACTED_EMAIL>')
git('config', 'core.autocrlf', 'false')
git('add', '--all', worktree=True)
staged = set(git('ls-files', '-z', worktree=True).decode().strip('\0').split('\0'))
assert staged == expected
for entry in git('ls-files', '--stage', '-z', worktree=True).decode().strip('\0').split('\0'):
    info, rel = entry.split('\t', 1)
    data = (REPO / rel).read_bytes()
    assert info.split()[1] == hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(), rel
result = {'target': 'https://github.com/BFC0/Iron-Ingot', 'base': base,
          'remote_history_blobs_checked': checked, 'files': len(expected),
          'snapshot_hashes_and_privacy_verified': True, 'local_history_uploaded': False}
if '--push' in sys.argv:
    numeric = json.loads((REPO.parent / 'numeric_verification.json').read_text(encoding='utf-8'))
    assert numeric['numeric_values_preserved']
    assert numeric['checked_json_python_files'] == sum(Path(x['path']).suffix in {'.json', '.py'} for x in manifest['files'])
    assert git('ls-remote', 'origin', 'refs/heads/main').decode().split()[0] == base
    git('commit', '-m', 'Update audited Cesim models and reports for formal round 5', worktree=True)
    head = git('rev-parse', 'HEAD').decode().strip()
    assert git('rev-parse', 'HEAD^').decode().strip() == base
    git('push', 'origin', 'HEAD:main')
    assert git('ls-remote', 'origin', 'refs/heads/main').decode().split()[0] == head
    result.update(commit=head, pushed=True)
(OUT / ('upload_result.json' if '--push' in sys.argv else 'prepush_verification.json')).write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
