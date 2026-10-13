"""Context is evidence, not an inference from a market or round label."""
from core import *
from archive_and_report import table_rows


def fingerprint(path):
    doc=read(path)
    cells=[r['cells'] for r in table_rows(doc['snapshot']) if len(r['cells'])==4]
    return digest(ROOT/path),cells


def tag(rows):
    registry={
        'M5_P1_FORMAL1_VISIBLE':dict(market_id=5,phases=[['practice',1],['formal',1]],
            outlook='raw/20261011_practice1_outlook.json',comparison='raw/20261011_model_v2_round1_outlook.json',
            narrative='泰国需求难回升、印尼略增；本年度无大客户；生产率提高',
            base_rate=.03,material_cost=900,machine_unit_capex=100,
            marketing_importance='未见练习2的越来越重要叙述',status='VISIBLE_CONTEXT_VERIFIED_NOT_HIDDEN_MECHANISM'),
        'M5_P2_GROWTH_MARKETING_BULK':dict(market_id=5,phases=[['practice',2]],
            outlook='raw/20261011_practice2_outlook.json',comparison=None,
            narrative='两国复合梁预计增5–10%；设计师及一般营销越来越重要；香港2000单位报价，明年交付',
            base_rate=.025,material_cost=1053,machine_unit_capex=100,
            narrative_future_material_increase=.20,narrative_future_machine_decline_up_to=.40,
            displayed_current_material_change=.17,current_machine_change=0,
            source_conflict='叙述未来约20%与参数当期17%并列；不强行统一或把未来机器降40%当作当期价60',
            screenshot_identity='用户明确练习2；原图无账号/市场，市场5由旧网页快照全文/参数匹配佐证',
            status='VISIBLE_CONTEXT_VERIFIED_NOT_HIDDEN_MECHANISM')}
    for context,meta in registry.items():
        sha,cells=fingerprint(meta['outlook'])
        meta.update(outlook_sha256=sha,parameter_rows=cells,parameter_fingerprint=hashlib.sha256(json.dumps(cells,ensure_ascii=False).encode()).hexdigest())
        if meta['comparison']:
            _,other=fingerprint(meta['comparison'])
            assert cells==other
            meta['practice_formal_visible_parameters_equal']=True
    labels=[]
    for r in rows:
        found=next((c for c,m in registry.items() if r['market_id']==m['market_id'] and [r['phase'],r['round']] in m['phases']),None)
        r['context_id']=found or f'UNVERIFIED_M{r["market_id"]}_{r["phase"]}{r["round"]}'
        r['context_verified']=found is not None
        r['context_fit_eligible']=bool(found and r['usable_for_fit'])
        r['context_source']=registry[found]['outlook'] if found else None
        labels.append(dict(key=key(r),context_id=r['context_id'],context_verified=r['context_verified'],
                           fit_eligible=r['context_fit_eligible'],outlook_source=r['context_source'],
                           status='WITHIN_CONTEXT_RESEARCH' if r['context_fit_eligible'] else 'QUARANTINED_FROM_VERIFIED_CONTEXT_FIT'))
    verified=[r for r in rows if r['context_fit_eligible']]
    unverified=[r for r in rows if r['usable_for_fit'] and not r['context_verified']]
    assert len(verified)==40 and len(unverified)==360
    return dict(registry=registry,row_labels=labels,verified_training_n=len(verified),unverified_training_n=len(unverified),
        quarantine='逻辑隔离，不移动删除源数据；其他市场编号的前景尚未逐一核验',
        old_cross_round_status='练习1→2为跨情境回溯；不得作为同情境迁移或隐藏函数改变证据',
        old_B_status='未核验情境的跨市场/跨回合探索；不得作为当前确定推荐依据',
        pre_context_run='output/model_v2/20261011T194918540163+0800',
        pre_context_run_status='SUPERSEDED_FOR_APPLICABILITY_KEEP_FOR_REPRODUCTION',
        need='其他市场各回合前景、国别需求机制和正式实际；同参数表也不证明同隐藏函数')


def research(rows,out):
    from demand import choose,options,prediction_rows
    params=read(FROZEN)['rd_curve_parameters']
    pools={};predictions=[]
    for context in sorted({r['context_id'] for r in rows if r['context_fit_eligible']}):
        rr=[r for r in rows if r['context_id']==context and r['context_fit_eligible']]
        selected,path=choose(rr,params,list(options()))
        selected_share,share_path=choose(rr,params,[dict(standardized=True,piecewise=p,rho=selected['rho'],penalty=l,loss='share') for p in [False,True] for l in PENALTIES])
        path+=share_path
        best=min(r['cv_share_mae_pp'] for r in path)
        winner=min([r for r in path if r['cv_share_mae_pp']<=best*1.01],key=lambda r:(r['parameter_count'],r['cv_share_mae_pp']))
        selected={k:winner[k] for k in ['standardized','piecewise','rho','penalty','loss']}
        fitted=fit(rr,params,**selected)
        pr=prediction_rows(rr,fitted,params,'A/'+context,rr)
        for r in pr:
            r.update(context_id=context,context_verified=True,category='in_sample_context_model',external_validation=False)
        predictions+=pr
        pools['A/'+context]=dict(context_id=context,market_id=5,selected=selected,cv_path=path,refit_model=fitted,
            training_keys=[key(r) for r in rr],forward_share_mae_pp=None,cv_share_mae_pp=winner['cv_share_mae_pp'],
            parameter_fit_scope='单一可核前景情境；只有一个回合，不能同时识别情境和回合效应',
            joint_extrapolation_note='当前投入范围不证明联合或跨情境支持',
            future_applicability='仅作为相同可见情境的研究候选；正式实际独立检验未完成')
        write(out/f'context_fit_{context}.json',pools['A/'+context])
        print(f'CONTEXT {context}: {selected}; inner CV {winner["cv_share_mae_pp"]:.4f}pp',flush=True)
    return dict(status='CONTEXT_STRATIFIED_RETROSPECTIVE_RESEARCH',pools=pools,predictions=predictions,
        stage2_gate=False,stage2_gate_reason='只有市场5两种各一回合可核情境；没有同情境跨回合外部验证，其他市场360条拟合样本隔离',
        assumptions=['研发曲线为练习1/正式1可见曲线；练习2迁移仍为敏感性假设','营销合计代理不能识别国别因果贡献'],
        selection='各可核情境单独在内部留队选参，逐折独立尺度；不汇总未核情境模型')
