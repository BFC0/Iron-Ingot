"""t5v2 frozen inference: formal4 marketing training with formal5 importance; no training or platform writes."""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'work/python_packages'))
import numpy as np

def curve(x,item):
    p=item['parameters']
    return p[0]+p[1]*(x+p[2])**p[3] if item['form']=='power' else p[0]+p[1]*x/(p[2]+x)

def effective_investment(current, previous, item):
    return item['current_weight'] * current + item['previous_weight'] * previous


class _BaseScenario:

    def demand(self, x, cfg, t):
        n = x.shape[1]
        price = x[:4].reshape(2, 2, n)
        g = x[4:8].reshape(2, 2, n)
        d = x[8:12].reshape(2, 2, n)
        b = self.beta[cfg['response']]
        tail = self.tail[cfg['response']]
        price_coefficients = np.array([[b[j, k, k] for k in range(2)] for j in range(2)])
        logp = -price_coefficients[:, :, None] * np.log(price / self.baseprices[:, :, None]) * cfg.get('price_elasticity', 1.0)
        thresholds = np.array([[2700.0, 3000.0], [1.5, 1.5]])
        logp -= tail[:, :, None] * (np.maximum(np.log(price / thresholds[:, :, None]), 0) - np.maximum(np.log(self.baseprices / thresholds), 0)[:, :, None])
        gm = np.log((1000 + g) / (1000 + self.gb[:, :, None]))
        dm = np.log((1000 + d) / (1000 + self.db[:, :, None]))
        if cfg.get('marketing_proxy') == 'total':
            gm = np.broadcast_to(np.log((1000 + g.sum(axis=(0, 1))) / (1000 + self.gb.sum()))[None, None, :], (2, 2, n))
            dm = np.broadcast_to(np.log((1000 + d.sum(axis=(0, 1))) / (1000 + self.db.sum()))[None, None, :], (2, 2, n))
        rdlog = np.array([np.log(curve(effective_investment(x[12+j], x[12+j] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.rdbase[j], self.investment_mapping['rd']), self.rdcurves[j]) / curve(effective_investment(self.rdbase[j], self.rdbase[j], self.investment_mapping['rd']), self.rdcurves[j])) for j in range(2)])
        delta = logp + cfg.get('marketing_scale', 1.0) * (b[:, :, 2, None] * gm + b[:, :, 3, None] * dm) + b[:, :, 4, None] * rdlog[:, None, :]
        delta = np.clip(delta, -30, 30)
        odds = self.share[:, :, None] * np.exp(delta)
        s = odds / (odds + (1 - self.share[:, :, None]) * cfg.get('rival_attractiveness', 1.0))
        growth = np.array([1.07, 0.95]) * cfg.get('market_scale', 1.0)
        total = self.totals * growth[None, :]
        if t:
            total = total * np.array(cfg['future_growth'])[:, None]
        demand = s * total[:, :, None]
        return demand

    def evaluate(self, decision, cfg, details=False, budget=False, overrides=None):
        x = np.asarray(decision, float)
        x = x[:, None] if x.ndim == 1 else x
        n = x.shape[1]
        overrides = overrides or {}
        prices = x[:4].reshape(2, 2, n)
        inv = np.broadcast_to(self.invbase[:, None], (2, n)).copy()
        book = np.broadcast_to(self.invbook[:, None], (2, n)).copy()
        cap = np.broadcast_to(self.capbase[:, None], (2, n)).copy()
        invest = np.array([np.rint(x[15]), 20 * np.rint(x[16])])
        cap += invest
        cash = np.full(n, self.state['cash'])
        ar = np.full(n, self.state['ar'])
        ap = np.full(n, self.state['ap'])
        machine = np.full(n, self.state['machine_book'])
        building = np.full(n, self.state['building_book'])
        equity = np.full(n, self.state['equity'])
        assets = np.full(n, self.state['assets'])
        debt = np.full(n, self.state['long_debt'])
        loss = np.full(n, cfg.get('tax_loss', 0.0))
        workers = np.full(n, self.prevworkers)
        total = np.zeros(n)
        minimum = np.full(n, np.inf)
        balance_max = np.zeros(n)
        quantity_error = np.zeros(n)
        periods = []
        valid = np.ones(n, bool)
        for t in range(2):
            demand = self.demand(x, cfg, t)
            if budget and t == 0:
                demand = np.broadcast_to(np.array([[self.current[58], self.current[59]], [self.current[61], self.current[62]]])[:, :, None], (2, 2, n)).copy()
            for j, rows in enumerate([[58, 59], [61, 62]]):
                for k, row in enumerate(rows):
                    if t == 0 and row in overrides:
                        demand[j, k] = overrides[row]
            for j, rows in enumerate([[65, 66], [68, 69]]):
                for k, row in enumerate(rows):
                    if row in overrides:
                        demand[j, k] *= (1 + overrides[row] / 100) / [1.07, 0.95][k]
            if t:
                for j, row in enumerate([72, 73]):
                    if row in overrides:
                        demand[j] *= (1 + overrides[row] / 100) / cfg['future_growth'][j]
            ef = self.effbase[:, None] * curve(effective_investment(x[14], x[14] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.opsbase, self.investment_mapping['operations']), self.opcurve) / curve(effective_investment(self.opsbase, self.opsbase, self.investment_mapping['operations']), self.opcurve) * cfg.get('efficiency_scale', 1.0)
            if budget:
                ef = np.broadcast_to(np.array([self.current[76], self.current[77]])[:, None], (2, n)).copy()
            for j, row in enumerate([76, 77]):
                if row in overrides:
                    ef[j] = overrides[row]
            q = cap * x[17:19] / 100
            if t and cfg.get('recourse', True):
                q = np.minimum(cap, np.maximum(demand.sum(axis=1) - inv, 0))
            else:
                q[0] = np.minimum(q[0], np.maximum(demand[0].sum(axis=0) - inv[0], 0))
            available = inv + q
            sales = np.zeros((2, 2, n))
            net = prices - self.freight[:, :, None]
            priorities = []
            for j in range(2):
                domestic = net[j, 0] >= net[j, 1]
                key = 34 if j == 0 else 37
                if key in overrides:
                    domestic = np.full(n, overrides[key] == '第一')
                key2 = 35 if j == 0 else 38
                if key2 in overrides:
                    domestic = np.full(n, overrides[key2] != '第一')
                first = np.minimum(np.where(domestic, demand[j, 0], demand[j, 1]), available[j])
                second = np.minimum(np.where(domestic, demand[j, 1], demand[j, 0]), available[j] - first)
                sales[j, 0] = np.where(domestic, first, second)
                sales[j, 1] = np.where(domestic, second, first)
                priorities.append(np.where(domestic, 0, 1))
            ending = np.maximum(available - sales.sum(axis=1), 0)
            wage = 43.5 * (cfg.get('future_wage', 1.0) if t else 1.0)
            bands = [np.minimum(q, cap / 3), np.minimum(np.maximum(q - cap / 3, 0), cap / 3), np.maximum(q - 2 * cap / 3, 0)]
            payroll = (bands[0] + 1.65 * bands[1] + 2.56 * bands[2]) / ef * wage
            newworkers = (q / ef).sum(axis=0)
            firing = np.maximum(workers * 0.9 - newworkers, 0) * wage * 0.35
            if cfg.get('firing_scope') == 'product':
                prev = np.array([92.84, 25.1])[:, None] if t == 0 else prev_product_workers
                firing = (np.maximum(prev * 0.9 - q / ef, 0) * wage * 0.35).sum(axis=0)
            material = self.costs[cfg.get('material', 'proportional')] * cfg.get('material_scale', 1.0)
            material_cost = q * material[:, None]
            production_cost = material_cost + payroll
            current_unit = np.divide(production_cost, q, out=np.divide(book, np.maximum(inv, 1e-30)), where=q > 1e-12)
            if cfg.get('valuation') == 'weighted':
                current_unit = np.divide(book + production_cost, available, out=np.zeros_like(book), where=available > 0)
            endingbook = ending * current_unit
            cogs = (book + production_cost - endingbook).sum(axis=0)
            revenue = (sales * prices).sum(axis=(0, 1))
            transport = (sales * self.freight[:, :, None]).sum(axis=(0, 1))
            spending = x[4:15].sum(axis=0)
            ebitda = revenue - cogs - transport - 0.6 * ending.sum(axis=0) - spending - firing - 10050
            capex = (invest * np.array([78.0, 1.1])[:, None]).sum(axis=0) if t == 0 else np.zeros(n)
            building_capex = cfg.get('building_capex', 800.0)
            md = (machine + capex) * 0.15
            bd = building * 0.07
            ebit = ebitda - md - bd
            change = 100 * np.rint(x[19]) if t == 0 else np.zeros(n)
            newdebt = debt + change
            ratio = equity / np.maximum(assets + change, 1.0)
            risk = self.r['risk']['solvency_exponential']['parameters']
            rate = 0.05 + risk[0] * np.exp(-risk[1] * np.clip(ratio, 0, 1))
            if budget:
                rate = np.full(n, self.current[79] / 100)
            if 79 in overrides:
                rate = np.full(n, overrides[79] / 100)
            timing = cfg.get('interest_timing', 0.5)
            interest = ((1 - timing) * debt + timing * newdebt) * rate
            newar = revenue * cfg.get('ar_days', 30.0) / 365
            newap = material_cost.sum(axis=0) * 30 / 365
            k = cash + ebitda - interest + ar - newar + newap - ap + book.sum(axis=0) - endingbook.sum(axis=0) - capex - building_capex + change
            no_tax_cash = (k + 0.005 * cash) / 0.995
            taxable = ebit - interest + 0.005 * (cash + no_tax_cash) - loss > 0
            newcash = np.where(taxable, (k + 0.005 * cash * 0.71 - 0.29 * (ebit - interest - loss)) / (1 - 0.005 * 0.71), no_tax_cash)
            cash_interest = 0.005 * (cash + newcash)
            pretax = ebit - interest + cash_interest
            tax = np.maximum(pretax - loss, 0) * 0.29
            profit = pretax - tax
            newequity = equity + profit
            newmachine = machine + capex - md
            newbuilding = building + building_capex - bd
            newassets = newmachine + newbuilding + newar + newcash + endingbook.sum(axis=0) + self.other_assets
            error = newassets - newequity - newdebt - newap
            balance_max = np.maximum(balance_max, np.abs(error))
            quantity_error = np.maximum(quantity_error, np.abs(inv + q - sales.sum(axis=1) - ending).max(axis=0))
            min_this = np.minimum(newcash, cash + change - capex - building_capex)
            minimum = np.minimum(minimum, min_this)
            valid &= (newdebt >= 0) & (newequity > 0) & (ratio > 0.25) & (ratio < 0.97) & np.isfinite(profit)
            total += profit
            if details:
                periods.append(dict(round=5 + t, profit=float(profit[0]), cash=float(newcash[0]), minimum_sampled_cash=float(min_this[0]), revenue=float(revenue[0]), ebitda=float(ebitda[0]), ebit=float(ebit[0]), tax=float(tax[0]), rate=float(rate[0]), long_interest=float(interest[0]), cash_interest=float(cash_interest[0]), long_debt=float(newdebt[0]), assets=float(newassets[0]), equity=float(newequity[0]), demand=demand[:, :, 0].tolist(), sales=sales[:, :, 0].tolist(), production=q[:, 0].tolist(), opening_inventory=inv[:, 0].tolist(), closing_inventory=ending[:, 0].tolist(), inventory_book=endingbook[:, 0].tolist(), capacity=cap[:, 0].tolist(), efficiency=ef[:, 0].tolist(), workers=float(newworkers[0]), materials=material_cost[:, 0].tolist(), payroll=payroll[:, 0].tolist(), firing=float(firing[0]), transport=float(transport[0]), holding=float(0.6 * ending[:, 0].sum()), spending=float(spending[0]), machine_capex=float(capex[0]), depreciation=float(md[0] + bd[0]), priority=[int(v[0]) for v in priorities], balance_error=float(error[0])))
            if details:
                rd_previous = x[12:14] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.rdbase[:, None]
                op_previous = x[14] if t and cfg.get('future_mapping') != 'freeze_formal5' else self.opsbase
                periods[-1]['effective_rd_kusd'] = effective_investment(x[12:14], rd_previous, self.investment_mapping['rd'])[:, 0].tolist()
                periods[-1]['effective_operations_kusd'] = float(effective_investment(x[14], op_previous, self.investment_mapping['operations'])[0])
                periods[-1]['future_mapping_assumption'] = bool(t)
            cash, ar, ap, machine, building, debt, equity, assets = (newcash, newar, newap, newmachine, newbuilding, newdebt, newequity, newassets)
            loss = np.maximum(loss - np.maximum(pretax, 0), 0) + np.maximum(-pretax, 0)
            inv, book, workers = (ending, endingbook, newworkers)
            prev_product_workers = q / ef
            cap *= 0.85
        penalty = np.maximum(3000 - minimum, 0) * 100 + np.where(valid, 0.0, 100000000.0)
        penalty += np.maximum(x[4:8].sum(axis=0) - 2700, 0) * 100 + np.maximum(x[8:12].sum(axis=0) - 3840, 0) * 100
        if details:
            return dict(profit_5_to_6=float(total[0]), sampled_minimum_cash=float(minimum[0]), feasible=bool(penalty[0] < 1e-06), penalty=float(penalty[0]), balance_error_max=float(balance_max[0]), quantity_error_max=float(quantity_error[0]), periods=periods)
        return (total, minimum, penalty)

