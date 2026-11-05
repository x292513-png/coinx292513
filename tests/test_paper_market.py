import unittest
import test_paper
from wave_monitor import paper,store

class MarketTests(unittest.TestCase):
 setUp=test_paper.PaperTests.setUp
 tearDown=test_paper.PaperTests.tearDown
 bar=test_paper.PaperTests.bar
 runbar=test_paper.PaperTests.runbar
 def analysis(self,mode='close_then_market',setup='c_wave_reversal'):
  a=test_paper.PaperTests.analysis(self)
  p=a['result']['trade_plan'];p.update(entry_preferred=102,entry_low=101.01,entry_high=104,tp1=120,tp2=130)
  p['paper_execution'].update(mode=mode,setup=setup,confirmation_tf='1m',confirmation_price=101,max_entry_deviation_pct=1.5,cancel_price=99,cancel_tf='1m')
  return a
 def register(self,a=None):
  paper.register(a or self.analysis(),60)
  with store.db() as c:return paper.read_states(c)[0]
 def arm(self,p):
  store.save_candles('BTCUSDT','1m',[[120000,100,102,99.5,101.5,1,179999,1]])
  self.runbar(p,t=120,o=100,h=102,l=99.5,c=101.5)
  self.assertEqual(p['status'],'armed');self.assertEqual(p['qty'],0)
 def test_reversal_fills_without_limit_revisit_next_minute(self):
  p=self.register();self.arm(p);self.runbar(p,t=180,o=102.5,h=103,l=102.2,c=102.8)
  self.assertEqual(p['status'],'open');self.assertEqual(p['average'],102.5);self.assertEqual(p['entry_time'],180)
  self.assertLessEqual(p['qty']*(p['average']-p['stop']),10*(102-95)/102+1e-9)
 def test_wave4_and_continuation_use_same_execution_without_fake_wave_detection(self):
  for setup in ['wave4_reversal','impulse_continuation','pullback']:
   self.assertTrue(paper.valid_execution(self.analysis(setup=setup)['result']))
 def test_trigger_candle_cannot_fill(self):
  p=self.register();self.arm(p)
  with store.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM paper_events WHERE kind='entry'").fetchone()[0],0)
 def test_no_confirmation_no_trade(self):
  p=self.register();store.save_candles('BTCUSDT','1m',[[120000,100,101,99.5,100.5,1,179999,1]])
  self.runbar(p,t=120,o=100,h=101,l=99.5,c=100.5);self.assertEqual(p['status'],'waiting')
 def test_broken_reclaim_cancels_before_entry(self):
  p=self.register();self.arm(p);self.runbar(p,t=180,o=100.9,h=102,l=100,c=101.5);self.assertEqual(p['status'],'canceled')
 def test_chase_and_low_reward_cancel(self):
  p=self.register();self.arm(p);self.runbar(p,t=180,o=106,h=107,l=105,c=106);self.assertEqual(p['status'],'canceled')
 def test_rr_checked_on_actual_fill(self):
  a=self.analysis();a['result']['trade_plan']['tp1']=112;p=self.register(a);self.arm(p)
  self.runbar(p,t=180,o=103,h=104,l=102,c=103);self.assertEqual(p['status'],'canceled')
 def test_immediate_market_requires_preexisting_closed_confirmation(self):
  p=self.register(self.analysis('market'));self.assertEqual(p['status'],'skipped')
 def test_immediate_market_uses_future_open(self):
  store.save_candles('BTCUSDT','1m',[[0,100,102,100,101.5,1,59999,1]])
  p=self.register(self.analysis('market'));self.assertEqual(p['status'],'armed');self.assertEqual(p['qty'],0)
  self.runbar(p,t=120,o=102,h=103,l=101.5,c=102.5);self.assertEqual(p['status'],'open')
 def test_market_stop_on_entry_bar(self):
  p=self.register();self.arm(p);self.runbar(p,t=180,o=102,h=121,l=94,c=100)
  self.assertEqual(p['status'],'closed')
  with store.db() as c:self.assertLess(paper.account(c),100)
 def test_structural_cancellation_before_confirmation(self):
  p=self.register();store.save_candles('BTCUSDT','1m',[[120000,100,100.5,98,98.5,1,179999,1]])
  self.runbar(p,t=120,o=100,h=100.5,l=98,c=98.5);self.assertEqual(p['status'],'canceled')
 def test_short_reversal_and_profit(self):
  a=self.analysis();a['result']['bias']='bearish';p=a['result']['trade_plan'];p.update(entry_preferred=98,entry_low=96,entry_high=98.99,stop=105,tp1=80,tp2=70)
  p['paper_execution'].update(confirmation_price=99,cancel_price=101)
  p=self.register(a);store.save_candles('BTCUSDT','1m',[[120000,100,100.5,98,98.5,1,179999,1]])
  self.runbar(p,t=120,o=100,h=100.5,l=98,c=98.5);self.runbar(p,t=180,o=98,h=98.5,l=97,c=97)
  self.assertEqual(p['status'],'open');self.runbar(p,t=240,o=82,h=83,l=79,c=80)
  with store.db() as c:self.assertGreater(paper.account(c),100)
 def test_render_market_is_not_labeled_as_limit(self):
  p=self.register();text=paper.order_status(p)
  self.assertIn('C파 말단 반전',text);self.assertIn('지정가 재방문 불필요',text);self.assertNotIn('활성 지정가',text)
 def test_cancellation_does_not_use_future_close(self):
  p=self.register();self.arm(p)
  store.save_candles('BTCUSDT','1m',[[180000,102,103,98,98.5,1,239999,1]])
  self.runbar(p,t=180,o=102,h=103,l=98,c=98.5)
  self.assertEqual(p['status'],'open') # failure was unknowable at this minute's open
 def test_reversal_requires_directional_reclaim_not_bearish_bar_above_line(self):
  p=self.register();store.save_candles('BTCUSDT','1m',[[120000,102,103,101.1,101.5,1,179999,1]])
  self.runbar(p,t=120,o=102,h=103,l=101.1,c=101.5);self.assertEqual(p['status'],'waiting')
 def test_market_restart_does_not_fill_twice(self):
  self.register()
  store.save_candles('BTCUSDT','1m',[[60000,100,101,99.5,100,1,119999,1],[120000,100,102,99.5,101.5,1,179999,1],[180000,102.5,103,102.2,102.8,1,239999,1]])
  paper.tick(240);paper.tick(241)
  with store.db() as c:
   self.assertEqual(c.execute("SELECT COUNT(*) FROM paper_events WHERE kind='entry'").fetchone()[0],1)
   self.assertEqual(paper.read_states(c)[0]['status'],'open')
 def test_actual_entry_sizing_respects_other_position_budget(self):
  p=self.register();self.arm(p)
  with store.db() as c:
   c.execute("INSERT INTO paper_events(plan_id,created,symbol,kind,price,qty,pnl,detail) VALUES (1,180,'BTCUSDT','test_loss',0,0,-99.5,'test')")
  self.runbar(p,t=180,o=102.5,h=103,l=102.2,c=102.8)
  self.assertLessEqual(p['amount'],.5)
  self.assertLessEqual(p['qty']*(p['average']-p['stop']),.005+1e-9)
 def test_market_expiry_uses_fill_open_not_reporting_close(self):
  p=self.register();self.arm(p);p['expires']=200
  self.runbar(p,t=180,o=102,h=103,l=101.5,c=102.5);self.assertEqual(p['status'],'open')
 def test_market_expired_before_open_does_not_fill(self):
  p=self.register();self.arm(p);p['expires']=179.999
  self.runbar(p,t=180,o=102,h=103,l=101.5,c=102.5);self.assertEqual(p['status'],'canceled')
 def test_reversal_does_not_silently_relax_open_cross_to_gap_cross(self):
  p=self.register();store.save_candles('BTCUSDT','1m',[[60000,100,100.8,99.5,100.5,1,119999,1],[120000,101.2,102,101.1,101.5,1,179999,1]])
  self.runbar(p,t=120,o=101.2,h=102,l=101.1,c=101.5);self.assertEqual(p['status'],'waiting')
