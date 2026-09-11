import unittest
from wave_monitor.trade_plan import validate,format_plan
class PlanTests(unittest.TestCase):
 def plan(self):return dict(enabled=True,entry_low=100,entry_high=102,stop=98,tp1=110,tp2=114,take_pct=50,entry_rule='재테스트 후',stop_reason='구조 이탈',breakeven_rule='1차 익절 후 지지 확인, 비용 반영',hold_rule='15분 저점 이탈 종료')
 def test_long_and_worst_entry_rr(self):
  p=self.plan();validate(p,'bullish');text=format_plan({'trade_plan':p,'bias':'bullish'})
  self.assertIn('3.0R',text);self.assertIn('50%',text);self.assertIn('미체결 가정',text)
 def test_short(self):
  p=self.plan();p.update(stop=106,tp1=94,tp2=88);validate(p,'bearish')
  self.assertIn('2.0R',format_plan({'trade_plan':p,'bias':'bearish'}))
 def test_wrong_side_targets_and_no_remaining_position_rejected(self):
  for update in [dict(stop=103),dict(tp1=99),dict(tp2=109),dict(take_pct=100),dict(entry_low=103),dict(stop=float('nan'))]:
   with self.subTest(update=update),self.assertRaises(ValueError):validate(self.plan()|update,'bullish')
 def test_disabled_and_legacy_have_no_fabricated_plan(self):
  validate({'enabled':False},'neutral')
  self.assertEqual(format_plan({}), '')
