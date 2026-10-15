"""Index existing formal4 evidence without changing or refitting it."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
APP = ROOT / 'output/t4v1a/20261014T175143627079+0800'
JOINT = ROOT / 'output/formal4_all/20261014T211634211494+0800'
INITIAL = ROOT / 'output/round_close/20261013_formal3_close/formal4_initial'
CURVES = ROOT / 'output/t4v1/20261014T153914569881+0800/formal4_curves'
HISTORY = ROOT / 'output/round_close/20261013_formal3_close/decision_history'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert (ROOT / 'README.md').exists()
    paths = set()
    for base in (APP, JOINT, CURVES):
        paths.update(p for p in base.iterdir() if p.suffix in ('.json', '.csv', '.md', '.py'))
    paths.update(INITIAL.glob('raw/*.json'))
    paths.update(INITIAL.glob('curves/20261014T004027/*.json'))
    paths.update(HISTORY.glob('final_decisions_labeled/*'))
    paths.update(HISTORY.glob('historical_5_rounds/*.json'))
    paths.update(ROOT / p for p in ('code/model_v2/core.py', 'code/model_v2/t4v1a.py',
                 'code/model_v2/verify_t4v1a.py', 'code/model_v2/formal4_joint_scenarios.py',
                 'code/model_v2/t4v1.py', 'work/label_round_final_decisions.py'))
    assertions = []
    manifests = [(APP / 'manifest.json', 'output_hashes', APP),
                 (APP / 'source_manifest.json', 'raw_sources', ROOT),
                 (JOINT / 'acceptance.json', 'source_hashes', ROOT),
                 (JOINT / 'acceptance.json', 'output_hashes', JOINT),
                 (CURVES / 'source_hashes.json', None, ROOT)]
    for source, key, base in manifests:
        mapping = read(source)
        if key:
            mapping = mapping[key]
        for relative, expected in mapping.items():
            path = base / relative
            # Dependencies are an unchanged bundled runtime; only selected evidence is checked.
            if source.name == 'manifest.json' and path not in paths:
                continue
            paths.add(path)
            actual = sha(path) if path.is_file() else None
            assertions.append(dict(manifest=source.relative_to(ROOT).as_posix(),
                                   path=path.relative_to(ROOT).as_posix(),
                                   expected_sha256=expected, actual_sha256=actual,
                                   passed=expected == actual))
    records = []
    for path in sorted(paths):
        is_raw = 'raw' in path.parts or 'sources' in path.parts
        records.append(dict(path=path.relative_to(ROOT).as_posix(), exists=path.is_file(),
                            sha256=sha(path) if path.is_file() else None,
                            bytes=path.stat().st_size if path.is_file() else None,
                            category='RAW_EVIDENCE_DO_NOT_SHARE' if is_raw else 'FROZEN_ARTIFACT_OR_CODE'))
    decisions = read(JOINT / 'decisions.json')
    plans = Counter(r['plan'] for r in decisions)
    assert len(plans) == 2 and set(plans.values()) == {42}
    assert len({(r['plan'], r['key']) for r in decisions}) == 84
    history = read(HISTORY / 'final_decisions_labeled/all_fields.json')
    categories = Counter(r['group_category'] for r in history['fields'])
    assert categories['ROUND_K_GROUP_FINAL_DECISION'] == 134
    assert categories['HISTORICAL_PLATFORM_BUDGET_NOT_ACTUAL'] == 10
    status = dict(status='FROZEN_INDEX_READY_FINAL_PLAN_PAIRING_PENDING',
                  checked_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  no_training=True, no_browser_action=True, no_source_edits=True,
                  indexed_files=len(records), manifest_checks=len(assertions),
                  manifest_checks_passed=sum(x['passed'] for x in assertions),
                  manifest_mismatches=[x for x in assertions if not x['passed']],
                  joint_candidate_fields=dict(plans), historical_categories=dict(categories),
                  direct_formal4_score_available=False,
                  direct_score_reason='正式4历史小组最终决策与实际尚未在本分工输入中配对；冻结应用情景不等同已提交方案。')
    for filename, data in [('source_index.json', records), ('hash_checks.json', assertions),
                           ('acceptance.json', status)]:
        with (OUT / filename).open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(status, ensure_ascii=False))


if __name__ == '__main__':
    main()
