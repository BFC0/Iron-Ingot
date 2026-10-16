"""Polish field labels before final delivery and repeat integrity verification."""
import hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/(ROOT/'work/t5v1_active_run.txt').read_text(encoding='utf-8-sig').strip()
read=lambda f:json.loads(f.read_text(encoding='utf-8'))
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
save=lambda f,v:f.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report=OUT/'report.md';before=sha(report)
backup=OUT/'documents_before/report_before_label_polish.md';assert not backup.exists();shutil.copy2(report,backup)
text=report.read_text(encoding='utf-8')
rows=read(OUT/'decisions.json')
for r in rows:
    if r['plan']!='稳健利润候选':continue
    label='／'.join(str(v) for v in [r['product'],r['label']] if v)
    text=text.replace('| '+label+' | '+r['unit']+' |','| '+r['section']+'／'+label+' | '+r['unit']+' |')
for product,models in read(OUT/'marketing_models_formal4.json').items():
    for name,v in models.items():
        old=f'| {product}／{name} | {v["n"]} | {v["beta_general"]:.8f} | {v["beta_designer"]:.8f} | 见训练原表 | 见训练原表 |'
        new=f'| {product}／{name} | {v["n"]} | {v["beta_general"]:.8f} | {v["beta_designer"]:.8f} | {v["old_nested_market_mean_rmse"]:.6f} | {v["nested_market_mean_rmse"]:.6f} |'
        assert old in text;text=text.replace(old,new)
report.write_text(text,encoding='utf-8')
save(OUT/'report_polish_hashes.json',dict(before=before,after=sha(report),backup=str(backup.relative_to(ROOT))))
for path in [Path(__file__),ROOT/'work/finalize_t5v1.py']:shutil.copy2(path,OUT/'code_snapshot'/path.name)
assert len({r['key'] for r in rows})==42 and len(rows)==84
for target in re.findall(r'\]\(([^)]+)\)',text):assert (report.parent/target).resolve().exists(),target
audit=read(OUT/'t5v0b_preservation_audit.json')
for item in audit['checks']:assert sha(ROOT/item['path'])==item['sha256']
manifest=read(OUT/'version_manifest.json')
manifest['outputs']={str(f.relative_to(OUT)):sha(f) for f in OUT.rglob('*') if f.is_file() and f.name!='version_manifest.json'}
save(OUT/'version_manifest.json',manifest)
for rel,digest in manifest['outputs'].items():assert sha(OUT/rel)==digest
for rel,digest in manifest['source_code'].items():assert sha(ROOT/rel)==digest
print('PASS: 42 fields, 84 records, original t5v0b 64 hashes, complete t5v1 manifest')
