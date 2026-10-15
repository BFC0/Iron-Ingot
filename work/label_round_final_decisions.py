"""Label captured team-column inputs; preserve sources and prior exports."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/round_close/20261013_formal3_close'
SOURCE = BASE / 'decision_history/historical_5_rounds/all_fields.json'
OUT = BASE / 'decision_history/final_decisions_labeled'


def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8-sig'))
    rows = data['fields']
    assert len(rows) == 144 and len({r['key'] for r in rows}) == 144
    names = {c['round_id']: c['selected'] + '小组最终决策' for c in data['coverage']}
    for source in data['coverage']:
        assert hashlib.sha256((BASE / source['source']).read_bytes()).hexdigest() == source['sha256']
    outputs = []
    for row in rows:
        item = dict(row)
        budget = row['category'] == 'HISTORICAL_PLATFORM_BUDGET_NOT_ACTUAL'
        item['group_data_label'] = (names[row['round_id']].replace('小组最终决策', '小组历史预算摘要')
                                    if budget else names[row['round_id']])
        item['group_category'] = ('HISTORICAL_PLATFORM_BUDGET_NOT_ACTUAL' if budget
                                  else 'ROUND_K_GROUP_FINAL_DECISION')
        item['group_column_name'] = '营销团队'
        item['PYT_category'] = 'HISTORICAL_PERSONAL_DRAFT_OR_ESTIMATE_NOT_GROUP_FINAL'
        outputs.append(item)
    assert sum(r['group_category'] == 'ROUND_K_GROUP_FINAL_DECISION' for r in outputs) == 134
    assert sum(r['group_category'] == 'HISTORICAL_PLATFORM_BUDGET_NOT_ACTUAL' for r in outputs) == 10
    assert {r['group_column_zero_based'] for r in outputs} == {1}
    OUT.mkdir(parents=True, exist_ok=False)
    result = dict(coverage=data['coverage'], fields=outputs,
                  label_authority='2026-10-13 用户要求：本次补采小组决策标为回合k小组最终决策',
                  source_export_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest())
    with (OUT / 'all_fields.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    with (OUT / 'all_fields.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(outputs[0]))
        writer.writeheader()
        writer.writerows(outputs)
    with (OUT / 'report.md').open('x', encoding='utf-8') as stream:
        stream.write('# 历史小组最终决策标签\n\n用户明确指定本次历史决策列表营销团队列为回合k小组最终决策。练习1/2、正式1/2/3共134项输入（含玩家预估）已标记；10项预算摘要另标历史预算，PYT列仍为个人草稿或预估。原件和旧导出未覆盖。\n\n5份原件SHA256、144唯一键及134/10类别分离自检通过。正式3模型候选未采用；本标签不表示存在与小组方案匹配的模型事前预测。不要输出真名，姓名统一用首字母替代。\n')
    print(json.dumps({'output': str(OUT), 'final_inputs': 134, 'budget_summaries': 10,
                      'source_hashes_passed': 5, 'selfchecks_passed': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
