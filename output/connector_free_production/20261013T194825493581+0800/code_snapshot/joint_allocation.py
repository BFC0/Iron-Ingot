"""Two dedicated production lines: conditional one-round contribution allocation."""
import math
import numpy as np
from scipy.optimize import linprog
from connector_free_production import project as project_connector, self_check as connector_check

PRODUCTS = ('复合梁', '连接件')
COUNTRIES = ('泰国', '印尼')


def allocate(products, worker_limit, wage, shift_multipliers, connector_plan=None):
    """Amounts in thousand units/USD; efficiencies in thousand units per person."""
    if set(products) != set(PRODUCTS):
        raise ValueError('Exactly two products are required')
    def nonnegative(value):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Expected finite nonnegative numeric input')
    nonnegative(wage)
    if worker_limit is not None:
        nonnegative(worker_limit)
    if len(shift_multipliers) != 3:
        raise ValueError('Three shift multipliers required')
    for v in shift_multipliers:
        nonnegative(v)
    if shift_multipliers[0] != 1 or list(shift_multipliers) != sorted(shift_multipliers):
        raise ValueError('Shift costs must start at 1 and be nondecreasing')
    if connector_plan is not None:
        connector = project_connector(products['连接件'], connector_plan, wage, shift_multipliers)
        remaining = None if worker_limit is None else worker_limit-connector['workers']
        if remaining is not None and remaining < -1e-8:
            raise ValueError('Fixed connector production plan exceeds shared worker limit')
        idle = dict(products, 连接件=dict(products['连接件'], capacity=0., demand=dict.fromkeys(COUNTRIES,0.)))
        out = allocate(idle, None if remaining is None else max(0.,remaining), wage, shift_multipliers)
        out['products']['连接件'] = connector
        out['products']['复合梁']['production_strategy'] = 'DEMAND_DRIVEN'
        out['total_workers'] += connector['workers']
        out['total_production_kunits'] += connector['production_kunits']
        out['contribution_kusd'] += connector['contribution_kusd']
        for p in out['products'].values():
            p['quantity_mix_pct'] = 100*p['production_kunits']/out['total_production_kunits'] if out['total_production_kunits'] else 0.
            p['labor_mix_pct'] = 100*p['workers']/out['total_workers'] if out['total_workers'] else 0.
        out.update(model='JOINT_ALLOCATION_CONNECTOR_FREE_V1', shared_worker_limit=worker_limit,
            objective='连接件固定自由生产计划占用用工后，优化复合梁当期贡献',
            scope='连接件库存数量已结转；库存期初成本转出/计价、订单和完整利润/现金流未建模',
            next_state={'连接件':connector['next_state']}, connector_plan_optimized=False)
        return out
    # shortcut: zero inventory/orders and fixed machines, extend before full-profit ranking.
    costs, bounds = [], []
    equalities = np.zeros((2, 10))
    labor = np.zeros(10)
    for i, name in enumerate(PRODUCTS):
        p = products[name]
        for key in ('capacity', 'efficiency', 'material_cost'):
            nonnegative(p[key])
        if p['efficiency'] == 0:
            raise ValueError('Efficiency must be positive even for an idle line')
        for key in ('demand', 'prices', 'transport_costs'):
            if set(p[key]) != set(COUNTRIES):
                raise ValueError('Both country values are required')
            for value in p[key].values():
                nonnegative(value)
        if any(v == 0 for v in p['prices'].values()):
            raise ValueError('Prices must be positive')
        base = i * 5
        for s, multiplier in enumerate(shift_multipliers):
            costs.append(p['material_cost'] + wage * multiplier / p['efficiency'])
            bounds.append((0, p['capacity'] / 3))
            equalities[i, base+s] = 1
            labor[base+s] = 1 / p['efficiency']
        for j, country in enumerate(COUNTRIES):
            costs.append(p['transport_costs'][country] - p['prices'][country])
            bounds.append((0, p['demand'][country]))
            equalities[i, base+3+j] = -1
    result = linprog(costs, A_ub=None if worker_limit is None else labor[None, :],
                     b_ub=None if worker_limit is None else [worker_limit],
                     A_eq=equalities, b_eq=np.zeros(2), bounds=bounds, method='highs')
    if not result.success:
        raise RuntimeError(result.message)
    output = {}
    for i, name in enumerate(PRODUCTS):
        p = products[name]
        bands = result.x[i*5:i*5+3]
        quantity = float(sum(bands))
        sales = dict(zip(COUNTRIES, map(float, result.x[i*5+3:i*5+5])))
        output[name] = dict(production_kunits=quantity, sales_kunits=sales,
            unmet_demand_kunits={c: max(0., p['demand'][c]-sales[c]) for c in COUNTRIES},
            capacity_allocation_pct=100*quantity/p['capacity'] if p['capacity'] else 0.,
            workers=quantity/p['efficiency'], shift_production_kunits=bands.tolist(),
            payroll_kusd=float(bands @ np.array(shift_multipliers))*wage/p['efficiency'])
    total_q = sum(p['production_kunits'] for p in output.values())
    total_workers = sum(p['workers'] for p in output.values())
    for p in output.values():
        p['quantity_mix_pct'] = 100*p['production_kunits']/total_q if total_q else 0.
        p['labor_mix_pct'] = 100*p['workers']/total_workers if total_workers else 0.
    if not np.allclose(equalities @ result.x, 0, atol=1e-7) or (worker_limit is not None and total_workers > worker_limit+1e-7):
        raise RuntimeError('Allocation conservation failed')
    return dict(model='JOINT_ALLOCATION_V1', products=output, total_workers=total_workers,
        total_production_kunits=total_q, contribution_kusd=float(-result.fun),
        objective='给定需求/产能/效率/成本下，最大化收入减材料、班次工资和运输费用',
        scope='当期条件贡献；不含研发/运营/固定费用、裁员、投资、税、利息、订单或跨期收益',
        dedicated_capacity=True, shared_worker_limit=worker_limit,
        actual_validation=False, automatic_deployment=False)


