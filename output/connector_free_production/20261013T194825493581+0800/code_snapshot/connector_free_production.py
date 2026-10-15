"""Connector plan -> production -> delivery -> physical inventory carryover."""
import math

COUNTRIES = ('泰国', '印尼')


def project(product, plan, wage, shift_multipliers):
    def nonnegative(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Expected finite nonnegative connector input')
    for key in ('capacity', 'efficiency', 'material_cost'):
        nonnegative(product[key])
    if product['efficiency'] == 0:
        raise ValueError('Connector efficiency must be positive')
    for key in ('allocation_pct', 'opening_inventory_kunits', 'holding_cost_per_unit'):
        nonnegative(plan[key])
    if plan['allocation_pct'] > 100:
        raise ValueError('Connector allocation must be within 0..100')
    if sorted(plan['country_priority']) != sorted(COUNTRIES):
        raise ValueError('Connector priority must contain each country once')
    for key in ('demand', 'prices', 'transport_costs'):
        if set(product[key]) != set(COUNTRIES):
            raise ValueError('Both connector country values required')
        for value in product[key].values():
            nonnegative(value)
    if min(product['prices'].values()) <= 0:
        raise ValueError('Connector prices must be positive')
    nonnegative(wage)
    if len(shift_multipliers) != 3 or shift_multipliers[0] != 1 or list(shift_multipliers) != sorted(shift_multipliers):
        raise ValueError('Three nondecreasing shift multipliers starting at 1 required')
    for value in shift_multipliers:
        nonnegative(value)
    quantity = product['capacity'] * plan['allocation_pct'] / 100
    bands = [min(quantity, product['capacity']/3),
             min(max(quantity-product['capacity']/3, 0), product['capacity']/3),
             max(quantity-2*product['capacity']/3, 0)]
    available = plan['opening_inventory_kunits'] + quantity
    sales = dict.fromkeys(COUNTRIES, 0.)
    for country in plan['country_priority']:
        sales[country] = min(product['demand'][country], available)
        available -= sales[country]
    payroll = sum(q*m for q,m in zip(bands,shift_multipliers))*wage/product['efficiency']
    materials = quantity*product['material_cost']
    revenue = sum(sales[c]*product['prices'][c] for c in COUNTRIES)
    transport = sum(sales[c]*product['transport_costs'][c] for c in COUNTRIES)
    holding = available*plan['holding_cost_per_unit']
    return dict(production_strategy='FREE_PRODUCTION_FIXED_PLAN', production_kunits=quantity,
        capacity_allocation_pct=plan['allocation_pct'], workers=quantity/product['efficiency'],
        shift_production_kunits=bands, payroll_kusd=payroll, material_expenditure_kusd=materials,
        production_expenditure_kusd=materials+payroll, sales_kunits=sales,
        sales_revenue_kusd=revenue, transport_expenditure_kusd=transport,
        opening_inventory_kunits=plan['opening_inventory_kunits'], closing_inventory_kunits=available,
        inventory_holding_kusd=holding,
        unmet_demand_kunits={c:product['demand'][c]-sales[c] for c in COUNTRIES},
        next_state=dict(opening_inventory_kunits=available),
        contribution_kusd=revenue-materials-payroll-transport-holding,
        inventory_book_value_kusd=None, actual_validation=False,
        scope='固定计划数量结转；持有费按输入单价乘期末数量假设；不含期初库存成本转出/库存计价、订单、税、利息、收款或跨期优化')


def self_check():
    p = dict(capacity=100., efficiency=10., material_cost=14.2,
        demand={'泰国':30.,'印尼':10.}, prices={'泰国':27.,'印尼':27.},
        transport_costs={'泰国':.5,'印尼':2.})
    plan = dict(allocation_pct=100., opening_inventory_kunits=0.,
                holding_cost_per_unit=.6, country_priority=list(COUNTRIES))
    a = project(p,plan,30.,[1.,1.65,2.56])
    assert a['production_kunits']==100 and sum(a['sales_kunits'].values())==40
    assert a['closing_inventory_kunits']==60 and a['inventory_holding_kusd']==36
    assert abs(a['payroll_kusd']-521.)<1e-8
    b = project(p,dict(plan,allocation_pct=0.,**a['next_state']),30.,[1.,1.65,2.56])
    assert b['production_kunits']==0 and b['closing_inventory_kunits']==20
    assert b['workers']==0 and b['material_expenditure_kusd']==0
    scarce = project(p,dict(plan,allocation_pct=20.,country_priority=['印尼','泰国']),30.,[1.,1.65,2.56])
    assert scarce['sales_kunits']=={'泰国':10.,'印尼':10.}
    none = project(dict(p,capacity=0.),plan,30.,[1.,1.65,2.56])
    assert none['production_kunits']==none['closing_inventory_kunits']==0
    for v in (-1.,101.,float('nan')):
        try:
            project(p,dict(plan,allocation_pct=v),30.,[1.,1.65,2.56])
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid connector allocation accepted')
    return dict(overproduction_inventory=True,two_round_carryover=True,
                payroll_and_materials_on_production=True,priority=True,
                zero_capacity=True,invalid_plan_rejected=True)
