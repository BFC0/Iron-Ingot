"""Read target metadata using the existing credential without logging it."""
import json
import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GH = ROOT / 'work/github_cli/runtime/bin/gh.exe'

def run(args, **kwargs):
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', **kwargs)
    if p.returncode:
        raise RuntimeError(p.stderr.strip())
    return p.stdout.strip()

credentials = run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\nusername=BFC0\n\n')
fields = dict(line.split('=', 1) for line in credentials.splitlines() if '=' in line)
assert fields.get('password'), 'GitHub credential unavailable'
env = dict(os.environ, GH_TOKEN=fields['password'], GH_PROMPT_DISABLED='1')
details = json.loads(run([str(GH), 'api', 'repos/BFC0/Iron-Ingot'], env=env))
print(json.dumps({k: details[k] for k in ('full_name', 'private', 'default_branch', 'size', 'permissions')}, ensure_ascii=False))
repo = ROOT / 'output/share_upload/20261012T233302_privacy/repository'
result = json.loads((repo.parent / 'upload_result.json').read_text(encoding='utf-8'))
head = json.loads(run([str(GH), 'api', 'repos/BFC0/Iron-Ingot/git/ref/heads/main'], env=env))['object']['sha']
assert head == result['commit'], 'Remote main changed since audited publication'
tree = json.loads(run([str(GH), 'api', 'repos/BFC0/Iron-Ingot/git/trees/' + head + '?recursive=1'], env=env))
assert not tree.get('truncated')
actual = {x['path']: x['sha'] for x in tree['tree'] if x['type'] == 'blob'}
expected = {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
assert set(actual) == set(expected)
assert all(actual[p] == hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() for p, data in expected.items())
verification = {'remote_main': head, 'verified_files': len(actual), 'all_blob_hashes_match': True}
(repo.parent / 'remote_verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
print(json.dumps(verification))
