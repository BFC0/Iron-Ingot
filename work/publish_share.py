"""Publish the prepared repository using existing GitHub credentials."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
repo = Path(sys.argv[1]).resolve()
assert repo.is_relative_to(ROOT / 'output/share_upload') and repo.name == 'repository'
gh = ROOT / 'work/github_cli/runtime/bin/gh.exe'


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Command failed')
    return result.stdout.strip()


credential = run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\nusername=BFC0\n\n')
fields = dict(line.split('=', 1) for line in credential.splitlines() if '=' in line)
assert fields.get('password'), 'No existing GitHub credential available'
env = dict(os.environ, GH_TOKEN=fields['password'], GH_PROMPT_DISABLED='1')
account = run([str(gh), 'api', 'user', '--jq', '.login'], env=env)
assert account == 'BFC0', 'Unexpected GitHub account'
url = 'https://github.com/' + account + '/Iron-Ingot'
existing = subprocess.run([str(gh), 'repo', 'view', account + '/Iron-Ingot', '--json', 'name'], env=env, capture_output=True)
assert existing.returncode != 0, 'Requested repository already exists; will not overwrite it'
manifest = json.loads((repo / 'SHARE_MANIFEST.json').read_text(encoding='utf-8'))
import hashlib
for item in manifest['files']:
    assert hashlib.sha256((repo / item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
run(['git', 'init', '-b', 'main'], cwd=repo)
run(['git', 'config', 'user.name', 'BFC0'], cwd=repo)
run(['git', 'config', 'user.email', '<REDACTED_EMAIL>'], cwd=repo)
run(['git', 'add', '--all'], cwd=repo)
run(['git', 'commit', '-m', 'Add anonymized Cesim documents, models and reports'], cwd=repo)
created = run([str(gh), 'repo', 'create', account + '/Iron-Ingot', '--public', '--source', str(repo), '--remote', 'origin', '--push'], env=env)
details = json.loads(run([str(gh), 'api', 'repos/' + account + '/Iron-Ingot'], env=env))
assert details['private'] is False and not details.get('description')
local_commit = run(['git', 'rev-parse', 'HEAD'], cwd=repo)
remote_commit = run([str(gh), 'api', 'repos/' + account + '/Iron-Ingot/commits/main', '--jq', '.sha'], env=env)
assert local_commit == remote_commit
tree = json.loads(run([str(gh), 'api', 'repos/' + account + '/Iron-Ingot/git/trees/' + local_commit + '?recursive=1'], env=env))
assert not tree.get('truncated')
remote_files = {x['path'] for x in tree['tree'] if x['type'] == 'blob'}
expected = {x['path'] for x in manifest['files']} | {'SHARING.md', 'SHARE_MANIFEST.json'}
assert remote_files == expected, {'missing': sorted(expected - remote_files), 'extra': sorted(remote_files - expected)}
result = {'url': url, 'visibility': 'public', 'description': details.get('description'), 'commit': local_commit, 'uploaded_files': len(remote_files), 'remote_file_list_verified': True}
with (repo.parent / 'upload_result.json').open('x', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
with (repo.parent / 'work_log.md').open('a', encoding='utf-8') as f:
    f.write('\n完成：新建公开仓库' + url + '，description为空。独立新历史提交' + local_commit + '，远端main提交一致，递归文件树逐文件核验通过，共' + str(len(remote_files)) + '份文件。既有项目仓库、原始证据和模型未改。\n')
print(json.dumps(result, ensure_ascii=False))
