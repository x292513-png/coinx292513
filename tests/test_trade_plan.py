import unittest
from wave_monitor.trade_plan import validate,format_plan,plan_summary
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

 def detailed(self):
  return self.plan()|dict(entry_preferred=101,entry_reason='FVG 중앙선 재지지',tp1_reason='앞선 고점 매물대',holding_invalidation=104,holding_timeframe='15m',holding_exit_rule='104 아래 15분 종가면 잔량 정리',review_rule='진입 후 15분 6개 안에 106 회복 실패면 재검토',expected_horizon='수 시간 동안 15분 구조 확인')

 def test_preferred_entry_and_holding_details_are_visible(self):
  p=self.detailed();validate(p,'bullish')
  text=format_plan({'trade_plan':p,'bias':'bullish'})
  for value in ['진입 기준 101.00','최초 손절 98.00','1차 익절 110.00','잔량 50%','104.00','15분 종가','15분 6개','앞선 고점 매물대','FVG 중앙선']:
   self.assertIn(value,text)

 def test_detailed_plan_rejects_entry_outside_zone_or_wider_stop(self):
  for update in [dict(entry_preferred=103),dict(holding_invalidation=97),dict(holding_timeframe='none'),dict(review_rule='')]:
   with self.subTest(update=update),self.assertRaises(ValueError):validate(self.detailed()|update,'bullish')

 def test_waiting_plan_explains_confirmation_condition(self):
  text=format_plan({'trade_plan':{'enabled':False,'reason':'110 위 15분 종가 확인 전 대기'}})
  self.assertIn('110 위 15분 종가',text)
  self.assertNotIn('진입 기준',text)

 def test_short_holding_line_cannot_widen_the_initial_stop(self):
  p=self.detailed()|dict(stop=106,tp1=94,tp2=88,holding_invalidation=100)
  validate(p,'bearish')
  with self.assertRaisesRegex(ValueError,'holding_line_beyond_stop'):validate(p|dict(holding_invalidation=107),'bearish')

 def test_summary_keeps_prices_but_moves_long_rules_to_details(self):
  result={'trade_plan':self.detailed(),'bias':'bullish'}
  short=plan_summary(result)
  for price in ['101.00','98.00','110.00','114.00']:self.assertIn(price,short)
  self.assertIn('<b>',short);self.assertIn('\n\n',short)
  self.assertNotIn(self.detailed()['review_rule'],short)
  self.assertIn(self.detailed()['review_rule'],format_plan(result))
