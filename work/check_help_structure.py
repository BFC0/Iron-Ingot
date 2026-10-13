"""Mechanism checks against current implementations; updates review artifacts only."""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/model_v2')]
import cross_market_validation as demand
import operations_rho as ops
OUT=ROOT/'output/help_review/20261012'


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def main():
    paths=list((ROOT/'code').rglob('*.py'))
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    params=json.loads((ROOT/'output/cross_market/parameters_20261011T081705179804Z.json').read_text(encoding='utf-8'))
    row=dict(country='泰国',price=1800,initial_price=1800,general=0,designer=0)
    rd_rows=[dict(row,rd=1000,previous_rd=0),dict(row,rd=0,previous_rd=1000),dict(row,rd=0,previous_rd=0)]
    rd_feature=demand.feature_matrix(rd_rows,params['rd_curve_parameters'])[:,4]
    assert rd_feature[0]>rd_feature[1]>rd_feature[2]
    op_rows=[dict(operations=1000,previous_operations=0),dict(operations=0,previous_operations=1000),dict(operations=0,previous_operations=0)]
    op_params=[.45,.75,400.1058201058195]
    import numpy as np
    op_factor=ops.factors(op_rows,op_params,np.array([.5]))[:,0]
    assert op_factor[0]>op_factor[1]>op_factor[2] and op_factor[2]==op_params[0]
    history=[dict(operations=100,previous_operations=200,operations_stock=0),dict(operations=100,previous_operations=200,operations_stock=10000)]
    paired=ops.factors(history,op_params,np.array([.5]))[:,0]
    assert paired[0]==paired[1]
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in before.items())
    write(OUT/'structural_checks.json',dict(rd_current_and_next_proxy_present=True,rd_effective_input=[1000,500,0],
        rd_feature=rd_feature.tolist(),operations_effective_input=[1000,500,0],operations_factor=op_factor.tolist(),
        operations_reverts_to_zero_input_after_two_rounds=True,different_earlier_stock_ignored=paired.tolist(),
        source_code_unchanged=True,scope='synthetic mechanism probes, not empirical time-weight identification',
        source_hashes={p.relative_to(ROOT).as_posix():h for p,h in before.items()}))
    updates={
        'RD':('当期与单期滞后代理未获机制确认','已有R_t+0.5R_(t-1)；不是完全遗漏下期影响，但时间权重、短期/延期曲线结构及历史条件未经确认，跨期收益链未接通。'),
        'OPS':('当期曲线相容；累计调用缺失','饱和形状相容，不代表累计机制成立；调用只读取本期与上期运营支出。'),
        'EFF':('累计机制未实现','只读取O_t与O_(t-1)，更早历史被忽略；单次投入第二个后续回合恢复零投入乘数，没有持续可更新的累计状态。'),
        'HORIZON':('跨期收益模型未建立','只对外部利润求和，不计算研发延期、运营累计和逐期经营；字典保留存量字段不是状态转移实现。'),
    }
    for name in ('model_review.json','saved_version_review.json'):
        rows=json.loads((OUT/name).read_text(encoding='utf-8'))
        for r in rows:
            if r['model_code'] in updates:
                r['status'],r['finding']=updates[r['model_code']]
        write(OUT/name,rows)
    # Keep the generator and current report in agreement without rerunning model fits.
    for name in ('report_base.md','report.md'):
        p=OUT/name
        text=p.read_text(encoding='utf-8')
        marker='结构审查更正：[按帮助正文检查模型自身的机制](模型结构重审.md)。研发已有当期/单期滞后代理，不能误报为完全没有；运营累计状态与跨期经营收益链确实未实现。本更正优先于下方原“部分符合”结论。\n\n'
        if marker not in text:
            text=text.replace('\n\n','\n\n'+marker,1)
        if name=='report.md':
            lines=text.splitlines()
            for i,line in enumerate(lines):
                for code,(status,finding) in updates.items():
                    if line.startswith(f'| {code} |'):
                        lines[i]=f'| {code} | {status} | {finding} |'
            text='\n'.join(lines)+'\n'
        p.write_text(text,encoding='utf-8')
    print(json.dumps(dict(rd_next_effect_proxy=True,operations_stock_missing=True,cross_period_profit_chain_missing=True,source_code_unchanged=True),ensure_ascii=False))


if __name__=='__main__':
    main()
