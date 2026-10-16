"""Frozen t6v0 inference for the terminal formal6 round; no platform writes."""
import argparse
import itertools
import json
import numbers
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'work/python_packages'))
import numpy as np

PRODUCTS = ['复合梁', '连接件']
COUNTRIES = ['泰国', '印尼', '菲律宾']
ORDERS = list(itertools.permutations(range(3)))
INTEGER = [21, 22, 23, 24, 27]
NAMES = ([f'price/{p}/{c}' for p in PRODUCTS for c in COUNTRIES]
         + [f'general/{p}/{c}' for p in PRODUCTS for c in COUNTRIES]
         + [f'designer/{p}/{c}' for p in PRODUCTS for c in COUNTRIES]
         + ['rd/复合梁', 'rd/连接件', 'operations/泰国', 'machine/泰国/复合梁',
            'machine/泰国/连接件', 'machine/印尼/复合梁', 'machine/印尼/连接件',
            'allocation/复合梁', 'allocation/连接件', 'loan_change'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def curve(x, item):
    p = item['parameters']
    return p[0]+p[1]*(x+p[2])**p[3] if item['form'] == 'power' else p[0]+p[1]*x/(p[2]+x)


def distribute(demand, available, prices, freight, unit_cost, holding, fixed=None):
    """Enumerate all six legal priorities, with stable tie-breaking."""
    n = demand.shape[-1]
    alternatives = []
    scores = []
    for order in ORDERS:
        remaining = available.copy()
        sales = np.zeros((3, n))
        for k in order:
            sales[k] = np.minimum(demand[k], remaining)
            remaining -= sales[k]
        alternatives.append(sales)
        scores.append((sales*(prices-freight[:, None]-unit_cost[None, :]+holding)).sum(axis=0))
    if fixed is None:
        # With ample supply all orders tie; keep the net-price order that also works under shortages.
        preferred = np.argsort(-(prices-freight[:, None]), axis=0, kind='stable')
        chosen = np.zeros(n, int)
        for i, order in enumerate(ORDERS):
            chosen[np.all(preferred == np.array(order)[:, None], axis=0)] = i
    else:
        chosen = np.full(n, fixed, int)
    return np.stack(alternatives)[chosen, :, np.arange(n)].T, chosen


class ApplicationModel:
    def __init__(self, bundle):
        self.r = read(Path(bundle)/'models_full.json')
        if (self.r.get('version'), self.r.get('application_round'), self.r.get('base_version')) != ('t6v1', 6, 't6v0'):
            raise ValueError('需要t6v1／t6v0／formal6应用包')
        self.s = self.r['state']
        self.bounds = np.array(self.r['bounds'], float)
        self.baseline = np.array(self.r['baseline'], float)

    def validate(self, decision):
        if isinstance(decision, (list, tuple)) and any(isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Real) for v in decision):
            raise ValueError('决策须为数值，不能含布尔或字符串')
        x = np.asarray(decision)
        if x.shape != (28,) or x.dtype.kind not in 'fiu' or not np.isfinite(x).all():
            raise ValueError('decision_vector必须包含28个有限数值')
        if np.any(x < self.bounds[:, 0]-1e-9) or np.any(x > self.bounds[:, 1]+1e-9):
            raise ValueError('决策超出保存的分析边界')
        if np.any(x[INTEGER] != np.rint(x[INTEGER])):
            raise ValueError('机器档位与贷款档位必须为整数')
        return x.astype(float)

    def demand(self, x, cfg):
        x = np.asarray(x, float)
        x = x[:, None] if x.ndim == 1 else x
        n = x.shape[1]
        prices = x[:6].reshape(2, 3, n)
        general = x[6:12].sum(axis=0)
        designer = x[12:18].sum(axis=0)
        shares = np.empty((2, 3, 10, n))
        for j, p in enumerate(PRODUCTS):
            for k in range(3):
                rows = self.r['competition'][p][COUNTRIES[min(k, 1)]]
                b = np.array(self.r['demand'][p]['COUNTRY/'+COUNTRIES[min(k, 1)]]['beta'])
                own = self.r['own_indices'][p][COUNTRIES[min(k, 1)]]
                baseprice = np.array([q['price'] for q in rows], float)
                pp = np.broadcast_to(baseprice[:, None], (10, n)).copy()
                pp[own] = prices[j, k]
                if k == 2:
                    # No Philippine history: all teams start at the same guide-price anchor.
                    pp[:] = self.r['guide_prices'][j]
                    pp[own] = prices[j, k]
                elasticity = cfg.get('ph_price', 1.) if k == 2 else cfg.get('old_price', 1.)
                marketing = cfg.get('ph_marketing', 1.) if k == 2 else cfg.get('old_marketing', 1.)
                g = np.broadcast_to(np.array([q['general'] for q in rows])[:, None], (10, n)).copy()
                d = np.broadcast_to(np.array([q['designer'] for q in rows])[:, None], (10, n)).copy()
                if not cfg.get('replay_training'):
                    g[own] = general
                    d[own] = designer
                old_rd = np.array([q['rd']+.5*q['previous_rd'] for q in rows])
                rdlog = np.broadcast_to(np.log(curve(old_rd, self.r['training_curves']['rd/'+p]))[:, None], (10, n)).copy()
                if not cfg.get('replay_training'):
                    mapping = self.r['investment_mapping']
                    previous = self.r['previous_rd'][j]
                    effective = mapping['rd_current']*x[18+j]+mapping['rd_previous']*previous
                    anchor = (mapping['rd_current']+mapping['rd_previous'])*previous
                    rdlog[own] += np.log(curve(effective, self.r['curves']['rd/'+p])/curve(anchor, self.r['curves']['rd/'+p]))
                reference = self.r['guide_prices'][j] if k == 2 else 1.
                utilities = (-b[min(k, 1)]*elasticity*np.log(np.maximum(pp, 1e-12)/reference)
                             + marketing*(b[2]*np.log1p(g/1000)+b[3]*np.log1p(d/1000))+b[4]*rdlog)
                active = np.array([q['price'] > 0 for q in rows]) if k < 2 else np.ones(10, bool)
                active[own] = True
                utilities[~active] = -np.inf
                utilities -= utilities.max(axis=0)
                attraction = np.exp(utilities)
                attraction[np.arange(10) != own] *= cfg.get('rival_scale', 1.)
                shares[j, k] = attraction/attraction.sum(axis=0)
        own_shares = np.stack([np.stack([shares[j, k, self.r['own_indices'][p][COUNTRIES[min(k, 1)]]] for k in range(3)]) for j, p in enumerate(PRODUCTS)])
        totals = np.array(self.r['market_totals'], float)*cfg.get('market_scale', 1.)
        if cfg.get('disable_ph'):
            totals[:, 2] = 0
        return own_shares*totals[:, :, None], shares

    def evaluate(self, decision, cfg=None, details=False, priorities=None):
        cfg = cfg or {}
        x = np.asarray(decision, float)
        x = x[:, None] if x.ndim == 1 else x
        n = x.shape[1]
        demand, shares = self.demand(x, cfg)
        price = x[:6].reshape(2, 3, n)
        s = self.s
        inv = np.array(self.r['inventory'])[:, None]
        invbook = np.array(self.r['inventory_book'])[:, None]
        thai_units = x[21:23]*np.array([1, 20])[:, None]
        indo_units = x[23:25]*np.array([1, 20])[:, None]
        capacity = np.array(self.r['capacity'])[:, None]+thai_units
        mapping = self.r['investment_mapping']
        effective_ops = x[20]+mapping['ops_previous']*self.r['previous_ops']
        anchor_ops = self.r['previous_ops']*(1+mapping['ops_previous'])
        efficiency = np.array(self.r['efficiency'])[:, None]*curve(effective_ops, self.r['curves']['operations/泰国'])/curve(anchor_ops, self.r['curves']['operations/泰国'])*cfg.get('efficiency_scale', 1.)
        q = capacity*x[25:27]/100
        q[0] = np.minimum(q[0], np.maximum(demand[0].sum(axis=0)-inv[0], 0))
        bands = [np.minimum(q, capacity/3), np.minimum(np.maximum(q-capacity/3, 0), capacity/3), np.maximum(q-2*capacity/3, 0)]
        payroll = (bands[0]+self.r['shift2']*bands[1]+self.r['shift3']*bands[2])/efficiency*self.r['wage']
        material = np.array(self.r['material_cost'])[:, None]*cfg.get('material_scale', 1.)
        material_cost = q*material
        available = inv+q
        unit_cost = np.divide(invbook+material_cost+payroll, available, out=np.zeros_like(q), where=available > 0)
        sales = np.zeros((2, 3, n))
        orders = []
        for j in range(2):
            sales[j], order = distribute(demand[j], available[j], price[j], np.array(self.r['freight'][j]), unit_cost[j], self.r['holding'], None if priorities is None else priorities[j])
            orders.append(order)
        ending = available-sales.sum(axis=1)
        ending_book = ending*unit_cost
        cogs = (invbook+material_cost+payroll-ending_book).sum(axis=0)
        revenue = (sales*price).sum(axis=(0, 1))
        transport = (sales*np.array(self.r['freight'])[:, :, None]).sum(axis=(0, 1))
        workers = q/efficiency
        firing = np.maximum(np.array(self.r['previous_workers'])[:, None]*.9-workers, 0).sum(axis=0)*self.r['wage']*.35
        spending = x[6:21].sum(axis=0)
        ebitda = revenue-cogs-transport-self.r['holding']*ending.sum(axis=0)-spending-firing-self.r['fixed_cost']
        thai_capex = (thai_units*np.array(self.r['machine_prices'])[:, None]).sum(axis=0)
        indo_capex = (indo_units*np.array(self.r['machine_prices'])[:, None]).sum(axis=0)
        capex = thai_capex+indo_capex
        building_capex = cfg.get('building_capex', self.r['building_capex_assumption'])
        md = (s['machine_book']+thai_capex+cfg.get('indo_depreciation', 1.)*indo_capex)*self.r['machine_depreciation']
        bd = s['building_book']*.07
        ebit = ebitda-md-bd
        change = x[27]*100
        debt = s['long_debt']+change
        ratio = np.clip(s['equity']/np.maximum(s['assets']+change, 1.), 0, 1)
        risk = self.r['risk']['solvency_exponential']['parameters']
        rate = self.r['base_rate']+risk[0]*np.exp(-risk[1]*ratio)
        interest = (s['long_debt']+.5*change)*rate
        newar = revenue*cfg.get('ar_days', 30.)/365
        newap = material_cost.sum(axis=0)*30/365
        minimum = self.r['minimum_cash']
        tax_loss = cfg.get('tax_loss_assumption', 0.)
        # shortcut: end-point short debt and average cash interest are scenarios; replace after timing experiments.
        k = s['cash']+ebitda-interest+s['ar']-newar+newap-s['ap']+invbook.sum()-ending_book.sum(axis=0)-capex-building_capex+change-s['short_debt']
        no_tax_cash = (k+.005*s['cash'])/.995
        taxable = ebit-interest+.005*(s['cash']+no_tax_cash)-tax_loss > 0
        newcash = np.where(taxable, (k+.005*s['cash']*.71-.29*(ebit-interest-tax_loss))/(1-.005*.71), no_tax_cash)
        short_rate = self.r['base_rate']+self.r['short_spread']
        needs_short = newcash < minimum
        short_no_tax = (minimum-k-.005*(s['cash']+minimum))/(1-short_rate)
        short_tax = (minimum-k-.005*(s['cash']+minimum)*.71+.29*(ebit-interest-tax_loss))/(1-short_rate*.71)
        use_tax = ebit-interest-short_rate*short_tax+.005*(s['cash']+minimum)-tax_loss > 0
        short = np.where(needs_short, np.maximum(np.where(use_tax, short_tax, short_no_tax), 0), 0)
        newcash = np.where(needs_short, minimum, newcash)
        short_interest = short*short_rate
        cash_interest = .005*(s['cash']+newcash)
        pretax = ebit-interest-short_interest+cash_interest
        tax = np.maximum(pretax-tax_loss, 0)*.29
        profit = pretax-tax
        preoperation_cash = s['cash']+change-capex-building_capex
        bridge = np.maximum(minimum-preoperation_cash, 0)
        min_cash = np.minimum(newcash, preoperation_cash)
        newassets = (s['machine_book']+capex-md+s['building_book']+building_capex-bd+newar+newcash+ending_book.sum(axis=0)+self.r['other_assets'])
        balance_error = newassets-(s['equity']+profit+debt+short+newap+s['advance_receipts'])
        quantity_error = np.max(np.abs(inv+q-sales.sum(axis=1)-ending), axis=0)
        penalty = bridge*100+np.where(debt >= 0, 0., 1e8)+np.maximum(minimum-newcash, 0)*100
        penalty += np.maximum(x[6:12].sum(axis=0)-self.r['general_limit'], 0)*100
        penalty += np.maximum(x[12:18].sum(axis=0)-self.r['designer_limit'], 0)*100
        if not details:
            return profit, min_cash, penalty
        if n != 1:
            raise ValueError('详细输出只接受单套决策')
        arr = lambda v: np.asarray(v)[..., 0].tolist()
        scalar = lambda v: float(np.asarray(v).reshape(-1)[0])
        return dict(round=6, start_round=6, end_round=6, terminal=True, profit=scalar(profit), cash=scalar(newcash),
            minimum_sampled_cash=scalar(min_cash), short_debt=scalar(short), preoperation_bridge_need=scalar(bridge),
            feasible=bool(penalty[0] < 1e-6), penalty=scalar(penalty), rate=scalar(rate), long_debt=scalar(debt),
            long_interest=scalar(interest), short_interest=scalar(short_interest), cash_interest=scalar(cash_interest),
            revenue=scalar(revenue), ebitda=scalar(ebitda), ebit=scalar(ebit), tax=scalar(tax),
            spending=scalar(spending), transport=scalar(transport), firing=scalar(firing),
            demand=arr(demand), shares=arr(shares), sales=arr(sales), production=arr(q), production_indonesia=[0., 0.],
            capacity=arr(capacity), efficiency=arr(efficiency), workers=arr(workers), payroll=arr(payroll), materials=arr(material_cost),
            opening_inventory=arr(inv), closing_inventory=arr(ending), inventory_book=arr(ending_book),
            thai_capex=scalar(thai_capex), indonesia_capex=scalar(indo_capex), machine_depreciation=scalar(md),
            building_depreciation=scalar(bd), building_capex=float(building_capex),
            priorities=[list(ORDERS[int(v[0])]) for v in orders], priority_alternatives_per_product=6,
            balance_error=scalar(balance_error), quantity_error=scalar(quantity_error), tax_loss_assumption=tax_loss,
            full_global_optimum=False, unknown_opening_state=self.r['unknown_opening_state'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    model = ApplicationModel(args.bundle)
    request = read(args.request)
    if set(request) != {'version', 'round', 'decision_vector', 'scenario'} or request['round'] != 6 or request['version'] != 't6v1':
        raise ValueError('请求须包含version=t6v1、round=6、decision_vector、scenario')
    scenarios = [c for c in model.r['scenarios'] if c['name'] == request['scenario']]
    if len(scenarios) != 1:
        raise ValueError('未知情景')
    x = model.validate(request['decision_vector'])
    print(json.dumps(model.evaluate(x, scenarios[0], details=True), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
