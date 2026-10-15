"""Verify complete HTML or independent supplements without modifying originals."""
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUN = Path(__file__).resolve().parent
BASE = RUN.parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def html_errors(doc):
    html = doc.get('html', '')
    errors = []
    if not html.strip().startswith('<html') or not html.rstrip().endswith('</html>'):
        errors.append('html_document_not_complete')
    if '[Truncated]' in html:
        errors.append('html_truncated')
    # Browser String.length counts UTF-16 code units, including both halves of emoji.
    if 'html_length' in doc and doc['html_length'] != len(html.encode('utf-16-le')) // 2:
        errors.append('html_length_mismatch')
    return errors


def check():
    spec = importlib.util.spec_from_file_location('archive_audit', BASE / 'audit/verify_archive.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    previous_path = RUN / 'html_recapture_pending.json'
    previous = {item['source_original']: item for item in read(previous_path)['items']} if previous_path.exists() else {}
    items, scanned, complete = [], 0, 0
    for path in sorted((BASE / 'raw').glob('market*.json')):
        if not re.fullmatch(r'market\d+_(initial|practice|formal)\d+_[a-z]+\.json', path.name):
            continue
        original = audit.normalize(read(path), path.name)
        source = path.relative_to(BASE).as_posix()
        fingerprint = sha(path)
        scanned += 1
        errors = html_errors(original) + audit.identity(original)
        prior = previous.get(source)
        if prior and fingerprint != prior['source_original_sha256']:
            errors.append('source_original_hash_changed')
        if not errors:
            complete += 1
            continue
        supplement_path = BASE / 'supplements/html' / f'{path.stem}_complete_html.json'
        item = {key: original[key] for key in ('market', 'phase', 'round', 'panel')}
        item.update(source_original=source,
                    source_original_sha256=prior['source_original_sha256'] if prior else fingerprint,
                    html_length=len(original.get('html', '')), original_errors=errors,
                    supplement_expected=supplement_path.relative_to(BASE).as_posix(), status='pending')
        supplement_errors = []
        if supplement_path.is_file():
            supplement = read(supplement_path)
            supplement_errors = html_errors(supplement)
            for key in ('market', 'phase', 'round', 'panel'):
                if supplement.get(key) != original[key]:
                    supplement_errors.append(key + '_metadata_mismatch')
            if supplement.get('kind') != 'html_supplement' or supplement.get('source_original') != source:
                supplement_errors.append('supplement_provenance_mismatch')
            if 'html_length' not in supplement:
                supplement_errors.append('declared_html_length_missing')
            selected = []
            for entry in supplement.get('selected', []):
                old = next((old for old in original.get('selected', []) if old.get('value') == entry.get('value')
                            and old.get('label') == entry.get('label')), {})
                selected.append(dict(entry, options=entry.get('options', old.get('options', []))))
            supplement_errors += audit.identity(dict(supplement, selected=selected))
            if 'source_original_hash_changed' in errors:
                supplement_errors.append('source_original_hash_changed')
            item.update(supplement_sha256=sha(supplement_path),
                        supplement_html_length=len(supplement.get('html', '')),
                        supplement_errors=supplement_errors)
            if not supplement_errors:
                item['status'] = 'resolved'
                complete += 1
        items.append(item)
    assert len({item['source_original'] for item in items}) == len(items)
    assert complete <= scanned <= 750
    resolved = sum(item['status'] == 'resolved' for item in items)
    result = {'generated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'scanned_target_pages': scanned, 'incomplete_original_pages': len(items),
              'resolved_count': resolved, 'pending_count': len(items) - resolved,
              'complete_html_pages': complete, 'complete_html_remaining_of_750': 750 - complete,
              'safe_supplement_directory': 'supplements/html',
              'note': 'Supplements remain outside raw; coverage and complete HTML are separate checks.',
              'items': items}
    temporary = previous_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(previous_path)
    return result


if __name__ == '__main__':
    assert 'html_truncated' in html_errors({'html': '<html>[Truncated]</html>'})
    assert not html_errors({'html': '<html>😀</html>', 'html_length': 15})
    assert 'html_length_mismatch' in html_errors({'html': '<html></html>', 'html_length': 12})
    print(json.dumps({key: value for key, value in check().items() if key != 'items'}, ensure_ascii=False))
