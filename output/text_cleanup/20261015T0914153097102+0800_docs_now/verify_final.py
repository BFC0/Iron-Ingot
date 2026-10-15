"""Verify document links, including Codex source-line targets, without running models."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]

def load(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def resolve(document, target):
    target = unquote(target.strip().strip('<>'))
    if re.match(r'^[a-z]+://', target, re.I):
        return None
    target, _, anchor = target.partition('#')
    line = re.search(r':(\d+)$', target)
    if line:
        target = target[:line.start()]
    path = (ROOT / document).parent / target if target else ROOT / document
    assert path.is_file(), (document, target)
    if line:
        assert 1 <= int(line[1]) <= len(path.read_text(encoding='utf-8-sig').splitlines())
    if anchor and path.suffix.lower() == '.md':
        headings = re.findall(r'^#{1,6}\s+(.+)$', path.read_text(encoding='utf-8-sig'), re.M)
        assert anchor in [re.sub(r'[^\w\-\s]', '', h.lower()).replace(' ', '-') for h in headings], (document, anchor)
    return True

assert resolve('README.md', 'code/build_model_inputs.py:11')
assert resolve('README.md', '#项目目标与执行边界')
count = 0
for p, expected in load('after_hashes.json').items():
    assert digest(ROOT / p) == expected, p
    assert digest(OUT / 'before' / p) == load('before_hashes.json')[p]
    for target in re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', (ROOT / p).read_text(encoding='utf-8-sig')):
        if resolve(p, target):
            count += 1
for p, expected in load('protected_hashes.json').items():
    assert digest(ROOT / p) == expected, p
result = {'status': 'PASS', 'document_count': len(load('after_hashes.json')), 'local_links_checked': count, 'broken_links': 0, 'source_line_link_verified': True, 'backups_and_final_hashes': True, 'protected_evidence_unchanged': True, 'prior_link_finding': '初次检查将合法的源文件:11行号误当文件名；已核实文件存在且第11行有效，无需修改文档。', 'model_training_rerun': False, 'word_updated': False, 'live_platform_checked': False, 'automation': '读取时已为PAUSED，本次未更改定时任务。'}
with (OUT / 'acceptance_final.json').open('x', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
with (OUT / 'work_log.md').open('a', encoding='utf-8') as f:
    f.write(f'\n最终追加验收：{count}条本地链接（含源文件行号）全部通过。初检1处提示是合法的“文件:11”行号链接，已验证并更正检查结论，原检查记录保留。文档改后哈希、备份及受保护来源再次一致。权威最终验收见[acceptance_final.json](acceptance_final.json)。定时任务读取状态已为PAUSED，无需再次停用。\n')
print(json.dumps(result, ensure_ascii=False))
