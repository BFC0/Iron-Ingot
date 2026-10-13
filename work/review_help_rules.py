"""Archive missing observed help and verify the bounded rule review; no model writes."""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'code'), str(ROOT / 'code/model_v2'), str(ROOT / 'code/t2v0_um')]
OUT = ROOT / 'output/help_review/20261012'
CATALOG = ROOT / 'output/model_catalog/20261012T122718963696+0800/model_versions.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


NEW_HELP = [
    ('bulk', '大客户订单', 'marketreportbulk', 2,
     '价格、销售力度和产品质量会影响一个团队的中标并获得可能的大宗交易。如果多个投标被认为吸引力相同，则交货金额由中标团队平分。如果没有一个投标被接受，客户有权不继续购买。大宗交易在竞标之后的回合交付。'),
    ('priority', '产品销售优先级', 'logistics', 2,
     '选择不同市场的物流优先级。 如果期初库存加产量小于需求，那么优先级最低的市场将最先出现交付不足的情况，依此类推。'),
    ('estimate', '需求预估', 'logistics', 2,
     '如果交货量低于你在需求页上所预估的需求量，你的生产规模就不足以满足需求，未满足的需求就表示为一个差额。'),
    ('capital', '额外实收资本', 'demand', 2,
     '额外实收资本是投资者支付的超出公司股票面值的金额。它等于已发行股票数*（发行价-票面价值）。它可能随股票发行或回购而变化。'),
    ('advance', '已收预付款', 'demand', 2,
     '收到的预付款包括大客户订单的预付款。 根据合同，客户将支付购买价款的百分之十作为预付款，其余部分将在下一回合交付时支付。'),
]

