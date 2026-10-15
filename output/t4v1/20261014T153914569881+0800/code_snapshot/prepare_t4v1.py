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

src = (ROOT / 'code/model_v2/t4v0.py').read_text(encoding='utf-8').replace('t4v0', 't4v1')
src = src.replace('import html\n', '')
src = src.replace('20261014T091756.838292+0800', '20261014T142929.104834+0800')
src = src.replace("PRODUCTS =", "REPAIRS = ROOT/'output/round_close/20261014_resume_verified/acceptance/20261014T152737.694032+0800'\nPRODUCTS =", 1)
start = src.index('    payload=json.dumps(point_rows')
end = src.index('    for path,digest in hashes.items():', start)
src = src[:start] + src[end:]
src = src.replace('正式3实际结果完整核验覆盖90/150页，市场1/2/4/5/9/10；其余市场不混入验收范围。',
                  '正式3实际结果完整核验覆盖150/150页，10市场100队全部纳入。')
src = src.replace("    prior_rows = nd.read(PRIOR/'rows.json')\n    for r in prior_rows:\n        path=PRIOR.parent.parent/r['source']\n        assert nd.sha(path)==r['sha256']\n        hashes[str(path.relative_to(ROOT))]=r['sha256']\n        r['source']=str(path.relative_to(ROOT))",
                  "    prior_rows = load_previous()\n    for r in prior_rows:\n        path=ROOT/r['source']\n        assert nd.sha(path)==r['sha256']\n        hashes[str(path.relative_to(ROOT))]=r['sha256']")
src = src.replace("PRIOR/'rows.json', DECISIONS", "PRIOR/'rows.json', REPAIRS/'historical_rows.json', REPAIRS/'acceptance.json', REPAIRS/'sources.json', DECISIONS")
helper = '''def load_previous():
    previous = nd.read(PRIOR/'rows.json')
    for row in previous:
        row['source'] = str((PRIOR.parent.parent/row['source']).relative_to(ROOT))
    repaired = nd.read(REPAIRS/'historical_rows.json')
    key = lambda r: (r['market'], r['phase'], r['round'], r['panel'])
    replaced = {key(r) for r in repaired}
    return [r for r in previous if key(r) not in replaced] + repaired


'''
src = src.replace('def main():', helper + 'def main():', 1)
src = src.replace("    sources = nd.read(AUDIT/'sources.json')", "    validation = nd.read(AUDIT/'validation.json')\n    assert validation['valid_complete_pages'] == 150 and validation['structure_reviews'] == 0\n    assert validation['financial_counts'] == {'pass': 500} and not validation['raw_hash_changes']\n    sources = nd.read(AUDIT/'sources.json') + nd.read(REPAIRS/'sources.json')")
src = src.replace("    actual = Actuals(all_rows)", "    actual = Actuals(all_rows)\n    assert sorted({r['market'] for r in nd.read(AUDIT/'rows.json')}) == list(range(1, 11))")
src = src.replace("    # Combined expenses", "    assert len(pairs) == 100 and len({(p['market_id'], p['team_id']) for p in pairs}) == 100\n    # Combined expenses")
src = src.replace('完成可估计曲线、风险/利率与材料重训及全部模型清单；需求和历史状态相关项明确阻塞。',
                  '完成10市场100队双产品需求、曲线、风险/利率、效率、材料重训；跨期与因果投入限制保留。')
(ROOT / 'code/model_v2/t4v1.py').write_text(src, encoding='utf-8')

verify = (ROOT / 'work/verify_t4v0.py').read_text(encoding='utf-8').replace('t4v0', 't4v1')
start = verify.index("    previous=nd.read(t.PRIOR/'rows.json')")
end = verify.index('    source_rows=', start)
verify = verify[:start] + '    previous=t.load_previous()\n' + verify[end:]
verify = verify.replace("    for product,rows in dataset", "    assert len(dataset['state_pairs']) == 100\n    assert {p['market_id'] for p in dataset['state_pairs']} == set(range(1, 11))\n    for product,rows in dataset", 1)
(ROOT / 'work/verify_t4v1.py').write_text(verify, encoding='utf-8')

final = (ROOT / 'work/finalize_t4v0.py').read_text(encoding='utf-8').replace('t4v0', 't4v1').replace('T4V0', 'T4V1')
final = final.replace('import html\n', '')
start = final.index("    header='<!doctype html>")
end = final.index("    for name in ['verify_t4v1.py'", start)
final = final[:start] + final[end:]
final = final.replace('PUBLISHED_SEVERANCE_RULE_60_CHECKS_PASS', 'PUBLISHED_SEVERANCE_RULE_100_CHECKS_PASS')
final = final.replace("'实际归档6市场、60队、90/150页；市场3/6/7/8尚未纳入。'", "'实际归档10市场、100队、150/150页；全部纳入。'")
final = final.replace("'复合梁120条、连接件110条需求训练记录；10条零售价且零实际需求/销量记录保留为范围外，不加伪小数。'", "f'有效需求记录：{counts}；零售价/零需求记录保留为范围外，不加伪小数。'")
final = final.replace("'风险/利率已拟合56个正权益有效状态；其余4项保留范围外。极端杠杆导致留出严重外推，稳定性门槛未通过。'", "f'风险/利率有效状态{len(data[\"risk\"])}项；极端杠杆外推与利率来源冲突仍限制部署。'")
final = final.replace('D类正式2→3残差已拟合60条', 'D类正式2→3残差已重训')
final = final.replace("'300项财务等式、600项生产环境/物流公式、60项解聘费核验通过。分产品工资重训：复合梁60样本、连接件54样本。'", "f'500项源财务等式通过；生产环境/物流公式{len(supplementary[\"physical_formulas\"])}项，解聘费{len(supplementary[\"severance\"])}项，失败数分别为{sum(not r[\"passed\"] for r in supplementary[\"physical_formulas\"])}/{sum(not r[\"passed\"] for r in supplementary[\"severance\"])}。分产品工资样本：' + str({p:m['n'] for p,m in supplementary['wages'].items()})")
final = final.replace('未归档四市场正式3全部实际、其他队', '其他队')
(ROOT / 'work/finalize_t4v1.py').write_text(final, encoding='utf-8')
for path in [ROOT/'code/model_v2/t4v1.py', ROOT/'work/verify_t4v1.py', ROOT/'work/finalize_t4v1.py']:
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')
    assert 'report.html' not in path.read_text(encoding='utf-8')
print(out)
