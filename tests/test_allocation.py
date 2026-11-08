import unittest
from wave_monitor.allocation import prepare,metrics,summary,limits

class AllocationTests(unittest.TestCase):
 def result(self):
  return {'bias':'bullish','wave_view':[{'tf':tf,'trend':'상승'} for tf in ['1d','4h','1h','15m']], 'trade_plan':{'enabled':True,'entry_preferred':100.,'entry_low':99.,'entry_high':101.,'stop':95.,'position_plan':{'thesis_timeframe':'4h','entry_timeframe':'15m','stop_timeframe':'1h','alignment_reason':'상위 상승 속 눌림','allocation_reason':'재지지 확인 후 분할','initial_units':30.,'add_units':20.,'add_price':97.,'add_condition':'97 재지지 확인','cancel_add_condition':'95 이탈 또는 4시간 만료','risk_budget_units':1.}}}
 def test_total_stop_risk_caps_both_stages(self):
  r=self.result();prepare(r);p=r['trade_plan']['position_plan'];m=p['calculation']
  self.assertLessEqual(m['full_stop_loss_units'],1)
  self.assertTrue(p['adjusted_by_risk_limit'])
  self.assertLess(m['total_units'],50)
  self.assertAlmostEqual(m['reserve_units']+m['total_units'],100)
 def test_notional_weighted_average_uses_quantities(self):
  r=self.result();p=r['trade_plan'];p['position_plan'].update(initial_units=10,add_units=10,add_price=80)
  m=metrics(p,'bullish');self.assertAlmostEqual(m['average_entry'],20/(10/100+10/80))
 def test_invalid_add_after_stop_rejected(self):
  for price in [94,95,100,101,float('nan')]:
   r=self.result();r['trade_plan']['position_plan']['add_price']=price
   with self.subTest(price=price),self.assertRaises(ValueError):prepare(r)
 def test_countertrend_cap(self):
  r=self.result()
  for v in r['wave_view']:
   if v['tf'] in ['1d','4h']:v['trend']='하락'
  self.assertEqual(limits(r),('countertrend',30,.5))
  prepare(r);m=r['trade_plan']['position_plan']['calculation']
  self.assertLessEqual(m['total_units'],30);self.assertLessEqual(m['full_stop_loss_units'],.5)
 def test_short_averaging_keeps_original_stop(self):
  r=self.result();r['bias']='bearish'
  for v in r['wave_view']:v['trend']='하락'
  r['trade_plan'].update(stop=105.)
  r['trade_plan']['position_plan']['add_price']=103.
  prepare(r);self.assertEqual(r['trade_plan']['stop'],105)
  self.assertLessEqual(r['trade_plan']['position_plan']['calculation']['full_stop_loss_units'],1)
 def test_display_explicit_timeframes_units_and_reserve(self):
  r=self.result();prepare(r);text=summary(r)
  for value in ['4시간봉','15분봉','1시간봉','예비','손실','5배','승률 아님']:self.assertIn(value,text)
 def test_wait_and_legacy_do_not_invent_units(self):
  r=self.result();r['trade_plan']['enabled']=False;prepare(r)
  self.assertEqual(r['trade_plan']['position_plan']['initial_units'],0)
  self.assertEqual(summary({'trade_plan':{'enabled':True}}),'')
 def test_mixed_not_high_conviction_just_from_score(self):
  r=self.result();r['wave_view'][-1]['trend']='하락';r['confidence']=99
  self.assertEqual(limits(r),('mixed',50,.75))
 def test_model_math_is_not_repeated_next_to_computed_math(self):
  r=self.result();p=r['trade_plan']['position_plan'];p['allocation_reason']='방향이 혼재한다. 평균가 123, 손실 0.11유닛이다.'
  prepare(r)
  self.assertEqual(p['allocation_reason'],'방향이 혼재한다.')
  self.assertNotIn('model_allocation_reason',p)
