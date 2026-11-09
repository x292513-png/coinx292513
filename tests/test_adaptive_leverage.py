import unittest
import test_allocation,test_paper_usdt
from wave_monitor import allocation,paper,store
class LeverageTests(unittest.TestCase):
 def result(self):
  r=test_allocation.AllocationTests().result();p=r['trade_plan'];p.update(tp1=120,paper_execution={'conditions_fully_encoded':True})
  p['position_plan'].update(leverage=10,leverage_reason='네 기준봉 방향 일치와 구조 무효화선, 첫 목표 손익비 확인',risk_budget_units=5)
  return r
 def test_high_leverage_and_no_fixed_one_percent_cap(self):
  r=self.result();allocation.prepare(r);p=r['trade_plan']['position_plan']
  self.assertEqual(p['leverage'],10);self.assertEqual(p['risk_budget_units'],5)
  self.assertGreater(p['calculation']['full_stop_loss_units'],1)
 def test_mixed_or_poor_rr_cannot_get_ten(self):
  for mixed in [True,False]:
   r=self.result()
   if mixed:r['wave_view'][0]['trend']='하락'
   else:r['trade_plan']['tp1']=105
   allocation.prepare(r);self.assertEqual(r['trade_plan']['position_plan']['leverage'],5)
 def test_invalid_leverage(self):
  for v in [0,11,float('nan'),True,8.5]:
   r=self.result();r['trade_plan']['position_plan']['leverage']=v
   with self.assertRaises(ValueError):allocation.prepare(r)
class ExecutionTests(unittest.TestCase):
 setUp=test_paper_usdt.USDTTests.setUp
 tearDown=test_paper_usdt.USDTTests.tearDown
 analysis=test_paper_usdt.USDTTests.analysis
 def test_dynamic_position_margin_and_old_position_unchanged(self):
  paper.start_usdt_account(60)
  with store.db() as c:spec=paper.account_spec(c)
  spec.update(max_leverage=10,risk_policy='structural');store.put('paper_account_v2',spec)
  a=self.analysis();a['result']['trade_plan']['position_plan'].update(leverage=10,risk_policy='structural',risk_budget_units=5)
  paper.register(a,60)
  with store.db() as c:p=paper.read_states(c)[0]
  self.assertEqual(p['leverage'],10);self.assertEqual(p['amount'],10000)
  self.assertEqual(paper.reserve(p),(1000,500))
  with store.db() as c:self.assertEqual(paper.market_amount(c,p,100),10000)
