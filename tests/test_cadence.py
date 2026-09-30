import tempfile,unittest,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from wave_monitor import store,cadence
class CadenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=store.ROOT;store.ROOT=Path(self.tmp.name);store.init()
  self.cfg={'notification_mode':'hourly','symbols':['BTCUSDT','ETHUSDT'],'sharp_move_rules':[[5,2],[15,3],[60,4]],'sharp_alert_cooldown_seconds':1800,'auto_calls_per_day':48}
  self.mock=patch.object(store,'settings',return_value=self.cfg);self.mock.start()
 def tearDown(self):self.mock.stop();store.ROOT=self.old;self.tmp.cleanup()
 def test_threshold_and_repeat_escalation(self):
  self.assertIsNone(cadence.sharp_candidate({5:1.99,15:2.99,60:3.99},self.cfg['sharp_move_rules']))
  self.assertEqual(cadence.sharp_candidate({5:-2},self.cfg['sharp_move_rules']),(5,-2))
  old={'time':100,'change':2.1}
  self.assertFalse(cadence.can_alert(old,110,2.2,1800))
  self.assertTrue(cadence.can_alert(old,110,3.2,1800))
  self.assertTrue(cadence.can_alert(old,110,-2,1800))
 def test_hourly_brief_once_and_works_without_ai(self):
  store.put('hourly_brief_slot',1)
  with patch.object(cadence,'briefing',return_value='brief'):
   cadence.tick(7201);cadence.tick(7220)
  with store.db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
 def test_extreme_still_alerts_at_budget_limit_and_deduplicates(self):
  with store.db() as c:
   for i in range(48):c.execute("INSERT INTO calls(started,kind) VALUES (7000,'auto')")
  store.put('price:BTCUSDT',{'price':100,'time':7200})
  store.put('briefing_sent_slot',cadence.briefing_slot(7201,self.cfg))
  with patch.object(cadence,'changes',return_value={5:2.2}):cadence.tick(7201);cadence.tick(7210)
  with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
 def test_hourly_ai_only_once_and_cap_respected(self):
  with patch.object(cadence,'briefing',return_value='brief'):
   cadence.tick(10501);cadence.tick(10505)
  with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],2)
 def test_pause_stops_notifications(self):
  store.put('paused',True);store.put('hourly_brief_slot',1)
  cadence.tick(7201)
  with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
 def test_missing_old_candles_not_fabricated(self):
  self.assertEqual(cadence.changes('BTCUSDT',100,7201),{})

 def test_next_briefing_uses_korean_schedule(self):
  self.cfg.update(briefing_hours_kst=[9,21])
  kst=timezone(timedelta(hours=9))
  morning=datetime(2026,9,30,8,30,tzinfo=kst).timestamp()
  night=datetime(2026,9,30,22,0,tzinfo=kst).timestamp()
  self.assertEqual(cadence.next_briefing(morning,self.cfg).strftime('%m/%d %H:%M'),'09/30 09:00')
  self.assertEqual(cadence.next_briefing(night,self.cfg).strftime('%m/%d %H:%M'),'10/01 09:00')

 def test_twice_daily_briefs_only_at_nine_and_twenty_one_kst(self):
  self.cfg.update(notification_mode='twice_daily',briefing_hours_kst=[9,21],auto_calls_per_day=4)
  kst=timezone(timedelta(hours=9))
  times=[datetime(2026,9,20,h,0,5,tzinfo=kst).timestamp() for h in (8,9,10,20,21,22)]
  with patch.object(cadence,'briefing',return_value='brief'):
   for now in times:cadence.tick(now)
  with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],2)

 def test_twice_daily_ai_refreshes_five_minutes_before_each_brief(self):
  self.cfg.update(notification_mode='twice_daily',briefing_hours_kst=[9,21],auto_calls_per_day=4)
  kst=timezone(timedelta(hours=9))
  morning=[datetime(2026,9,20,8,minute,5,tzinfo=kst).timestamp() for minute in (54,55,56)]
  for now in morning:cadence.tick(now)
  with store.db() as c:c.execute("UPDATE jobs SET status='done'")
  evening=[datetime(2026,9,20,20,minute,5,tzinfo=kst).timestamp() for minute in (55,56)]
  for now in evening:cadence.tick(now)
  with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],4)

 def test_full_budget_skips_hourly_ai_but_sends_brief(self):
  from wave_monitor.budget import day_start
  with store.db() as c:
   for i in range(48):c.execute("INSERT INTO calls(started,kind) VALUES (?,'auto')",(10500,))
  store.put('hourly_brief_slot',1)
  with patch.object(cadence,'briefing',return_value='brief'):cadence.tick(10501)
  with store.db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
 def test_invalid_analysis_does_not_repeat_old_entry_advice(self):
  now=10000;store.put('price:BTCUSDT',{'price':110,'time':now})
  a={'id':7,'created':9900,'result':{'headline':'OLD ENTRY','next_watch':'BUY OLD LEVEL','invalidation_price':105,'invalidation_side':'above'}}
  with patch.object(store,'latest',return_value=a),patch('wave_monitor.message_links.existing',return_value=None):
   text=cadence.briefing(now)
  self.assertIn('무효화됨',text);self.assertNotIn('OLD ENTRY',text);self.assertNotIn('BUY OLD LEVEL',text)
 def test_current_conviction_evidence_and_invalidation_visible(self):
  now=10000;store.put('price:BTCUSDT',{'price':110,'time':now})
  a={'id':8,'created':9990,'result':{'headline':'상승 우선','thesis':'나는 상승 재개를 강하게 본다','fractal_comment':'확인된 과거 사례','fractal_evidence':[{'id':'real'}],'invalidation_price':105,'invalidation_side':'below'}}
  with patch.object(store,'latest',return_value=a),patch('wave_monitor.message_links.existing',return_value=None):text=cadence.briefing(now)
  self.assertIn('나는 상승 재개를 강하게 본다',text);self.assertIn('확인된 과거 사례',text);self.assertIn('105.00 하회',text)
  a['result']['fractal_evidence']=[]
  with patch.object(store,'latest',return_value=a),patch('wave_monitor.message_links.existing',return_value=None):text=cadence.briefing(now)
  self.assertNotIn('확인된 과거 사례',text)
