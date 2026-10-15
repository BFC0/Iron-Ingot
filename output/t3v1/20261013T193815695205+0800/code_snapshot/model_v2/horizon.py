"""Formal rounds t..6 only; preserve terminal state without inventing rewards."""
import math


def remaining_profit(start_round, periods):
    if not isinstance(start_round,int) or isinstance(start_round,bool) or not 1<=start_round<=6:
        raise ValueError('Formal start round must be 1..6')
    required=list(range(start_round,7))
    if [r['round'] for r in periods]!=required:
        raise ValueError('Supply exactly ordered formal rounds t..6; no round 7 or duplicate/missing period')
    complete=all(r.get('in_scope') is True and isinstance(r.get('profit'),(int,float))
                 and not isinstance(r.get('profit'),bool) and math.isfinite(r['profit']) for r in periods)
    return dict(start_round=start_round,end_round=6,remaining_rounds=7-start_round,
        remaining_profit=sum(r['profit'] for r in periods) if complete else None,
        complete_profit_path=complete,terminal_state=periods[-1].get('end_state'),terminal_reward=None,
        ranking_eligible=False,
        scope='仅剩余回合利润小计；需独立验证状态结转和计分规则才可用于完整决策排名；无自动变现、清债或第7回合收益')


def self_check():
    for start in range(1,7):
        state=dict(cash=12,long_debt=7,inventory=3,tax_loss=9,orders=[{'delivery_round':7}],rd_stock=4,operations_stock=5)
        path=[dict(round=i,profit=i,in_scope=True,end_state=state) for i in range(start,7)]
        result=remaining_profit(start,path)
        assert result['remaining_profit']==sum(range(start,7)) and result['remaining_rounds']==7-start
        assert result['terminal_state']==state and result['terminal_reward'] is None
        path[-1]['profit']=None
        assert remaining_profit(start,path)['remaining_profit'] is None
    for path in [[],[dict(round=7,profit=100,in_scope=True)],
                 [dict(round=6,profit=1,in_scope=True),dict(round=6,profit=1,in_scope=True)]]:
        try: remaining_profit(6,path)
        except ValueError: pass
        else: raise AssertionError('Invalid horizon accepted')
    return dict(six_start_rounds=True,unknown_profit_not_zero=True,round7_and_missing_or_duplicate_rejected=True,
                terminal_state_preserved=True,terminal_reward_not_invented=True)
