"""Create the full-market version without changing historical training code."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f%z')
out = ROOT / 'output/t4v1' / stamp
out.mkdir(parents=True, exist_ok=False)
(out / 'work_log.md').write_text(
    '# t4v1 工作日志\n\n' + stamp + ' 开始：用户授权使用正式3完整数据训练并保存t4v1。'
    '采用10市场100队150页已验收实际，复用现有方法；不覆盖旧模型。'
    '不要输出真名，姓名统一用首字母替代。仅输出Markdown报告。\n', encoding='utf-8')
(ROOT / 'work/t4v1_active_run.txt').write_text(str(out), encoding='utf-8')

# Maintained t4v1 sources must not be regenerated from the historical t4v0 code.
for path in [ROOT/'code/model_v2/t4v1.py', ROOT/'work/verify_t4v1.py', ROOT/'work/finalize_t4v1.py']:
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')
print(out)
