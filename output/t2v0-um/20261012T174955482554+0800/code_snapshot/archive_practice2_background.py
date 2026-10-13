"""Append-only archive of the user background and scenario evidence; offline."""
import csv
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from archive_and_report import table_rows, write_json

ROOT = Path(__file__).resolve().parent.parent
IMAGE = Path(r'<LOCAL_USER_DIR>\AppData\Local\Temp\codex-clipboard-872e08d1-a194-49ce-b424-d1c06ab6106e.png')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    out = ROOT / 'output' / 'scenario_archive' / now.strftime('%Y%m%dT%H%M%S%f+0800')
    out.mkdir(parents=True, exist_ok=False)
    protected = [ROOT / name for name in ('数据分组索引.json', '归档覆盖与待办.json', 'SHA256_manifest.json')]
    protected += list((ROOT / 'raw').rglob('*'))
    protected += list((ROOT / 'output' / 'cross_market').glob('*.json'))
    before = {p: digest(p) for p in protected if p.is_file()}
    image_path = out / '用户提供_练习回合2_市场前景.png'
    shutil.copy2(IMAGE, image_path)
    evidence = {}
    for name in ('practice1', 'practice2', 'round1'):
        path = ROOT / 'raw' / f'20261011_{name}_outlook.json'
        obj = json.loads(path.read_text(encoding='utf-8'))
        rows = [r for r in table_rows(obj['snapshot']) if r['cells']]
        content = [r['cells'] for r in rows]
        evidence[name] = dict(file=path.relative_to(ROOT).as_posix(), sha256=digest(path),
                              captured_at=obj['captured_at'], rows=rows,
                              visible_content_sha256=hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest())
    rows = evidence['practice2']['rows']
    assert len(rows) == 34
    params = [r for r in rows if len(r['cells']) == 4]
    narratives = [r for r in rows if len(r['cells']) == 1]
    assert len(params) == 28 and len(narratives) == 5
    groups = ['货币汇率', '财务', '财务'] + ['利率'] * 3 + ['年折旧', '固定成本', '固定成本'] + ['行政管理'] * 3 + ['可变成本', '原材料成本'] + ['运输成本'] * 2 + ['生产工资'] + ['工资乘数'] * 2 + ['人员流动'] * 2 + ['投资成本', '年产能下降'] + ['生产环境影响'] * 3 + ['运输碳排量'] * 2
    units = ['美元/美元', '%', '千美元'] + ['%'] * 4 + ['千美元'] * 5 + ['美元/单位'] * 4 + ['千美元'] + ['乘数'] * 2 + ['%'] * 2 + ['美元/单位', '%', 'kg/单位', 'kWh/单位', 'l/单位'] + ['克/单位'] * 2
    assert len(groups) == len(units) == len(params)
    for row, group, unit in zip(params, groups, units):
        row.update(section=group, unit=unit)
    assert next(r['cells'] for r in params if r['cells'][0] == '复合梁') == ['复合梁', '1 053.00', '+17%', '900.00']
    assert evidence['practice1']['visible_content_sha256'] == evidence['round1']['visible_content_sha256']
    assert evidence['practice2']['visible_content_sha256'] != evidence['round1']['visible_content_sha256']
    sid = 'market5_practice2_visible_' + evidence['practice2']['visible_content_sha256'][:12]
    baseline_sid = 'market5_practice1_formal1_visible_' + evidence['round1']['visible_content_sha256'][:12]
    archive = dict(archived_at=now.isoformat(), captured_at=None,
                   source_image=str(IMAGE), archived_image=image_path.relative_to(ROOT).as_posix(),
                   source_image_sha256=digest(image_path), phase='practice', round=2,
                   market=None, team=None, country=['泰国', '印尼'], data_kind='published_scenario_information',
                   scenario_id=sid, identity_basis='练习2由用户明确指定；原图未显示市场/团队/时间；市场5旧DOM的全部可见内容经人工图文核对匹配，仅作关联证据',
                   representation='旧DOM文本复用，逐项人工核对本次截图；不是本次网页采集或OCR',
                   linked_dom=evidence['practice2'], usable_for_demand_fit=False,
                   narratives=narratives, parameters=params,
                   tags=['财政刺激', '需求预期增长5–10%', '营销作用预期增强', '香港订单招标2000单位_明年交货',
                         '机器未来降价可达40%', '原料未来涨约20%', '原料当期涨17%', '基准利率下降0.5个百分点'],
                   cautions=['叙述预期不是实际需求或已实现成本', '订单招标不等于中标或当期交付',
                             '机器未来降价40%不能覆盖当期投资成本100美元/单位', '原料叙述约20%与参数17%保留不同口径',
                             '截图不证明其他编号市场情境相同，也不证明隐藏函数改变'])
    write_json(out / 'background.json', archive)
    lines = ['练习回合2市场前景：截图可见正文及参数；身份见background.json。']
    lines += [r['cells'][0] for r in narratives]
    lines += ['分区 | 单位 | 字段 | 今年 | Δ% | 去年'] + [' | '.join([r['section'], r['unit'], *r['cells']]) for r in params]
    (out / 'background.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    with (out / 'parameters.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['情境ID', '源文件', '源行', '分区', '单位', '字段', '今年显示值', '显示变化', '去年显示值', '数据类别'])
        writer.writerows([sid, evidence['practice2']['file'], r['line'], r['section'], r['unit'], *r['cells'], 'K_当期或历史公布参数'] for r in params)
    # shortcut: source-level scenario joins only; modeling must validate row-level identity before fitting.
    index = json.loads((ROOT / '数据分组索引.json').read_text(encoding='utf-8'))
    index += json.loads((ROOT / 'output/cross_market/archive_index.json').read_text(encoding='utf-8'))
    joins = []
    for item in index:
        market = item.get('market', item.get('market_id'))
        key = (market, item.get('phase'), item.get('round'))
        assigned = sid if key == (5, 'practice', 2) else baseline_sid if key in ((5, 'practice', 1), (5, 'formal', 1)) else None
        joins.append(dict(file=item['file'], market=market, phase=item.get('phase'), round=item.get('round'),
                          data_kind=item.get('data_kind', item.get('kind')), scenario_id=assigned,
                          scenario_status='市场5当期前景来源关联，仍须行级核验' if assigned else '情境未核实，禁止自动跨情境合并',
                          basis='原索引身份和当期前景，非逐行重审' if assigned else '缺少本市场当期独立前景或身份关联'))
    write_json(out / 'scenario_source_index.json', joins)
    write_json(out / 'visible_comparison.json', dict(evidence=evidence,
        practice1_formal1_visible_equal=True,
        practice2_formal1_differences=[dict(practice2=a, formal1=b) for a, b in zip(rows, evidence['round1']['rows']) if a['cells'] != b['cells']],
        limits='可见内容一致不等于状态、竞争策略或隐藏机制一致；其他市场未独立确认'))
    report = f'''# 练习2背景补档与情境分类

归档：{now.isoformat()}。用户原图、5段背景、28行参数及源行定位已保存。仓库此前已有相同练习2网页快照，本次补齐原图和独立情境标签。练习2身份由用户指定，截图市场与团队不可直接核验；旧市场5快照提供内容匹配关联。

情境ID：`{sid}`。市场5练习1/正式1可见前景逐行一致，练习2与它们的叙述和部分参数不同；不能据此判定隐藏函数改变。

需求5–10%为官方预期区间；香港2000单位为招标、明年交货；机器未来降价可达40%，当期表中仍100美元/单位；原料当期1053美元/单位、去年900、涨17%，叙述约20%保留为未来预期。不能直接重复施加到当期参数。

## 情境标签与分类要求

- 数据键保留市场、阶段、回合、团队、国家、数据类别，再关联情境ID、来源、有效期和核验状态。情境不能用回合编号替代，未知不补成市场5情境。
- 分开官方叙述、当期参数、历史状态、竞争策略、玩家预测、平台预算、模型假定。用可见内容指纹定位版本，指纹相同仅证明可见资料相同。
- `scenario_source_index.json`是原索引的附加分类，不修改旧文件。其它市场及未关联身份的来源标为情境未核实，待补各市场当期前景；不自动共同训练或转化成本。
- 建模重审按情境分层比较A/B，固定市场内比较，再检验跨市场同情境迁移与跨情境留出。训练内选择参数，练习2仍标回溯研究；情境与回合共变时不能宣称识别独立因果作用。
- 审查旧输入的参数时点、成本/利率、行业规模及大客户交付，区分数据本身错误、情境错配和模型外推。保留旧冻结结果及版本，先复现再重新标注或重训。

## 通知与待办

用户授权通知的“Cesim建模重审与版本隔离”（01a12aba-af08-7252-be8c-2de471192b6a）已发送紧急消息及1053数值勘误；当前对话01a12acc-1ce2-7ea1-a9ce-13b98ac71cbb为新增要求来源。归档方只增量保存证据；模型方负责行级归类、模型重审与研究报告。

未核实：其它市场前景、正式2情境、截图拍摄时间与身份、隐藏函数及情境独立因果效应。未改Cesim决策页面，未重训模型。
'''
    (out / 'report.md').write_text(report, encoding='utf-8')
    shutil.copy2(Path(__file__), out / 'archive_code.py')
    assert digest(IMAGE) == digest(image_path)
    assert all(digest(p) == h for p, h in before.items()), '已有基线在归档期间改变'
    assert all(x['scenario_id'] is None for x in joins if x['market'] not in (5,))
    write_json(out / 'validation.json', dict(result='PASS', image_hash_equal=True, narratives=5, parameters=28,
        visible_rows=34, source_records=len(joins), protected_files_unchanged=len(before),
        scenario_unknown=sum(x['scenario_id'] is None for x in joins), browser_accessed=False, model_retrained=False))
    write_json(out / 'SHA256_manifest.json', [dict(file=p.name, bytes=p.stat().st_size, sha256=digest(p)) for p in sorted(out.iterdir()) if p.is_file()])
    print(out)


if __name__ == '__main__':
    main()
