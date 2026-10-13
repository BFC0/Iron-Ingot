"""Delivery checks for one saved unified-market run; no training or platform mutation."""
import ast
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work/python_packages'),str(ROOT/'code/model_v2'),str(ROOT/'code')]
import core
import unified_market as unified
import numpy as np

out=Path(sys.argv[1]).resolve()
assert out.parent==ROOT/'output/unified-market'
manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
assert manifest['status']=='COMPLETE_INDEPENDENT_ASSUMPTION_VERSION'
for file,sha in manifest['input_hashes'].items():
    assert core.digest(ROOT/file)==sha,file
for file,sha in manifest['output_hashes'].items():
    assert core.digest(out/file)==sha,file
result=json.loads((out/'models.json').read_text(encoding='utf-8'))
data=json.loads((out/'dataset.json').read_text(encoding='utf-8'))['rows']
curves=result['curve_registry']['formal/1']['curves']
changed=[dict(r,operations=r['operations']+1000) for r in data]
assert np.array_equal(core.features(data,curves['rd']['parameters']),core.features(changed,curves['rd']['parameters']))
legacy=[dict(r,market=r['country']) for r in data]
legacy_changed=[dict(r,operations=r['operations']+1000) for r in legacy]
assert np.array_equal(core.step.demand_features(legacy,curves),core.step.demand_features(legacy_changed,curves))
op=curves['operations']
assert core.step.curve_value(1400,op['parameters'],op['form'])>core.step.curve_value(400,op['parameters'],op['form'])
for country,m in result['demand'].items():
    rows=[r for r in data if r['country']==country]
    assert len(m['training_keys'])==100 and set(m['market_scope'])==set(range(1,11))
    assert sorted(mk for fold in m['outer_folds'] for mk in fold['held_markets'])==list(range(1,11))
    for fold in m['outer_folds']:
        tr={k[0] for k in fold['training_keys']};te={k[0] for k in fold['test_keys']}
        assert len(tr)==8 and len(te)==2 and not tr & te
        for candidate in fold['inner_cv_path']:
            assert all(set(f['held_markets'])<=tr for f in candidate['folds'])
    p=unified.prediction(rows,m,curves['rd']['parameters'])
    assert np.all(np.isfinite(p)) and np.all((p>=0)&(p<=1))
    try: unified.prediction(rows,dict(m,country=next(c for c in core.COUNTRIES if c!=country)),curves['rd']['parameters'])
    except ValueError: pass
    else: raise AssertionError('Wrong country accepted')
assert result['curve_registry']['formal/2']['demand_coefficients_status']=='NO_ACTUAL_LABELS_NOT_TRAINED'
for p in [ROOT/'code/unified_market.py',Path(__file__)]:
    ast.parse(p.read_text(encoding='utf-8'),str(p))
checks=dict(source_and_old_model_hashes=True,completed_output_hashes=True,nested_market_boundaries=True,
    country_rejection=True,shares_valid=True,legacy_and_new_demand_exclude_direct_operations=True,
    operations_curve_changes_efficiency=True,formal2_no_invented_training=True,python_syntax=True)
with (out/'delivery_checks.json').open('x',encoding='utf-8') as f:
    json.dump(checks,f,ensure_ascii=False,indent=2)
with (out/'work_log.md').open('a',encoding='utf-8') as f:
    f.write('\n交付追加验收：原模型和新增需求特征在运营投入增加1000时均完全不变；效率乘数随运营有效投入增加而上升，未发现运营直接乘需求错误，无需改写旧模型。来源、旧模型及全部输出哈希通过；嵌套整市场留出、国家拒绝、份额边界、正式2无标签拒绝训练及语法检查通过。\n')
manifest['output_hashes']={p.relative_to(out).as_posix():core.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}
core.write(out/'manifest.json',manifest)
print(json.dumps(dict(checks=checks,coefficients={c:m['coefficients'] for c,m in result['demand'].items()},
    holdout_mae_pp={c:m['nested_market_holdout_share_mae_pp'] for c,m in result['demand'].items()},
    operations=result['mechanisms']['operations_efficiency']['chosen']),ensure_ascii=False))
