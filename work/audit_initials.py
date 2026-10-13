"""One-off privacy cleanup; preserve source evidence and record changed hashes."""
import ast
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
source = ROOT / 'code/archive_and_report.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
identities = next(ast.literal_eval(n.value) for n in ast.walk(tree)
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'identities' for t in n.targets))
names = {}
for path in ROOT.glob('raw/*checklist*.json'):
    snapshot = json.loads(path.read_text(encoding='utf-8-sig')).get('snapshot', '')
    for length in (4, 3, 2):
        for match in re.finditer(r'(?=([\u4e00-\u9fff](?:[ \t]*[\u4e00-\u9fff]){' + str(length - 1) + r'}))', snapshot):
            candidate = re.sub(r'[ \t]', '', match.group(1))
            key = hashlib.sha256(candidate.encode()).hexdigest()
            if key in identities:
                names[candidate] = identities[key]
assert len(names) == len(identities)
patterns = [(re.compile(r'[ \t]*'.join(map(re.escape, name))), initials)
            for name, initials in names.items()]


def redact(text):
    for pattern, initials in patterns:
        text = pattern.sub(initials, text)
    for name, initials in names.items():
        text = text.replace(name.encode('unicode_escape').decode(), initials)
    return text


def sha(data):
    return hashlib.sha256(data).hexdigest()


def evidence(path):
    if any(p in {'raw', 'sources', 'quarantine'} for p in path.relative_to(ROOT).parts):
        return True
    if path.suffix == '.json':
        try:
            doc = json.loads(path.read_text(encoding='utf-8-sig'))
            return isinstance(doc, dict) and isinstance(doc.get('snapshot'), str)
        except (ValueError, UnicodeError):
            pass
    if path.suffix == '.txt' and path.with_suffix('.json').exists():
        return evidence(path.with_suffix('.json'))
    return False


stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
out = ROOT / 'output/name_audit' / stamp
out.mkdir(parents=True, exist_ok=False)
log = out / 'work_log.md'
with log.open('x', encoding='utf-8') as f:
    f.write('# 姓名脱敏核验\n\n' + stamp + '（北京时间）\n\n'
            '不要输出真名，姓名统一用首字母替代。\n\n'
            '用户授权：核验项目并按README清理姓名；已明确选择保留原始证据，只清理文档、代码、报告和导出，标记原件不宜分享。\n'
            '进行中：扫描当前及历史交付文本、代码与文件名；只替换姓名，不重新训练或调整决策。记录旧/新哈希，旧哈希清单保留为历史。\n')

runtime = '''
def redact_names(text):
    # shortcut: known project roster only; extend hashes when new members appear.
    identities = HASHES
    matches = []
    for length in (4, 3, 2):
        for match in re.finditer(r'(?=([\u4e00-\u9fff](?:[ \\t]*[\u4e00-\u9fff]){' + str(length - 1) + r'}))', text):
            candidate = match.group(1)
            key = hashlib.sha256(re.sub(r'[ \\t]', '', candidate).encode('utf-8')).hexdigest()
            if key in identities:
                matches.append((match.start(), match.start() + len(candidate), identities[key]))
    for start, end, initials in sorted(set(matches), reverse=True):
        text = text[:start] + initials + text[end:]
    return text

'''.replace('HASHES', repr({sha(k.encode()): v for k, v in names.items()}))

files = [p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts]
changed, originals, checked, unsupported = [], [], [], []
for path in files:
    rel = path.relative_to(ROOT).as_posix()
    if out in path.parents:
        continue
    assert redact(path.name) == path.name, 'Name in filename requires a linked-path migration'
    data = path.read_bytes()
    if evidence(path):
        originals.append({'path': rel, 'sha256': sha(data), 'shareable': False})
        continue
    if path.suffix == '.docx':
        with ZipFile(path) as z:
            text = '\n'.join(z.read(n).decode('utf-8') for n in z.namelist() if n.endswith('.xml'))
        assert redact(text) == text, 'DOCX requires an OOXML edit'
        checked.append(rel)
        continue
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError:
        unsupported.append(rel)
        continue
    updated = redact(text)
    if path.name == 'archive_and_report.py' and 'def redact_names(' not in updated:
        updated = updated.replace('def table_rows(snapshot):', runtime + 'def table_rows(snapshot):\n    snapshot = redact_names(snapshot)')
    if path.name == 'formal_update_report.py':
        updated = updated.replace("    initials = {'JY': 'JY', 'XXL': 'XXL', 'SRQ': 'SRQ', 'PYT': 'PYT'}\n", '')
        updated = updated.replace("header=[initials.get(cell.replace(' ', ''), cell) for cell in header]", 'header=header')
    if updated != text:
        if path.suffix == '.json':
            json.loads(updated)
        if path.suffix == '.py':
            ast.parse(updated)
        result = (b'\xef\xbb\xbf' if data.startswith(b'\xef\xbb\xbf') else b'') + updated.encode('utf-8')
        with (out / 'changes.jsonl').open('a', encoding='utf-8') as journal:
            journal.write(json.dumps({'path': rel, 'before_sha256': sha(data), 'after_sha256': sha(result)}) + '\n')
        path.write_bytes(result)
        changed.append({'path': rel, 'before_sha256': sha(data), 'after_sha256': sha(result)})
    checked.append(rel)

# Validate the shared parser against unchanged raw evidence and original column positions.
import sys
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import redact_names, table_rows
from formal_update_report import personal_inputs
for name, initials in names.items():
    assert redact_names(name) == initials
    assert redact_names(' '.join(name)) == initials
assert redact_names('泰国, 美元 123.45 营销团队') == '泰国, 美元 123.45 营销团队'
checklist = next(p for p in ROOT.glob('output/formal_update/*_sources/formal2_current_checklist.json'))
current = personal_inputs(checklist)
assert current['person'] == 'PYT' and current['header'] == ['营销团队', 'JY', 'XXL', 'SRQ', 'PYT'], current['header']
assert all(sha((ROOT / x['path']).read_bytes()) == x['sha256'] for x in originals)
remaining = [p for p in checked if (ROOT / p).suffix != '.docx' and redact((ROOT / p).read_text(encoding='utf-8-sig')) != (ROOT / p).read_text(encoding='utf-8-sig')]
assert not remaining, remaining
report = {'time_beijing': stamp, 'changed': changed, 'evidence_not_for_sharing': originals,
          'checked_files': checked, 'binary_files_for_separate_review': unsupported,
          'checks': {'remaining_known_names': remaining, 'original_hashes_unchanged': True,
                     'parser_initials_and_spacing': True, 'personal_column': current['personal_column']},
          'scope': 'Known project roster; source evidence is deliberately excluded; historical hashes are not rewritten.'}
with (out / 'audit.json').open('x', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
with log.open('a', encoding='utf-8') as f:
    f.write(f'\n文本清理完成：修改{len(changed)}个文件；检查{len(checked)}个交付文件；保留{len(originals)}份原始证据及副本。已识别姓名残留为0，原件哈希不变；JSON/Python语法检查通过；原始表头解析为首字母，个人列定位通过。\n'
            '哈希说明：被脱敏交付文件的旧哈希已失效；audit.json逐文件保留前后哈希，不覆盖历史哈希记录。\n')
print(json.dumps({'audit_directory': out.as_posix(), 'changed_files': len(changed), 'checked_files': len(checked), 'preserved_evidence': len(originals), 'binary_review': unsupported}, ensure_ascii=False))
