"""Build a fresh, audited sharing repository without local Git history."""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'code'))
from archive_and_report import redact_names

audit = json.loads((ROOT / 'output/name_audit/20261011T233048320800+0800/audit.json').read_text(encoding='utf-8'))
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
out = ROOT / 'output/share_upload' / stamp
repo = out / 'repository'
repo.mkdir(parents=True, exist_ok=False)
log = out / 'work_log.md'
with log.open('x', encoding='utf-8') as f:
    f.write('# 分享仓库上传记录\n\n' + stamp + '（北京时间）\n\n'
            '不要输出真名，姓名统一用首字母替代。\n\n'
            '用户授权：全部适宜分享文件上传新Git仓库；指定名称Iron Ingot、公开、无description；GitHub名称使用Iron-Ingot。\n'
            '进行中：独立复制已核验交付文件，排除原始证据、历史截图、缓存、原Git历史和工具下载。副本移除本机用户路径；不改原项目数值、模型或来源。\n')

excluded = {x['path'] for x in audit['evidence_not_for_sharing']}
paths = set(audit['checked_files']) - excluded
paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'output/name_audit').rglob('*') if p.is_file())
paths.add('output/model_word_qa/preview.pdf')
secrets = re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN .*PRIVATE KEY-----|(?:password|passwd|access_token|refresh_token|api_key|authorization|cookie)\s*["\']?\s*[:=]\s*["\'][^"\']{8,}', re.I)
manifest = []
for rel in sorted(paths):
    source = ROOT / rel
    assert source.is_file() and source.resolve().is_relative_to(ROOT)
    assert not any(p in {'raw', 'sources', 'quarantine', '.git', '__pycache__', 'github_cli', 'share_upload'} for p in source.relative_to(ROOT).parts)
    original = source.read_bytes()
    data = original
    if source.suffix not in {'.docx', '.pdf'}:
        text = data.decode('utf-8-sig')
        assert redact_names(text) == text, rel
        assert not secrets.search(text), 'Potential secret in ' + rel
        # Keep project-relative references; external local paths become placeholders.
        for prefix in (str(ROOT) + '\\', ROOT.as_posix() + '/', str(ROOT).replace('\\', '\\\\') + '\\\\'):
            text = text.replace(prefix, '')
        for prefix in (str(ROOT), ROOT.as_posix(), str(ROOT).replace('\\', '\\\\')):
            text = text.replace(prefix, '.')
        text = re.sub(r'C:(?:/|\\\\|\\)Users(?:/|\\\\|\\)17765', '<LOCAL_USER_DIR>', text, flags=re.I)
        text = text.replace('LOCAL_PROJECT_OWNER', 'LOCAL_PROJECT_OWNER')
        assert not re.search(r'C:(?:/|\\)Users', text, re.I), 'Personal local path still present in ' + rel
        if source.suffix == '.json':
            json.loads(text)
        data = (b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'') + text.encode('utf-8')
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as f:
        f.write(data)
    assert target.stat().st_size < 100 * 1024 * 1024
    manifest.append({'path': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'local_paths_removed': data != original})

notice = ('# Iron Ingot 分享范围\n\n'
          '本仓库包含已脱敏文档、代码、模型结果、报告及导出，姓名使用首字母。\n\n'
          '原始网页快照、原始附件、历史截图、缓存及原项目Git历史未上传。报告中指向这些原件的链接会缺失；依赖原件的采集、训练和来源哈希验证无法仅凭本仓库完整复现。已有模型及报告可查阅，本次未重新训练模型。\n\n'
          '本机绝对路径已改为项目相对引用或<LOCAL_USER_DIR>占位。历史哈希记录保持原值，不能代表分享副本的当前哈希；当前文件哈希见SHARE_MANIFEST.json。\n')
(repo / 'SHARING.md').write_text(notice, encoding='utf-8')
with (repo / 'SHARE_MANIFEST.json').open('x', encoding='utf-8') as f:
    json.dump({'time_beijing': stamp, 'files': manifest, 'excluded_evidence_count': len(excluded)}, f, ensure_ascii=False, indent=2)
readme = repo / 'README.md'
text = readme.read_text(encoding='utf-8')
readme.write_text('> 公开分享副本：阅读[分享范围与复现边界](SHARING.md)。原始证据与历史截图未上传。\n\n' + text, encoding='utf-8')
# Refresh README hash after adding the sharing notice.
manifest = [dict(x, bytes=(repo / x['path']).stat().st_size, sha256=hashlib.sha256((repo / x['path']).read_bytes()).hexdigest()) for x in manifest]
(repo / 'SHARE_MANIFEST.json').write_text(json.dumps({'time_beijing': stamp, 'files': manifest, 'excluded_evidence_count': len(excluded)}, ensure_ascii=False, indent=2), encoding='utf-8')
with log.open('a', encoding='utf-8') as f:
    f.write(f'\n上传内容准备完成：{len(manifest)}份既有可分享文件，加分享说明与当前哈希清单；共{sum(x["bytes"] for x in manifest)}字节。已检查已知姓名、凭据模式、本机用户路径、JSON可解析性和单文件100MiB限制。原件排除清单共{len(excluded)}份。仓库创建和上传尚未完成。\n')
print(json.dumps({'repository': repo.as_posix(), 'files': len(manifest) + 2, 'bytes': sum(x['bytes'] for x in manifest)}, ensure_ascii=False))
