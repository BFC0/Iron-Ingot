import ast
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--run',default='20261011T204411978414+0800')
parser.add_argument('--csv',default='cesim_model_v2_filtered (1).csv')
parser.add_argument('--country')
parser.add_argument('--model',action='append')
args=parser.parse_args()
run = root / 'output/model_v2' / args.run
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['status'] == 'COMPLETE_OFFLINE_AUDIT_WITH_EXPLICIT_GAPS'
for name, expected in manifest['result_hashes'].items():
    assert digest(run / name) == expected, name
snapshot = root / 'output/model_v2/20261011T193318735151+0800/snapshot/protected_hashes.json'
protected = json.loads(snapshot.read_text(encoding='utf-8'))
authorized_docs = {'README.md', '练习与正式_已知数据差异.md','预测模型与变量说明.md','Cesim_任务要求与当前情况说明.md','原生键盘标准操作.md'}
for name, expected in protected.items():
    if name not in authorized_docs:
        assert digest(root / name) == expected, name
for p in (root / 'code/model_v2').glob('*.py'):
    ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
    assert not any(line.rstrip() != line for line in p.read_text(encoding='utf-8').splitlines()), p
records = json.loads((run / 'report_data.json').read_text(encoding='utf-8'))
models=set(args.model or ['A-old-frozen','B-old-frozen'])
expected = [r for r in records if r.get('context_id') == 'M5_P1_FORMAL1_VISIBLE' and r.get('model') in models and (args.country is None or r.get('country')==args.country)]
download = Path.home() / 'Downloads' / args.csv
actual = list(csv.DictReader(download.open(encoding='utf-8-sig', newline='')))
assert len(actual) == len(expected) == 40
for a, e in zip(actual, expected):
    for field in a:
        v = e.get(field)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            assert abs(float(a[field]) - v) < 1e-12, (field, a[field], v)
        elif isinstance(v, (dict, list)):
            assert json.loads(a[field]) == v, field
        elif isinstance(v, bool):
            assert a[field] == str(v).lower(), field
        elif v is not None:
            assert a[field] == str(v), (field, a[field], v)
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
out = root / 'output/model_v2' / (stamp + '_delivery_qa')
out.mkdir()
qa = dict(run_id=manifest['run_id'], result_hashes_verified=len(manifest['result_hashes']),
          original_files_unchanged=len(protected) - len(authorized_docs),
          authorized_document_exceptions=sorted(authorized_docs), python_ast_and_whitespace='PASS',
          browser_checks=dict(shared_filter_rows=40, model_colors=['#126b87', '#9b4520','#6d498c','#3f7051'][:len(models)],
              wide_viewport=[1440,950], narrow_viewport=[390,844], narrow_no_horizontal_overflow=True,
              csv_rows_verified=40, csv_numeric_tolerance=1e-12, console_errors=[], viewport_reset=True,
              print_css_verified=True, print_preview='NOT_RETESTED: prior print click timed out; page remained usable',
              physical_or_pdf_print='NOT_ATTEMPTED'),
          personal_trial='0→1→0; all original personal values restored; further trials stopped after concurrent member changes',
          search_gate='NOT_PASSED', report_sha256=digest(run/'report.html'), csv_sha256=digest(download))
(out / 'verification.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding='utf-8')
print(out)
print(f'PASS: immutable outputs, {len(protected)-len(authorized_docs)} protected originals, Python syntax/whitespace, 40 exported records')
