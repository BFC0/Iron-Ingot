"""Use formal4-trained aggregate marketing responses and formal5 importance values."""
import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import train_formal4_marketing as train
import solve_formal5_full as base
import numpy as np

ROOT=train.ROOT;OUT=train.OUT
PRIOR=ROOT/(ROOT/'work/formal5_full_active.txt').read_text(encoding='utf-8-sig').strip()
base.OUT=OUT
read=base.read;save=base.save


class MarketingModel(base.ScenarioModel):
    def __init__(self):
        super().__init__()
        fitted=read(OUT/'marketing_models_formal4.json')
        importance=read(OUT/'sales_importance_4_5.json')
        self.importance=importance
        self.original_beta=copy.deepcopy(self.beta)
        self.beta4=copy.deepcopy(self.beta)
        for mode in ['SHARE','COUNTRY']:
            for j,p in enumerate(base.P):
                for k,c in enumerate(base.C):
                    m=fitted[p][mode if mode=='SHARE' else 'COUNTRY/'+c]
                    self.beta4[mode][j,k,2:4]=[m['beta_general'],m['beta_designer']]
        self.beta=copy.deepcopy(self.beta4)
        for mode in self.beta:
            for j,p in enumerate(base.P):
                for k,c in enumerate(base.C):
                    for index,factor in enumerate(['价格','unused','一般营销','设计师营销','研发']):
                        if index==1:continue
                        self.beta[mode][j,k,index]*=importance['ratios_5_over_4'][p][c][factor]
        self.local_general=self.gb.copy();self.local_designer=self.db.copy()
        self.general_total=float(self.gb.sum());self.designer_total=float(self.db.sum())
        self.gb=np.full((2,2),self.general_total);self.db=np.full((2,2),self.designer_total)
        save('applied_marketing_coefficients.json',dict(
            training_round=4,application_round=5,training_source='actual_initial3_to_closing4_company_expense_proxy',
            fixed_price_rd_source='formal3_known_response_coefficients',
            raw_formal4_beta={k:v.tolist() for k,v in self.beta4.items()},
            beta_with_formal5_importance={k:v.tolist() for k,v in self.beta.items()},
            importance_ratios=importance['ratios_5_over_4'],
            importance_mapping_assumption='beta5 = beta4 / importance4 * importance5, one replacement only',
            marketing_application='Primary aggregate budget response; eight allocations are objective-equivalent, not identified causal local responses'))

    def demand(self,x,cfg,t):
        transformed=x.copy();cfg=dict(cfg)
        mapping=cfg.pop('marketing_mapping','aggregate')
        cfg.pop('marketing_proxy',None)
        if mapping=='aggregate':
            transformed[4:8]=x[4:8].sum(axis=0)
            transformed[8:12]=x[8:12].sum(axis=0)
        elif mapping=='inferred_local':
            # shortcut: current allocation shares infer local scaling; keep as a stress case until competitor allocations exist.
            transformed[4:8]=x[4:8]*(self.general_total/self.local_general.ravel())[:,None]
            transformed[8:12]=x[8:12]*(self.designer_total/self.local_designer.ravel())[:,None]
        else:raise ValueError('Unknown marketing application mapping')
        return super().demand(transformed,cfg,t)


def distribute(total,weights):
    raw=total*weights/weights.sum();values=np.floor(raw).astype(int)
    for i in np.argsort(-(raw-values))[:int(round(total-values.sum()))]:values[i]+=1
    assert values.sum()==total
    return values


