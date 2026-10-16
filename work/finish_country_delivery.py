"""Finish the current report update after its self-link check."""
import json,sys,shutil,re
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work'),str(ROOT/'work/python_packages')]
import solve_formal5_full as base
OUT=ROOT/(ROOT/'work/t5v1_active_run.txt').read_text(encoding='utf-8-sig').strip()
CHANGE=sorted((OUT/'country_update').glob('*/before'))[-1].parent
read=base.read
save=lambda name,v:(CHANGE/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
write=lambda name,v:(OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
result=read(OUT/'full_result.json');text=(OUT/'report.md').read_text(encoding='utf-8');backups=CHANGE/'before'
changed=[f.name for f in backups.iterdir()];hashes={name:{'before':base.sha(backups/name)} for name in changed}
source=ROOT/'work/add_t5v1_country.py'
suffix=source.read_text(encoding='utf-8').split("audit=read(OUT/'t5v0b_preservation_audit.json')",1)[1]
exec(compile("audit=read(OUT/'t5v0b_preservation_audit.json')"+suffix,str(source),'exec'),dict(globals(),__file__=str(source),plan=read(CHANGE/'country_result.json'),evaluations=read(CHANGE/'country_result.json')['evaluations']))
