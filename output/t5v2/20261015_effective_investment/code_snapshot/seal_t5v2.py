"""Seal final documentation changes and verification code in the t5v2 manifest."""
import json,shutil
from pathlib import Path
import build_t5v2 as b
ROOT,OUT=b.ROOT,b.OUT
backup=OUT/'documents_before_final';backup.mkdir(exist_ok=False)
changes={}
for name in ['README.md','code/model_v2/t5v2_README.md']:
    p=ROOT/name;shutil.copy2(p,backup/name.replace('/','__'));changes[name]={'before':b.sha(p)}
    text=p.read_text(encoding='utf-8')
    if name=='README.md':
        text=text.replace('决策基准读取于2026-10-15 17:04，前景、曲线、预算及物流核对至16:34','t5v2个人试验基准读取于2026-10-15 19:11并于19:46恢复核验；前景及物流沿用已核归档')
        text=text.replace('自动支出→有效横轴映射未证实，t5v0效率ρ不可识别。先补最终投入历史及存量机制，避免重复叠加','t5v2已用网页单字段试验识别正式5投入斜率及历史截距，采用研发0.75×当期＋0.50×上期、运营当期＋0.35×上期；上期权重解释、更早存量及正式6迁移未独立识别。t5v0效率ρ仍不可识别')
    else:
        text+='\n只读验收：\n\n```powershell\npython code/model_v2/verify_t5v2.py '+OUT.relative_to(ROOT).as_posix()+'\n```\n'
    p.write_text(text,encoding='utf-8');changes[name]['after']=b.sha(p)
b.save('document_changes_final.json',changes)
for name in ['code/model_v2/verify_t5v2.py','work/seal_t5v2.py']:
    shutil.copy2(ROOT/name,OUT/'code_snapshot'/Path(name).name)
with (OUT/'work_log.md').open('a',encoding='utf-8') as f:
    f.write('\n\n最终只读验收：64情景回放、126项候选字段、三套42字段敏感性、全部报告链接与输出哈希通过。新增独立verify_t5v2入口并冻结源码；当前状态文档已备份当前磁盘后更新，改前/改后哈希保留。\n')
manifest=b.read(OUT/'version_manifest.json')
manifest['outputs']={p.relative_to(OUT).as_posix():b.sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='version_manifest.json'}
manifest['runtime']['code/model_v2/verify_t5v2.py']=b.sha(ROOT/'code/model_v2/verify_t5v2.py')
manifest['documents_final']=changes
b.save('version_manifest.json',manifest)
print('SEALED',OUT)
