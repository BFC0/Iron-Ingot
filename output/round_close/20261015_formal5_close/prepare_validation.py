"""Reuse the frozen dual-product checks in an isolated formal-5 audit."""
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PRIOR = ROOT / 'output/round_close/20261014_formal4_close'


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(data)


def normalize():
    for market in range(1, 11):
        for panel in ['print', 'summary', 'productionenvironmental', 'productionhr', 'logisticsemissions',
                      'marketdetails', 'productiondetails', 'market', 'production', 'logistics',
                      'incomestatement', 'balancesheet', 'cashflow', 'societalimpact']:
            prefix = f'm{market:02d}_{panel}'
            choices = [BASE / (prefix + suffix + '.json') for suffix in ['_verified', '_complete', '']]
            source = next((p for p in choices if p.exists()), None)
            if source is None:
                continue
            target = BASE / 'raw' / f'market{market}_formal5_{panel}.json'
            if target.exists() and source.stem.endswith('_complete'):
                target = target.with_name(target.stem + '_complete.json')
            if target.exists():
                continue
            doc = json.loads(source.read_text(encoding='utf-8-sig'))
            html = ''.join(doc['html_parts']) if doc.get('html_parts') else doc.get('html', '')
            assert len(html.encode('utf-16-le')) // 2 == doc['html_length'], source
            assert html.rstrip().endswith('</html>'), source
            for selector in doc.get('selects', []):
                if not isinstance(selector.get('selected'), str):
                    selector['selected'] = next(o.get('text', o.get('label')) for o in selector['options'] if o['selected'])
                for option in selector.get('options', []):
                    option['text'] = option.get('text', option.get('label'))
            doc['original_capture'] = str(source.relative_to(ROOT)).replace('\\', '/')
            doc['normalization'] = 'Selector label alias only; HTML and table values unchanged.'
            write(target, json.dumps(doc, ensure_ascii=False))


def setup():
    validation = BASE / 'validation'
    for name in ['field_requirements_template.json', 'sequence_requirements_template.json', 'pair_results_svg.py']:
        text = (PRIOR / 'validation' / name).read_text(encoding='utf-8-sig')
        write(validation / name, text.replace('formal4', 'formal5').replace('正式4', '正式5').replace('round=4', 'round=5'))
    text = (PRIOR / 'validation/validate_market.py').read_text(encoding='utf-8-sig')
    text = text.replace('formal4', 'formal5').replace('round=4', 'round=5').replace("'回合4'", "'回合5'")
    text = text.replace("ROOT / f'output/round_close/20261014_resume_verified/raw/market{m}_formal3_summary.json'",
                        "ROOT / f'output/round_close/20261014_formal4_close/raw/market{m}_formal4_summary.json'")
    text = text.replace("'回合3' in formal.selected(prior)", "'回合4' in formal.selected(prior)")
    write(validation / 'validate_market.py', text)


if __name__ == '__main__':
    normalize()
    if not (BASE / 'validation/validate_market.py').exists():
        setup()
    assert ROOT == Path.cwd()
    print('Prepared isolated audit; original captures preserved.')
