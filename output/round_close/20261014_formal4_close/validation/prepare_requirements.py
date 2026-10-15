"""Build a traceable formal-4 requirement template from accepted dual-product evidence."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PRIOR = ROOT / 'output/round_close/20261014_resume_verified/acceptance/20261014T152737.694032+0800'
OUT = Path(__file__).parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    fields_path = PRIOR / 'market8_field_coverage.json'
    sequences_path = PRIOR / 'market8_sequences.json'
    fields = json.loads(fields_path.read_text(encoding='utf-8-sig'))
    sequences = json.loads(sequences_path.read_text(encoding='utf-8-sig'))
    required_fields = []
    for item in fields:
        source = item['web']
        required_fields.append(dict(
            requirement_id=f"{item['panel']}:{source['table_index']}:{source['row_index']}",
            panel=item['panel'], label=item['label'], section_path=item['section_path'],
            units=item['units'], team_columns=item['team_columns'],
            formal4_status='not_collected',
            prior_verified_status=item['status'],
            prior_web_reference=source,
            prior_print_references=item.get('print_matches', []),
            print_to_web_display_sign=item.get('print_to_web_display_sign', 1),
            transfer_condition='Confirm formal4 product/country/layout and team order; then verify same field semantics and displayed precision. Prior values are never formal4 actuals.',
        ))
    required_sequences = [dict(
        requirement_id=f"{item['panel']}:{item['chart_id']}",
        panel=item['panel'], chart_id=item['chart_id'], chart_type=item['chart_type'],
        formal4_status='not_collected', prior_source=item['source'], prior_sha256=item['sha256'],
        independent_sample=False,
        fulfillment='Original formal4 JSON and preserved SVG; or explicitly justified printed/reconstructed sequence where no original precision requirement remains.',
    ) for item in sequences]
    assert len({x['requirement_id'] for x in required_fields}) == len(required_fields)
    assert len({x['requirement_id'] for x in required_sequences}) == len(required_sequences)
    assert all(len(x['team_columns']) == 10 for x in required_fields)
    write('field_requirements_template.json', required_fields)
    write('sequence_requirements_template.json', required_sequences)
    write('preparation_manifest.json', dict(
        status='PREPARATION_ONLY_NO_FORMAL4_VALIDATION',
        accepted_dual_product_reference=dict(fields=fields_path.relative_to(ROOT).as_posix(),
                                            fields_sha256=sha(fields_path),
                                            sequences=sequences_path.relative_to(ROOT).as_posix(),
                                            sequences_sha256=sha(sequences_path)),
        field_count=len(required_fields), fields_by_panel=dict(Counter(x['panel'] for x in required_fields)),
        prior_print_crosschecked_count=sum(x['prior_verified_status'] == 'print_direct_crosschecked' for x in required_fields),
        prior_web_supplement_count=sum(x['prior_verified_status'] == 'web_supplement_direct' for x in required_fields),
        sequence_count=len(required_sequences), sequences_by_panel=dict(Counter(x['panel'] for x in required_sequences)),
        intended_markets=list(range(1, 11)), intended_phase='formal', intended_round=4,
        prior_values_reused_as_actual=False, model_trained=False, selfchecks_passed=True,
    ))
    print(json.dumps(dict(fields=len(required_fields), sequences=len(required_sequences), output=str(OUT))))


if __name__ == '__main__':
    main()
