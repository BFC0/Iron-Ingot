"""Small regression checks for privacy, causality, units and experimental gates."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import new_data_value as value


class ValueChecks(unittest.TestCase):
    def test_missing_and_zero(self):
        for missing in ('NaN','-','',None,'Infinity'):
            self.assertEqual(value.numeric(missing),(None,None))
        self.assertEqual(value.numeric('0.00'),(0,.005))
        self.assertEqual(value.numeric('1\u00a0355.32'),(1355.32,.005))

    def test_formal_restart_and_stable_identity(self):
        key=(1,'formal',1,'hash','泰国','复合梁')
        self.assertEqual(value.previous_key(key),(1,'initial',0,'hash','泰国','复合梁'))
        self.assertEqual(value.previous_key((1,'formal',2,'hash','泰国','复合梁')),key)
        self.assertEqual(value.team_id(1,'A B'),value.team_id(1,'AB'))
        self.assertNotEqual(value.team_id(1,'AB'),value.team_id(2,'AB'))
        self.assertNotIn('AB',value.team_id(1,'AB'))

    def test_intervals_and_thresholds(self):
        self.assertTrue(value.compatible(.1,.05,.2,.05))
        self.assertIsNone(value.intersect([[0,1],[2,3]]))
        self.assertEqual(value.intersect([[0,2],[1,3]]),[1,2])

    def test_calibration_preserves_bounds_and_not_water(self):
        s=dict(values=dict(q=10,workers=50,eta=.2,co2=13553.2,co2_intensity=1355.32,
                           energy=47783.8,energy_intensity=4778.38,water=999999),
               refs={k:dict(display_half_unit=.005 if k in ('q','workers','eta') else .05)
                     for k in ('q','workers','eta','co2','co2_intensity','energy','energy_intensity','water')},
               exact_workers=50)
        c=value.calibration(s,{'co2':1355.32,'energy':4778.38})
        self.assertEqual(c['status'],'CALIBRATION_ONLY')
        self.assertAlmostEqual(c['q'],10)
        self.assertLess(c['q_interval'][1]-c['q_interval'][0],.01)
        self.assertNotIn('water',c['channels'])
        s['values']['co2']=1
        self.assertEqual(value.calibration(s,{'co2':1355.32,'energy':4778.38})['status'],'CONFLICTING_OBSERVATIONS')

    def test_zero_workers_and_efficiency_conflict(self):
        self.assertEqual(value.calibration(dict(values=dict(q=0,workers=0),refs={}))['status'],
                         'MISSING_POSITIVE_OUTPUT_OR_WORKERS')
        s=dict(values=dict(q=10,workers=50,eta=.4),refs={k:dict(display_half_unit=.005) for k in ('q','workers','eta')})
        self.assertEqual(value.calibration(s)['status'],'CONFLICTING_EFFICIENCY_LABEL')

    def test_market_equal_bootstrap_and_no_deployment(self):
        rows=[dict(market=m,actual=0,B1=1,B2=.5) for m in range(5)]
        result=value.paired_summary(rows)
        self.assertTrue(result['allowed_refit'])
        self.assertFalse(result['allow_deployment'])
        self.assertEqual(result,value.paired_summary(rows))
        self.assertFalse(value.paired_summary(rows[:4])['allowed_refit'])
        rows += [dict(market=0,actual=0,B1=1,B2=.5)]*100
        self.assertEqual(value.paired_summary(rows)['baseline_mae'],1)
        self.assertFalse(value.paired_summary([dict(market=m,actual=0,B1=0,B2=0) for m in range(5)])['allowed_refit'])

    def test_ridge_has_fold_local_scale(self):
        x=[[0],[1],[2],[3],[4],[5]]; y=[2,3,4,5,6,7]; markets=[0,1,2,3,4,5]
        fit,predict=value.select_ridge(x,y,markets)
        np.testing.assert_allclose(predict(fit,x),y,atol=.001)
        self.assertIn(fit['penalty'],value.PENALTIES)
        empty,predict=value.select_ridge(np.zeros((6,0)),y,markets)
        self.assertEqual(len(empty['beta']),1)

    def test_field_use_rejects_derived_wage(self):
        stats={'average_wage':dict(cells=10,varying_groups=1)}
        checks=[dict(check='人均工资派生性',pass_=True)]
        verdict=value.information_verdicts(stats,checks)[0]
        self.assertIn('恒等式',verdict['purpose'])

    def test_source_mutation_rejected(self):
        with tempfile.TemporaryDirectory(dir=value.ROOT/'work') as tmp:
            self.assertTrue(Path(tmp).resolve().is_relative_to((value.ROOT/'work').resolve()))
            p=Path(tmp)/'source.json'; p.write_text('{}')
            bundle={'files':{str(p):value.sha(p)}}
            value.assert_unchanged(bundle)
            p.write_text('{"changed":true}')
            with self.assertRaises(ValueError):value.assert_unchanged(bundle)

    def test_parser_context_privacy_and_budget_exclusion(self):
        headers=[f'TEST_TEAM_{i}' for i in range(10)]
        def row(panel,table,index,cells,phase='formal',round_=1,kind=None):
            return dict(source=f'raw/{panel}.json',sha256='fixture',market=1,phase=phase,round=round_,
                        panel=panel,table_index=table,row_index=index,cells=cells,kind=kind,
                        identity_status='verified',team_order=headers if len(cells)==11 else [],product_context=[],errors=[])
        rows=[row('logisticsdetails',0,0,['复合梁 - 泰国, 千单位']),
              row('logisticsdetails',0,1,['运往 泰国']+['1.00']*10),
              row('logisticsemissions',0,0,['泰国, kg CO2']),
              row('logisticsemissions',0,1,['复合梁']),
              row('logisticsemissions',0,2,['运往 泰国']+['3920.5']*10),
              row('logisticsemissions',3,0,['平均每单位销售, g CO2']),
              row('logisticsemissions',3,1,['复合梁']),
              row('logisticsemissions',3,2,['运往 泰国']+['3920.5']*10),
              row('productiondetails',0,0,['复合梁']),
              row('productiondetails',0,1,['生产规模, 千单位']+['10.00']*10,round_=3),
              row('productionhr',0,0,['复合梁']),
              row('productionhr',0,1,['每人平均工资, 千 美元']+['28']*10,kind='platform_budget')]
        original=value.read
        def fake_read(path):
            if Path(path).name=='rows.json':return rows
            if Path(path).name=='charts.json':return []
            return original(path)
        with patch.object(value,'read',side_effect=fake_read):
            samples,evidence,excluded,conflicts=value.extract({'audit':'fixture','refs':[]})
        self.assertEqual(len(samples),10)
        self.assertEqual(samples[0]['values']['route_TH'],1)
        self.assertEqual(samples[0]['values']['route_co2_TH'],3920.5)
        self.assertEqual(samples[0]['values']['route_intensity_TH'],3920.5)
        self.assertNotIn('q',samples[0]['values'])
        self.assertGreaterEqual(len(excluded),2)
        self.assertNotIn('TEST_TEAM_',json.dumps(samples)+json.dumps(evidence))
        self.assertFalse(conflicts)

    def test_physical_route_units(self):
        # 千单位 × g/单位 = kg; treating either operand as units changes by 1000.
        quantity=5.2; intensity=3920.5
        self.assertAlmostEqual(quantity*intensity,20386.6)

    def test_unknown_country_and_duplicate_roster_rejected(self):
        headers=[f'group{i}' for i in range(10)]
        common=dict(source='raw/fixture.json',sha256='test',market=1,phase='formal',round=1,
                    panel='productiondetails',table_index=0,kind=None,identity_status='verified',
                    team_order=headers,product_context=['连接件'],errors=[])
        rows=[dict(common,row_index=0,cells=['生产规模, 千单位']+['0.00']*10)]
        original=value.read
        def fake(path):
            if Path(path).name=='rows.json':return rows
            if Path(path).name=='charts.json':return []
            return original(path)
        with patch.object(value,'read',side_effect=fake):
            samples,_,excluded,_=value.extract({'audit':'fixture','refs':[]})
        self.assertFalse(samples)
        self.assertIn('上下文',excluded[0]['reason'])
        rows[0]['team_order']=['same']*10
        with patch.object(value,'read',side_effect=fake):
            samples,_,excluded,_=value.extract({'audit':'fixture','refs':[]})
        self.assertFalse(samples)
        self.assertIn('列宽',excluded[0]['reason'])


if __name__=='__main__':
    unittest.main()
