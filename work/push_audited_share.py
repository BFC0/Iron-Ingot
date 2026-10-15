"""Publish a verified snapshot through GitHub Git Data API, preserving main history."""
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = Path(sys.argv[1]).resolve()
assert REPO.is_relative_to(ROOT / 'output/share_upload') and REPO.name == 'repository'
OUT = REPO.parent
GH = ROOT / 'work/github_cli/runtime/bin/gh.exe'
TARGET = 'repos/BFC0/Iron-Ingot'

def run(args, **kwargs):
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', **kwargs)
    if p.returncode:
        raise RuntimeError(p.stderr.strip())
    return p.stdout.strip()

credentials = run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\nusername=BFC0\n\n')
fields = dict(line.split('=', 1) for line in credentials.splitlines() if '=' in line)
assert fields.get('password'), 'No credential available'
env = dict(os.environ, GH_TOKEN=fields['password'], GH_PROMPT_DISABLED='1')

def api(endpoint, payload=None, method=None):
    args = [str(GH), 'api', TARGET + endpoint]
    if method:
        args.extend(['--method', method])
    if payload is None:
        return json.loads(run(args, env=env))
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json', dir=OUT, delete=False) as f:
        json.dump(payload, f, ensure_ascii=False)
        filename = f.name
    try:
        for attempt in range(3):
            try:
                return json.loads(run(args + ['--input', filename], env=env))
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(2)
    finally:
        Path(filename).unlink()

def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

assert blob_sha(b'') == 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'
manifest = json.loads((REPO / 'SHARE_MANIFEST.json').read_text(encoding='utf-8'))
expected = {x['path'] for x in manifest['files']} | {'SHARING.md', 'SHARE_MANIFEST.json'}
assert {p.relative_to(REPO).as_posix() for p in REPO.rglob('*') if p.is_file()} == expected
for item in manifest['files']:
    assert hashlib.sha256((REPO / item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
details = api('')
assert details['full_name'] == 'BFC0/Iron-Ingot' and details['permissions']['push']
assert details['default_branch'] == 'main'
head = api('/git/ref/heads/main')['object']['sha']
old_commit = api('/git/commits/' + head)
old_tree = api('/git/trees/' + old_commit['tree']['sha'] + '?recursive=1')
assert not old_tree.get('truncated')
existing_blobs = {x['sha'] for x in old_tree['tree'] if x['type'] == 'blob'}
entries = []
uploads = {}
for rel in sorted(expected):
    data = (REPO / rel).read_bytes()
    sha = blob_sha(data)
    entry = {'path': rel, 'mode': '100644', 'type': 'blob'}
    if sha in existing_blobs or len(data) > 65536:
        entry['sha'] = sha
        if sha not in existing_blobs:
            uploads.setdefault(sha, rel)
    else:
        entry['content'] = data.decode('utf-8')
    entries.append(entry)
print(json.dumps({'base_commit': head, 'visibility': 'private' if details['private'] else 'public',
                  'files': len(entries), 'large_blob_uploads': len(uploads)}, ensure_ascii=False), flush=True)

def upload(item):
    sha, rel = item
    data = (REPO / rel).read_bytes()
    result = api('/git/blobs', {'content': base64.b64encode(data).decode(), 'encoding': 'base64'})
    assert result['sha'] == sha, rel
    return sha

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(upload, item) for item in uploads.items()]
    for count, future in enumerate(as_completed(futures), 1):
        future.result()
        if count % 10 == 0 or count == len(futures):
            print(json.dumps({'uploaded_blobs': count, 'total': len(futures)}), flush=True)
tree = api('/git/trees', {'tree': entries})
assert not tree.get('truncated')
created = api('/git/commits', {'message': 'Update privacy-filtered Cesim models, decisions and reports',
                             'tree': tree['sha'], 'parents': [head],
                             'author': {'name': 'BFC0', 'email': '<REDACTED_EMAIL>'}})
remote_tree = api('/git/trees/' + tree['sha'] + '?recursive=1')
assert not remote_tree.get('truncated')
actual = {x['path']: x['sha'] for x in remote_tree['tree'] if x['type'] == 'blob'}
assert set(actual) == expected
assert all(actual[rel] == blob_sha((REPO / rel).read_bytes()) for rel in expected)
assert api('/git/ref/heads/main')['object']['sha'] == head, 'Remote changed during upload; retry without overwriting'
api('/git/refs/heads/main', {'sha': created['sha'], 'force': False}, method='PATCH')
assert api('/git/ref/heads/main')['object']['sha'] == created['sha']
result = {'url': 'https://github.com/BFC0/Iron-Ingot', 'branch': 'main', 'commit': created['sha'],
          'parent': head, 'files': len(expected), 'remote_file_hashes_verified': True, 'local_history_uploaded': False}
(OUT / 'upload_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result), flush=True)
