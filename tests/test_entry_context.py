import unittest
from wave_monitor.entry_context import measured_levels,display

class EntryContextTests(unittest.TestCase):
 def test_moving_average_is_closed_series_sma_not_ema(self):
  rows=[{'c':float(i),'close_t':i} for i in range(1,201)]
  snap={'frames':{'1d':{'pivots':[]}}}
  levels=measured_levels(snap,{'1d':rows})['levels'];m={x['id']:x for x in levels}
  self.assertEqual(m['1d:SMA100']['price'],150.5)
  self.assertEqual(m['1d:SMA200']['price'],100.5)
  self.assertEqual(m['1d:SMA200']['asof'],200)
  self.assertNotIn('1h:SMA200',m)
 def test_retracement_anchors_and_unconfirmed_extreme(self):
  p=lambda t,price,kind,confirmed=True:dict(t=t,price=price,kind=kind,confirmed=confirmed)
  snap={'frames':{'1d':{'pivots':[p(1,100,'L'),p(2,200,'H'),p(3,150,'L'),p(4,180,'H'),p(5,300,'H',False)]}}}
  levels=measured_levels(snap,{})['levels']
  measured=next(x for x in levels if x['id']=='1d:fib:1:2:0.618')
  self.assertAlmostEqual(measured['price'],138.2)
  self.assertFalse(any(x.get('end',{}).get('t')==5 for x in levels))
 def test_shared_path_and_exit_differences_visible_and_escaped(self):
  r={'entry_logic':{'shared_path':'저점 유지 < 확인','supporting_scenarios':[{'scenario':'ABC 종료','why_same_entry':'지지','exit_difference':'추세 확인 후 홀딩'},{'scenario':'W 종료 X 반등','why_same_entry':'같은 지지','exit_difference':'반등 저항에서 축소'}],'confluence':'FVG와 지지 중첩','trigger':'5분 회복','failure_case':'저점 붕괴','measured_evidence':[]}}
  text='\n'.join(display(r))
  for term in ['&lt;','ABC 종료','X 반등','홀딩','축소','저점 붕괴']:self.assertIn(term,text)
  self.assertEqual(display({}),[])
