from pathlib import Path
import ast
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from zipfile import ZipFile
from lxml import etree
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / (ROOT/'work/document_refresh_active.txt').read_text(encoding='utf-8')
files = sorted(set(ROOT.glob('*.md')) | set((ROOT/'模型说明').glob('*.md')) | set((ROOT/'code').rglob('*.md')))
before = json.loads((OUT/'before_hashes.json').read_text(encoding='utf-8'))
tree = ast.parse((ROOT/'code/archive_and_report.py').read_text(encoding='utf-8'))
identities = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='identities' for t in n.targets))
def has_known_name(text):
    for length in (4,3,2):
        for match in re.finditer(r'(?=([\u4e00-\u9fff](?:[ \t]*[\u4e00-\u9fff]){'+str(length-1)+r'}))',text):
            candidate = re.sub(r'[ \t]','',match.group(1))
            if hashlib.sha256(candidate.encode('utf-8')).hexdigest() in identities:
                return True
    return False
assert not any(has_known_name(p.read_text(encoding='utf-8')) for p in files)
with ZipFile(ROOT/'预测模型与变量说明.docx') as z:
    xml = z.read('word/document.xml')
    assert not has_known_name(xml.decode('utf-8'))
    document = etree.fromstring(xml)
ns = {'m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
with ZipFile(OUT/'before/预测模型与变量说明.docx') as z:
    old_doc = etree.fromstring(z.read('word/document.xml'))
old_math = Counter(''.join(e.itertext()) for e in old_doc.xpath('//m:oMath',namespaces=ns))
new_math = Counter(''.join(e.itertext()) for e in document.xpath('//m:oMath',namespaces=ns))
assert not (old_math-new_math), 'Existing native formula content was lost'
assert len(document.xpath('//m:oMath',namespaces=ns)) == 134

# Complete-precision historical coefficient table rows must survive unchanged.
preserved_parameter_rows = 0
for p in files:
    backup = OUT/'before'/p.relative_to(ROOT)
    if not backup.exists():
        continue
    t = p.read_text(encoding='utf-8')
    for line in backup.read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('|') and ('{"' in line or '::/' in line):
            assert line in t, str(p)+' lost a saved parameter row'
            preserved_parameter_rows += 1

findings = json.loads((OUT/'link_findings.json').read_text(encoding='utf-8'))
assert not findings, findings
assert not list(OUT.rglob('*.html'))
assert '{{time}}' in (ROOT/'code/要求说明_模板.md').read_text(encoding='utf-8')
assert '## HTML报告与一致性验收' not in (ROOT/'建模重审与验收要求.md').read_text(encoding='utf-8')

pdf = pdfium.PdfDocument(OUT/'word_qa/preview.pdf')
for i in range(len(pdf)):
    pdf[i].render(scale=1.5).to_pil().save(OUT/'word_qa'/f'page-{i+1}.png')
after_files = files + [ROOT/'预测模型与变量说明.docx']
changes = []
for p in after_files:
    rel = p.relative_to(ROOT).as_posix()
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    assert before.get(rel) != sha, 'A current document was not updated: '+rel
    changes.append({'path':rel,'before':before.get(rel),'after':sha,'new':rel not in before})
(OUT/'document_changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
checks = {'time_beijing':datetime.now(timezone(timedelta(hours=8))).isoformat(),
          'markdown_documents':len(files),'word_documents':1,
          'new_markdown_documents':sum(1 for c in changes if c['new']),
          'all_current_documents_updated':True,'local_file_links_and_section_anchors':True,
          'historical_full_precision_parameter_rows_preserved':preserved_parameter_rows,
          'known_roster_names_absent_in_markdown_and_word':True,
          'old_word_native_formula_content_preserved':True,
          'word_native_equations':134,'word_pages':len(pdf),
          'new_html_reports':0,'platform_actions':0,'training_runs':0,
          'scope':'Current root/model/code docs; archived output reports, original evidence and history are unchanged by this task.',
          'limitations':['No live platform status check','No new training or model performance validation','Archived reports remain versioned history','Name check covers the confirmed project roster']}
(OUT/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'work_log.md').open('a',encoding='utf-8') as f:
    f.write('\n## 完成与验收\n\n'+checks['time_beijing']+'。更新'+str(len(files))+'份Markdown（含2份新增t4v1a说明）及1份Word。现状集中于README，模型索引按业务分组，专题按范围、公式、输入输出、参数、来源与历史排列；目录入口、运行说明、当前证据及报告格式要求统一。\n\n所有本地文件链接与章节锚点、已确认人员姓名哈希扫描、'+str(preserved_parameter_rows)+'行完整精度参数保留检查通过；Word旧原生公式全部保留，当前134个原生公式、8页。打包渲染器缺少LibreOffice，改用获准的本机Word后台PDF预览并生成逐页PNG。\n\n未访问平台、未重训、未修改业务代码、未新建HTML报告；历史output报告及原件不改写。最新训练t4v1与冻结应用t4v1a、研究候选各自边界保持，未解决经营链缺口仍明确列示。完整变更及哈希见document_changes.json；验收见verification.json。\n')
print(json.dumps(checks,ensure_ascii=False,indent=2))
