import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from wave_monitor import store,paper

class PaperTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=patch.object(store,'ROOT',Path(self.tmp.name));self.root.start();store.init()
  self.cfg=patch.object(store,'settings',return_value={'paper_enabled':True,'symbols':['BTCUSDT','ETHUSDT']});self.cfg.start();store.put('paper_started',60)
 def tearDown(self):self.cfg.stop();self.root.stop();self.tmp.cleanup()
 def analysis(self,aid=1,symbol='BTCUSDT'):
  return {'id':aid,'created':60,'symbol':symbol,'snapshot':{},'result':{'bias':'bullish','trade_plan':{'enabled':True,'entry_preferred':100,'stop':95,'tp1':110,'tp2':120,'take_pct':50,'position_plan':{'initial_units':10,'add_units':10,'add_price':97},'paper_execution':{'conditions_fully_encoded':True,'mode':'limit','reason':'test','confirmation_tf':'5m','confirmation_price':102,'expires_hours':4,'hold_hours':24,'breakeven_after_tp1':True,'add_enabled':False,'add_confirmation_price':102}}}}
 def plan(self):
  paper.register(self.analysis(),60)
  with store.db() as c:return paper.read_states(c)[0]
 def bar(self,t=120,o=101,h=102,l=99,c=100):return dict(t=t*1000,close_t=(t+60)*1000-1,o=o,h=h,l=l,c=c)
 def runbar(self,p,**kwargs):
  with store.db() as c:paper.step(c,p,self.bar(**kwargs));paper.save(c,p)
 def test_entry_not_at_registration_and_idempotence(self):
  p=self.plan();self.assertEqual(p['status'],'armed');self.assertEqual(p['qty'],0)
  self.runbar(p);self.assertAlmostEqual(p['qty'],.1)
  paper.register(self.analysis(),300)
  with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM paper_plans').fetchone()[0],1)
 def test_entry_stop_same_bar_counts_loss(self):
  p=self.plan();self.runbar(p,l=94,h=121)
  self.assertEqual(p['status'],'closed')
  with store.db() as c:self.assertAlmostEqual(paper.account(c),99.5)
 def test_partial_then_breakeven(self):
  p=self.plan();self.runbar(p);self.runbar(p,t=180,o=105,l=104,h=111,c=110)
  self.assertAlmostEqual(p['qty'],.05);self.assertEqual(p['stop'],100)
  self.runbar(p,t=240,o=102,l=99,h=103)
  with store.db() as c:self.assertAlmostEqual(paper.account(c),100.5)
 def test_gap_stop_uses_open(self):
  p=self.plan();self.runbar(p);self.runbar(p,t=180,o=90,l=89,h=94)
  with store.db() as c:self.assertAlmostEqual(paper.account(c),99)
 def test_add_then_stop_conservative(self):
  p=self.plan();self.runbar(p);p.update(add_amount=10,add_limit=97,add_armed=180)
  self.runbar(p,t=240,o=99,l=94,h=101)
  self.assertTrue(p['added']);self.assertEqual(p['status'],'closed')
  with store.db() as c:self.assertAlmostEqual(paper.account(c),100-.5-10/97*2)
 def test_portfolio_risk_shared(self):
  a=self.analysis();a['result']['trade_plan']['position_plan']['initial_units']=100
  paper.register(a,60);a=self.analysis(2,'ETHUSDT');paper.register(a,60)
  with store.db() as c:self.assertLessEqual(sum(paper.reserve(p)[1] for p in paper.read_states(c)),1.000001)
 def test_topic_routing(self):
  store.enqueue_message('test',topic_id=42)
  with store.db() as c:self.assertEqual(c.execute('SELECT topic_id FROM outbox').fetchone()[0],42)
 def test_fill_notification_actual_price_once(self):
  store.put('paper_topic_id',42);p=self.plan();p['reason']='FVG <중앙> 반전'
  with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
  self.runbar(p,o=99,h=102,l=98);self.runbar(p,t=180,o=101,h=102,l=99)
  with store.db() as c:
   rows=c.execute('SELECT * FROM outbox').fetchall()
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['topic_id'],42)
  self.assertIn('99.00 USDT',rows[0]['text']);self.assertIn('BTCUSDT 롱',rows[0]['text'])
  self.assertIn('&lt;중앙&gt;',rows[0]['text'])
 def test_fill_notification_rolls_back_with_fill(self):
  store.put('paper_topic_id',42);p=self.plan()
  with self.assertRaises(RuntimeError):
   with store.db() as c:
    paper.step(c,p,self.bar());raise RuntimeError('rollback')
  with store.db() as c:
   self.assertEqual(c.execute("SELECT COUNT(*) FROM paper_events WHERE kind='entry'").fetchone()[0],0)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
 def test_closed_confirmation_then_future_fill(self):
  a=self.analysis();a['result']['trade_plan']['paper_execution']['mode']='close_then_limit';paper.register(a,60)
  store.save_candles('BTCUSDT','5m',[[300000,101,104,100,103,1,599999,1]])
  with store.db() as c:p=paper.read_states(c)[0]
  self.runbar(p,t=540,o=101,h=104,l=99);self.assertEqual(p['status'],'armed');self.assertEqual(p['qty'],0)
  self.runbar(p,t=600);self.assertEqual(p['status'],'open')
 def test_paused_cancels_waiting(self):
  self.plan();store.put('paused',True);paper.tick(120)
  with store.db() as c:self.assertEqual(paper.read_states(c)[0]['status'],'canceled')
 def test_no_old_analysis_or_clock_entry(self):
  a=self.analysis();a['created']=0
  with patch.object(store,'latest',return_value=a):paper.tick(1000)
  with store.db() as c:self.assertEqual(paper.read_states(c),[])
 def test_short_stop_and_target(self):
  a=self.analysis();a['result']['bias']='bearish';a['result']['trade_plan'].update(stop=105,tp1=90,tp2=80)
  paper.register(a,60)
  with store.db() as c:p=paper.read_states(c)[0]
  self.runbar(p,o=99,h=101,l=98);self.runbar(p,t=180,o=95,h=96,l=89,c=90)
  self.runbar(p,t=240,o=89,h=90,l=79,c=80)
  with store.db() as c:self.assertAlmostEqual(paper.account(c),101.5)
 def test_restart_candle_is_not_executed_twice(self):
  self.plan();store.save_candles('BTCUSDT','1m',[[60000,101,102,100.5,101,1,119999,1],[120000,101,102,99,100,1,179999,1]])
  paper.tick(180);paper.tick(181)
  with store.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM paper_events WHERE kind='entry'").fetchone()[0],1)
 def test_missing_bar_closes_at_observed_open(self):
  p=self.plan();self.runbar(p)
  store.save_candles('BTCUSDT','1m',[[240000,98,99,97,98,1,299999,1]])
  paper.tick(300)
  with store.db() as c:
   self.assertEqual(paper.read_states(c)[0]['status'],'closed');self.assertAlmostEqual(paper.account(c),99.8)
 def test_reports_once_per_slot_and_not_every_tick(self):
  from datetime import datetime
  stamp=datetime(2026,11,5,9,tzinfo=paper.KST).timestamp();store.put('paper_topic_id',42)
  paper.tick(stamp);paper.tick(stamp+5);paper.tick(stamp+3600)
  with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
 def test_existing_open_plan_not_replaced_or_replayed(self):
  p=self.plan();self.runbar(p);paper.register(self.analysis(2),180);paper.register(self.analysis(3),181)
  with store.db() as c:
   states=paper.read_states(c);self.assertEqual(sum(x['status']=='open' for x in states),1);self.assertEqual(len(states),3)
 def test_unencoded_or_contradictory_plan_rejected(self):
  for i,kind in enumerate(('missing','false','contradiction'),10):
   a=self.analysis(i);x=a['result']['trade_plan']['paper_execution']
   if kind=='missing':x.pop('conditions_fully_encoded')
   elif kind=='false':x['conditions_fully_encoded']=False
   else:x['reason']='필수 반전 구조를 완전히 표현할 수 없어 추가 확인 필요'
   paper.register(a,60)
   with store.db() as c:self.assertEqual(paper.read_states(c)[-1]['status'],'skipped')
 def test_limit_cross_only_fills_active_order(self):
  a=self.analysis();a['result']['trade_plan']['paper_execution']['mode']='close_then_limit';paper.register(a,60)
  with store.db() as c:p=paper.read_states(c)[0]
  self.runbar(p,t=120,o=99,h=101,l=98)
  self.assertEqual(p['status'],'waiting');self.assertEqual(p['qty'],0)
  self.assertIn('지정가 미활성',paper.order_status(p));self.assertIn('지금 이 가격을 지나도 체결하지 않음',paper.order_status(p))
  p.update(status='armed',armed_time=180)
  self.runbar(p,t=240,o=99,h=101,l=98)
  self.assertEqual(p['status'],'open');self.assertEqual(p['average'],99)
 def test_legacy_unverified_pending_canceled_not_backfilled(self):
  p=self.plan();p['rules'].pop('conditions_fully_encoded')
  with store.db() as c:paper.save(c,p)
  paper.tick(180)
  with store.db() as c:
   self.assertEqual(paper.read_states(c)[0]['status'],'canceled')
   self.assertEqual(c.execute("SELECT COUNT(*) FROM paper_events WHERE kind='entry'").fetchone()[0],0)
