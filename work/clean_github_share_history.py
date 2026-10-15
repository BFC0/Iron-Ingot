"""Replace main history only after explicit authorization to remove personal identifiers."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output/share_upload/20261012T233302_privacy'
GH = ROOT / 'work/github_cli/runtime/bin/gh.exe'

def run(args, **kwargs):
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', **kwargs)
    if p.returncode:
        raise RuntimeError(p.stderr.strip())
    return p.stdout.strip()

credentials = run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\nusername=BFC0\n\n')
fields = dict(line.split('=', 1) for line in credentials.splitlines() if '=' in line)
assert fields.get('password')
env = dict(os.environ, GH_TOKEN=fields['password'], GH_PROMPT_DISABLED='1')

def api(path, payload=None):
    args = [str(GH), 'api', 'repos/BFC0/Iron-Ingot' + path]
    if payload is None:
        return json.loads(run(args, env=env))
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=OUT, suffix='.json', delete=False) as f:
        json.dump(payload, f)
        filename = f.name
    try:
        if path.startswith('/git/refs/'):
            args += ['--method', 'PATCH']
        return json.loads(run(args + ['--input', filename], env=env))
    finally:
        Path(filename).unlink()

result = json.loads((OUT / 'upload_result.json').read_text(encoding='utf-8'))
verified = json.loads((OUT / 'remote_verification.json').read_text(encoding='utf-8'))
assert verified['remote_main'] == result['commit'] and verified['all_blob_hashes_match']
refs = api('/git/refs')
assert [x['ref'] for x in refs] == ['refs/heads/main'], 'Other references need independent privacy review'
assert refs[0]['object']['sha'] == result['commit'], 'Remote changed; do not overwrite'
previous = api('/git/commits/' + result['commit'])
identity = {'name': 'BFC0', 'email': '<REDACTED_EMAIL>'}
clean = api('/git/commits', {'message': 'Publish audited privacy-filtered Cesim project',
                           'tree': previous['tree']['sha'], 'parents': [], 'author': identity, 'committer': identity})
assert clean['parents'] == [] and clean['tree']['sha'] == previous['tree']['sha']
assert api('/git/ref/heads/main')['object']['sha'] == result['commit']
api('/git/refs/heads/main', {'sha': clean['sha'], 'force': True})
assert api('/git/ref/heads/main')['object']['sha'] == clean['sha']
assert api('/git/commits/' + clean['sha'])['parents'] == []
assert [x['ref'] for x in api('/git/refs')] == ['refs/heads/main']
cleanup = {'explicit_user_authorization': True, 'old_main': result['commit'], 'new_main': clean['sha'],
           'same_verified_file_tree': True, 'root_commit_without_old_history': True, 'other_refs': [],
           'local_originals_unchanged': True, 'caveat': 'Removing branch history cannot retract prior downloads or guarantee GitHub cached objects are purged.'}
(OUT / 'history_cleanup.json').write_text(json.dumps(cleanup, indent=2), encoding='utf-8')
result.update(commit=clean['sha'], parent=None, remote_history_cleaned=True)
(OUT / 'upload_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