def self_check():
    p = dict(capacity=9., efficiency=1., material_cost=1.,
             demand={'泰国': 20., '印尼': 20.}, prices={'泰国': 20., '印尼': 15.},
             transport_costs={'泰国': 0., '印尼': 1.})
    products = {name: dict(p) for name in PRODUCTS}
    a = allocate(products, None, 1., [1., 1.65, 2.56])
    assert all(abs(v['production_kunits']-9) < 1e-9 for v in a['products'].values())
    assert all(abs(v['capacity_allocation_pct']-100) < 1e-9 for v in a['products'].values())
    assert all(abs(v['quantity_mix_pct']-50) < 1e-9 for v in a['products'].values())
    assert abs(a['contribution_kusd']-2*(9*19-3*(1+1.65+2.56))) < 1e-8
    b = allocate(products, 4., 1., [1., 1.65, 2.56])
    assert abs(b['total_workers']-4) < 1e-9
    low = {name: dict(p, prices={'泰国': .1, '印尼': .1}) for name in PRODUCTS}
    assert allocate(low, None, 1., [1., 1.65, 2.56])['total_production_kunits'] == 0
    zero = {name: dict(p, capacity=0.) for name in PRODUCTS}
    assert allocate(zero, None, 1., [1., 1.65, 2.56])['total_production_kunits'] == 0
    asymmetric = dict(products, 连接件=dict(p, efficiency=2., prices={'泰国': 50., '印尼': 50.}))
    c = allocate(asymmetric, 2., 1., [1., 1.65, 2.56])
    assert abs(c['products']['连接件']['production_kunits']-4) < 1e-9
    assert c['products']['复合梁']['production_kunits'] == 0
    for bad in (-1., float('nan'), float('inf')):
        try:
            allocate(products, bad, 1., [1., 1.65, 2.56])
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid labor bound accepted')
    plan = dict(allocation_pct=100., opening_inventory_kunits=0., holding_cost_per_unit=.6,
                country_priority=list(COUNTRIES))
    fixed = dict(products, 连接件=dict(p,demand={'泰国':1.,'印尼':1.}))
    out = allocate(fixed,10.,1.,[1.,1.65,2.56],plan)
    assert out['products']['连接件']['production_kunits']==9.
    assert out['products']['连接件']['closing_inventory_kunits']==7.
    assert abs(out['products']['复合梁']['production_kunits']-1.)<1e-8
    assert abs(sum(v['quantity_mix_pct'] for v in out['products'].values())-100)<1e-8
    try:
        allocate(fixed,8.,1.,[1.,1.65,2.56],plan)
    except ValueError:
        pass
    else:
        raise AssertionError('Infeasible fixed production accepted')
    return dict(connector_free_path=connector_check(),fixed_plan_reserves_shared_workers=True,
                infeasible_plan_rejected=True,dedicated_capacity=True, shared_labor=True, shift_costs=True,
                negative_margin_idle=True, zero_capacity=True, unequal_efficiencies=True,
                invalid_inputs_rejected=True)
