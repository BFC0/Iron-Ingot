"""Verify trial restoration and record conditional predictions, never demand labels."""
from archive_and_report import write_json, number
from audit_incremental import ROOT, cells, load
from build_model_inputs import production_and_delivery


def main():
    before = cells('20261011_modeltest_baseline_checklist')
    after = cells('20261011_modeltest_final_checklist')
    assert before == after, 'Final decisions differ from latest baseline'
    assert ['泰国', '5.00', '5.00', '5.00', '5.00', '1.00'] in after
    assert ['复合梁', '20.0', '20.0', '20.0', '20.0', '20.0'] in after
    price = next(r for r in after if r[0]=='泰国, 美元')
    assert all(number(v)==3000 for v in price[1:])
    assert ['每单位价格, 美元','3100','-','+67','1 800.0'] in cells('20261011_modeltest_C_sales')
    assert ['总收入, 千 美元','3 000','100','-61','7 780'] in cells('20261011_modeltest_C_sales')
    assert ['产能分配, %','40'] in cells('20261011_modeltest_D_production')
    assert ['生产, 千单位','3.40'] in cells('20261011_modeltest_D_production')
    scenarios = []
    for label, allocation, th_price in [('baseline',20,3000),('C',20,3100),('D',40,3000)]:
        output = production_and_delivery(17,allocation,.15,[1,11],[0,1],28,1.65,2.56,106.31,.1,.35)
        output.update(revenue=output['sales'][0]*th_price+output['sales'][1]*2000,
                      transport=output['sales'][0]*30+output['sales'][1]*120)
        scenarios.append(dict(case=label, allocation_percent=allocation, thailand_price=th_price,
                              kind='conditional_formula_prediction', observed_trial=False, output=output))
    result = dict(latest_baseline_captured_at=load('20261011_modeltest_baseline_checklist')['captured_at'],
                  final_captured_at=load('20261011_modeltest_final_checklist')['captured_at'],
                  restored_cells_equal=True, new_valid_trials=0, prior_valid_budget_trials=1,
                  group_submission_performed=False, personal_demand_preserved=1, group_demand=5,
                  hypothesis='练习/正式隐藏需求函数可能不同，尚不能判断',
                  failed_trials=['C: 输入框3100，派生收入仍3000，个人列回读价格3000',
                                 'D: 输入框40，派生产量仍3.4，个人列回读分配20'],
                  predictions=scenarios,
                  source_files=['raw/20261011_modeltest_baseline_checklist.json',
                                'raw/20261011_modeltest_final_checklist.json',
                                'raw/20261011_modeltest_C_sales.json',
                                'raw/20261011_modeltest_D_production.json',
                                'raw/round1_outlook.json','raw/initial0_printable.json'],
                  formulas=dict(revenue='sales_TH*price_TH + sales_ID*price_ID',
                                transport='sales_TH*30 + sales_ID*120',
                                payroll='sum(shift_quantity*shift_multiplier)/efficiency*28',
                                severance='max(previous_workers*0.9-production/efficiency,0)*28*0.35'),
                  units=dict(quantity='千单位',finance='千美元',price='美元/单位'),
                  limitations=['条件预测不是有效平台试验；未保存的输入不用于任何拟合',
                               '财务预算不能作为正式实际需求外部检验集',
                               '未估算完整利润变化，利息与税费机制仍需校准'])
    write_json(ROOT/'网页模型试验核验.json',result)
    assert scenarios[1]['output']['revenue']-scenarios[0]['output']['revenue']==100
    assert scenarios[2]['output']['production']==6.8
    print('PASS: final cells equal baseline; 0 new valid trials; conditional C/D predictions recorded')


if __name__=='__main__':
    main()
