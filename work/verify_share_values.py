"""Verify privacy filtering preserved model numbers and Python numeric literals."""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = Path(sys.argv[1]).resolve()
assert REPO.is_relative_to(ROOT / 'output/share_upload')
manifest = json.loads((REPO / 'SHARE_MANIFEST.json').read_text(encoding='utf-8'))

def numbers(value):
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers(v)]
    return [value] if isinstance(value, (int, float, bool)) else []

assert numbers({'x': [1, 'name', True, 2.5]}) == [1, True, 2.5]
checked = 0
for item in manifest['files']:
    rel = item['path']
    suffix = Path(rel).suffix
    if suffix not in {'.json', '.py'}:
        continue
    original = (ROOT / rel).read_text(encoding='utf-8-sig')
    shared = (REPO / rel).read_text(encoding='utf-8-sig')
    if suffix == '.json':
        assert numbers(json.loads(original)) == numbers(json.loads(shared)), rel
    else:
        a, b = ast.parse(original), ast.parse(shared)
        assert [n.value for n in ast.walk(a) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, bool))] == [n.value for n in ast.walk(b) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, bool))], rel
    checked += 1
result = {'numeric_values_preserved': True, 'checked_json_python_files': checked}
(REPO.parent / 'numeric_verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
