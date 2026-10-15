from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / (ROOT/'work/document_refresh_active.txt').read_text(encoding='utf-8')
changes = {
    '项目结构.md': [('截至正式2覆盖750/750，财务待核与同期HTML冲突另列','截至正式2覆盖750/750；后续60项财务配对已通过，旧附加列归属及拒绝/冲突原件保留'),
                  ('`t3v0/`、`t3v1/`、`t4v0/` | 各版本独立训练、参数及验收；t4v0最新交付使用具体现有报告，旧版本保留','`t3v0/`、`t3v1/`、`t4v0/`、`t4v1/`、`t4v1a/` | 独立版本；t4v1完整训练、t4v1a冻结应用，历史版本保留；去重参数在`t4v1_deduplicated/`')],
    '模型迁移与预估验证.md': [('最新原生需求修改只保存了','该历史原生需求修改只保存了'),('本批次尚未归档正式实际','2026-10-11该研究批次当时尚未归档正式实际')],
    'code/model_v2/t4v0_README.md': [('最新训练目录：','t4v0历史训练目录：'),('HTML脚本核验使用','历史HTML脚本核验使用')],
    'code/model_v2/t3v0_README.md': [('HTML静态脚本核验：','历史HTML静态脚本核验：')],
    'code/model_v2/t3v1_README.md': [('最新训练：','t3v1历史训练：'),('最新连接件扩展：','该版本连接件扩展：')],
}
for rel, replacements in changes.items():
    p = ROOT/rel
    t = p.read_text(encoding='utf-8')
    for a,b in replacements:
        t = t.replace(a,b)
    p.write_text(t,encoding='utf-8')
p = ROOT/'code/t2v0_um/README.md'
t = p.read_text(encoding='utf-8-sig')
title,body = t.split('\n',1)
p.write_text(title+'\n\n更新：2026-10-14（北京时间）。本文仅说明练习2组件及正式2迁移的历史版本；最新实际训练t4v1及非重训应用t4v1a见[代码目录](../README.md)。当前29类清单移除T2V0重复组合登记，历史功能与原参数仍保留。以下命令、给定值及门槛均按本版本范围使用，不作为正式4整体预测入口。\n'+body,encoding='utf-8')

# Word's existing native renderer is the fallback when packaged LibreOffice is unavailable.
script = (ROOT/'output/model_word_qa/export_pdf.ps1').read_text(encoding='utf-8-sig')
script = script.replace("$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\\..'))", "$taskRoot = '"+str(ROOT).replace("'","''")+"'")
(OUT/'word_qa/export_pdf.ps1').write_text(script,encoding='utf-8-sig')

# Names: reuse the already-confirmed audit's names locally, never print them.
audit_path = ROOT/'output/name_audit/20261011T233048320800+0800/audit.json'
audit = json.loads(audit_path.read_text(encoding='utf-8'))
print('name audit top-level fields:', list(audit) if isinstance(audit,dict) else 'list')
print('renderer:',str(OUT/'word_qa/export_pdf.ps1'))
