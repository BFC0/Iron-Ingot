"""只读核验已整理文档，补充原整理脚本的验收记录。"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/text_cleanup/20261013T110453410933+0800'
LOG = OUT / 'work_log.md'
NOW = datetime.now(timezone(timedelta(hours=8)))

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(name):
    return (ROOT / name).read_text(encoding='utf-8-sig')

before = {str(p.relative_to(OUT / 'before')): digest(p)
          for p in (OUT / 'before').rglob('*') if p.is_file()}
names = list(before) + ['建模重审与验收要求.md', 'history/项目记录_整理前_20261013.md']
texts = {name: read(name) for name in names}
protected = {str(p.relative_to(ROOT)): digest(p)
             for folder in ('raw', 'sources', 'quarantine', 'code', 'history')
             for p in (ROOT / folder).rglob('*') if p.is_file()
             and str(p.relative_to(ROOT)) != 'history/项目记录_整理前_20261013.md'}
# 原脚本在链接检查失败之前已通过编辑前后受保护哈希比较。
with LOG.open('a', encoding='utf-8') as f:
    f.write('\n核验更正：原件/业务代码/既有历史哈希比较先已通过，随后本地链接检查把合法的文件行号“:11”当成文件名而失败。现按应用文件链接语法去除行号再检查；未重跑文档改写。\n')
source = read('work/tidy_project_text.py').split('# 自检只核验文档变化；不导入或重跑任何业务模型。', 1)[1]
import re
exec(compile(source, str(ROOT / 'work/tidy_project_text.py'), 'exec'))
