"""Reuse existing exporter while keeping this task's QA independent of old artifacts."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / (ROOT/'work/document_refresh_active.txt').read_text(encoding='utf-8')
source = (ROOT/'code/export_model_docx.py').read_text(encoding='utf-8')
source = source.replace("ROOT = Path(__file__).resolve().parents[1]", 'ROOT = Path('+repr(str(ROOT))+')')
source = source.replace("QA = ROOT / 'output/model_word_qa'", 'QA = Path('+repr(str(OUT/'word_qa'))+')')
source = source.replace("    if line.startswith('# '):", "    if line.startswith('**主题导航：**'): continue\n    if line.startswith('# '):")
source = source.replace('formula=part[1:-1]; assert formula in FORMULAS,formula', "formula=part[1:-1]\n            if formula not in FORMULAS:\n                run=p.add_run(formula); fonts(run._r.get_or_add_rPr()); continue")
source = source.replace("            if target.startswith('C:/'): target='file:///'+target", "            if target.startswith('C:/'): target='file:///'+target\n            elif not target.startswith(('http:', 'https:')): target=SOURCE.parent.joinpath(target).as_uri()")
source = source.replace("def rich(p,text):", "def rich(p,text):\n    text=text.replace('**','')")
(OUT/'word_builder.py').write_text(source,encoding='utf-8')
exec(compile(source,str(OUT/'word_builder.py'),'exec'))
