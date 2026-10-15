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
    if any(product['prices'][c] == 0 and product['demand'][c] > 0 for c in COUNTRIES):
        raise ValueError('Positive connector demand requires a positive selling price')
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
    lifecycle = plan.get('lifecycle')
    orders_due, orders_awarded = [], []
    if lifecycle is not None:
        for key in ('opening_inventory_book_value_kusd', 'rd_kusd', 'marketing_kusd',
                    'attributed_operations_kusd', 'investment_kunits', 'investment_unit_cost',
                    'capacity_decay_pct'):
            nonnegative(lifecycle[key])
        if lifecycle['capacity_decay_pct'] > 100:
            raise ValueError('Capacity decay must be within 0..100')
        if plan['opening_inventory_kunits'] == 0 and lifecycle['opening_inventory_book_value_kusd'] != 0:
            raise ValueError('Empty inventory cannot have a positive book value')
        orders_due, orders_awarded = lifecycle['orders_due'], lifecycle['orders_awarded']
        for orders in (orders_due, orders_awarded):
            if not isinstance(orders, list):
                raise ValueError('Confirmed orders must be a list; tenders are not orders')
            for order in orders:
                if order['status'] != 'CONFIRMED':
                    raise ValueError('Only confirmed awards enter the delivery chain')
                for key in ('quantity_kunits', 'price', 'advance_received_kusd'):
                    nonnegative(order[key])
                if order['quantity_kunits'] == 0 or order['price'] == 0:
                    raise ValueError('Confirmed orders need positive quantity and price')
                if order['advance_received_kusd'] > order['quantity_kunits']*order['price']:
                    raise ValueError('Order advance exceeds contract value')
                if not math.isclose(order['advance_received_kusd'], .1*order['quantity_kunits']*order['price'], rel_tol=1e-10, abs_tol=1e-8):
                    raise ValueError('Confirmed order advance must equal 10 percent of contract value')
        order_quantity = sum(o['quantity_kunits'] for o in orders_due)
        if order_quantity > available + 1e-9:
            raise ValueError('Confirmed orders exceed available inventory and production; shortage penalty unknown')
        available = max(0., available-order_quantity)
    sales = dict.fromkeys(COUNTRIES, 0.)
    for country in plan['country_priority']:
        sales[country] = min(product['demand'][country], available)
        available -= sales[country]
    payroll = sum(q*m for q,m in zip(bands,shift_multipliers))*wage/product['efficiency']
    materials = quantity*product['material_cost']
    revenue = sum(sales[c]*product['prices'][c] for c in COUNTRIES)
    transport = sum(sales[c]*product['transport_costs'][c] for c in COUNTRIES)
    holding = available*plan['holding_cost_per_unit']
    result = dict(production_strategy='FREE_PRODUCTION_FIXED_PLAN', production_kunits=quantity,
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
    if lifecycle is not None:
        order_revenue = sum(o['quantity_kunits']*o['price'] for o in orders_due)
        order_balance = order_revenue-sum(o['advance_received_kusd'] for o in orders_due)
        new_advances = sum(o['advance_received_kusd'] for o in orders_awarded)
        sold = sum(sales.values()) + order_quantity
        pool_quantity = plan['opening_inventory_kunits']+quantity
        pool_value = lifecycle['opening_inventory_book_value_kusd']+materials+payroll
        # shortcut: weighted-average costing is a scenario, verify the platform valuation before actual-profit use.
        unit_cost = pool_value/pool_quantity if pool_quantity else 0.
        closing_value = available*unit_cost
        cogs = sold*unit_cost
        expenses = lifecycle['rd_kusd']+lifecycle['marketing_kusd']+lifecycle['attributed_operations_kusd']
        capex = lifecycle['investment_kunits']*lifecycle['investment_unit_cost']
        margin = revenue+order_revenue-cogs-transport-holding-expenses
        resource = revenue+order_revenue-materials-payroll-transport-holding-expenses
        result.update(path_version='CONNECTOR_LIFECYCLE_V2', orders_delivered_kunits=order_quantity,
            order_revenue_kusd=order_revenue, order_balance_due_kusd=order_balance,
            new_order_advances_received_kusd=new_advances,
            closing_contract_liability_kusd=new_advances,
            orders_due_next_round=orders_awarded,
            valuation_method='WEIGHTED_AVERAGE_SCENARIO', inventory_book_value_kusd=closing_value,
            cost_of_goods_sold_kusd=cogs, attributed_expenses_kusd=expenses,
            operating_contribution_kusd=margin, contribution_kusd=resource,
            investment_expenditure_kusd=capex,
            next_capacity_kunits=product['capacity']*(1-lifecycle['capacity_decay_pct']/100)+lifecycle['investment_kunits'],
            order_cash_movement_kusd=order_balance+new_advances,
            cash_collection_assumption='到期订单余款按交付当期收取；零售回款及支付时点未建模',
            scope='确认订单优先交付/余款与预收；加权平均库存计价情景；经营贡献不含折旧、税、利息、共享固定费；投资下期生效假设；非完整现金流')
        result['next_state'].update(opening_inventory_book_value_kusd=closing_value,
            orders_due=orders_awarded, capacity_kunits=result['next_capacity_kunits'],
            previous_rd_kusd=lifecycle['rd_kusd'])
        environment = lifecycle.get('environment_per_unit')
        if environment is not None:
            for key in ('production_co2_kg', 'energy_kwh', 'water_l', 'domestic_transport_co2_g', 'export_transport_co2_g'):
                nonnegative(environment[key])
            result['environment'] = dict(production_co2_kg=quantity*1000*environment['production_co2_kg'],
                energy_kwh=quantity*1000*environment['energy_kwh'], water_l=quantity*1000*environment['water_l'],
                retail_transport_co2_kg=sales['泰国']*environment['domestic_transport_co2_g']+sales['印尼']*environment['export_transport_co2_g'],
                scope='生产按产量、零售运输按交付量；大客户运输环境影响未知')
        if not math.isclose(pool_value, cogs+closing_value, rel_tol=1e-10, abs_tol=1e-8):
            raise RuntimeError('Connector inventory cost conservation failed')
    return result


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