class ApplicationModel(_BaseScenario):

    def demand(self, x, cfg, t):
        transformed = x.copy()
        cfg = dict(cfg)
        mapping = cfg.pop('marketing_mapping', 'aggregate')
        cfg.pop('marketing_proxy', None)
        if mapping == 'aggregate':
            transformed[4:8] = x[4:8].sum(axis=0)
            transformed[8:12] = x[8:12].sum(axis=0)
        elif mapping == 'inferred_local':
            transformed[4:8] = x[4:8] * (self.general_total / self.local_general.ravel())[:, None]
            transformed[8:12] = x[8:12] * (self.designer_total / self.local_designer.ravel())[:, None]
        else:
            raise ValueError('Unknown marketing application mapping')
        return super().demand(transformed, cfg, t)


def decode(value):
    if isinstance(value,dict):
        if set(value)=={'__ndarray__'}:return np.array(value['__ndarray__'],float)
        return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list):return [decode(v) for v in value]
    return value


def apply_request(registry,request):
    if (registry.get('version'),registry.get('base_version'),registry.get('application_round'))!=('t5v2','t5v1',5):
        raise ValueError('需要t5v2注册表，基线t5v1，应用正式5')
    if (request.get('version'),request.get('market_id'),request.get('phase'),request.get('round'))!=('t5v2',5,'formal',5):
        raise ValueError('需要t5v2／市场5／formal／正式5请求')
    if set(request)-{'version','market_id','phase','round','plan','scenario','decision_vector'}:
        raise ValueError('未知请求字段')
    scenario_name=request.get('scenario','中性SHARE')
    scenarios=[s for s in registry['scenario_configs'] if s['name']==scenario_name]
    if len(scenarios)!=1:raise ValueError('未知情景')
    if 'decision_vector' in request:values=request['decision_vector']
    else:
        plans=[p for p in registry['saved_plans'] if p['name']==request.get('plan','稳健利润候选')]
        if len(plans)!=1:raise ValueError('未知方案')
        values=plans[0]['x']
    if not isinstance(values,list) or len(values)!=20 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
        raise ValueError('decision_vector须为20个有限数；机器连接件为20千单位档，贷款为100千美元档')
    bounds=registry['application_state']['bounds']
    if any(not lo<=v<=hi for v,(lo,hi) in zip(values,bounds)) or any(v<=0 for v in values[:4]):
        raise ValueError('决策超出保存的分析范围')
    if any(values[i]!=round(values[i]) for i in [15,16,19]) or sum(values[4:8])>2700+1e-8 or sum(values[8:12])>3840+1e-8:
        raise ValueError('投资/融资档位或营销预算范围不合法')
    model=ApplicationModel()
    model.__dict__.update(decode(registry['application_state']))
    model.r={'risk':registry['risk']}
    model.current={int(k):v for k,v in model.current.items()}
    result=model.evaluate(np.array(values,float),scenarios[0],details=True)
    result.update(investment_mapping_status=registry['investment_mapping']['status'], version='t5v2',base_version='t5v1',marketing_training_round=4,importance_round=5,
        inference_training_performed=False,country_product_marketing_allocation_identified=False,
        independent_forward_validation=False,full_global_optimum=False,
        scope='正式5—6条件税后利润；营销合计费用代理；正式6同价同投入、同曲线及投入滞后权重为情景；基准为同投入反事实归一化，非历史有效存量已识别；非实际成绩或已核平台候选预算')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--request',type=Path)
    args=parser.parse_args()
    registry=json.loads((args.bundle/'models_full.json').read_text(encoding='utf-8'))
    request=json.loads((args.request or args.bundle/'example_request.json').read_text(encoding='utf-8'))
    print(json.dumps(apply_request(registry,request),ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
