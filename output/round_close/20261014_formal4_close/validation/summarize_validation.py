"""Index latest per-market validation without claiming unresolved coverage complete."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
ROOT = BASE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    runs, status, fields, sequences, finance, cumulative = [], Counter(), Counter(), Counter(), Counter(), Counter()
    for market in range(1,11):
        candidates = sorted((BASE/f'market{market}').glob('*/validation.json'))
        assert candidates, market
        path = candidates[-1]
        doc = json.loads(path.read_text(encoding='utf-8'))
        status.update([doc['status']])
        fields.update(doc['field_status_counts'])
        sequences.update(doc.get('sequence_status_counts',{}))
        finance.update(doc['financial_numerical_counts'])
        cumulative.update(doc['cumulative_numerical_counts'])
        for source in doc['sources']:
            assert sha(ROOT/source['source']) == source['sha256'], source
        runs.append(dict(market=market,source=path.relative_to(ROOT).as_posix(),sha256=sha(path),status=doc['status']))
    assert sum(status.values())==10
    summary=dict(generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                 status='BASELINE_CAPTURE_VALIDATED_REMAINING_FIELD_AND_SEQUENCE_COVERAGE_REQUIRED',
                 per_market=runs,market_status_counts=dict(status),field_status_counts=dict(fields),
                 sequence_status_counts=dict(sequences),financial_counts=dict(finance),cumulative_counts=dict(cumulative),
                 source_hashes_unchanged=True,print_pages=10,summary_web_pages=10,
                 fixed_15_panel_coverage_claimed=False,source_type_duplicates_are_independent_samples=False,
                 complete_round_archive=False)
    out = BASE/'summary'/datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S.%f+0800')
    out.mkdir(parents=True,exist_ok=False)
    with (out/'validation_index.json').open('x',encoding='utf-8') as stream:
        json.dump(summary,stream,ensure_ascii=False,indent=2)
    with (out/'report.md').open('x',encoding='utf-8') as stream:
        stream.write('# 正式4主采离线核验\n\n'
                     f'市场1–10打印及概要身份/内容核验：{dict(status)}。打印10页，概要网页10页，未虚算固定15栏覆盖。\n\n'
                     f'财务等式核验：{dict(finance)}；正式3至正式4累计衔接：{dict(cumulative)}。原显示数字未改，残差及半步误差容差在各市场明细保留。\n\n'
                     f'字段覆盖：{dict(fields)}；原始图表JSON覆盖：{dict(sequences)}。字段单位/产品/国家/源行列和图表初始化数据保留在逐市场产物。打印与网页重复表示不重复计独立样本。\n\n'
                     '有效打印布局为253行；426行中的末尾173行为空行，未当新增业务字段。截断旧件保留，完整分块件另存并用于本次核验。来源SHA256重新检查未变。\n\n'
                     '本次仅完成打印及概要主采验收。尚需合并计算值、补采独有字段与原始序列，不能标为正式4全部归档完成。未评分或重训，未改README或决策。\n')
    print(json.dumps(dict(output=str(out),**{k:v for k,v in summary.items() if k!='per_market'}),ensure_ascii=False))


if __name__=='__main__':
    main()
