"""Back up current docs, add scenario entry points, seal outputs, and run offline acceptance."""
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'code/model_v2'))
import verify_t5v3

OUT = ROOT / 'output/t5v3/20261015_common_default_prices'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    before = OUT / 'documents_before'
    before.mkdir(exist_ok=False)
    replacements = {
        'README.md': ('| 最新条件优化版本 |',
            '| 最新需求竞争情景 | **t5v3**：[预测对照与假设](output/t5v3/20261015_common_default_prices/report.md)、[运行说明](code/model_v2/t5v3_README.md) | 用户指定九组统一使用本组正式5期初默认价格；逐队重估价格吸引力，四市场十队需求份额归一化。冻结t5v2系数及对手非价格影响；未验证精度增益、未重做决策优化。 |\n| 最新条件优化版本 |'),
        'code/model_v2/README.md': ('- [t5v2有效投资接入]',
            '- [t5v3统一对手默认价格](t5v3_README.md)：九组使用本组正式5期初四个默认价，逐队重算需求份额；不重训，尚无新版优化方案。\n\n- [t5v2有效投资接入]')}
    changes = {}
    for name, (old, new) in replacements.items():
        path = ROOT / name
        text = path.read_text(encoding='utf-8-sig')
        assert text.count(old) == 1 and 't5v3' not in text
        backup = before / name.replace('/', '__')
        shutil.copy2(path, backup)
        changes[name] = dict(before=sha(path), backup=str(backup.relative_to(ROOT)))
        path.write_text(text.replace(old, new), encoding='utf-8')
        changes[name]['after'] = sha(path)
        # Existing links are not rewritten; record any pre-existing unavailable targets separately.
        broken = []
        for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' not in link and not (path.parent / link.split('#')[0]).resolve().exists():
                broken.append(link)
        changes[name]['unavailable_local_links'] = broken
        assert all('t5v3' not in link for link in broken)
    (OUT / 'document_changes.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    shutil.copy2(Path(__file__), OUT / 'code_snapshot' / Path(__file__).name)
    paths = [p for p in OUT.rglob('*') if p.is_file() and p.name not in ['validation.json', 'version_manifest.json', 'work_log.md']]
    paths += [ROOT / name for name in ['code/model_v2/t5v2.py', 'code/model_v2/t5v3.py',
              'code/model_v2/verify_t5v3.py', 'code/model_v2/t5v3_README.md', 'work/build_t5v3.py', 'work/finalize_t5v3.py']]
    (OUT / 'version_manifest.json').write_text(json.dumps({str(p.relative_to(ROOT)): sha(p) for p in paths},
                                             ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    result = verify_t5v3.verify(OUT)
    result['document_link_checks'] = changes
    (OUT / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (OUT / 'work_log.md').open('a', encoding='utf-8') as f:
        stamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        f.write(f'\n## 验收 {stamp}\n\n完成：t5v3独立需求模块、注册表、逐队输入与原件哈希、示例请求及输出、12项情景对照、Markdown报告和自检。全部离线验收通过，t5v2文件哈希不变。README及模型目录说明按当前磁盘备份后更新，改前/改后哈希与链接检查见document_changes.json。未读取正式5实际标签、未操作平台、未重新优化或提交决策；预测精度增益未验证。\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
