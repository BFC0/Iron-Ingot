"""Stage byte-identical evidence for the existing fixed-panel audit."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'output/round_close/20261014_resume_verified'


def main():
    manifest = []
    for folder in ['20261013_formal3_close', '20261014_full_archive']:
        for source in sorted((ROOT / 'output/round_close' / folder / 'raw').glob('market*_formal3_*.json')):
            target = DEST / 'raw' / source.name
            data = source.read_bytes()
            if target.exists():
                assert target.read_bytes() == data, f'Conflicting evidence: {source.name}'
            else:
                with target.open('xb') as stream:
                    stream.write(data)
            assert target.read_bytes() == data
            manifest.append(dict(source=str(source.relative_to(ROOT)), copy=str(target.relative_to(ROOT)),
                                 sha256=hashlib.sha256(data).hexdigest()))
    with (DEST / 'reuse_manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(reused_files=len(manifest), byte_identity_verified=True)))


if __name__ == '__main__':
    main()