# Each model class is reviewed once; saved parameter versions inherit the class finding.
REVIEWS = [
    ('ABS', '仅历史对照', ['需求要素', '研发', '营销'], '缺少显式竞争归一化；0.5研发延续及合计营销代理不是帮助确认的权重。旧fit_demand初期无上期资料时填0，不能代表已知初始研发600。', 'code/fit_demand.py'),
    ('SHARE', '部分符合', ['需求要素', '研发', '营销'], '相对竞争份额守恒；softmax、投入对数及系数为经验结构。两国共用投入系数及公司合计营销代理仍需国别证据。', 'code/model_v2/core.py'),
    ('COUNTRY', '部分符合', ['需求要素', '研发', '营销'], '分国系数与不同市场重视程度方向相容；固定曲线与R+rho*上期R不能确认历史条件变动后的真实函数。', 'code/model_v2/country_demand.py'),
    ('RD', '当期与单期滞后代理未获机制确认', ['研发'], '已有R_t+0.5R_(t-1)；不是完全遗漏下期影响，但时间权重、短期/延期曲线结构及历史条件未经确认，跨期收益链未接通。', 'code/fit_chart_json.py'),
    ('OPS', '当期曲线相容；累计调用缺失', ['运营改进'], '饱和形状相容，不代表累计机制成立；调用只读取本期与上期运营支出。', 'code/stepwise_model.py'),
    ('EFF', '累计机制未实现', ['运营改进'], '只读取O_t与O_(t-1)，更早历史被忽略；单次投入第二个后续回合恢复零投入乘数，没有持续可更新的累计状态。', 'code/operations_rho.py'),
    ('RISK_POWER', '提示不足以验证', ['负债'], '幂函数是期末状态条件关联；帮助未规定幂函数、风险状态时点或平均本金计息。', 'code/model_v2/finance.py'),
    ('RISK_EXP', '提示不足以验证', ['负债'], '指数函数是经验拟合；当期基准及期末状态需正确绑定，帮助未确认函数形式。', 'code/model_v2/finance.py'),
    ('MATERIAL', '提示不足以验证', ['生产策略'], '单位差额是经验校准；只计复合梁，不能叠加比例校准，也不能扩展到连接件库存成本。', 'code/stepwise_model.py'),
    ('MATERIAL_PROP', '提示不足以验证', ['生产策略'], '比例参数不是官方材料附加费；练习2单基价不能独立识别跨价位比例关系；连接件未训练。', 'code/material_unit_cost_model.py'),
    ('INTEREST', '部分符合', ['负债'], '接受当期基准与短贷附加溢价；帮助未确认短贷=长贷+溢价或计息时点；未实现自动短贷借还。', 'code/interest_rate_model.py'),
    ('TOTAL', '提示不足以验证', ['需求预估'], '行业增长仍需独立情景，玩家增长输入和预算需求不能训练实际总量；历史增长外推不是官方需求函数。', 'code/cross_market_validation.py'),
    ('BASELINE', '条件诊断', ['需求要素', '需求预估'], '等份额只是基线；使用实际总量的oracle仅为条件诊断，不能当事前预测成绩。', 'code/cross_market_validation.py'),
    ('CAPACITY', '仅限定范围符合', ['生产策略', '产品销售优先级', '大客户订单'], '需求驱动且零库存零订单时产量截断、顺序交付符合；连接件自由生产不可截断，需库存和跨期订单。', 'code/build_model_inputs.py'),
    ('LABOR', '条件符合', ['运营改进', '生产策略'], 'q/效率及班次工资在给定正确产量效率时可计算；帮助未确认具体班次比例。新产品及当期工资必须重新绑定。', 'code/build_model_inputs.py'),
    ('OPERATING', '仅限定范围符合', ['营销', '研发', '运营改进', '大客户订单'], '本期投入作为费用与帮助相容；自由生产的库存改变、持有费、连接件、订单收入尚未实现。正式3管理费不可继续用4000。', 'code/model_v2/finance.py'),
    ('FINANCE', '完整规则未实现', ['负债', '结转亏损', '已收预付款', '额外实收资本'], '税亏抵扣方向符合；缺自动短贷借还利息、10%预付款及交付清算、库存和股权变化。只有零相关状态的条件链。', 'code/model_v2/finance.py'),
    ('GROWTH', '条件公式', ['研发', '大客户订单'], '增长比值本身成立；下期需求依赖前景、历史条件、竞争和产品，新订单下一回合交付不能混进普通需求增长。', 'code/stepwise_model.py'),
    ('HORIZON', '跨期收益模型未建立', ['研发', '运营改进', '大客户订单', '已收预付款'], '只对外部利润求和，不计算研发延期、运营累计和逐期经营；字典保留存量字段不是状态转移实现。', 'code/model_v2/horizon.py'),
    ('METRICS', '计算口径相容', ['需求预估'], '误差公式可核；必须区分实际、预算和条件回算，不能以预算重放证明需求预测有效。', 'code/fit_demand.py'),
    ('UNIFIED', '组合未完整符合', ['研发', '运营改进', '生产策略', '负债'], '正式1同期共享为用户假设；登记正式2曲线不代表完整迁移。历史条件、非零财务分支和正式3多产品仍缺。', 'code/unified_market.py'),
    ('T2V0', '正式3不适用', ['研发', '运营改进', '负债', '生产策略'], '练习2利率材料两组件已训练，迁移门槛仍关闭；代码明确只支持回合2，不可用于正式3。', 'code/t2v0_um/calibrated.py'),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    protected = set(ROOT / r['source'] for r in catalog)
    protected.update(ROOT.glob('raw/*help*'))
    protected.update((ROOT / 'code').rglob('*.py'))
    protected.update((ROOT / '模型说明').glob('*.md'))
    frozen_forecast=ROOT/'output/cross_market/future_predictions_20261011T081705179804Z.json'
    protected.add(frozen_forecast)
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in protected if p.is_file()}
    help_index = []
    for p in sorted((ROOT / 'raw').glob('*help.txt')):
        text = p.read_text(encoding='utf-8')
        modal = text.rsplit('- button "关闭":', 1)[-1]
        title = re.search(r'- heading "([^"]+)" \[level=1\]', modal).group(1)
        body = '\n'.join(line.removeprefix('- paragraph: ') for line in modal.splitlines() if line.startswith('- paragraph: '))
        help_index.append(dict(title=title, text=body, file=p.relative_to(ROOT).as_posix(), sha256=sha(p), action='复用原件', verified_current_text=title=='负债'))
    corpus = [(p, p.read_text(encoding='utf-8', errors='replace')) for p in (ROOT / 'raw').glob('*.txt')]
    for slug, title, panel, rnd, body in NEW_HELP:
        prior = next((p for p, text in corpus if body in text), None)
        p = prior or ROOT / f'raw/20261012_{slug}_help.json'
        if not prior:
            value = dict(archived_at=datetime.now(timezone(timedelta(hours=8))).isoformat(), observed_date='2026-10-12',
                source_url=f'http://sim.cesim.cn/ul/Decisions?panel={panel}&sim=se', market=5, team='营销团队', account='PYT',
                phase='formal', round=rnd, title=title, text=body, representation='verbatim visible modal excerpt',
                capture_method='cua_repl playwright.domSnapshot', timestamp_note='archived_at为写入时间；未保留精确首次读取时间',
                budget_panel={'capital':'资产负债表', 'advance':'现金流量表'}.get(slug), data_kind='help_rule', usable_for_demand_fit=False)
            if p.exists():
                existing = json.loads(p.read_text(encoding='utf-8'))
                assert existing['title']==title and existing['text']==body
            else:
                write(p, value)
        help_index.append(dict(title=title, text=body, file=p.relative_to(ROOT).as_posix(), sha256=sha(p), action='复用原件' if prior else '新增原件'))
    assert len(help_index)==12 and len({r['title'] for r in help_index})==12
    write(OUT / 'help_index.json', help_index)
    rows = [dict(model_code=c, status=s, help_rules=h, finding=f, implementation=p) for c,s,h,f,p in REVIEWS]
    assert len(rows)==22 and {r['model_code'] for r in rows}=={p.stem.rsplit('_',1)[0] for p in (ROOT/'模型说明').glob('*.md') if '_' in p.stem}
    bycode = {r['model_code']:r for r in rows}
    reviewed_versions=[]
    for r in catalog:
        doc=json.loads((ROOT/r['source']).read_text(encoding='utf-8'))
        value=doc
        for token in r['json_pointer'].strip('/').split('/') if r['json_pointer'] not in ('','/') else []:
            token=token.replace('~1','/').replace('~0','~')
            value=value[int(token)] if isinstance(value,list) else value[token]
        assert value is not None
        finding=bycode[r['model_code']]
        reviewed_versions.append(dict(model_code=r['model_code'],version_name=r['version_name'],source=r['source'],
            json_pointer=r['json_pointer'],sha256=sha(ROOT/r['source']),status=finding['status'],finding=finding['finding']))
    write(OUT/'model_review.json',rows)
    write(OUT/'saved_version_review.json',reviewed_versions)
    from build_model_inputs import production_and_delivery
    from model_v2.finance import accounts, parameters
    from model_v2.horizon import self_check as horizon_check
    import operations_rho
    import interest_rate_model
    import material_unit_cost_model
    checks={}
    a=production_and_delivery(10,100,.2,[3,9],[0,1],28,1.65,2.56,0,.1,.35)
    b=production_and_delivery(10,100,.2,[3,9],[1,0],28,1.65,2.56,0,.1,.35)
    assert a['sales']==[3,7] and b['sales']==[1,9]
    checks['zero_inventory_priority_correct']=True
    free=production_and_delivery(10,100,.2,[1,1],[0,1],28,1.65,2.56,0,.1,.35)
    assert free['production']==2 and free['production']!=10
    checks['free_production_unsupported_demonstrated']=dict(current_output=2,free_production_planned=10,expected_inventory_if_deliver_2=8)
    inp=json.loads((ROOT/'分步模型拟合与验证.json').read_text(encoding='utf-8'))['decisions']['current_inputs']
    decision=dict(inp['decision'],long_rate=inp['decision']['long_rate']/100)
    base=accounts(inp['state'],decision,inp['demand'],inp['efficiency'],parameters())
    assert abs(base['balance_error'])<1e-6
    state=dict(inp['state'],tax_loss=max(base['pretax'],0)+10000)
    tax=accounts(state,decision,inp['demand'],inp['efficiency'],parameters())
    assert tax['tax']==0
    checks['tax_loss_deduction']=True
    low=accounts(inp['state'],decision,inp['demand'],inp['efficiency'],dict(parameters(),minimum_cash=base['cash']+100))
    assert not low['fully_computed_in_scope'] and abs(low['short_debt_needed_before_unidentified_short_interest']-100)<1e-6
    checks['short_loan_incomplete_flag']=True
    checks['horizon']=horizon_check()
    operations_rho.self_test(); interest_rate_model.self_check(); material_unit_cost_model.self_check()
    checks['existing_component_self_checks']=True
    curves=[]
    for r in catalog:
        p=r['parameters'].get('parameters')
        if r['model_code']=='RD' and p is not None:
            aa,bb,cc,dd=p
            assert bb>0 and cc>0 and 0<dd<1
            curves.append(dict(version=r['version_name'],increasing=True,diminishing_returns=True,history_condition_verified=False))
        elif r['model_code']=='OPS':
            p=p or r['parameters'].get('curve_parameters')
            if p is not None:
                assert len(p)==3 and p[1]>0 and p[2]>0
                curves.append(dict(version=r['version_name'],increasing=True,diminishing_returns=True,history_condition_verified=False))
    checks['curve_shape_checks']=curves
    assert all(sha(ROOT/name)==digest for name,digest in before.items())
    checks['protected_originals_unchanged']=True
    checks['reviewed_classes']=len(rows)
    checks['reviewed_catalog_entries']=len(reviewed_versions)
    checks['help_rules']=len(help_index)
    checks['new_help_rules']=sum(r['action']=='新增原件' for r in help_index)
    checks['all_models_certified_compliant']=False
    future=json.loads(frozen_forecast.read_text(encoding='utf-8'))
    write(OUT/'prediction_review.json',dict(
        frozen_formal1=dict(file=frozen_forecast.relative_to(ROOT).as_posix(),sha256=sha(frozen_forecast),
            records=len(future['records']),status='保留原预测用于事后评分；不可作为当前正式3预测'),
        archived_scenarios='旧分步/网格/联合情景基于零库存零订单及早期参数，仅按原回合、原输入解释',
        unified='正式1条件份额回算；不作为正式2或正式3事前误差',
        t2v0='两组件已训练，整体预测关闭；回合3超出代码支持范围',
        current_formal3=dict(complete_prediction_available=False,new_product='连接件',production_strategy='自由生产',
            required=['正式2实际期末结转','正式3参数和曲线历史条件','连接件需求/效率/材料','库存及订单/预收款','短贷完整分支']),
        interpretation='本次审查各预测链的规则适用性；没有重算全部历史数值或改写冻结预测'))
    table=['| 模型 | 审查结论 | 依据与缺口 |','| --- | --- | --- |']
    table += [f"| {r['model_code']} | {r['status']} | {r['finding']} |" for r in rows]
    template=(OUT/'report_base.md').read_text(encoding='utf-8')
    report=template.replace('{{MODEL_TABLE}}','\n'.join(table)).replace('{{VERSION_COUNT}}',str(len(reviewed_versions)))
    (OUT/'report.md').write_text(report,encoding='utf-8')
    write(OUT/'verification.json',checks)
    write(OUT/'source_manifest.json',before)
    print(json.dumps({k:v for k,v in checks.items() if k not in ('curve_shape_checks','horizon')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