def main():
    assert not (OUT/'full_result.json').exists()
    for path in (PRIOR/'latest').glob('*.json'):
        dest=OUT/'latest'/path.name
        if not dest.exists():shutil.copy2(path,dest)
    refreshed=read(OUT/'latest/checklist_refresh.json')
    assert refreshed['tables'][1]==read(PRIOR/'latest/checklist.json')['tables'][1]
    shutil.copy2(OUT/'latest/checklist_refresh.json',OUT/'latest/checklist.json')
    m=MarketingModel();cfgs=base.configs()
    cfgs=[c for c in cfgs if c['name']!='营销合计代理']
    cfgs += [dict(cfgs[0],name='推断局部分配响应',marketing_mapping='inferred_local')]
    base_e=m.evaluate(m.baseline,cfgs[0],True)
    expected=m.share*m.totals*np.array([1.07,.95])[None,:]
    assert np.allclose(base_e['periods'][0]['demand'],expected)
    budget=m.evaluate(m.baseline,cfgs[0],True,budget=True)
    save('budget_replay.json',dict(model=budget,display_profit=4435,error_kusd=budget['periods'][0]['profit']-4435,
        scope='latest paired draft budget, not actual outcome or new-candidate platform validation'))
    winners=base.search(m,cfgs)
    comparisons=[]
    for name,x in [('最新基准',m.baseline),('中性利润候选',winners[0]),('稳健利润候选',winners[1])]:
        raw=x.copy()
        if name!='最新基准':
            x[4:8]=distribute(int(round(x[4:8].sum())),m.local_general.ravel())
            x[8:12]=distribute(int(round(x[8:12].sum())),m.local_designer.ravel())
            for c in cfgs[:3]:
                assert abs(m.evaluate(raw,c)[0][0]-m.evaluate(x,c)[0][0])<1e-7
        e=[dict(name=c['name'],**m.evaluate(x,c,True)) for c in cfgs]
        assert all(v['balance_error_max']<1e-6 and v['quantity_error_max']<1e-8 for v in e)
        if name!='最新基准':assert all(v['feasible'] for v in e[:3])
        comparisons.append(dict(name=name,x=x.tolist(),raw_search_allocation=raw.tolist(),evaluations=e))
    save('full_result.json',dict(status='FORMAL4_MARKETING_FIT_WITH_FORMAL5_IMPORTANCE_REPLACEMENT',
        marketing_training_round=4,nonmarketing_known_response_round=3,importance_round=5,
        baseline_anchor_round=4,application_round=5,end_round=6,
        country_allocation_identified=False,comparisons=comparisons,configs=cfgs))
    base.sensitivity(m,comparisons,cfgs)
    # A fixed-total redistribution must not manufacture profit under an aggregate-only trained response.
    x=np.array(comparisons[2]['x']);z=x.copy();amount=min(10.,z[6]);z[6]-=amount;z[4]+=amount
    assert abs(m.evaluate(x,cfgs[0])[0][0]-m.evaluate(z,cfgs[0])[0][0])<1e-8
    if amount>0:assert not np.allclose(m.demand(x[:,None],cfgs[-1],0),m.demand(z[:,None],cfgs[-1],0))
    m2=MarketingModel();d1=m.demand(x[:,None],cfgs[0],0);d2=m2.demand(x[:,None],cfgs[0],0)
    assert np.allclose(d1,d2), 'Importance must not be multiplied a second time'
    changed=x.copy();changed[6]+=100
    assert m.demand(changed[:,None],cfgs[0],0)[1,0,0]>=d1[1,0,0]
    validation=dict(status='PASS',source_pairs=376,fit_pairs=264,weights_4_and_5=32,
        trained_marketing_round=4,application_importance_round=5,
        importance_replacement_idempotent=True,negative_relative_position_not_multiplied=True,
        aggregate_spend_conservation=True,fixed_total_allocation_equivalence=True,
        quantity_and_financial_identities=True,core_cash_floor=3000,
        candidate_sensitivity_fields=42,country_product_allocations_identified=False,
        actual_independent_forward_validation=False,platform_modified=False)
    save('validation.json',validation)
    for path in [Path(__file__),ROOT/'work/train_formal4_marketing.py']:
        shutil.copy2(path,OUT/path.name)
    print(json.dumps(validation,ensure_ascii=False))
    for p in comparisons:print(p['name'],p['x'],[(e['name'],round(e['profit_5_to_6'],2),round(e['sampled_minimum_cash'],2)) for e in p['evaluations'][:3]],flush=True)


if __name__=='__main__':main()
