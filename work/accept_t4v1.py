"""Verify the complete saved version and update its documentation entries."""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'work/python_packages'), str(ROOT/'code/model_v2'), str(ROOT/'code')]
sys.dont_write_bytecode = True
import t4v1 as t
from archive_and_report import redact_names

out = Path(sys.argv[1])
assert not (out/'manifest_final.json').exists(), 'Final acceptance already saved; preserve the old version'
nd = t.nd
model = nd.read(out/'models_full.json')
data = nd.read(out/'dataset.json')
supp = nd.read(out/'supplementary_verification.json')
assert model['version'] == 't4v1' and model['training_round'] == 3
assert not model['deployment_enabled']
assert len(data['state_pairs']) == 100
assert sorted({r['market_id'] for r in data['state_pairs']}) == list(range(1, 11))
assert len(model['model_inventory']) == 29
assert not {'UNIFIED', 'T2V0'} & model['model_inventory'].keys()
assert model['interest']['parameters_source'] == 'risk' and 'parameters' not in model['interest']
assert len(supp['severance']) == 100 and all(r['passed'] for r in supp['severance'])
assert len(supp['physical_formulas']) == 1000 and all(r['passed'] for r in supp['physical_formulas'])
assert not supp['missing_or_ambiguous'], 'Supplementary fields need review'
assert nd.read(t.AUDIT/'validation.json')['financial_counts'] == {'pass': 500}
assert not list(out.glob('*.html'))
counts = {p: len(r) for p, r in data['competitive_rows_by_product'].items()}
for product, rows in data['competitive_rows_by_product'].items():
    assert {r['market_id'] for r in rows} == set(range(1, 11))
    for name, fitted in model['demand'][product].items():
        if name == 'ABS':
            continue
        assert len(fitted['nested_validation']['folds']) == 10

rel = out.relative_to(ROOT).as_posix()
summary = ('2026-10-14最新实际训练版本为 **t4v1**：正式3完整10市场、100队、150/150页；'
           f'有效需求记录{counts}。双产品需求、效率、材料、工资、风险/利率及附加实验已重训，29类状态保存。'
           '公司合计营销/研发仍为代理；留出为同期条件验证，未部署，完整六回合收益未验证。')
entries = [ROOT/'README.md', ROOT/'code/README.md', ROOT/'code/model_v2/README.md',
           ROOT/'模型说明/README.md', ROOT/'模型版本重新统计.md', ROOT/'训练拟合模型与版本清单.md',
           ROOT/'训练拟合模型与版本清单_文字说明版.md', ROOT/'预测模型与训练参数汇总.md']
backups = out/'entry_backups'
for path in entries:
    backup = backups/path.relative_to(ROOT)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    prefix = '../' * len(path.relative_to(ROOT).parts[:-1])
    paragraph = summary + f'[报告]({prefix}{rel}/report_final.md)、[参数]({prefix}{rel}/models_full.json)。以下旧版本记录保留其历史范围。\n\n'
    text = path.read_text(encoding='utf-8')
    # Historical notes keep their dated conclusions, while the first entry is current.
    text = text.replace('定时状态核对：最新实际训练版本为 **t4v0**', '定时状态核对（历史记录）：当时实际训练版本为 **t4v0**')
    text = text.replace('最新正式3实际入口：[t4v0.py]', '原正式3实际入口：[t4v0.py]')
    first, rest = text.split('\n', 1)
    path.write_text(first+'\n\n'+paragraph+rest.lstrip('\n'), encoding='utf-8')

readme = (f'# t4v1 正式3完整数据训练\n\n{summary}\n\n'
          f'输出目录：`{rel}`。权威参数为 `models_full.json`，29类状态为 `model_inventory_final.json`。\n\n'
          '运行顺序：\n\n'
          '1. `python code/model_v2/t4v1.py`（独立创建新目录；自检加 `--self-check`）。\n'
          '2. `python work/verify_t4v1.py <目录>`（复算参数并训练附加实验）。\n'
          '3. `python work/finalize_t4v1.py <目录>`。\n'
          '4. `python work/accept_t4v1.py <目录>`，再用验证脚本加 `--check-only`核验最终哈希。\n\n'
          '正式3使用150页验收及历史补证；正式2实际期末结转期初，正式3实际需求/成本作标签；'
          '正式3三条曲线600点匹配，正式4曲线不进入训练。预算与玩家预估不作真实标签。\n\n'
          '营销/研发保留公司合计代理，不伪造产品或国别投入；缺失不补零，零价和零需求范围外记录保留。'
          '连接件初始价、完整订单、税亏、累计投入及独立后续回合仍限制应用。\n')
(ROOT/'code/model_v2/t4v1_README.md').write_text(readme, encoding='utf-8')
(ROOT/'模型说明/T4V1_正式3完整数据训练.md').write_text(readme + f'\n[报告](../{rel}/report_final.md)、[完整参数](../{rel}/models_full.json)。\n', encoding='utf-8')
(ROOT/'output/t4v1/README.md').write_text('# t4v1\n\n'+summary+f'\n\n[报告]({out.name}/report_final.md)、[参数]({out.name}/models_full.json)。\n', encoding='utf-8')

with (out/'work_log.md').open('a', encoding='utf-8') as log:
    log.write('\n验收完成：10市场100队、双产品重训、29类注册；500项源财务等式、1000项生产环境/物流公式、100项解聘费通过。'
              '需求复算、市场隔离与份额守恒通过；历史修正来源接入并保留哈希。新报告仅Markdown。'
              '风险/利率保存新留出误差，不继承t4v0稳定性失败断言；无数值阈值与后续回合证据，不部署。'
              'A按本次增量门槛结果保存。旧模型、原件、原预测保留，未操作平台。\n')
    log.write('过程更正：日志追加后原训练清单的日志哈希不再等于整个文件；验证改为核对原日志完整前缀哈希，其余文件仍核对全文件哈希。最终清单保存当前完整日志哈希。\n')
for name in ['accept_t4v1.py', 'prepare_t4v1.py', 'verify_t4v1.py', 'finalize_t4v1.py']:
    shutil.copy2(ROOT/'work'/name, out/'code_snapshot'/name)
delivered = [p for p in out.iterdir() if p.suffix in {'.md', '.json', '.csv'}] + entries + [ROOT/'code/model_v2/t4v1_README.md', ROOT/'模型说明/T4V1_正式3完整数据训练.md', ROOT/'output/t4v1/README.md']
for path in delivered:
    text = path.read_text(encoding='utf-8')
    assert redact_names(text) == text, 'Unredacted roster name in delivery'
for path in [out/'report_final.md', ROOT/'output/t4v1/README.md']:
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        assert (path.parent/link).exists(), link
checks = dict(version='t4v1',markets=10,teams=100,result_pages=150,demand_counts=counts,
              source_financial_pass=500,physical_pass=1000,severance_pass=100,
              demand_replay=True,market_isolation=True,share_conservation=True,initials_check=True,
              no_html_report=True,deployment=False)
nd.save(out/'acceptance.json', checks)
initial = nd.read(out/'manifest.json')
assert all(nd.sha(ROOT/p) == h for p,h in initial['input_hashes'].items())
nd.save(out/'manifest_final.json', dict(version='t4v1',status='TRAINED_FULL_MARKET_WITH_EXPLICIT_LIMITS',
        training_round=3,input_hashes=initial['input_hashes'],protected_inputs_unchanged=True,
        output_hashes={p.relative_to(out).as_posix(): nd.sha(p) for p in out.rglob('*') if p.is_file() and p.name != 'manifest_final.json'}))
print(json.dumps(checks, ensure_ascii=False))
