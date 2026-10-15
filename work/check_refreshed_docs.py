from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / (ROOT/'work/document_refresh_active.txt').read_text(encoding='utf-8')
files = sorted(set(ROOT.glob('*.md')) | set((ROOT/'模型说明').glob('*.md')) | set((ROOT/'code').rglob('*.md')))
rows = []
for p in files:
    for label, target in re.findall(r'\[([^\]]*)\]\(([^)]+)\)',p.read_text(encoding='utf-8-sig')):
        target = target.strip('<>')
        if target.startswith(('http:', 'https:', 'codex:', 'app:')):
            continue
        name, _, fragment = target.partition('#')
        name = re.sub(r':\d+$','',name)
        q = p.parent/name if name else p
        if not q.exists():
            rows.append({'file':p.relative_to(ROOT).as_posix(),'target':target,'reason':'missing'})
        elif fragment and q.suffix == '.md':
            headings = re.findall(r'^#{1,6} (.+)$',q.read_text(encoding='utf-8-sig'),re.M)
            anchors = [re.sub(r'[^\w\- ]','',h.lower()).replace(' ','-') for h in headings]
            if fragment not in anchors:
                rows.append({'file':p.relative_to(ROOT).as_posix(),'target':target,'reason':'anchor'})
(OUT/'link_findings.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False,indent=2))

